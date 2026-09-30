"""Load generator: replays a synthetic concurrent request trace.

Each concurrency level runs N independent "worker" loops for a fixed wall
clock duration. Each worker sends a chat completion request, waits for the
full response, then pauses for `think_time_s` before sending the next one.
That think-time pause is what makes concurrency 1 produce a nonzero idle
score in the first place: a single user reading a reply before typing the
next question is exactly the gap a hardware GPU sampler would also see as
idle. At higher concurrency, more independent workers are pausing and
requesting at staggered, uncorrelated times, so the chance that all of them
are paused at once drops fast and the measured idle percentage drops with it.
See the README for the full explanation, this is workload shape, not a
broken server.
"""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field

import httpx

from gpuwait.prompts import build_prompt
from gpuwait.sampler.base import SamplerResult
from gpuwait.sampler.runner import make_sampler


@dataclass
class RequestResult:
    start: float
    end: float
    ok: bool
    ttft: float | None
    output_tokens: int
    error: str | None = None

    @property
    def latency_s(self) -> float:
        return self.end - self.start


@dataclass
class LevelResult:
    concurrency: int
    duration_s: float
    think_time_s: float
    prompt_tokens: int
    max_tokens: int
    stream: bool
    requests: list[RequestResult] = field(default_factory=list)
    sampler_result: SamplerResult | None = None

    @property
    def completed(self) -> list[RequestResult]:
        return [r for r in self.requests if r.ok]

    @property
    def failed(self) -> list[RequestResult]:
        return [r for r in self.requests if not r.ok]


class RequestFailed(Exception):
    pass


async def send_chat_request(
    client: httpx.AsyncClient,
    url: str,
    model: str,
    prompt: str,
    max_tokens: int,
    stream: bool,
) -> tuple[float | None, int]:
    """POST one chat completion. Returns (time_to_first_token, output_tokens)."""
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "stream": stream,
    }
    if stream:
        return await _send_streaming(client, url, payload)
    resp = await client.post(url, json=payload)
    resp.raise_for_status()
    body = resp.json()
    usage = body.get("usage") or {}
    tokens = usage.get("completion_tokens")
    if tokens is None:
        choices = body.get("choices") or [{}]
        content = (choices[0].get("message") or {}).get("content", "")
        tokens = max(len(content.split()), 1)
    return None, int(tokens)


async def _send_streaming(
    client: httpx.AsyncClient, url: str, payload: dict
) -> tuple[float | None, int]:
    t_start = time.monotonic()
    ttft: float | None = None
    chunk_count = 0
    last_usage: dict | None = None
    async with client.stream("POST", url, json=payload) as resp:
        resp.raise_for_status()
        async for line in resp.aiter_lines():
            if not line or not line.startswith("data:"):
                continue
            data = line[len("data:") :].strip()
            if data == "[DONE]":
                break
            try:
                obj = json.loads(data)
            except json.JSONDecodeError:
                continue
            usage = obj.get("usage")
            if usage:
                last_usage = usage
            choices = obj.get("choices") or []
            if choices:
                delta = choices[0].get("delta") or {}
                # A reasoning model (Qwen3 in thinking mode, among others) streams its
                # thinking as delta.reasoning with delta.content held at "" until the
                # visible answer starts, sometimes for the entire response if max_tokens
                # is reached first. Reasoning tokens are still real GPU work, so we count
                # them the same as content tokens for time-to-first-token and the
                # chunk-count throughput proxy, instead of reporting a false zero.
                if delta.get("content") or delta.get("reasoning"):
                    if ttft is None:
                        ttft = time.monotonic() - t_start
                    chunk_count += 1
    if last_usage and last_usage.get("completion_tokens") is not None:
        return ttft, int(last_usage["completion_tokens"])
    return ttft, max(chunk_count, 1 if ttft is not None else 0)


async def _run_worker(
    client: httpx.AsyncClient,
    url: str,
    model: str,
    prompt: str,
    max_tokens: int,
    stream: bool,
    think_time_s: float,
    end_time: float,
    sampler,
    results: list[RequestResult],
    lock: asyncio.Lock,
) -> None:
    while time.monotonic() < end_time:
        start = time.monotonic()
        try:
            ttft, tokens = await send_chat_request(client, url, model, prompt, max_tokens, stream)
            ok, err = True, None
        except (httpx.HTTPError, asyncio.TimeoutError, RequestFailed) as exc:
            ttft, tokens = None, 0
            ok, err = False, str(exc)
        end = time.monotonic()
        result = RequestResult(
            start=start, end=end, ok=ok, ttft=ttft, output_tokens=tokens, error=err
        )
        async with lock:
            results.append(result)
        sampler.record_interval(start, end)
        remaining = end_time - time.monotonic()
        if remaining <= 0:
            break
        await asyncio.sleep(min(think_time_s, remaining))


async def run_level(
    *,
    base_url: str,
    model: str,
    concurrency: int,
    duration_s: float,
    think_time_s: float,
    prompt_tokens: int,
    max_tokens: int,
    stream: bool,
    sampler_mode: str,
    sampler_reason: str = "",
    http_timeout_s: float = 60.0,
    client_factory=httpx.AsyncClient,
) -> LevelResult:
    url = f"{base_url.rstrip('/')}/v1/chat/completions"
    prompt = build_prompt(prompt_tokens)
    sampler = make_sampler(sampler_mode, base_url=base_url, model=model)
    results: list[RequestResult] = []
    lock = asyncio.Lock()
    start_time = time.monotonic()
    async with sampler, client_factory(timeout=http_timeout_s) as client:
        end_time = time.monotonic() + duration_s
        workers = [
            _run_worker(
                client,
                url,
                model,
                prompt,
                max_tokens,
                stream,
                think_time_s,
                end_time,
                sampler,
                results,
                lock,
            )
            for _ in range(concurrency)
        ]
        await asyncio.gather(*workers)
    actual_duration_s = time.monotonic() - start_time
    sampler_result = sampler.result()
    if not sampler_result.reason:
        sampler_result.reason = sampler_reason
    return LevelResult(
        concurrency=concurrency,
        duration_s=actual_duration_s,
        think_time_s=think_time_s,
        prompt_tokens=prompt_tokens,
        max_tokens=max_tokens,
        stream=stream,
        requests=results,
        sampler_result=sampler_result,
    )
