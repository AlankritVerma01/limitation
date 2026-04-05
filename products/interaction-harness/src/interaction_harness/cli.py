"""CLI and top-level orchestration for the reference-service recommender audit."""

from __future__ import annotations

import argparse

from .audit import run_recommender_audit
from .regression import run_regression_audit
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
    return parser


def main(argv: list[str] | None = None) -> dict[str, str]:
    """Run the CLI entrypoint and return the generated artifact paths."""
    args = _build_parser().parse_args(argv)
    scenario_names = None if args.scenario == "all" else (args.scenario,)
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
        )
        print("Compare audit artifacts:")
        print(f"  Regression report: {result['regression_report_path']}")
        print(f"  Regression summary: {result['regression_summary_path']}")
        print(f"  Regression traces: {result['regression_traces_path']}")
        return result
    result = run_recommender_audit(
        seed=args.seed,
        output_dir=args.output_dir,
        scenario_names=scenario_names,
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
