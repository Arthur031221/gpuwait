"""Terminal timeline and summary table, printed with rich."""

from __future__ import annotations

from rich.console import Console
from rich.table import Table

from gpuwait.score import BenchmarkResult

_BLOCKS = " ▁▂▃▄▅▆▇█"


def _sparkline(samples: list[dict]) -> str:
    if not samples:
        return "(no samples)"
    chars = []
    for s in samples:
        idx = min(int(s["busy_pct"] / 100 * (len(_BLOCKS) - 1)), len(_BLOCKS) - 1)
        idx = max(idx, 0)
        chars.append(_BLOCKS[idx])
    return "".join(chars)


def render_terminal(result: BenchmarkResult, console: Console | None = None) -> None:
    console = console or Console()
    console.print(f"[bold]gpuwait[/bold]  target={result.target}  model={result.model}")

    for lvl in result.levels:
        console.print()
        console.print(
            f"[bold]concurrency {lvl.concurrency}[/bold]"
            f"  idle [magenta]{lvl.idle_percent}%[/magenta]"
            f"  busy {lvl.busy_percent}%"
            f"  sampler={lvl.sampler_mode}"
        )
        console.print(
            f"  timeline (busy per {'sample' if lvl.samples else 'n/a'}): {_sparkline(lvl.samples)}"
        )
        console.print(
            f"  requests ok={lvl.requests_ok} failed={lvl.requests_failed}"
            f"  throughput={lvl.throughput_tok_s if lvl.throughput_tok_s is not None else 'n/a'} tok/s"
            f"  p50={lvl.p50_latency_s}s p95={lvl.p95_latency_s}s"
            f"  ttft={lvl.mean_ttft_s}s"
        )
        if lvl.requests_failed and not lvl.requests_ok:
            console.print(
                "  [red]every request at this concurrency level failed, see errors above[/red]"
            )

    table = Table(title=f"{result.metric_label} summary")
    table.add_column("concurrency", justify="right")
    table.add_column("idle %", justify="right")
    table.add_column("busy %", justify="right")
    table.add_column("throughput tok/s", justify="right")
    table.add_column("p50 latency s", justify="right")
    for lvl in result.levels:
        table.add_row(
            str(lvl.concurrency),
            f"{lvl.idle_percent}",
            f"{lvl.busy_percent}",
            f"{lvl.throughput_tok_s if lvl.throughput_tok_s is not None else 'n/a'}",
            f"{lvl.p50_latency_s}",
        )
    console.print()
    console.print(table)

    headline = result.headline_idle_percent
    if headline is not None:
        console.print()
        console.print(f"[bold]{result.metric_label} (concurrency 1): {headline}% idle[/bold]")
        console.print(
            "[dim]a high number here reflects the workload shape (one user, gaps between "
            "messages), not a broken server. See the README for what actually raises "
            "utilization.[/dim]"
        )
