"""HTML report generator for an EvalResult.

Plain HTML + inline CSS — no Jinja2, no JS framework. Output is one
``index.html`` per run. Open in any browser; CI can attach as artifact.
"""

from __future__ import annotations

import html
from dataclasses import asdict
from pathlib import Path

from eval.runner import EvalResult


def write_html_report(result: EvalResult, run_dir: Path, *, dataset_name: str) -> Path:
    out_path = run_dir / "index.html"
    agg = result.aggregate

    rows = "".join(
        f"<tr>"
        f"<td>{html.escape(s.item_id)}</td>"
        f"<td>{s.final_answer_accuracy:.2f}</td>"
        f"<td>{s.tool_call_accuracy:.2f}</td>"
        f"<td>{s.retrieval_precision:.2f}</td>"
        f"<td>{s.hallucination_rate:.2f}</td>"
        f"<td>${s.cost_usd:.4f}</td>"
        f"</tr>"
        for s in sorted(result.item_scores, key=lambda x: x.item_id)
    )

    failure_rows = "".join(
        f"<tr>"
        f"<td>{html.escape(f.get('item_id', '?'))}</td>"
        f"<td>{html.escape(f.get('stage', '?'))}</td>"
        f"<td><pre>{html.escape(f.get('error', ''))}</pre></td>"
        f"</tr>"
        for f in result.failures
    )

    failures_block = (
        f"<h2>Failures ({len(result.failures)})</h2>"
        f"<table><tr><th>item_id</th><th>stage</th><th>error</th></tr>{failure_rows}</table>"
        if result.failures
        else "<p>No failures.</p>"
    )

    html_body = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>ITV eval — {html.escape(dataset_name)}</title>
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; max-width: 980px; margin: 2em auto; color: #1a1a1a; padding: 0 1em; }}
  h1 {{ margin-bottom: 0.2em; }}
  .ts {{ color: #666; font-size: 0.9em; margin-bottom: 1.5em; }}
  .agg {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 0.5em 2em; padding: 1em; background: #f5f5f5; border-radius: 6px; margin: 1em 0; }}
  .agg dt {{ font-weight: 600; color: #333; }}
  .agg dd {{ margin: 0 0 0.5em 0; font-variant-numeric: tabular-nums; }}
  table {{ border-collapse: collapse; width: 100%; margin: 1em 0; }}
  th, td {{ padding: 6px 10px; text-align: left; border-bottom: 1px solid #ddd; font-variant-numeric: tabular-nums; }}
  th {{ background: #fafafa; }}
  tr:hover {{ background: #f9f9f9; }}
  pre {{ margin: 0; font-size: 0.85em; max-width: 600px; overflow-x: auto; }}
</style>
</head>
<body>
<h1>Investment Thesis Validator — eval</h1>
<div class="ts">dataset: {html.escape(dataset_name)} · n_succeeded={agg.n} · n_failed={len(result.failures)}</div>

<dl class="agg">
  <dt>final_answer_accuracy</dt><dd>{agg.final_answer_accuracy:.3f}</dd>
  <dt>tool_call_accuracy</dt>   <dd>{agg.tool_call_accuracy:.3f}</dd>
  <dt>retrieval_precision</dt>  <dd>{agg.retrieval_precision:.3f}</dd>
  <dt>hallucination_rate</dt>   <dd>{agg.hallucination_rate:.3f}</dd>
  <dt>cost_usd_total</dt>       <dd>${agg.cost_usd_total:.4f}</dd>
  <dt>cost_usd_mean</dt>        <dd>${agg.cost_usd_mean:.4f}</dd>
</dl>

<h2>Per-item scores</h2>
<table>
<tr><th>id</th><th>final_acc</th><th>tool_acc</th><th>retr_prec</th><th>halluc</th><th>cost</th></tr>
{rows}
</table>

{failures_block}

</body>
</html>
"""
    out_path.write_text(html_body, encoding="utf-8")
    return out_path


def aggregate_dict(result: EvalResult) -> dict[str, float | int]:
    return asdict(result.aggregate)
