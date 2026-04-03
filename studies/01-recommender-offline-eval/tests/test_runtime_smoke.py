from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

from recommender_offline_eval.canonical import CANONICAL_RUN_CONFIG
from recommender_offline_eval.config import load_evaluation_config
from recommender_offline_eval.report import CHART_FILENAME, artifact_filenames
from recommender_offline_eval.run_demo import main, run_canonical_demo, run_evaluation

run_demo_module = importlib.import_module("recommender_offline_eval.run_demo")

EXAMPLES_ROOT = Path(__file__).resolve().parents[1] / "examples"
CANONICAL_ARTIFACTS_ROOT = (
    Path(__file__).resolve().parents[1] / "artifacts" / "canonical"
)


def _section_headings(markdown: str) -> list[str]:
    return [line for line in markdown.splitlines() if line.startswith("## ")]


def test_canonical_pipeline_outputs_are_stable(tmp_path: Path) -> None:
    first_output = tmp_path / "run-a"
    second_output = tmp_path / "run-b"
    filenames = artifact_filenames(CANONICAL_RUN_CONFIG)

    first_result = run_canonical_demo(output_dir=first_output)
    run_canonical_demo(output_dir=second_output)

    first_json = json.loads((first_output / filenames["json"]).read_text())
    second_json = json.loads((second_output / filenames["json"]).read_text())
    assert list(first_json.keys()) == [
        "run_summary",
        "offline_metrics",
        "bucket_utility",
        "behavioral_diagnostics",
        "key_takeaways",
        "trace_examples",
        "reproducibility",
    ]
    assert first_json == second_json

    first_report = (first_output / filenames["report"]).read_text()
    second_report = (second_output / filenames["report"]).read_text()
    assert first_report == second_report
    assert _section_headings(first_report) == [
        "## Run summary",
        "## Standard offline metrics",
        "## Bucket-level utility",
        "## Behavioral diagnostics",
        "## Key takeaways",
        "## Short traces",
        "## Reproducibility note",
    ]

    first_chart = (first_output / CHART_FILENAME).read_text()
    second_chart = (second_output / CHART_FILENAME).read_text()
    assert first_chart == second_chart
    assert first_json == json.loads(
        (CANONICAL_ARTIFACTS_ROOT / filenames["json"]).read_text()
    )
    assert first_report == (CANONICAL_ARTIFACTS_ROOT / filenames["report"]).read_text()
    assert first_chart == (CANONICAL_ARTIFACTS_ROOT / CHART_FILENAME).read_text()

    assert first_result["report_path"].name == filenames["report"]
    assert first_result["metrics_path"].name == filenames["json"]
    assert first_result["chart_path"].name == CHART_FILENAME

    offline_rows = first_json["offline_metrics"]["rows"]
    model_a_offline = next(row for row in offline_rows if row["Model"] == "Model A")
    model_b_offline = next(row for row in offline_rows if row["Model"] == "Model B")
    assert model_a_offline["Recall@10"] > model_b_offline["Recall@10"]
    assert model_a_offline["NDCG@10"] > model_b_offline["NDCG@10"]

    bucket_rows = first_json["bucket_utility"]["rows"]
    explorer = next(
        row for row in bucket_rows if row["Bucket"] == "Explorer / novelty-seeking"
    )
    niche = next(row for row in bucket_rows if row["Bucket"] == "Niche-interest")
    assert explorer["Model B"] > explorer["Model A"]
    assert niche["Model B"] > niche["Model A"]

    behavior_rows = first_json["behavioral_diagnostics"]["rows"]
    model_a_behavior = next(row for row in behavior_rows if row["Model"] == "Model A")
    model_b_behavior = next(row for row in behavior_rows if row["Model"] == "Model B")
    assert model_b_behavior["Catalog concentration"] < model_a_behavior[
        "Catalog concentration"
    ]


def test_canonical_json_config_matches_builtin_canonical_run(tmp_path: Path) -> None:
    config = load_evaluation_config(EXAMPLES_ROOT / "canonical_run.json")
    configured_output = tmp_path / "configured"
    builtin_output = tmp_path / "builtin"
    filenames = artifact_filenames(config)

    run_evaluation(config, output_dir=configured_output)
    run_canonical_demo(output_dir=builtin_output)

    assert (configured_output / filenames["json"]).read_text() == (
        builtin_output / filenames["json"]
    ).read_text()
    assert (configured_output / filenames["report"]).read_text() == (
        builtin_output / filenames["report"]
    ).read_text()
    assert (configured_output / CHART_FILENAME).read_text() == (
        builtin_output / CHART_FILENAME
    ).read_text()


def test_custom_run_uses_generic_artifact_names(tmp_path: Path) -> None:
    config = load_evaluation_config(EXAMPLES_ROOT / "custom_csv_run.json")
    output_dir = tmp_path / "custom-run"
    filenames = artifact_filenames(config)

    run_evaluation(config, output_dir=output_dir)

    payload = json.loads((output_dir / filenames["json"]).read_text())
    report_text = (output_dir / filenames["report"]).read_text()
    assert filenames["json"] == "results.json"
    assert filenames["report"] == "report.md"
    assert not (output_dir / "official_demo_results.json").exists()
    assert not (output_dir / "official_demo_report.md").exists()
    assert payload["run_summary"]["dataset_type"] == "csv"
    assert payload["run_summary"]["models"]["Model B"]["label"] == "Feature-aware candidate"
    assert payload["reproducibility"]["candidate_model"]["type"] == "genre_profile"
    assert _section_headings(report_text) == [
        "## Run summary",
        "## Standard offline metrics",
        "## Bucket-level utility",
        "## Behavioral diagnostics",
        "## Key takeaways",
        "## Short traces",
        "## Reproducibility note",
    ]


def test_cli_no_args_dispatches_to_canonical(monkeypatch, capsys) -> None:
    called = {}

    def fake_run_canonical_demo(*, output_dir, data_dir):
        called["output_dir"] = output_dir
        called["data_dir"] = data_dir
        return {
            "report_path": Path("report.md"),
            "metrics_path": Path("metrics.json"),
            "chart_path": Path("chart.svg"),
        }

    monkeypatch.setattr(run_demo_module, "run_canonical_demo", fake_run_canonical_demo)
    monkeypatch.setattr(sys, "argv", ["recommender_offline_eval"])

    main()

    output = capsys.readouterr().out
    assert "Report: report.md" in output
    assert "Metrics: metrics.json" in output
    assert "Chart: chart.svg" in output
    assert "output_dir" in called


def test_cli_config_dispatches_to_custom_run(
    monkeypatch,
    capsys,
    tmp_path: Path,
) -> None:
    called = {}
    config_path = tmp_path / "config.json"
    config_path.write_text((EXAMPLES_ROOT / "custom_csv_run.json").read_text())

    def fake_load_config(path):
        called["config_path"] = path
        return load_evaluation_config(EXAMPLES_ROOT / "custom_csv_run.json")

    def fake_run_evaluation(config, *, data_dir, output_dir):
        called["dataset_type"] = config.dataset.type
        called["data_dir"] = data_dir
        called["output_dir"] = output_dir
        return {
            "report_path": Path("report.md"),
            "metrics_path": Path("metrics.json"),
            "chart_path": Path("chart.svg"),
        }

    monkeypatch.setattr(run_demo_module, "load_evaluation_config", fake_load_config)
    monkeypatch.setattr(run_demo_module, "run_evaluation", fake_run_evaluation)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "recommender_offline_eval",
            "--config",
            str(config_path),
            "--output-dir",
            str(tmp_path / "out"),
        ],
    )

    main()

    output = capsys.readouterr().out
    assert "Report: report.md" in output
    assert called["config_path"] == str(config_path)
    assert called["dataset_type"] == "csv"
    assert called["output_dir"] == str(tmp_path / "out")


def test_cli_refresh_canonical_dispatches_to_refresh(monkeypatch, capsys) -> None:
    called = {}

    def fake_refresh(*, output_dir, data_dir):
        called["output_dir"] = output_dir
        called["data_dir"] = data_dir
        return {
            "report_path": Path("report.md"),
            "metrics_path": Path("metrics.json"),
            "chart_path": Path("chart.svg"),
        }

    monkeypatch.setattr(run_demo_module, "refresh_canonical_artifacts", fake_refresh)
    monkeypatch.setattr(
        sys,
        "argv",
        ["recommender_offline_eval", "--refresh-canonical"],
    )

    main()

    output = capsys.readouterr().out
    assert "Chart: chart.svg" in output
    assert "output_dir" in called
