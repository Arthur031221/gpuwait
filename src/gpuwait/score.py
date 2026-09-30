"""Turn raw level results into the numbers the report shows."""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field

from gpuwait.load import LevelResult


@dataclass
class LevelSummary:
    concurrency: int
    duration_s: float
    think_time_s: float
    idle_percent: float
    busy_percent: float
    sample_count: int
    requests_ok: int
    requests_failed: int
    throughput_tok_s: float | None
    p50_latency_s: float | None
    p95_latency_s: float | None
    mean_ttft_s: float | None
    sampler_mode: str
    sampler_reason: str
    sampler_notes: list[str]
    samples: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "concurrency": self.concurrency,
            "duration_s": self.duration_s,
            "think_time_s": self.think_time_s,
            "idle_percent": self.idle_percent,
            "busy_percent": self.busy_percent,
            "sample_count": self.sample_count,
            "requests_ok": self.requests_ok,
            "requests_failed": self.requests_failed,
            "throughput_tok_s": self.throughput_tok_s,
            "p50_latency_s": self.p50_latency_s,
            "p95_latency_s": self.p95_latency_s,
            "mean_ttft_s": self.mean_ttft_s,
            "sampler_mode": self.sampler_mode,
            "sampler_reason": self.sampler_reason,
            "sampler_notes": self.sampler_notes,
            "samples": self.samples,
        }


def _percentile(sorted_data: list[float], p: float) -> float | None:
    if not sorted_data:
        return None
    idx = min(int(len(sorted_data) * p), len(sorted_data) - 1)
    return sorted_data[idx]


def summarize_level(level: LevelResult) -> LevelSummary:
    sres = level.sampler_result
    samples = sres.samples if sres else []
    busy = statistics.fmean(s.busy_pct for s in samples) if samples else 0.0
    busy = max(0.0, min(100.0, busy))
    idle = max(0.0, min(100.0, 100.0 - busy))

    ok = level.completed
    failed = level.failed
    total_tokens = sum(r.output_tokens for r in ok)
    throughput = total_tokens / level.duration_s if level.duration_s and total_tokens else None
    latencies = sorted(r.latency_s for r in ok)
    ttfts = [r.ttft for r in ok if r.ttft is not None]

    return LevelSummary(
        concurrency=level.concurrency,
        duration_s=level.duration_s,
        think_time_s=level.think_time_s,
        idle_percent=round(idle, 1),
        busy_percent=round(busy, 1),
        sample_count=len(samples),
        requests_ok=len(ok),
        requests_failed=len(failed),
        throughput_tok_s=round(throughput, 1) if throughput is not None else None,
        p50_latency_s=round(v, 3) if (v := _percentile(latencies, 0.5)) is not None else None,
        p95_latency_s=round(v, 3) if (v := _percentile(latencies, 0.95)) is not None else None,
        mean_ttft_s=round(statistics.fmean(ttfts), 3) if ttfts else None,
        sampler_mode=sres.mode if sres else "unknown",
        sampler_reason=sres.reason if sres else "",
        sampler_notes=sres.notes if sres else [],
        samples=[{"t": round(s.t, 2), "busy_pct": round(s.busy_pct, 1)} for s in samples],
    )


@dataclass
class BenchmarkResult:
    target: str
    model: str
    levels: list[LevelSummary] = field(default_factory=list)

    @property
    def headline_idle_percent(self) -> float | None:
        for lvl in self.levels:
            if lvl.concurrency == 1:
                return lvl.idle_percent
        return self.levels[0].idle_percent if self.levels else None

    @property
    def headline_level(self) -> LevelSummary | None:
        for lvl in self.levels:
            if lvl.concurrency == 1:
                return lvl
        return self.levels[0] if self.levels else None

    @property
    def metric_label(self) -> str:
        level = self.headline_level
        if level is not None and level.sampler_mode == "ollama-timing":
            return "Request Idle Score"
        return "GPU Idle Score"
