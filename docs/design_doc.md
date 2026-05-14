# Investment Thesis Validator — Design Doc

> Eval-first LLM agent that validates US-equity investment theses using LangGraph,
> the Anthropic SDK, FMP, NewsAPI, and SEC EDGAR. Standalone `uv` project; SignalPilot
> AI assets are pattern-borrowed only (no import coupling).

## Resolved decisions (2026-05-13)

| # | Question | Decision |
|---|----------|----------|
| 1 | News provider for v1 | **NewsAPI dev tier (free, 100 req/day)**. Tavily deferred behind a flag in M9 if quality is the bottleneck. |
| 2 | DSPy fallback policy | **Pre-declared kill criterion**: if M5 first compile cycle does not improve `final_answer_accuracy` on the 30-item dev set by **≥3pp** vs baseline, abandon DSPy for that node and revert to eval-driven hand-tuning. Other nodes may still attempt. |
| 3 | `as_of_date` semantics | **Point-in-time correctness required.** Every FMP/news/SEC client accepts and respects a virtual "now" so golden-dataset items are reproducible across calendar drift. |
| — | SignalPilot coupling | **Pattern-borrow only.** Read `services/api/app/briefing_v5/`, `.agents/skills/fmp-fetcher/` for endpoint tables and the citation-binding audit pattern. Do not add SignalPilot as a Python dependency. |

## Architecture

```
                         ┌──────────────────────────────────────────┐
POST /validate ─────────▶│  FastAPI (async)                         │
   { thesis: str,        │  ─ enqueue → background task             │
     ticker: str }       │  ─ poll status / result via job_id       │
                         └────────────────┬─────────────────────────┘
                                          │
                                          ▼
                   ┌──────────────────────────────────────────────────┐
                   │  LangGraph StateGraph: ThesisValidator           │
                   │                                                  │
                   │  parse_thesis (Haiku 4.5)                        │
                   │      │  → ThesisClaims[]                         │
                   │      ▼                                            │
                   │  plan_evidence (Haiku 4.5)                       │
                   │      │  → ToolCallPlan                           │
                   │      ▼                                            │
                   │  ┌──── parallel fan-out ────┐                    │
                   │  │ stock_data │ news_search │ filings_retrieval ││
                   │  │  (FMP)     │ (NewsAPI)   │  (SEC EDGAR)      ││
                   │  └─────────────┴────────────┴───────────────────┘│
                   │      │  → EvidenceBundle                         │
                   │      ▼                                            │
                   │  contradiction_check (Haiku 4.5)                 │
                   │      │  → SupportingEv[], RefutingEv[]            │
                   │      ▼                                            │
                   │  validator_synthesizer (Opus 4.7, cached system) │
                   │      │  → Verdict { stance, confidence, cites }  │
                   │      ▼                                            │
                   │  guardrails (numeric + citation binding)         │
                   └────────────────┬─────────────────────────────────┘
                                    │
                                    ▼
                       Prometheus metrics + cost ledger
```

Cheap nodes (parse, plan, contradiction-check) → `claude-haiku-4-5-20251001`.
Synthesizer → `claude-opus-4-7` with prompt caching on system + tool-schema block
(`cache_control: {"type": "ephemeral"}`). Per-node hooks emit telemetry consumed
by both the eval harness and the Prometheus middleware.

## Sequencing

1. **(M1-M2) LangGraph agent** — gates everything else.
2. **(M3) Golden Dataset** — needs stable agent contract.
3. **(M4) Eval harness** — baseline numbers BEFORE optimization.
4. **(M5) DSPy** — only on weak nodes the eval harness identifies; subject to
   the +3pp kill criterion above.
5. **(M6-M8) FastAPI + Prom + Grafana** — productionize a validated agent.

Inverting (M4) and (M5) is the most common mistake. Don't.

## Milestones (~12-16 sessions, 1 session ≈ 1-2h focused work)

### M0 — Project hygiene + tool baseline (1 session)
**Goal:** runnable `uv` project with linting, typing, test harness, configured secrets.

**Files:**
- `pyproject.toml` — add `langgraph`, `httpx`, `tenacity`, `structlog`, `pytest-asyncio`, `respx`, `pytest-cov`
- `src/__init__.py`, `src/config.py` — Pydantic `Settings`: `ANTHROPIC_API_KEY`, `FMP_API_KEY`, `NEWS_API_KEY`, `MAX_COST_USD=0.50`, `MODEL_VALIDATOR="claude-opus-4-7"`, `MODEL_CHEAP="claude-haiku-4-5-20251001"`
- `.env.example` — extend
- `tests/conftest.py` — `anyio_backend`, `frozen_settings`
- `ruff.toml` (line-length 100, py311, `E,F,I,UP,B,SIM`), `mypy.ini` (`strict = True`)
- `.github/workflows/ci.yml` — ruff + mypy + pytest

**Acceptance:** `uv run pytest`, `uv run ruff check .`, `uv run mypy src` all green. CI runs all three.

### M1 — Pydantic contracts + tool clients (1-2 sessions)
**Goal:** typed I/O + three external clients with retries and respx-mocked tests.

**Files:**
- `src/agent/state.py` — `ValidatorState`, `ThesisClaim`, `Evidence`, `Verdict`, `Citation`, `Confidence`
- `src/ingestion/fmp.py` — async `FMPClient.profile/income_statement/quote/ratios` (mirror `signalpilotai/.agents/skills/fmp-fetcher/SKILL.md` endpoint table)
- `src/ingestion/news.py` — async `NewsClient.search(query, from_date, to_date)` against NewsAPI
- `src/ingestion/sec.py` — async `SECClient.recent_filings(cik, forms=["10-K","10-Q","8-K"])` + transcript stub
- `src/ingestion/_http.py` — shared `httpx.AsyncClient` + `tenacity` retry + 30s timeout + structured logging
- `tests/ingestion/` — respx mocks; happy-path + 401/429/empty-payload tests

**Acceptance:** No live network in CI. Each client has rate-limit + empty-payload coverage. All clients accept an `as_of_date` kwarg for point-in-time correctness.

### M2 — LangGraph agent skeleton (2-3 sessions)
**Goal:** end-to-end graph runs against fixtures, returns a `Verdict`.

**Files:**
- `src/agent/graph.py` — `build_graph() -> CompiledGraph`, sequential nodes with parallel evidence fan-out
- `src/agent/nodes/{parse_thesis,plan_evidence,fetch_stock,fetch_news,fetch_filings,contradiction,synthesize}.py`
- `src/agent/llm.py` — Anthropic SDK wrapper: `call_haiku()`, `call_opus()`, returns `(text, usage, cache_stats)`. See `claude-api` skill for caching/usage pattern.
- `src/agent/prompts/{synthesizer_system,parse_thesis,contradiction}.md` — system prompts >1024 tokens (cache-eligible)
- `tests/agent/test_graph_smoke.py` — fixture thesis → asserts `Verdict` with ≥1 supporting evidence + ≥1 citation

**Acceptance:** Smoke passes against frozen fixtures. One live-API integration test gated by `RUN_LIVE=1`.

### M3 — Golden Dataset (2 sessions)
**Goal:** 100 reviewed Q→A pairs in `eval/datasets/golden_v1.jsonl`.

**Files:**
- `eval/schema.py` — `GoldenItem` Pydantic: `id`, `category`, `thesis`, `ticker`, `as_of_date`, `expected_stance` (`SUPPORTED|REFUTED|UNCERTAIN`), `expected_evidence_keys[]`, `min_tools_called[]`, `notes`
- `eval/generate_seed.py` — script: 20 hand-curated CSV rows → Opus expansion → 100 candidates (5 categories × 20)
- `eval/datasets/seed_v1.csv`, `eval/datasets/golden_v1.jsonl`
- `eval/REVIEW_CHECKLIST.md`

**Categories (20 each):**
1. Fundamentals lookup ("AAPL FCF margin > 25% TTM")
2. Sentiment / news catalyst ("NVDA momentum continues post Q3 print")
3. Contradiction detection (thesis cites a fact filings refute)
4. Edge cases (delisted LEHM, recent IPO, foreign ADR thin coverage, BRK.A vs BRK.B collision)
5. Multi-claim theses (3+ claims, partial truth → expected `UNCERTAIN`)

**Acceptance:** 100 items load via `GoldenItem.model_validate`; review checklist signed off; ≥30% of items have `expected_stance=REFUTED|UNCERTAIN` (anti-sycophancy).

### M4 — Per-step eval harness (2 sessions)
**Goal:** baseline numbers + HTML report.

**Files:**
- `eval/runner.py` — async runner: per `GoldenItem` → invoke graph → capture per-node trace → write per-(item,node) row to `eval/runs/<ts>.jsonl`
- `eval/metrics.py` — pure functions:
  - `tool_call_accuracy` (recall over `min_tools_called`)
  - `retrieval_precision` (returned evidence keys ∩ expected)
  - `final_answer_accuracy` (stance exact match)
  - `hallucination_rate` (every numeric/claim in verdict text must map to a citation; pattern from `briefing_v5/audit.py`)
  - `cost_per_item_usd` (Anthropic pricing table inline)
- `eval/report.py` — Jinja2 → `eval/reports/<ts>/index.html`, plain HTML+CSS, no JS framework
- `eval/cli.py` — `python -m eval.cli run --dataset golden_v1 --sample 20`
- `.github/workflows/eval.yml` — nightly + on-PR-label, posts comment with metric deltas

**Acceptance:** First baseline lives in `eval/reports/baseline/`. Each metric has a unit test. Re-running same dataset → identical numbers (`temperature=0`).

### M5 — DSPy optimization layer (2 sessions)
**Goal:** measurably better numbers on the weakest 1-2 nodes.

**Pre-condition:** M4 baseline identifies underperformers (likely `contradiction` and `synthesize`).

**Files:**
- `src/agent/optimized/__init__.py` — DSPy adapter
- `src/agent/optimized/{contradiction,synthesize}_signature.py` — `dspy.Signature` classes
- `eval/dspy_compile.py` — 70/30 train/dev split, `dspy.BootstrapFewShot(metric=final_answer_accuracy, max_bootstrapped_demos=4)`, persists compiled module to `src/agent/optimized/compiled/`
- Wire compiled prompts behind `USE_DSPY_PROMPTS=1` flag for clean A/B

**Acceptance (kill criterion):** Compiled version must beat baseline by **≥3pp on `final_answer_accuracy`** on the 30-item dev set. If not, abandon DSPy for that node and revert to eval-driven hand-tuning. Document the result either way in `docs/dspy_postmortem.md`. Other metrics must not regress by >2pp.

### M6 — FastAPI + background tasks (1-2 sessions)
**Goal:** async serving with job semantics.

**Files:**
- `src/api/main.py` — FastAPI app, lifespan-scoped `httpx.AsyncClient`, structured logging
- `src/api/routes/validate.py` — `POST /validate` returns `{job_id}`; `GET /validate/{job_id}` returns status/result; FastAPI `BackgroundTasks` + in-process `dict[str, JobState]` (intentionally not Celery — solo dev, single process)
- `src/api/routes/health.py`
- `src/api/schemas.py`
- `tests/api/test_validate.py` — async client, 202 → poll → 200

**Acceptance:** `uvicorn src.api.main:app` boots, end-to-end POST → poll → result against fixtures.

### M7 — Prometheus + cost metrics (1 session)
**Goal:** observable in Grafana.

**Files:**
- `src/api/metrics.py` — `prometheus_client` collectors:
  - `itv_node_latency_seconds` (Histogram, labels `node,status`)
  - `itv_validation_total` (Counter, labels `stance,status`)
  - `itv_tokens_total` (Counter, labels `model,kind` ∈ `input|output|cache_read|cache_write`)
  - `itv_cost_usd_total` (Counter, labels `model`; pricing constants in `src/agent/llm.py`)
  - `itv_tool_call_total` (Counter, labels `tool,outcome`)
- `src/api/middleware.py` — request-scoped timer + per-node hook injected into `ValidatorState`
- `GET /metrics` via `prometheus_client.make_asgi_app`

**Acceptance:** Single validation against smoke fixture increments every counter; cost matches hand-calculation to ±$0.0001.

### M8 — Grafana + docker-compose (1 session)
**Files:**
- `infra/docker-compose.yml` — `prometheus`, `grafana`, scrapes `host.docker.internal:8000/metrics`
- `infra/prometheus.yml`, `infra/grafana/provisioning/datasources/prometheus.yml`
- `infra/grafana/dashboards/itv.json` — panels: per-node p50/p95 latency, validations/min by stance, tokens/hour by model, $/hour, error rate, top tools by failure
- `docs/RUNBOOK.md`

**Acceptance:** Stack boots; 5 validations recorded; screenshots in RUNBOOK.

### M9 — Hardening (1 session, optional)
**Files:** `src/guardrails/numeric_check.py` (every numeric in verdict text appears in evidence), `src/guardrails/citation_binding.py` (every claim has `evidence_id`), surface `cost_usd` in API response, enforce per-thesis cost cap (`MAX_COST_USD`).

## Key design decisions

| # | Decision | Choice | Runner-up | Why |
|---|----------|--------|-----------|-----|
| 1 | Orchestration | **LangGraph** `StateGraph` | Raw Anthropic tool-use loop | Free DAG visualization + per-node hooks the eval harness needs |
| 2 | News source | **NewsAPI dev tier** (free, 100 req/day) | Tavily ($0.005/req) | NewsAPI enough for 100-pair eval; Tavily burns money on DSPy compile loops |
| 3 | Filings source | **SEC EDGAR direct** (free, no key) | FMP `/sec_filings` | EDGAR is canonical; FMP wraps with delay |
| 4 | DSPy compile timing | **Sync, offline, checked-in artifact** | Online compile on app startup | Reproducible, PR-reviewable, free at request time |
| 5 | Prometheus client | **Official `prometheus_client` + `make_asgi_app`** | `starlette-prometheus` | Custom token/cost metrics → middleware doesn't help |
| 6 | Background jobs | **`BackgroundTasks` + in-process dict** | Celery + Redis | Solo dev, single instance; document upgrade path |
| 7 | SignalPilot coupling | **Pattern-borrow only** | Editable install | Sibling-path import coupling rots within a month |

## First-session task list (M0)

1. `uv add langgraph httpx tenacity structlog` and `uv add --dev pytest-asyncio respx pytest-cov`
2. Create `src/config.py` with Pydantic `Settings` (5 keys above); extend `.env.example`
3. Create `ruff.toml` (line-length 100, py311, `E,F,I,UP,B,SIM`) and `mypy.ini` (`strict = True`, `ignore_missing_imports = True` for `langgraph`, `dspy`)
4. Add `tests/conftest.py` with `anyio_backend` fixture and `frozen_settings` fixture
5. Create `.github/workflows/ci.yml` running `uv run ruff check .`, `uv run mypy src`, `uv run pytest -q` on push and PR

After M0, M1 begins with `src/agent/state.py` so every subsequent module imports against a frozen contract.
