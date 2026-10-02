"""Tests for the chat completion stream parser in load.py.

These cover the OpenAI-compatible SSE format for both a plain content stream
and a reasoning model's stream, where a "thinking" model such as Qwen3 sends
its thinking as delta.reasoning while delta.content stays "" (sometimes for
the whole response, if max_tokens is reached before the visible answer
starts). This is the real shape Ollama serves for qwen3:4b, confirmed against
a live server while building this test.
"""

from __future__ import annotations

import json

import httpx
import pytest

from gpuwait.load import send_chat_request


def _sse(*chunks: dict) -> bytes:
    body = b""
    for chunk in chunks:
        body += f"data: {json.dumps(chunk)}\n\n".encode()
    body += b"data: [DONE]\n\n"
    return body


@pytest.mark.parametrize("stream", [True, False])
async def test_plain_content_stream_counts_tokens(stream: bool):
    if stream:
        body = _sse(
            {"choices": [{"delta": {"role": "assistant", "content": ""}}]},
            {"choices": [{"delta": {"content": "hi"}}]},
            {"choices": [{"delta": {"content": " there"}}]},
            {"choices": [{"delta": {}, "finish_reason": "stop"}]},
        )

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, content=body)
    else:

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "choices": [{"message": {"role": "assistant", "content": "hi there"}}],
                    "usage": {"completion_tokens": 2},
                },
            )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        ttft, tokens = await send_chat_request(
            client, "http://mock/v1/chat/completions", "m", "prompt", 32, stream
        )

    assert tokens >= 2
    if stream:
        assert ttft is not None


async def test_reasoning_only_stream_is_not_reported_as_zero_tokens():
    """Regression test: a reasoning model whose visible content stays empty
    for the whole response (max_tokens reached mid-thought) must still be
    counted as having produced output, not reported as zero-token, zero-ttft.
    """
    body = _sse(
        {"choices": [{"delta": {"role": "assistant", "content": "", "reasoning": "We"}}]},
        {"choices": [{"delta": {"content": "", "reasoning": " should"}}]},
        {"choices": [{"delta": {"content": "", "reasoning": " think"}}]},
        {"choices": [{"delta": {}, "finish_reason": "length"}]},
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=body)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        ttft, tokens = await send_chat_request(
            client, "http://mock/v1/chat/completions", "m", "prompt", 32, True
        )

    assert ttft is not None
    assert tokens == 3


async def test_legacy_vllm_reasoning_content_stream_counts_tokens():
    body = _sse(
        {"choices": [{"delta": {"reasoning_content": "We should"}}]},
        {"choices": [{"delta": {"reasoning_content": " think"}}]},
        {"choices": [{"delta": {}, "finish_reason": "length"}]},
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=body)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        ttft, tokens = await send_chat_request(
            client, "http://mock/v1/chat/completions", "m", "prompt", 32, True
        )

    assert ttft is not None
    assert tokens == 2


async def test_streaming_usage_in_final_chunk_overrides_chunk_count():
    body = _sse(
        {"choices": [{"delta": {"content": "a"}}]},
        {
            "choices": [{"delta": {}, "finish_reason": "stop"}],
            "usage": {"completion_tokens": 41},
        },
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=body)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        _ttft, tokens = await send_chat_request(
            client, "http://mock/v1/chat/completions", "m", "prompt", 32, True
        )

    assert tokens == 41


async def test_non_streaming_reasoning_model_uses_usage_not_empty_content():
    """Matches a live Ollama response for a Qwen3 thinking model: message.content
    is "" and the answer lives in message.reasoning, but usage.completion_tokens
    is still accurate and must win over counting words in the empty content."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [
                    {"message": {"role": "assistant", "content": "", "reasoning": "Hmm..."}}
                ],
                "usage": {"prompt_tokens": 16, "completion_tokens": 40, "total_tokens": 56},
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        ttft, tokens = await send_chat_request(
            client, "http://mock/v1/chat/completions", "m", "prompt", 40, False
        )

    assert ttft is None  # non-streaming never has a meaningful time-to-first-token
    assert tokens == 40
