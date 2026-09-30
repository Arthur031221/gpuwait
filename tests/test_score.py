from __future__ import annotations

from gpuwait.load import LevelResult, RequestResult
from gpuwait.sampler.base import Sample, SamplerResult
from gpuwait.score import BenchmarkResult, summarize_level


def _level(samples_busy: list[float], requests: list[RequestResult] | None = None) -> LevelResult:
    samples = [Sample(t=i * 0.5, busy_pct=b) for i, b in enumerate(samples_busy)]
    sres = SamplerResult(mode="ollama-timing", reason="test", samples=samples, notes=["note"])
    return LevelResult(
        concurrency=1,
        duration_s=2.0,
        think_time_s=1.0,
        prompt_tokens=32,
        max_tokens=32,
        stream=True,
        requests=requests or [],
        sampler_result=sres,
    )


def test_summarize_level_idle_is_inverse_of_busy():
    level = _level([100.0, 0.0])  # average busy 50 -> idle 50
    summary = summarize_level(level)
    assert summary.busy_percent == 50.0
    assert summary.idle_percent == 50.0


def test_summarize_level_no_samples_is_fully_idle():
    level = _level([])
    summary = summarize_level(level)
    assert summary.idle_percent == 100.0
    assert summary.sample_count == 0


def test_summarize_level_does_not_claim_token_throughput_without_token_counts():
    req = RequestResult(start=0.0, end=1.0, ok=True, ttft=None, output_tokens=0)
    summary = summarize_level(_level([50.0], requests=[req]))
    assert summary.requests_ok == 1
    assert summary.throughput_tok_s is None


def test_summarize_level_counts_requests_and_throughput():
    reqs = [
        RequestResult(start=0.0, end=0.5, ok=True, ttft=0.1, output_tokens=10),
        RequestResult(start=0.5, end=1.0, ok=True, ttft=0.1, output_tokens=20),
        RequestResult(start=1.0, end=1.2, ok=False, ttft=None, output_tokens=0, error="boom"),
    ]
    level = _level([50.0], requests=reqs)
    summary = summarize_level(level)
    assert summary.requests_ok == 2
    assert summary.requests_failed == 1
    assert summary.throughput_tok_s == 15.0  # 30 tokens / 2s duration
    assert summary.mean_ttft_s == 0.1


def test_benchmark_result_headline_picks_concurrency_one():
    level1 = summarize_level(_level([80.0]))
    level1.concurrency = 1
    level16 = summarize_level(_level([5.0]))
    level16.concurrency = 16
    result = BenchmarkResult(target="http://x", model="m", levels=[level1, level16])
    assert result.headline_idle_percent == level1.idle_percent
    assert result.metric_label == "Request Idle Score"


def test_benchmark_result_headline_falls_back_to_first_level():
    level4 = summarize_level(_level([20.0]))
    level4.concurrency = 4
    result = BenchmarkResult(target="http://x", model="m", levels=[level4])
    assert result.headline_idle_percent == level4.idle_percent
