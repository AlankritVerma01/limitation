"""Report writer interface for artifact rendering."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from ..schema import RunResult


class ReportWriter(Protocol):
    """Writes artifacts from precomputed run results only."""

    def write(self, run_result: RunResult, output_dir: Path) -> dict[str, str]: ...
