from __future__ import annotations

from gpuwait.badge import render_badge_svg
from gpuwait.load import LevelResult
from gpuwait.render_html import render_report_html
from gpuwait.sampler.base import Sample, SamplerResult
from gpuwait.score import BenchmarkResult, summarize_level


def _summary(concurrency: int, busy: float):
    sres = SamplerResult(
        mode="ollama-timing", reason="test reason", samples=[Sample(0.0, busy)], notes=["a note"]
    )
    level = LevelResult(
        concurrency=concurrency,
        duration_s=60.0,
        think_time_s=2.0,
        prompt_tokens=128,
        max_tokens=128,
        stream=True,
        requests=[],
        sampler_result=sres,
    )
    return summarize_level(level)


def test_report_html_contains_headline_and_table():
    result = BenchmarkResult(
        target="http://localhost:11434",
        model="qwen3:4b",
        levels=[_summary(1, 20.0), _summary(16, 90.0)],
    )
    badge = render_badge_svg("gpu idle", "80.0%", 80.0)
    html = render_report_html(result, badge_svg=badge)
    assert "<html" in html
    assert "qwen3:4b" in html
    assert "80.0% idle" in html  # concurrency 1 idle = 100 - 20 = 80
    assert "Request Idle Score" in html
    assert "concurrency 16" in html
    assert "test reason" in html
    assert "a note" in html
    assert badge in html


def test_report_html_handles_no_levels():
    result = BenchmarkResult(target="http://x", model="m", levels=[])
    html = render_report_html(result, badge_svg="<svg></svg>")
    assert "n/a% idle" in html
