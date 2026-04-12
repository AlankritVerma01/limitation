"""Report writer interface for artifact rendering."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Protocol

from ..schema import RegressionDiff, RunResult


class ReportWriter(Protocol):
    """Writes artifacts from precomputed run results only."""

    def write(self, run_result: RunResult, output_dir: Path) -> dict[str, str]: ...


@dataclass(frozen=True)
class ReportBulletSection:
    """Structured bullet-section definition for shared report rendering."""

    title: str
    bullets: tuple[str, ...]


@dataclass(frozen=True)
class ReportTableSection:
    """Structured table-section definition for shared report rendering."""

    title: str
    columns: tuple[str, ...]
    rows: tuple[tuple[str, ...], ...]


@dataclass(frozen=True)
class DomainReportingHooks:
    """Optional domain-supplied report semantics for the shared artifact pipeline."""

    build_scenario_coverage_section: Callable[[RunResult], ReportBulletSection] | None = None
    build_cohort_summary_section: Callable[[RunResult], ReportTableSection] | None = None
    build_trace_score_section: Callable[[RunResult], ReportTableSection] | None = None
    build_metadata_highlights_section: Callable[[RunResult], ReportBulletSection] | None = None
    build_run_summary_fields: Callable[[RunResult], dict[str, object]] | None = None
    build_regression_cohort_change_section: Callable[[RegressionDiff], ReportTableSection] | None = None
    build_regression_risk_change_section: Callable[[RegressionDiff], ReportBulletSection] | None = None
    build_regression_slice_change_section: Callable[
        [RegressionDiff], ReportTableSection | ReportBulletSection
    ] | None = None
    build_regression_trace_change_section: Callable[[RegressionDiff], ReportTableSection] | None = None
