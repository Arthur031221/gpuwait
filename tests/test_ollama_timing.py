from __future__ import annotations

import asyncio

import httpx
import pytest

from gpuwait.sampler.ollama_timing import OllamaTimingSampler, _Interval, _overlap_fraction


def test_overlap_fraction_no_overlap():
    intervals = [_Interval(0.0, 0.2)]
    assert _overlap_fraction(intervals, 1.0, 2.0) == 0.0


def test_overlap_fraction_full_bucket():
    intervals = [_Interval(0.0, 5.0)]
    assert _overlap_fraction(intervals, 1.0, 2.0) == 1.0


def test_overlap_fraction_partial():
    intervals = [_Interval(0.5, 1.0)]
    # bucket [0, 1), interval covers [0.5, 1.0) -> half
    assert _overlap_fraction(intervals, 0.0, 1.0) == pytest.approx(0.5)


def test_overlap_fraction_merges_overlapping_intervals():
    intervals = [_Interval(0.0, 0.6), _Interval(0.4, 1.0)]
    # union covers the whole [0, 1) bucket even though the two overlap
    assert _overlap_fraction(intervals, 0.0, 1.0) == pytest.approx(1.0)


def _offline_client_factory(**kwargs):
    # a transport with nothing behind it: every request fails fast and locally
    return httpx.AsyncClient(
        transport=httpx.MockTransport(lambda r: (_ for _ in ()).throw(httpx.ConnectError("down")))
    )


@pytest.mark.asyncio
async def test_sampler_buckets_recorded_intervals():
    sampler = OllamaTimingSampler(
        base_url="http://127.0.0.1:1",
        model="m",
        bucket_s=0.5,
        http_client_factory=_offline_client_factory,
    )
    async with sampler:
        t0 = sampler._t0
        sampler.record_interval(t0 + 0.0, t0 + 1.0)  # busy for buckets 0 and 1
        await asyncio.sleep(1.1)
    result = sampler.result()
    assert result.mode == "ollama-timing"
    assert len(result.samples) >= 2
    assert result.samples[0].busy_pct == pytest.approx(100.0)
    assert any(s.busy_pct == 0.0 for s in result.samples)


@pytest.mark.asyncio
async def test_sampler_notes_mention_the_proxy_limitation():
    sampler = OllamaTimingSampler(
        base_url="http://127.0.0.1:1", http_client_factory=_offline_client_factory, ps_poll_s=100
    )
    async with sampler:
        await asyncio.sleep(0.05)
    result = sampler.result()
    assert any("outstanding" in n for n in result.notes)
