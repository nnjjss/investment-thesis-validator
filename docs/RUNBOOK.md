# RUNBOOK — Investment Thesis Validator

## Local stack

### 1. Start the API

```bash
cd ~/projects/investment-thesis-validator
cp .env.example .env  # then fill in real keys
uv sync --all-extras --dev
uv run uvicorn src.api.main:app --reload --port 8000
```

Verify:
```bash
curl -s http://localhost:8000/health
curl -s http://localhost:8000/metrics | head -20
```

### 2. Start Prometheus + Grafana

```bash
docker compose -f infra/docker-compose.yml up -d
```

- Prometheus UI: http://localhost:9090 — verify the `itv` target is `UP` under Status → Targets.
- Grafana UI: http://localhost:3000 (login `admin` / `admin`, or just browse anonymously).
- The `ITV / ITV — Validator Overview` dashboard is provisioned automatically.

To stop and wipe volumes:
```bash
docker compose -f infra/docker-compose.yml down -v
```

### 3. Submit a validation

```bash
curl -s -X POST http://localhost:8000/validate \
  -H 'content-type: application/json' \
  -d '{"thesis": "TSM is undervalued at 18x forward P/E", "ticker": "TSM"}' | jq

# Poll the returned job_id:
curl -s http://localhost:8000/validate/<JOB_ID> | jq
```

Within ~10s of the validation completing, the Grafana dashboard panels should populate.

---

## Eval

Quick smoke (5 random items from the seed):
```bash
uv run python -m eval.cli run \
  --dataset eval/datasets/golden_v1_seed.jsonl \
  --sample 5 \
  --concurrency 2
```

Open the generated `eval/runs/<ts>/index.html` in a browser.

CI eval is in `.github/workflows/eval.yml` — triggers nightly, on `workflow_dispatch`, and on PRs labeled `eval`. Requires `ANTHROPIC_API_KEY`, `FMP_API_KEY`, `NEWS_API_KEY` repo secrets.

---

## DSPy compile

After M4 baseline numbers exist:

```bash
uv run python -m eval.dspy_compile \
  --dataset eval/datasets/golden_v1.jsonl \
  --target contradiction \
  --train-split 0.7
```

Then fill in `docs/dspy_postmortem.md`. **Kill criterion: +3pp on `final_answer_accuracy` on the 30-item dev split, no other metric regressing >2pp.** If unmet, abandon DSPy for that node.

---

## Common operations

### Tail metrics

```bash
curl -s http://localhost:8000/metrics | grep itv_
```

### Override SEC User-Agent

EDGAR returns 403 if the User-Agent header doesn't include a real contact email. Set `SEC_USER_AGENT="Your Org you@example.com"` in `.env` for production deployments.

### Cost cap

Per-validation cost cap defaults to `$0.50` (`MAX_COST_USD`). The cap is enforced at synthesize-time in M9 hardening — until then it is informational only and surfaced via `/validate/{job_id}.cost_usd`.

---

## Upgrade paths

These are intentionally simple in v1; the table below tracks when each becomes a real bottleneck and what to do about it.

| Component | Current | Pivot when… | Next |
|---|---|---|---|
| Job store | in-process `dict[str, JobState]` | second instance / restart-loss matters | Redis + RQ or Celery |
| News provider | NewsAPI dev tier (free, 100/day) | per-day cap blocks evals | Tavily (~$0.005/req) — flag in `src/ingestion/news.py` |
| LangGraph state merge | sequential, replace-on-write | parallel evidence fan-out becomes worth it | `Annotated[..., operator.add]` reducers per accumulating field |
| Eval persistence | JSONL | rows > ~100k | Parquet via `pyarrow` |
| Secrets | `.env` file | multi-deployer / rotation | 1Password CLI / SOPS / cloud secret manager |

---

## Known gotchas

- `langgraph 1.x` returns `Any` from `StateGraph(...)` which mypy strict trips on; cast to `Any` in `src/agent/graph.py`.
- `dspy.Signature` types as `Any` — subclass requires `# type: ignore[misc]`.
- `respx` route mocks are scoped to the test function; importing them as fixtures in conftest doesn't work — keep them inside the `@respx.mock` decorated test body.
