"""Factory that turns a sampler mode name into a sampler instance."""

from __future__ import annotations

from typing import Protocol

from gpuwait.sampler.base import SamplerResult
from gpuwait.sampler.nvidia_smi import NvidiaSmiSampler
from gpuwait.sampler.ollama_timing import OllamaTimingSampler
from gpuwait.sampler.powermetrics import PowermetricsSampler


class Sampler(Protocol):
    mode: str

    def record_interval(self, start: float, end: float) -> None: ...
    async def __aenter__(self) -> Sampler: ...
    async def __aexit__(self, *exc) -> bool: ...
    def result(self) -> SamplerResult: ...


def make_sampler(mode: str, *, base_url: str, model: str | None) -> Sampler:
    if mode == "powermetrics":
        return PowermetricsSampler()
    if mode == "nvidia-smi":
        return NvidiaSmiSampler()
    if mode == "ollama-timing":
        return OllamaTimingSampler(base_url=base_url, model=model)
    raise ValueError(f"unknown sampler mode {mode!r}")
