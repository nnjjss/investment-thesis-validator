# Golden Dataset — Review Checklist

Before promoting `golden_v1_seed.jsonl` (or generator output) to `golden_v1.jsonl`, walk every item through this checklist. The whole point of the eval harness is that the answer key is *trustworthy* — a wrong label costs more than a missing item.

## Per-item checks

- [ ] **`thesis` is a single coherent statement.** Not a question, not a list of unrelated claims tucked into one string.
- [ ] **`ticker` is a real, currently-trading US-listed equity** (or, for the `edge_case` category, a deliberately broken ticker — delisted, IPO collision, ADR, etc.).
- [ ] **`as_of_date` is in the past relative to today** AND is a date when the relevant data actually exists (e.g. don't ask about Q1 2026 income statement with `as_of_date: 2026-01-15` — Q1 hasn't reported yet).
- [ ] **`expected_stance` is the answer a careful human analyst would give** with full data — not a guess. If uncertain, default to `UNCERTAIN`.
- [ ] **`expected_evidence_keys` lists evidence the agent must cite** for the verdict to count as correct. Use the agent's own key naming convention (`fmp.income_statement.<ticker>.<date>`, `sec.10-K.<padded_cik>`, etc.). Leave empty for sentiment-only items.
- [ ] **`min_tools_called` is the smallest set of tool nodes** that could plausibly produce the verdict. Don't require `fetch_filings` for a quote-derived claim.
- [ ] **`notes` explains the answer.** A reviewer should be able to understand the label without re-deriving it.

## Dataset-level checks

- [ ] **≥30% of items have `expected_stance` ∈ {`REFUTED`, `UNCERTAIN`}** (anti-sycophancy — a model that always says SUPPORTED must lose points on this dataset).
- [ ] **All five categories represented:** fundamentals, sentiment, contradiction, edge_case, multi_claim. Target distribution at full size: 20 each.
- [ ] **No two items are paraphrases of the same underlying claim.** Diversity matters more than count.
- [ ] **At least one item per category that should be UNCERTAIN.** UNCERTAIN must be a *first-class* answer, not a fallback.
- [ ] **Ticker collision items present** (BRK.A vs BRK.B, GOOGL vs GOOG) in `edge_case`.
- [ ] **Foreign ADR present** (ASML, TSM, BABA) in `edge_case` or `fundamentals` to test US-only assumption blast radius.
- [ ] **At least one delisted ticker** in `edge_case` to test graceful failure.

## Sign-off

After checklist passes, copy / promote the file and tag the review:

```bash
cp eval/datasets/golden_v1_seed.jsonl eval/datasets/golden_v1.jsonl
git add eval/datasets/golden_v1.jsonl
git commit -m "data: golden_v1 dataset reviewed and signed off"
```

Append a short reviewer signature to the bottom of this file:

```
- 2026-MM-DD reviewed by <name>: 100/100 items signed off, distribution { fundamentals: 20, sentiment: 20, contradiction: 20, edge_case: 20, multi_claim: 20 }, REFUTED+UNCERTAIN share = NN%.
```
