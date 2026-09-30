"""Hardware sampler: `nvidia-smi` on Linux.

No special privilege needed. We spawn `nvidia-smi` once with `-l 1` (loop
every second) and parse `utilization.gpu` as a plain percentage per line.
"""

from __future__ import annotations

import asyncio
import contextlib
import time

from gpuwait.sampler.base import Sample, SamplerResult


class NvidiaSmiSampler:
    mode = "nvidia-smi"

    def __init__(self, interval_s: float = 1.0) -> None:
        self.interval_s = max(int(interval_s), 1)
        self._proc: asyncio.subprocess.Process | None = None
        self._reader_task: asyncio.Task | None = None
        self._samples: list[Sample] = []
        self._t0: float = 0.0

    def record_interval(self, start: float, end: float) -> None:
        pass  # hardware sampler ignores request timing entirely

    async def __aenter__(self) -> NvidiaSmiSampler:
        self._t0 = time.monotonic()
        self._proc = await asyncio.create_subprocess_exec(
            "nvidia-smi",
            "--query-gpu=utilization.gpu",
            "--format=csv,noheader,nounits",
            "-l",
            str(self.interval_s),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        self._reader_task = asyncio.create_task(self._read_loop())
        return self

    async def _read_loop(self) -> None:
        assert self._proc is not None and self._proc.stdout is not None
        async for raw in self._proc.stdout:
            line = raw.decode("utf-8", "ignore").strip()
            try:
                pct = float(line)
            except ValueError:
                continue
            self._samples.append(Sample(t=time.monotonic() - self._t0, busy_pct=pct))

    async def __aexit__(self, *exc) -> bool:
        if self._proc is not None:
            try:
                self._proc.terminate()
                await asyncio.wait_for(self._proc.wait(), timeout=2)
            except (ProcessLookupError, TimeoutError, asyncio.TimeoutError):
                if self._proc.returncode is None:
                    self._proc.kill()
        if self._reader_task is not None:
            self._reader_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._reader_task
        return False

    def result(self) -> SamplerResult:
        notes = ["sampled `nvidia-smi --query-gpu=utilization.gpu`, one reading per second"]
        return SamplerResult(mode=self.mode, reason="", samples=self._samples, notes=notes)
