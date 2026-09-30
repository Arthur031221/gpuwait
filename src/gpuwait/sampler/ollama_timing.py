"""Fallback sampler: infer GPU busy and idle time from HTTP request timing.

This is what runs on a Mac without a passwordless sudo rule for powermetrics,
which is the common case for a fresh checkout. We have no hardware access to
the GPU at all, so "busy" is redefined honestly as "at least one HTTP request
is outstanding against the server" and "idle" is "the client is holding zero
outstanding requests". That is a real, useful signal (it is exactly what a
user's session looks like from the outside) but it cannot see whether the GPU
is actually computing in the middle of a single request. The notes on the
result say so explicitly, and the README repeats it.

We also poll Ollama's native `/api/ps` a few times during the run, purely to
record whether the target model stayed resident in VRAM. An evicted model
cannot be doing any GPU work, so that is a real (if coarse) extra signal, and
free to collect. If `/api/ps` is not present (a non-Ollama backend), polling
fails silently and we just skip the extra note.
"""

from __future__ import annotations

import asyncio
import contextlib
import math
import time
from dataclasses import dataclass

import httpx

from gpuwait.sampler.base import Sample, SamplerResult


@dataclass
class _Interval:
    start: float
    end: float


class OllamaTimingSampler:
    mode = "ollama-timing"

    def __init__(
        self,
        base_url: str,
        model: str | None = None,
        bucket_s: float = 0.5,
        ps_poll_s: float = 2.0,
        http_client_factory=httpx.AsyncClient,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.bucket_s = bucket_s
        self.ps_poll_s = ps_poll_s
        self._http_client_factory = http_client_factory
        self._intervals: list[_Interval] = []
        self._t0: float = 0.0
        self._t1: float = 0.0
        self._ps_task = None
        self._ps_seen_loaded = False
        self._ps_seen_unloaded = False
        self._ps_supported = True

    def record_interval(self, start: float, end: float) -> None:
        self._intervals.append(_Interval(start, end))

    async def __aenter__(self) -> OllamaTimingSampler:
        self._t0 = time.monotonic()
        self._ps_task = asyncio.create_task(self._poll_ps())
        return self

    async def __aexit__(self, *exc) -> bool:
        self._t1 = time.monotonic()
        if self._ps_task is not None:
            self._ps_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._ps_task
        return False

    async def _poll_ps(self) -> None:
        async with self._http_client_factory(timeout=2.0) as client:
            while True:
                try:
                    resp = await client.get(f"{self.base_url}/api/ps")
                    if resp.status_code == 200:
                        body = resp.json()
                        names = {m.get("name") or m.get("model") for m in body.get("models", [])}
                        loaded = (self.model in names) if self.model else bool(names)
                        if loaded:
                            self._ps_seen_loaded = True
                        else:
                            self._ps_seen_unloaded = True
                    else:
                        self._ps_supported = False
                except (httpx.HTTPError, ValueError, OSError):
                    self._ps_supported = False
                await asyncio.sleep(self.ps_poll_s)

    def result(self) -> SamplerResult:
        duration = max(self._t1 - self._t0, 0.0)
        samples: list[Sample] = []
        if duration > 0:
            n_buckets = max(math.ceil(duration / self.bucket_s), 1)
            for i in range(n_buckets):
                b_start = self._t0 + i * self.bucket_s
                b_end = min(b_start + self.bucket_s, self._t1)
                busy_fraction = _overlap_fraction(self._intervals, b_start, b_end)
                samples.append(Sample(t=b_start - self._t0, busy_pct=busy_fraction * 100.0))
        notes = [
            "busy means at least one HTTP request was in flight, idle means zero were",
            "cannot see GPU activity inside a single request, only whether one was outstanding",
        ]
        if self._ps_supported and self.model:
            if self._ps_seen_unloaded and not self._ps_seen_loaded:
                notes.append(
                    f"/api/ps never reported {self.model} resident in VRAM during this run"
                )
            elif self._ps_seen_unloaded:
                notes.append(f"/api/ps reported {self.model} evicted from VRAM at some point")
        return SamplerResult(mode=self.mode, reason="", samples=samples, notes=notes)


def _overlap_fraction(intervals: list[_Interval], b_start: float, b_end: float) -> float:
    width = b_end - b_start
    if width <= 0:
        return 0.0
    clipped = []
    for iv in intervals:
        s, e = max(iv.start, b_start), min(iv.end, b_end)
        if e > s:
            clipped.append((s, e))
    clipped.sort()
    covered = 0.0
    merged_end: float | None = None
    for s, e in clipped:
        if merged_end is None or s > merged_end:
            covered += e - s
            merged_end = e
        elif e > merged_end:
            covered += e - merged_end
            merged_end = e
    return min(covered / width, 1.0)
