"""Shared data model for every sampler mode.

Every sampler mode, however it gets its data, boils down to the same thing:
a series of (timestamp, gpu busy percent) points covering the test window.
The rest of the pipeline (scoring, timeline rendering, HTML, JSON) only
ever looks at that series plus a `mode` label and free-text `notes`.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Sample:
    """One point in time. `t` is seconds since the sampler started."""

    t: float
    busy_pct: float  # 0..100, GPU active residency (or its proxy) at this instant


@dataclass
class SamplerResult:
    mode: str  # "powermetrics" | "ollama-timing" | "nvidia-smi"
    reason: str  # why this mode was picked
    samples: list[Sample] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "mode": self.mode,
            "reason": self.reason,
            "samples": [{"t": s.t, "busy_pct": s.busy_pct} for s in self.samples],
            "notes": self.notes,
        }
