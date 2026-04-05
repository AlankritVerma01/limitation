"""CLI and top-level orchestration for the reference-service recommender audit."""

from __future__ import annotations

import argparse

from .audit import run_recommender_audit
from .config import DEFAULT_OUTPUT_DIR
from .regression import run_regression_audit
from .scenario_generation import (
    DEFAULT_PROVIDER_MODEL,
    build_default_scenario_pack_path,
    generate_scenario_pack,
    write_scenario_pack,
)
from .schema import RegressionTarget


def _build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser for single-run and compare modes."""
    parser = argparse.ArgumentParser(
        description=(
            "Run a single recommender audit or compare two artifact-backed systems "
            "through the interaction harness."
        )
    )
    parser.add_argument("--seed", type=int, default=0, help="Seed for audit rollouts.")
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Optional output directory override for the generated artifact bundle.",
    )
    parser.add_argument(
        "--scenario",
        default="all",
        choices=("all", "returning-user-home-feed", "sparse-history-home-feed"),
        help="Scenario selection for the audit.",
    )
    parser.add_argument(
        "--service-mode",
        default="reference",
        choices=("reference", "mock"),
        help="Local service mode used when no external adapter base URL is provided.",
    )
    parser.add_argument(
        "--service-artifact-dir",
        default=None,
        help="Artifact directory for the local reference recommender service in single-run mode.",
    )
    parser.add_argument(
        "--adapter-base-url",
        default=None,
        help="Optional existing recommender endpoint for single-run mode. If omitted, a local service is started.",
    )
    parser.add_argument(
        "--run-name",
        default=None,
        help="Optional display name override for single-run audit mode.",
    )
    parser.add_argument(
        "--scenario-pack-path",
        default=None,
        help="Saved scenario-pack path for single-run mode, or output path in generation mode.",
    )
    parser.add_argument(
        "--generate-scenarios",
        action="store_true",
        help="Generate and save a structured scenario pack instead of running an audit.",
    )
    parser.add_argument(
        "--scenario-brief",
        default=None,
        help="Short brief used when generating structured scenario packs.",
    )
    parser.add_argument(
        "--generation-mode",
        default="fixture",
        choices=("fixture", "provider"),
        help="Scenario generation mode for --generate-scenarios.",
    )
    parser.add_argument(
        "--generation-model",
        default=DEFAULT_PROVIDER_MODEL,
        help="Provider model name used in scenario generation mode.",
    )
    parser.add_argument(
        "--scenario-count",
        type=int,
        default=3,
        help="Number of scenarios to generate in scenario-generation mode.",
    )
    parser.add_argument(
        "--compare",
        action="store_true",
        help="Run compare/regression mode against baseline and candidate artifact bundles.",
    )
    parser.add_argument(
        "--baseline-artifact-dir",
        default=None,
        help="Artifact directory for the baseline reference-service target in compare mode.",
    )
    parser.add_argument(
        "--candidate-artifact-dir",
        default=None,
        help="Artifact directory for the candidate reference-service target in compare mode.",
    )
    parser.add_argument(
        "--rerun-count",
        type=int,
        default=3,
        help="Number of reruns per target in compare mode.",
    )
    parser.add_argument(
        "--baseline-label",
        default="baseline",
        help="Display label for the baseline target in compare mode.",
    )
    parser.add_argument(
        "--candidate-label",
        default="candidate",
        help="Display label for the candidate target in compare mode.",
    )
    parser.add_argument(
        "--policy-mode",
        default="default",
        choices=("default", "report_only"),
        help="Regression policy mode for compare runs.",
    )
    return parser


def main(argv: list[str] | None = None) -> dict[str, str | int]:
    """Run the CLI entrypoint and return the generated artifact paths."""
    args = _build_parser().parse_args(argv)
    scenario_names = None if args.scenario == "all" else (args.scenario,)
    if args.generate_scenarios:
        if args.compare:
            raise SystemExit("--generate-scenarios cannot be combined with --compare.")
        if args.scenario_brief is None:
            raise SystemExit("--generate-scenarios requires --scenario-brief.")
        output_root = args.output_dir or str(DEFAULT_OUTPUT_DIR)
        scenario_pack_path = args.scenario_pack_path or build_default_scenario_pack_path(
            output_root,
            brief=args.scenario_brief,
            generator_mode=args.generation_mode,
        )
        pack = generate_scenario_pack(
            args.scenario_brief,
            generator_mode=args.generation_mode,
            scenario_count=args.scenario_count,
            model_name=args.generation_model,
        )
        saved_path = write_scenario_pack(pack, scenario_pack_path)
        print("Scenario generation artifacts:")
        print(f"  Pack ID: {pack.metadata.pack_id}")
        print(f"  Scenario pack: {saved_path}")
        return {
            "scenario_pack_path": saved_path,
            "pack_id": pack.metadata.pack_id,
            "scenario_count": len(pack.scenarios),
        }
    if args.compare:
        if args.baseline_artifact_dir is None or args.candidate_artifact_dir is None:
            raise SystemExit(
                "--compare requires both --baseline-artifact-dir and --candidate-artifact-dir."
            )
        result = run_regression_audit(
            baseline_target=RegressionTarget(
                label=args.baseline_label,
                mode="reference_artifact",
                service_artifact_dir=args.baseline_artifact_dir,
            ),
            candidate_target=RegressionTarget(
                label=args.candidate_label,
                mode="reference_artifact",
                service_artifact_dir=args.candidate_artifact_dir,
            ),
            base_seed=args.seed,
            rerun_count=args.rerun_count,
            output_dir=args.output_dir,
            scenario_names=scenario_names,
            policy_mode=args.policy_mode,
        )
        print("Compare audit artifacts:")
        print(f"  Decision: {str(result['decision_status']).upper()}")
        print(f"  Regression report: {result['regression_report_path']}")
        print(f"  Regression summary: {result['regression_summary_path']}")
        print(f"  Regression traces: {result['regression_traces_path']}")
        return result
    result = run_recommender_audit(
        seed=args.seed,
        output_dir=args.output_dir,
        scenario_names=scenario_names,
        scenario_pack_path=args.scenario_pack_path,
        service_mode=args.service_mode,
        service_artifact_dir=args.service_artifact_dir,
        adapter_base_url=args.adapter_base_url,
        run_name=args.run_name,
    )
    print("Single-run audit artifacts:")
    print(f"  Report: {result['report_path']}")
    print(f"  Results: {result['results_path']}")
    print(f"  Traces: {result['traces_path']}")
    print(f"  Chart: {result['chart_path']}")
    return result
