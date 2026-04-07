from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from interaction_harness.cli import main
from interaction_harness.domains.recommender import ensure_reference_artifacts


def test_main_without_args_defaults_to_audit_command(tmp_path: Path) -> None:
    artifact_dir = tmp_path / "artifacts"
    ensure_reference_artifacts(artifact_dir)
    with patch(
        "interaction_harness.cli.run_recommender_audit",
        return_value={
            "report_path": str(tmp_path / "report.md"),
            "results_path": str(tmp_path / "results.json"),
            "traces_path": str(tmp_path / "traces.jsonl"),
            "chart_path": str(tmp_path / "chart.svg"),
        },
    ) as mock_audit:
        main([])

    assert mock_audit.call_count == 1


def test_audit_progress_and_summary_are_visible(
    tmp_path: Path,
    capsys,
) -> None:
    artifact_dir = tmp_path / "artifacts"
    ensure_reference_artifacts(artifact_dir)

    result = main(
        [
            "audit",
            "--seed",
            "7",
            "--reference-artifact-dir",
            str(artifact_dir),
            "--output-dir",
            str(tmp_path / "audit"),
        ]
    )

    captured = capsys.readouterr()
    assert "Resolving scenarios and population" in captured.err
    assert "Running traces" in captured.err
    assert "Writing artifacts" in captured.err
    assert "Audit complete:" in captured.out
    assert Path(str(result["report_path"])).exists()


def test_compare_progress_and_summary_are_visible(
    tmp_path: Path,
    capsys,
) -> None:
    baseline_dir = tmp_path / "baseline"
    candidate_dir = tmp_path / "candidate"
    ensure_reference_artifacts(baseline_dir)
    ensure_reference_artifacts(candidate_dir)

    result = main(
        [
            "compare",
            "--baseline-artifact-dir",
            str(baseline_dir),
            "--candidate-artifact-dir",
            str(candidate_dir),
            "--rerun-count",
            "1",
            "--output-dir",
            str(tmp_path / "compare"),
        ]
    )

    captured = capsys.readouterr()
    assert "Running baseline reruns" in captured.err
    assert "Running candidate reruns" in captured.err
    assert "Compare complete:" in captured.out
    assert result["decision_status"] == "pass"


def test_generation_command_shows_progress_and_summary(
    tmp_path: Path,
    capsys,
) -> None:
    result = main(
        [
            "generate-scenarios",
            "--mode",
            "fixture",
            "--brief",
            "test novelty balance for sparse-history users",
            "--output-dir",
            str(tmp_path),
        ]
    )

    captured = capsys.readouterr()
    assert "Generating scenario candidates" in captured.err
    assert "Writing scenario pack" in captured.err
    assert "Scenario generation complete:" in captured.out
    assert Path(str(result["scenario_pack_path"])).exists()


def test_serve_reference_reports_ready_url(tmp_path: Path, capsys) -> None:
    artifact_dir = tmp_path / "reference-artifacts"

    with patch("interaction_harness.cli._wait_for_interrupt", return_value=None):
        result = main(["serve-reference", "--artifact-dir", str(artifact_dir)])

    captured = capsys.readouterr()
    assert "Preparing reference artifacts" in captured.err
    assert "Reference service ready" in captured.out
    assert str(result["base_url"]).startswith("http://127.0.0.1:")
