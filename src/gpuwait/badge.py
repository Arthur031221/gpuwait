"""A tiny, dependency-free flat badge SVG generator.

We do not call out to shields.io: the whole point of this tool is a report
that works offline against your own server, so the badge should not need a
network round trip either. The width math is an approximation of Verdana
11px metrics, the same convention shields.io badges use, it will not kern
perfectly but it will never clip text.
"""

from __future__ import annotations

_CHAR_WIDTH_PX = 6.5
_PAD_PX = 10


def _text_width(s: str) -> int:
    return max(round(len(s) * _CHAR_WIDTH_PX) + _PAD_PX, 10)


def _color_for_idle(idle_percent: float) -> str:
    """Color is informational, not a pass/fail signal.

    A high idle percent at low concurrency is normal, so this is not a
    red/green gauge. It is a small visual cue for where a number sits on
    the 0-100 scale, always paired with the printed percentage.
    """
    if idle_percent >= 60:
        return "#6d28d9"
    if idle_percent >= 25:
        return "#2563eb"
    return "#059669"


def render_badge_svg(label: str, value: str, idle_percent: float) -> str:
    color = _color_for_idle(idle_percent)
    label_w = _text_width(label)
    value_w = _text_width(value)
    total_w = label_w + value_w
    label_x = label_w / 2
    value_x = label_w + value_w / 2
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{total_w}" height="20" \
role="img" aria-label="{label}: {value}">
  <linearGradient id="s" x2="0" y2="100%">
    <stop offset="0" stop-color="#bbb" stop-opacity=".1"/>
    <stop offset="1" stop-opacity=".1"/>
  </linearGradient>
  <clipPath id="r"><rect width="{total_w}" height="20" rx="3" fill="#fff"/></clipPath>
  <g clip-path="url(#r)">
    <rect width="{label_w}" height="20" fill="#555"/>
    <rect x="{label_w}" width="{value_w}" height="20" fill="{color}"/>
    <rect width="{total_w}" height="20" fill="url(#s)"/>
  </g>
  <g fill="#fff" text-anchor="middle" font-family="Verdana,Geneva,sans-serif" font-size="11">
    <text x="{label_x}" y="14">{label}</text>
    <text x="{value_x}" y="14">{value}</text>
  </g>
</svg>"""
