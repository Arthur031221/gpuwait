"""Command line entry point for gpuwait."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

import httpx
from rich.console import Console

from gpuwait import __version__
from gpuwait.badge import render_badge_svg
from gpuwait.jsonout import to_json_dict
from gpuwait.load import run_level
from gpuwait.render_html import render_report_html
from gpuwait.render_terminal import render_terminal
from gpuwait.sampler.detect import detect_mode
from gpuwait.score import BenchmarkResult, summarize_level


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="gpuwait",
        description=(
            "Measure how much of the time your local LLM server's GPU sits idle. "
            "Point it at any OpenAI-compatible endpoint (Ollama, llama-server, vLLM, "
            "mlx-lm, LM Studio) and it replays a concurrent request trace at "
            "concurrency 1, 4 and 16, then reports one number per level: the GPU Idle "
            "Score."
        ),
    )
    parser.add_argument(
        "base_url", nargs="?", help="server base URL, for example http://localhost:11434"
    )
    parser.add_argument(
        "--model", help="model name to request, autodetected from /api/ps when omitted"
    )
    parser.add_argument(
        "--concurrency",
        default="1,4,16",
        help="comma separated concurrency levels to test (default: 1,4,16)",
    )
    parser.add_argument(
        "--duration-s",
        type=float,
        default=60.0,
        help="seconds to run at each concurrency level (default: 60, keep this short on shared hardware)",
    )
    parser.add_argument(
        "--think-time",
        type=float,
        default=2.0,
        help="seconds a worker pauses between its own requests, simulates a user "
        "reading a reply before the next message (default: 2.0)",
    )
    parser.add_argument(
        "--prompt-tokens", type=int, default=128, help="approx input prompt length (default: 128)"
    )
    parser.add_argument(
        "--max-tokens", type=int, default=128, help="max output tokens per request (default: 128)"
    )
    parser.add_argument(
        "--no-stream", dest="stream", action="store_false", help="disable streaming responses"
    )
    parser.set_defaults(stream=True)
    parser.add_argument(
        "--sampler",
        choices=("auto", "powermetrics", "nvidia-smi", "ollama-timing"),
        default="auto",
        help="GPU sampler mode (default: auto-detect, never prompts for a password)",
    )
    parser.add_argument("--json", action="store_true", help="print the JSON report to stdout")
    parser.add_argument(
        "--report-html", default="report.html", help="HTML report filename (default: report.html)"
    )
    parser.add_argument(
        "--out-dir", default=".", help="directory to write report.html and badge.svg into"
    )
    parser.add_argument(
        "--no-html", action="store_true", help="skip writing report.html and badge.svg"
    )
    parser.add_argument(
        "--quiet", action="store_true", help="suppress the terminal timeline and table"
    )
    parser.add_argument(
        "--http-timeout-s", type=float, default=60.0, help="per-request HTTP timeout (default: 60)"
    )
    parser.add_argument("--version", action="version", version=f"gpuwait {__version__}")
    return parser


def _parse_concurrency(raw: str) -> list[int]:
    levels = []
    for piece in raw.split(","):
        piece = piece.strip()
        if not piece:
            continue
        value = int(piece)
        if value < 1:
            raise ValueError(f"concurrency levels must be >= 1, got {value}")
        levels.append(value)
    if not levels:
        raise ValueError("no concurrency levels given")
    return levels


async def _autodetect_model(base_url: str, client: httpx.AsyncClient) -> str | None:
    try:
        resp = await client.get(f"{base_url.rstrip('/')}/api/ps", timeout=3.0)
        if resp.status_code == 200:
            models = resp.json().get("models", [])
            names = [m.get("name") or m.get("model") for m in models]
            names = [n for n in names if n]
            if len(names) == 1:
                return names[0]
    except (httpx.HTTPError, ValueError):
        pass
    try:
        resp = await client.get(f"{base_url.rstrip('/')}/v1/models", timeout=3.0)
        if resp.status_code == 200:
            data = resp.json().get("data", [])
            ids = [m.get("id") for m in data if m.get("id")]
            if len(ids) == 1:
                return ids[0]
    except (httpx.HTTPError, ValueError):
        pass
    return None


async def _check_reachable(base_url: str, client: httpx.AsyncClient) -> str | None:
    """Return an error message, or None if the server looks reachable."""
    try:
        await client.get(f"{base_url.rstrip('/')}/", timeout=3.0)
        return None
    except httpx.HTTPError as exc:
        # a non-2xx status still proves the server is up and answering
        if isinstance(exc, httpx.HTTPStatusError):
            return None
        return f"cannot reach {base_url}: {exc}"


async def _amain(argv: list[str] | None, console: Console) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if not args.base_url:
        parser.print_usage(sys.stderr)
        console.print("[red]error: base_url is required, for example http://localhost:11434[/red]")
        return 2

    try:
        levels = _parse_concurrency(args.concurrency)
    except ValueError as exc:
        console.print(f"[red]error: {exc}[/red]")
        return 2

    async with httpx.AsyncClient() as probe_client:
        unreachable = await _check_reachable(args.base_url, probe_client)
        if unreachable:
            console.print(f"[red]error: {unreachable}[/red]")
            console.print("[dim]is the server running and is the URL correct?[/dim]")
            return 1

        model = args.model
        if not model:
            model = await _autodetect_model(args.base_url, probe_client)
            if not model:
                console.print(
                    "[red]error: could not autodetect a model, pass --model explicitly "
                    "(found zero or more than one candidate from /api/ps or /v1/models)[/red]"
                )
                return 2

    mode, reason = detect_mode(None if args.sampler == "auto" else args.sampler)
    if not args.quiet:
        console.print(f"[dim]sampler: {mode} ({reason})[/dim]")

    result = BenchmarkResult(target=args.base_url, model=model)
    any_ok = False
    for concurrency in levels:
        if not args.quiet:
            console.print(
                f"[dim]running concurrency {concurrency} for {args.duration_s:.0f}s...[/dim]"
            )
        level = await run_level(
            base_url=args.base_url,
            model=model,
            concurrency=concurrency,
            duration_s=args.duration_s,
            think_time_s=args.think_time,
            prompt_tokens=args.prompt_tokens,
            max_tokens=args.max_tokens,
            stream=args.stream,
            sampler_mode=mode,
            sampler_reason=reason,
            http_timeout_s=args.http_timeout_s,
        )
        summary = summarize_level(level)
        result.levels.append(summary)
        any_ok = any_ok or summary.requests_ok > 0

    if not any_ok:
        console.print(
            "[red]every request failed at every concurrency level, nothing to report[/red]"
        )
        if not args.quiet:
            render_terminal(result, console=console)
        return 1

    if not args.quiet:
        render_terminal(result, console=console)

    if args.json:
        print(json.dumps(to_json_dict(result), indent=2))

    if not args.no_html:
        out_dir = Path(args.out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        headline = result.headline_idle_percent or 0.0
        badge_name = "request idle" if result.metric_label == "Request Idle Score" else "gpu idle"
        badge_svg = render_badge_svg(badge_name, f"{headline}%", headline)
        (out_dir / "badge.svg").write_text(badge_svg, encoding="utf-8")
        html = render_report_html(result, badge_svg=badge_svg)
        (out_dir / args.report_html).write_text(html, encoding="utf-8")
        if not args.quiet:
            console.print(
                f"[dim]wrote {out_dir / args.report_html} and {out_dir / 'badge.svg'}[/dim]"
            )

    return 0


def main(argv: list[str] | None = None) -> int:
    console = Console()
    try:
        return asyncio.run(_amain(argv, console))
    except KeyboardInterrupt:
        console.print("\n[yellow]interrupted[/yellow]")
        return 130


if __name__ == "__main__":
    sys.exit(main())
