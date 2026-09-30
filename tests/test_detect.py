from __future__ import annotations

import subprocess

import pytest

from gpuwait.sampler.detect import detect_mode, sudo_noninteractive_ok


def _runner_ok(*a, **k):
    return subprocess.CompletedProcess(a, returncode=0)


def _runner_fail(*a, **k):
    return subprocess.CompletedProcess(a, returncode=1)


def _runner_raises(*a, **k):
    raise OSError("no sudo binary")


def test_sudo_noninteractive_ok_true():
    assert sudo_noninteractive_ok(runner=_runner_ok) is True


def test_sudo_noninteractive_ok_false_on_nonzero():
    assert sudo_noninteractive_ok(runner=_runner_fail) is False


def test_sudo_noninteractive_ok_false_on_error():
    assert sudo_noninteractive_ok(runner=_runner_raises) is False


def test_detect_mode_forced():
    mode, reason = detect_mode("nvidia-smi")
    assert mode == "nvidia-smi"
    assert "forced" in reason


def test_detect_mode_forced_invalid():
    with pytest.raises(ValueError):
        detect_mode("not-a-real-mode")


def test_detect_mode_darwin_with_sudo():
    mode, reason = detect_mode(
        None, system="Darwin", which=lambda name: "/usr/bin/powermetrics", sudo_check=lambda: True
    )
    assert mode == "powermetrics"
    assert "sudo -n true" in reason


def test_detect_mode_darwin_without_sudo():
    mode, reason = detect_mode(
        None, system="Darwin", which=lambda name: "/usr/bin/powermetrics", sudo_check=lambda: False
    )
    assert mode == "ollama-timing"
    assert "no passwordless sudo" in reason


def test_detect_mode_darwin_no_powermetrics_binary():
    mode, reason = detect_mode(
        None, system="Darwin", which=lambda name: None, sudo_check=lambda: True
    )
    assert mode == "ollama-timing"
    assert "not found" in reason


def test_detect_mode_linux_with_nvidia_smi():
    mode, _reason = detect_mode(None, system="Linux", which=lambda name: "/usr/bin/nvidia-smi")
    assert mode == "nvidia-smi"


def test_detect_mode_linux_without_nvidia_smi():
    mode, _reason = detect_mode(None, system="Linux", which=lambda name: None)
    assert mode == "ollama-timing"


def test_detect_mode_other_platform():
    mode, reason = detect_mode(None, system="Windows")
    assert mode == "ollama-timing"
    assert "Windows" in reason
