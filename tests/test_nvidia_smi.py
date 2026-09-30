"""nvidia-smi sampler test: the subprocess is mocked, this machine has no
NVIDIA GPU and CI runners for this project do not either."""

from __future__ import annotations

import asyncio

import pytest

from gpuwait.sampler.nvidia_smi import NvidiaSmiSampler


class _FakeStdout:
    def __init__(self, lines: list[bytes]):
        self._lines = lines

    def __aiter__(self):
        return self

    async def __anext__(self):
        if not self._lines:
            raise StopAsyncIteration
        await asyncio.sleep(0)
        return self._lines.pop(0)


class _FakeProcess:
    def __init__(self, lines: list[bytes]):
        self.stdout = _FakeStdout(lines)
        self.returncode = None

    def terminate(self):
        self.returncode = 0

    async def wait(self):
        return 0

    def kill(self):
        self.returncode = -9


@pytest.mark.asyncio
async def test_nvidia_smi_parses_utilization(monkeypatch):
    lines = [b"0\n", b"73\n", b"not-a-number\n", b"100\n"]
    fake_proc = _FakeProcess(lines)

    async def fake_create_subprocess_exec(*args, **kwargs):
        return fake_proc

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)

    sampler = NvidiaSmiSampler(interval_s=1)
    async with sampler:
        await asyncio.sleep(0.05)
    result = sampler.result()
    assert result.mode == "nvidia-smi"
    assert [s.busy_pct for s in result.samples] == [0.0, 73.0, 100.0]
