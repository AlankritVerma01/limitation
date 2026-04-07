from __future__ import annotations

from pathlib import Path

from interaction_harness.cli import main
from interaction_harness.domains.recommender import ensure_reference_artifacts


def test_demo_audit_flow_surfaces_risky_and_healthy_cohorts(tmp_path: Path) -> None:
    artifact_dir = tmp_path / "reference-artifacts"
    ensure_reference_artifacts(artifact_dir)

    result = main(
        [
            "audit",
            "--domain",
            "recommender",
            "--seed",
            "7",
            "--reference-artifact-dir",
            str(artifact_dir),
            "--output-dir",
            str(tmp_path / "demo-audit"),
        ]
    )

    report = Path(str(result["report_path"])).read_text(encoding="utf-8")
    assert "## Executive Summary" in report
    assert "## Launch Risks" in report
    assert "## Representative Traces To Inspect" in report
    assert "Main concern:" in report
    assert "Strongest cohort:" in report
    assert "trust_collapse" in report


def test_demo_compare_flow_writes_buyer_readable_regression_summary(tmp_path: Path) -> None:
    baseline_dir = tmp_path / "baseline"
    candidate_dir = tmp_path / "candidate"
    ensure_reference_artifacts(baseline_dir)
    ensure_reference_artifacts(candidate_dir)

    result = main(
        [
            "compare",
            "--domain",
            "recommender",
            "--baseline-artifact-dir",
            str(baseline_dir),
            "--candidate-artifact-dir",
            str(candidate_dir),
            "--baseline-label",
            "current-prod",
            "--candidate-label",
            "current-prod-copy",
            "--rerun-count",
            "2",
            "--output-dir",
            str(tmp_path / "demo-compare"),
        ]
    )

    report = Path(str(result["regression_report_path"])).read_text(encoding="utf-8")
    assert "## Decision" in report
    assert "## Executive Summary" in report
    assert "## Most Important Changes" in report
    assert "Comparison: `current-prod` -> `current-prod-copy`" in report
    assert "Overall direction:" in report
