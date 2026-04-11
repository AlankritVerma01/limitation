from __future__ import annotations

import json
from pathlib import Path

from interaction_harness.cli import main
from interaction_harness.domains.recommender import ensure_reference_artifacts
from interaction_harness.population_generation import (
    generate_population_pack,
    write_population_pack,
)
from interaction_harness.scenario_generation import (
    generate_scenario_pack,
    write_scenario_pack,
)


def test_run_swarm_writes_run_plan_and_links_manifest(tmp_path: Path) -> None:
    result = main(
        [
            "run-swarm",
            "--domain",
            "recommender",
            "--use-mock",
            "--brief",
            "test planner artifact for impatient exploratory users",
            "--generation-mode",
            "fixture",
            "--output-dir",
            str(tmp_path / "run-swarm"),
        ]
    )

    plan_path = Path(str(result["run_plan_path"]))
    manifest_path = Path(str(result["run_manifest_path"]))
    report_path = Path(str(result["report_path"]))

    plan_payload = json.loads(plan_path.read_text(encoding="utf-8"))
    manifest_payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    report_text = report_path.read_text(encoding="utf-8")

    assert plan_payload["workflow_type"] == "run-swarm"
    assert plan_payload["coverage_intent"]["scenario"]["decision"] == "generate_new"
    assert plan_payload["coverage_intent"]["swarm"]["decision"] == "generate_new"
    assert plan_payload["run_shaping"]["generation_mode"] == "fixture"
    assert manifest_payload["run_plan"]["run_plan_path"] == str(plan_path)
    assert manifest_payload["run_plan"]["run_plan_id"] == plan_payload["plan_id"]
    assert "Run plan:" in report_text


def test_run_swarm_explicit_pack_paths_remain_authoritative_in_run_plan(
    tmp_path: Path,
) -> None:
    scenario_pack = generate_scenario_pack("saved scenario pack", generator_mode="fixture")
    population_pack = generate_population_pack(
        "saved population pack",
        generator_mode="fixture",
        population_size=8,
        candidate_count=16,
    )
    scenario_pack_path = tmp_path / "saved-scenarios.json"
    population_pack_path = tmp_path / "saved-population.json"
    write_scenario_pack(scenario_pack, scenario_pack_path)
    write_population_pack(population_pack, population_pack_path)

    result = main(
        [
            "run-swarm",
            "--domain",
            "recommender",
            "--use-mock",
            "--brief",
            "this brief should not override explicit packs",
            "--scenario-pack-path",
            str(scenario_pack_path),
            "--population-pack-path",
            str(population_pack_path),
            "--output-dir",
            str(tmp_path / "run-swarm"),
        ]
    )

    plan_payload = json.loads(
        Path(str(result["run_plan_path"])).read_text(encoding="utf-8")
    )
    assert plan_payload["coverage_intent"]["scenario"]["decision"] == "explicit_reuse"
    assert plan_payload["coverage_intent"]["swarm"]["decision"] == "explicit_reuse"
    assert (
        plan_payload["planned_artifacts"]["scenario_pack_path"] == str(scenario_pack_path)
    )
    assert (
        plan_payload["planned_artifacts"]["population_pack_path"]
        == str(population_pack_path)
    )


def test_compare_writes_run_plan_for_built_in_coverage_without_brief(tmp_path: Path) -> None:
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
            "--scenario",
            "returning-user-home-feed",
            "--rerun-count",
            "1",
            "--output-dir",
            str(tmp_path / "compare"),
        ]
    )

    plan_path = Path(str(result["run_plan_path"]))
    manifest_path = Path(str(result["run_manifest_path"]))
    report_path = Path(str(result["regression_report_path"]))

    plan_payload = json.loads(plan_path.read_text(encoding="utf-8"))
    manifest_payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    report_text = report_path.read_text(encoding="utf-8")

    assert plan_payload["workflow_type"] == "compare"
    assert plan_payload["coverage_intent"]["coverage_source"] == "built_in"
    assert (
        plan_payload["coverage_intent"]["scenario"]["decision"] == "use_built_in_scenarios"
    )
    assert (
        plan_payload["coverage_intent"]["swarm"]["decision"] == "use_built_in_population"
    )
    assert manifest_payload["run_plan"]["run_plan_path"] == str(plan_path)
    assert "Run plan:" in report_text


def test_compare_brief_driven_planning_generates_shared_coverage_and_keeps_manifest_linked(
    tmp_path: Path,
) -> None:
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
            "--brief",
            "compare trust collapse and novelty balance across the two systems",
            "--generation-mode",
            "fixture",
            "--rerun-count",
            "1",
            "--output-dir",
            str(tmp_path / "compare"),
        ]
    )

    plan_payload = json.loads(
        Path(str(result["run_plan_path"])).read_text(encoding="utf-8")
    )
    manifest_payload = json.loads(
        Path(str(result["run_manifest_path"])).read_text(encoding="utf-8")
    )
    scenario_pack_path = Path(str(plan_payload["planned_artifacts"]["scenario_pack_path"]))
    population_pack_path = Path(
        str(plan_payload["planned_artifacts"]["population_pack_path"])
    )

    assert plan_payload["brief"] == "compare trust collapse and novelty balance across the two systems"
    assert plan_payload["coverage_intent"]["coverage_source"] == "generated"
    assert plan_payload["coverage_intent"]["scenario"]["decision"] == "generate_new"
    assert plan_payload["coverage_intent"]["swarm"]["decision"] == "generate_new"
    assert scenario_pack_path.exists()
    assert population_pack_path.exists()
    assert manifest_payload["run_plan"]["run_plan_id"] == plan_payload["plan_id"]


def test_run_swarm_plan_and_manifest_capture_semantic_intent(tmp_path: Path) -> None:
    result = main(
        [
            "run-swarm",
            "--domain",
            "recommender",
            "--use-mock",
            "--brief",
            "test semantic advisory planning metadata",
            "--generation-mode",
            "fixture",
            "--semantic-mode",
            "fixture",
            "--output-dir",
            str(tmp_path / "run-swarm"),
        ]
    )

    plan_payload = json.loads(
        Path(str(result["run_plan_path"])).read_text(encoding="utf-8")
    )
    manifest_payload = json.loads(
        Path(str(result["run_manifest_path"])).read_text(encoding="utf-8")
    )
    assert plan_payload["run_shaping"]["semantic_mode"] == "fixture"
    assert manifest_payload["semantic_mode"] == "fixture"
    assert manifest_payload["run_plan"]["run_plan_path"] == str(result["run_plan_path"])
