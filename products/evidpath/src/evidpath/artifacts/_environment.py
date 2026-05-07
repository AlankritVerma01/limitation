"""Environment fingerprint helpers for run manifests."""

from __future__ import annotations

import platform
import subprocess
import sys
from importlib.metadata import PackageNotFoundError, version


def collect_environment_fingerprint(
    *,
    cli_invocation: list[str] | None = None,
) -> dict[str, str]:
    """Collect a deterministic fingerprint of the runtime environment."""
    return {
        "evidpath_version": _evidpath_version(),
        "python_version": _python_version(),
        "platform": _platform_descriptor(),
        "git_sha": _git_sha(),
        "cli_invocation": _format_cli_invocation(cli_invocation or sys.argv),
    }


def _evidpath_version() -> str:
    try:
        return version("evidpath")
    except PackageNotFoundError:
        return "unknown"


def _python_version() -> str:
    return sys.version.split()[0]


def _platform_descriptor() -> str:
    return f"{platform.system().lower()}-{platform.machine().lower()}"


def _git_sha() -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            check=False,
            capture_output=True,
            text=True,
            timeout=2.0,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return ""
    if result.returncode != 0:
        return ""
    return result.stdout.strip()


def _format_cli_invocation(argv: list[str]) -> str:
    if not argv:
        return ""
    parts = list(argv)
    if parts and parts[0]:
        parts[0] = parts[0].rsplit("/", 1)[-1]
    return " ".join(parts)
