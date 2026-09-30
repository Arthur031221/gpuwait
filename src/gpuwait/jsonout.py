"""Serialize a BenchmarkResult to a JSON-safe dict for `--json`."""

from __future__ import annotations

from datetime import UTC, datetime

from gpuwait import __version__
from gpuwait.score import BenchmarkResult


def to_json_dict(result: BenchmarkResult) -> dict:
    return {
        "tool": "gpuwait",
        "version": __version__,
        "generated_at": datetime.now(UTC).isoformat(),
        "target": result.target,
        "model": result.model,
        "headline_idle_percent": result.headline_idle_percent,
        "levels": [lvl.to_dict() for lvl in result.levels],
    }
