from __future__ import annotations

from gpuwait.prompts import build_prompt


def test_build_prompt_roughly_matches_target_tokens():
    prompt = build_prompt(128)
    words = prompt.split()
    # 0.75 words/token rule of thumb, allow slack for the trailing instruction sentence
    assert 80 <= len(words) <= 110


def test_build_prompt_minimum_length():
    prompt = build_prompt(0)
    assert len(prompt.split()) >= 4


def test_build_prompt_is_deterministic():
    assert build_prompt(64) == build_prompt(64)
