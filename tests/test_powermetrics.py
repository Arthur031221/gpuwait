"""powermetrics sampler test: the subprocess itself is mocked. We never spawn
a real `sudo powermetrics` in CI, there is no GPU there and no passwordless
sudo rule, and we should not depend on either."""

from __future__ import annotations

import asyncio

import pytest

from gpuwait.sampler.powermetrics import PowermetricsSampler


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
async def test_powermetrics_parses_active_residency(monkeypatch):
    lines = [
        b"*** Sampled system activity ***\n",
        b"GPU HW active residency:  12.50%\n",
        b"GPU HW active residency:  87.30%\n",
    ]
    fake_proc = _FakeProcess(lines)

    async def fake_create_subprocess_exec(*args, **kwargs):
        return fake_proc

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)

    sampler = PowermetricsSampler(interval_ms=100)
    async with sampler:
        await asyncio.sleep(0.05)
    result = sampler.result()
    assert result.mode == "powermetrics"
    assert [round(s.busy_pct, 2) for s in result.samples] == [12.5, 87.3]
    assert "GPU HW active residency" in result.notes[0]


@pytest.mark.asyncio
async def test_powermetrics_ignores_unrelated_lines(monkeypatch):
    lines = [b"some other powermetrics output\n", b"GPU HW active residency:   5.00%\n"]
    fake_proc = _FakeProcess(lines)

    async def fake_create_subprocess_exec(*args, **kwargs):
        return fake_proc

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)

    sampler = PowermetricsSampler()
    async with sampler:
        await asyncio.sleep(0.05)
    result = sampler.result()
    assert len(result.samples) == 1
    assert result.samples[0].busy_pct == 5.0
