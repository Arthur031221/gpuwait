"""Static, dependency-free report.html generator.

No JavaScript, no external fonts or scripts: the report has to open
correctly from a local file:// URL and on GitHub Pages with nothing else
running. The bar chart is plain HTML/CSS, the badge is inline SVG.
"""

from __future__ import annotations

import html
from datetime import UTC, datetime

from gpuwait import __version__
from gpuwait.score import BenchmarkResult, LevelSummary

_BAR_COLOR = "#2563eb"

_CSS = """
:root { color-scheme: light dark; }
body {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
  max-width: 860px;
  margin: 2rem auto;
  padding: 0 1.25rem;
  line-height: 1.5;
  color: #1a1a1a;
  background: #ffffff;
}
@media (prefers-color-scheme: dark) {
  body { color: #e5e5e5; background: #14141a; }
  .card { background: #1e1e26 !important; border-color: #33333d !important; }
  .bar-track { background: #2a2a33 !important; }
  table { border-color: #33333d !important; }
  th, td { border-color: #33333d !important; }
}
h1 { font-size: 1.5rem; margin-bottom: 0.25rem; }
.subtitle { color: #666; margin-top: 0; }
.card {
  border: 1px solid #ddd;
  border-radius: 10px;
  padding: 1.25rem 1.5rem;
  margin: 1.25rem 0;
  background: #fafafa;
}
.headline { font-size: 2.25rem; font-weight: 700; margin: 0.25rem 0; }
.bar-row { display: flex; align-items: center; gap: 0.75rem; margin: 0.5rem 0; }
.bar-label { width: 6rem; font-variant-numeric: tabular-nums; }
.bar-track { flex: 1; background: #e8e8ec; border-radius: 4px; overflow: hidden; height: 1.25rem; }
.bar-fill { background: __BAR_COLOR__; height: 100%; }
.bar-value { width: 3.5rem; text-align: right; font-variant-numeric: tabular-nums; }
table { border-collapse: collapse; width: 100%; margin: 1rem 0; }
th, td { border: 1px solid #ddd; padding: 0.4rem 0.6rem; text-align: right; font-variant-numeric: tabular-nums; }
th:first-child, td:first-child { text-align: left; }
footer { color: #666; font-size: 0.85rem; margin-top: 2rem; }
code { background: rgba(127,127,127,0.15); padding: 0.1rem 0.3rem; border-radius: 4px; }
""".replace("__BAR_COLOR__", _BAR_COLOR)


def _bar_row(lvl: LevelSummary) -> str:
    pct = max(0.0, min(100.0, lvl.idle_percent))
    return f"""
    <div class="bar-row">
      <div class="bar-label">concurrency {lvl.concurrency}</div>
      <div class="bar-track"><div class="bar-fill" style="width:{pct:.1f}%"></div></div>
      <div class="bar-value">{lvl.idle_percent}%</div>
    </div>"""


def _table_rows(levels: list[LevelSummary]) -> str:
    rows = []
    for lvl in levels:
        rows.append(
            f"<tr><td>{lvl.concurrency}</td><td>{lvl.idle_percent}</td><td>{lvl.busy_percent}</td>"
            f"<td>{lvl.throughput_tok_s if lvl.throughput_tok_s is not None else 'n/a'}</td><td>{lvl.p50_latency_s}</td><td>{lvl.p95_latency_s}</td>"
            f"<td>{lvl.requests_ok}</td><td>{lvl.requests_failed}</td></tr>"
        )
    return "\n".join(rows)


def render_report_html(result: BenchmarkResult, badge_svg: str) -> str:
    headline_lvl = result.headline_level
    headline = result.headline_idle_percent
    generated = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    method = ""
    notes_html = ""
    if headline_lvl is not None:
        method = (
            f"sampler: <code>{html.escape(headline_lvl.sampler_mode)}</code>"
            f" ({html.escape(headline_lvl.sampler_reason)})"
        )
        if headline_lvl.sampler_notes:
            items = "".join(f"<li>{html.escape(n)}</li>" for n in headline_lvl.sampler_notes)
            notes_html = f"<ul>{items}</ul>"

    bars = "\n".join(_bar_row(lvl) for lvl in result.levels)
    rows = _table_rows(result.levels)

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>gpuwait report: {html.escape(result.target)}</title>
<style>{_CSS}</style>
</head>
<body>
<h1>gpuwait report</h1>
<p class="subtitle">target <code>{html.escape(result.target)}</code>, model <code>{html.escape(result.model)}</code>, generated {generated}</p>

<div class="card">
  {badge_svg}
  <div class="headline">{headline if headline is not None else "n/a"}% idle</div>
  <p>{result.metric_label} at concurrency 1. This is the percentage of the test window where the
  server had zero requests in flight (or, with a hardware sampler, where the GPU itself was
  not active). A high number here at concurrency 1 reflects one user's think-time between
  messages, not a broken server. See idle percent drop as concurrency rises below.</p>
  <p>{method}</p>
  {notes_html}
</div>

<div class="card">
  <h2>Idle percent by concurrency</h2>
  {bars}
</div>

<div class="card">
  <h2>Full results</h2>
  <table>
    <thead>
      <tr><th>concurrency</th><th>idle %</th><th>busy %</th><th>tok/s</th>
      <th>p50 latency s</th><th>p95 latency s</th><th>ok</th><th>failed</th></tr>
    </thead>
    <tbody>
      {rows}
    </tbody>
  </table>
</div>

<footer>
  <p>Generated by gpuwait {html.escape(__version__)}. Method: an OpenAI-compatible chat
  completion trace at each concurrency level, think time between a worker's own requests,
  idle percent averaged from sampler readings over the window. Full methodology and the
  fix for a high idle score (batching, per-backend concurrency settings) are in the
  project README.</p>
</footer>
</body>
</html>
"""
