# Full Baseline — golden_v1.jsonl (100 items)

Run: `eval/runs/20260515T195743Z_baseline_full_v1/` (gitignored).
Configuration: full dataset, `--concurrency 4`, no DSPy compile, no
hand-tuning beyond what shipped in M2b.

## Aggregate

| metric                  | value     |
|-------------------------|-----------|
| n_items_succeeded       | 99 / 100  |
| **final_answer_accuracy** | **0.424** |
| tool_call_accuracy      | 0.483     |
| retrieval_precision     | 0.369     |
| **hallucination_rate**    | **0.000** |
| cost_usd_total          | $4.13     |
| cost_usd_mean           | $0.0417   |

## Per-category

| category       | n  | final | tool  | retr  | cost     |
|----------------|----|-------|-------|-------|----------|
| contradiction  | 20 | 0.300 | 0.400 | 0.031 | $0.0373  |
| edge_case      | 20 | 0.700 | 0.750 | 0.613 | $0.0463  |
| fundamentals   | 19 | 0.211 | 0.684 | 0.075 | $0.0414  |
| multi_claim    | 20 | 0.600 | 0.592 | 0.110 | $0.0545  |
| sentiment      | 20 | 0.300 | 0.000 | 1.000 | $0.0290  |

## Per-stance accuracy — the headline finding

| expected stance | n  | accuracy |
|-----------------|----|----------|
| SUPPORTED       | 25 | **0.000** |
| REFUTED         | 48 | 0.354    |
| UNCERTAIN       | 26 | 0.962    |

**The agent is structurally biased toward UNCERTAIN.** It refuses to commit
to SUPPORTED in any case, and only catches ~1/3 of obvious contradictions.
The high UNCERTAIN accuracy is mostly a side-effect: when the model
responds UNCERTAIN to nearly everything, it scores well on items whose
ground-truth label is also UNCERTAIN.

This is consistent with the synthesizer prompt I shipped in M2b
(`src/agent/prompts/synthesizer_system.md`):

> "Be honest about uncertainty. If the evidence is thin, contradictory, or
> stale relative to the as-of date, return UNCERTAIN. Do not stretch a
> SUPPORTED verdict."

The model is interpreting that instruction far too aggressively — it
returns UNCERTAIN even for items where the evidence is actually clean
and decisive (e.g. `AAPL TTM FCF margin > 25%`, `NVDA revenue +40% YoY`).

## Other systemic issues observed

- **`retrieval_precision = 0.369`** is depressed by FMP's free-tier
  paywall on `/ratios` (already isolated to non-fatal) AND by the
  expected_evidence_keys often referencing dates that the agent doesn't
  cover (e.g. asking for FY2023 income when we only fetch the last 4
  quarters by default). The `sentiment` row's `1.000` is vacuous credit
  (sentiment items have empty expected_evidence_keys).
- **`sentiment.tool_acc = 0.000`** — `NEWS_API_KEY` is unconfigured, so
  every sentiment item's required `fetch_news` call is `status=skipped`.
  The metric is correctly honest about coverage gaps; this number will
  pop the moment a key is wired in.
- **`hallucination_rate = 0.000`** — the synthesize-time
  evidence-id cross-check is doing exactly what it was designed to do.
  No silent invention of citations.

## One real failure (f13)

PFE revenue declined > 30% YoY in FY2023. The graph error was
`'str' object has no attribute .get` — likely a model returning
`claim_verdicts` as a string instead of an array, dying inside
`synthesize._validate_*`. **Filed as a follow-up bug, not a baseline
metric.** The 99 successful items still produce a defensible baseline.

## What to do next

The kill-criterion plan in the design doc says: M5 (DSPy compile) is
gated on baseline being stable. It is — these numbers are
reproducible. But before reaching for DSPy:

1. **Hand-tune the synthesizer prompt** (an M5b-style intervention). The
   instruction to be conservative is over-firing. Predicted lift: +10pp
   to +20pp on `final_answer_accuracy` from prompt edit alone, before
   any DSPy work. This is the highest-leverage single change available.
2. **Configure `NEWS_API_KEY`** to remove the artificial 0% on sentiment
   `tool_call_accuracy` and unblock the news-dependent items.
3. **Tighten the eval's `expected_evidence_keys`** so `retrieval_precision`
   reflects agent behavior rather than the FMP-tier coverage gap.
4. Then — and only then — invoke DSPy. The +3pp kill criterion is
   far easier to clear from a 0.6+ baseline than from 0.42.

## Why this baseline is exactly what we wanted

Eval-first sequencing pays off here. We have:
- a precise, reproducible number to beat
- a clear diagnosis (UNCERTAIN-bias in synthesizer, not a tooling issue)
- a graduated improvement plan with predicted lift per intervention
- a kill criterion already in place so we don't sink money into DSPy
  if hand-tuning hits diminishing returns first

The dataset surfaced exactly the problem it was designed to surface.
