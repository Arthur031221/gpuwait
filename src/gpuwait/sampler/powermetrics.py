"""Hardware sampler: `powermetrics --samplers gpu_power` on macOS.

Only used when `sudo -n true` already succeeds without a prompt (see
`detect.py`). We spawn `powermetrics` once for the whole level and parse its
streaming stdout for the "GPU HW active residency" line, which is the
percentage of the sampling window the GPU was actually doing work. That is a
real hardware measurement, unlike the request-timing fallback.
"""

from __future__ import annotations

import asyncio
import contextlib
import re
import time

from gpuwait.sampler.base import Sample, SamplerResult

_RESIDENCY_RE = re.compile(r"GPU HW active residency:\s+([\d.]+)%")


class PowermetricsSampler:
    mode = "powermetrics"

    def __init__(self, interval_ms: int = 1000) -> None:
        self.interval_ms = interval_ms
        self._proc: asyncio.subprocess.Process | None = None
        self._reader_task: asyncio.Task | None = None
        self._samples: list[Sample] = []
        self._t0: float = 0.0

    def record_interval(self, start: float, end: float) -> None:
        pass  # hardware sampler ignores request timing entirely

    async def __aenter__(self) -> PowermetricsSampler:
        self._t0 = time.monotonic()
        self._proc = await asyncio.create_subprocess_exec(
            "sudo",
            "-n",
            "powermetrics",
            "--samplers",
            "gpu_power",
            "-i",
            str(self.interval_ms),
            "-n",
            "0",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        self._reader_task = asyncio.create_task(self._read_loop())
        return self

    async def _read_loop(self) -> None:
        assert self._proc is not None and self._proc.stdout is not None
        async for raw in self._proc.stdout:
            line = raw.decode("utf-8", "ignore")
            match = _RESIDENCY_RE.search(line)
            if match:
                pct = float(match.group(1))
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
        notes = [
            "sampled `powermetrics --samplers gpu_power`, GPU HW active residency percent per sample"
        ]
        return SamplerResult(mode=self.mode, reason="", samples=self._samples, notes=notes)
