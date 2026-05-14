# DSPy compilation — postmortem template

Use this template after every M5 compile cycle. **Always fill it out**, even
when DSPy wins — the discipline is the point.

## Run metadata

- date:
- baseline run dir: `eval/runs/<ts>/`
- compiled artifact: `src/agent/optimized/compiled/<target>_<sha>.json`
- target node: `<contradiction | synthesize>`
- train / dev split: 70 / 30 (seed 42)
- `max_bootstrapped_demos`:
- model on both sides:
- approx token spend:

## Numbers

| metric                  | baseline | compiled | delta (pp) |
| ----------------------- | -------- | -------- | ---------- |
| final_answer_accuracy   |          |          |            |
| tool_call_accuracy      |          |          |            |
| retrieval_precision     |          |          |            |
| hallucination_rate      |          |          |            |
| cost_usd_mean           |          |          |            |

## Decision (M5 kill criterion)

**Rule:** if `final_answer_accuracy` on the 30-item dev set does not improve
by **≥3pp** vs baseline AND no other metric regresses by >2pp, abandon DSPy
for this node and revert to eval-driven hand-tuning.

- met +3pp threshold? `[ ] yes  [ ] no`
- any metric regressed >2pp? `[ ] yes  [ ] no` (which: ___)

**Action taken:** ___

If kill criterion fired:
- [ ] runtime feature flag (`USE_DSPY_PROMPTS`) is OFF for this node
- [ ] compiled artifact is kept under `compiled/` for reference, not loaded
- [ ] follow-up issue filed for hand-tuning the same node, citing this postmortem

If DSPy won:
- [ ] runtime loader wired to load `compiled/<target>_<sha>.json` when
      `USE_DSPY_PROMPTS=1`
- [ ] regression test added: re-run dev set, assert metrics within ±1pp of
      compile-time numbers
- [ ] `MEMORY.md` updated to note which node now uses compiled prompts

## Notes / surprises

(prompt drift observed, demo selection issues, cost surprises, etc.)
