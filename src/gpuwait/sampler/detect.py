"""Pick a sampler mode without ever prompting the user for a password.

Priority:
1. `powermetrics --samplers gpu_power`, macOS only, and only if `sudo -n true`
   succeeds non-interactively (meaning a password-less sudo rule is already
   in place). We never run bare `sudo`, which would block on a TTY prompt or
   hang in a non-interactive shell.
2. `nvidia-smi`, Linux (or anywhere the binary is on PATH), no privilege needed.
3. Ollama request-timing inference: works anywhere, needs no privilege, and
   is the honest fallback on a Mac without passwordless sudo, which is the
   common case.
"""

from __future__ import annotations

import platform
import shutil
import subprocess

MODES = ("powermetrics", "nvidia-smi", "ollama-timing")


def sudo_noninteractive_ok(runner=subprocess.run) -> bool:
    """True if `sudo -n true` succeeds. Never prompts: -n fails fast instead."""
    try:
        result = runner(
            ["sudo", "-n", "true"],
            capture_output=True,
            timeout=3,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return result.returncode == 0


def detect_mode(
    forced: str | None = None,
    *,
    system: str | None = None,
    which=shutil.which,
    sudo_check=sudo_noninteractive_ok,
) -> tuple[str, str]:
    """Return (mode, reason). `forced` skips detection entirely if valid."""
    if forced and forced != "auto":
        if forced not in MODES:
            raise ValueError(f"unknown sampler mode {forced!r}, choose from {', '.join(MODES)}")
        return forced, "forced with --sampler"

    system = system or platform.system()

    if system == "Darwin":
        if not which("powermetrics"):
            return "ollama-timing", "powermetrics binary not found, falling back to request timing"
        if sudo_check():
            return "powermetrics", "sudo -n true succeeded, powermetrics can run without a prompt"
        return (
            "ollama-timing",
            "no passwordless sudo for powermetrics, falling back to request-timing inference "
            "(run `sudo visudo` to add a NOPASSWD rule for powermetrics if you want hardware "
            "samples instead)",
        )

    if system == "Linux":
        if which("nvidia-smi"):
            return "nvidia-smi", "nvidia-smi found on PATH"
        return "ollama-timing", "no nvidia-smi on PATH, falling back to request-timing inference"

    return (
        "ollama-timing",
        f"no GPU sampler for platform {system!r}, using request-timing inference",
    )
