from __future__ import annotations

import socket
from pathlib import Path
from unittest.mock import patch

import pytest
from evidpath.cli import main
from evidpath.domains.recommender import ensure_reference_artifacts


def test_main_without_args_prints_help_instead_of_assuming_a_domain(capsys) -> None:
    with pytest.raises(SystemExit) as exc_info:
        main([])

    captured = capsys.readouterr()
    assert exc_info.value.code == 0
    assert "usage:" in captured.out
    assert "audit --domain recommender" in captured.out


def test_audit_progress_and_summary_are_visible(
    tmp_path: Path,
    capsys,
) -> None:
    artifact_dir = tmp_path / "artifacts"
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
            str(tmp_path / "audit"),
        ]
    )

    captured = capsys.readouterr()
    assert "Resolving scenarios and population" in captured.err
    assert "Running traces" in captured.err
    assert "Writing artifacts" in captured.err
    assert "Audit complete:" in captured.out
    assert Path(str(result["report_path"])).exists()


def test_serve_reference_reports_ready_url(tmp_path: Path, capsys) -> None:
    artifact_dir = tmp_path / "reference-artifacts"
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        explicit_port = probe.getsockname()[1]

    with patch("evidpath.cli_app.handlers.wait_for_interrupt", return_value=None):
        result = main(
            [
                "serve-reference",
                "--domain",
                "recommender",
                "--artifact-dir",
                str(artifact_dir),
                "--host",
                "127.0.0.1",
                "--port",
                str(explicit_port),
            ]
        )

    captured = capsys.readouterr()
    assert "Preparing reference artifacts" in captured.err
    assert "Reference service ready" in captured.out
    assert "Health URL" in captured.out
    assert str(result["base_url"]) == f"http://127.0.0.1:{explicit_port}"


def test_public_cli_domain_choices_hide_stub(capsys) -> None:
    try:
        main(["audit", "--domain", "stub"])
    except SystemExit as exc:
        assert exc.code == 2
    else:
        raise AssertionError(
            "Expected non-public stub domain to be rejected by the CLI."
        )

    with patch("evidpath.cli_app.handlers.wait_for_interrupt", return_value=None):
        try:
            main(["--help"])
        except SystemExit:
            pass
    captured = capsys.readouterr()
    assert "stub" not in captured.out


def test_search_domain_is_available_through_cli_audit(tmp_path: Path, capsys) -> None:
    result = main(
        [
            "audit",
            "--domain",
            "search",
            "--seed",
            "7",
            "--scenario",
            "navigational-query",
            "--output-dir",
            str(tmp_path / "search-audit"),
        ]
    )

    captured = capsys.readouterr()
    assert "Audit complete:" in captured.out
    assert "reference_search" in captured.out
    assert Path(str(result["report_path"])).exists()
