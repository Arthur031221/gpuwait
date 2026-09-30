from __future__ import annotations

import xml.etree.ElementTree as ET

from gpuwait.badge import render_badge_svg


def test_badge_is_valid_xml_and_contains_text():
    svg = render_badge_svg("gpu idle", "42.0%", 42.0)
    root = ET.fromstring(svg)  # raises if not well-formed XML
    assert root.tag.endswith("svg")
    assert "42.0%" in svg
    assert "gpu idle" in svg


def test_badge_color_bands():
    low = render_badge_svg("gpu idle", "5%", 5.0)
    mid = render_badge_svg("gpu idle", "40%", 40.0)
    high = render_badge_svg("gpu idle", "80%", 80.0)
    assert "#059669" in low
    assert "#2563eb" in mid
    assert "#6d28d9" in high


def test_badge_width_grows_with_label_length():
    short = render_badge_svg("a", "1%", 1.0)
    long = render_badge_svg("a much longer label", "1%", 1.0)
    assert 'width="' in short and 'width="' in long
