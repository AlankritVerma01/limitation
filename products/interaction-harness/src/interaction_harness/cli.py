"""CLI-first entrypoint for the supported recommender audit workflow.

The CLI is the main user-facing surface today. It keeps the deterministic
runtime and regression flow explicit while offering optional AI-backed authoring
and advisory interpretation on top.
"""

from __future__ import annotations

import argparse

from .audit import run_recommender_audit
from .config import DEFAULT_OUTPUT_DIR
from .domains.recommender.scenarios import BUILT_IN_RECOMMENDER_SCENARIO_NAMES
from .population_generation import (
    build_default_population_pack_path,
    generate_population_pack,
    write_population_pack,
)
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
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=(
            "Run the supported recommender audit workflow through the interaction harness.\n\n"
            "Recommended paths:\n"
            "- Single-run: local reference recommender service or an external recommender URL\n"
            "- Compare: artifact-backed reference targets or external recommender URLs\n"
            "- AI features: provider-backed scenario/population authoring and semantic interpretation\n"
            "  are recommended for richer workflows, but the runtime and regression core stay deterministic."
        ),
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
        choices=("all", *BUILT_IN_RECOMMENDER_SCENARIO_NAMES),
        help="Scenario selection for the audit.",
    )
    parser.add_argument(
        "--service-mode",
        default="reference",
        choices=("reference", "mock"),
        help=(
            "Local service mode used when no external adapter base URL is provided. "
            "`reference` is the supported local path; `mock` is a narrow test/debug fixture."
        ),
    )
    parser.add_argument(
        "--service-artifact-dir",
        default=None,
        help="Artifact directory for the local reference recommender service in single-run mode.",
    )
    parser.add_argument(
        "--adapter-base-url",
        default=None,
        help=(
            "Optional existing recommender endpoint for single-run mode. "
            "This is the main real-system integration path; if omitted, a local reference service is started."
        ),
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
        "--population-pack-path",
        default=None,
        help="Saved population-pack path for audit/compare mode, or output path in population-generation mode.",
    )
    parser.add_argument(
        "--include-slice-membership",
        action="store_true",
        help="Include full discovered-slice membership in results.json for single-run audits.",
    )
    parser.add_argument(
        "--semantic-mode",
        default="off",
        choices=("off", "fixture", "provider"),
        help=(
            "Optional advisory semantic interpretation mode for audit and compare runs. "
            "Use `provider` for richer user-facing explanations; `fixture` stays useful for tests and offline demos."
        ),
    )
    parser.add_argument(
        "--semantic-model",
        default=DEFAULT_PROVIDER_MODEL,
        help="Provider model name used when semantic mode is `provider`.",
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
        help=(
            "Scenario generation mode for --generate-scenarios. "
            "Use `provider` for authored user workflows; `fixture` is the deterministic CI/demo path."
        ),
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
        "--generate-population",
        action="store_true",
        help="Generate and save a recommender population pack instead of running an audit.",
    )
    parser.add_argument(
        "--population-brief",
        default=None,
        help="Short brief used when generating recommender population packs.",
    )
    parser.add_argument(
        "--population-generation-mode",
        default="fixture",
        choices=("fixture", "provider"),
        help=(
            "Population generation mode for --generate-population. "
            "Use `provider` for authored user workflows; `fixture` is the deterministic CI/demo path."
        ),
    )
    parser.add_argument(
        "--population-generation-model",
        default=DEFAULT_PROVIDER_MODEL,
        help="Provider model name used in population-generation mode.",
    )
    parser.add_argument(
        "--population-size",
        type=int,
        default=None,
        help=(
            "Optional explicit swarm size for generated population packs. If omitted, "
            "provider mode may suggest one; otherwise the default is 12."
        ),
    )
    parser.add_argument(
        "--population-candidate-count",
        type=int,
        default=None,
        help="Optional candidate count before deterministic diversity filtering in population-generation mode.",
    )
    parser.add_argument(
        "--compare",
        action="store_true",
        help="Run compare/regression mode against baseline and candidate artifact-backed or external URL targets.",
    )
    parser.add_argument(
        "--baseline-artifact-dir",
        default=None,
        help="Artifact directory for the baseline reference-service target in compare mode.",
    )
    parser.add_argument(
        "--baseline-base-url",
        default=None,
        help="External recommender base URL for the baseline target in compare mode.",
    )
    parser.add_argument(
        "--candidate-artifact-dir",
        default=None,
        help="Artifact directory for the candidate reference-service target in compare mode.",
    )
    parser.add_argument(
        "--candidate-base-url",
        default=None,
        help="External recommender base URL for the candidate target in compare mode.",
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
    if args.generate_scenarios and args.generate_population:
        raise SystemExit("--generate-scenarios cannot be combined with --generate-population.")
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
    if args.generate_population:
        if args.compare:
            raise SystemExit("--generate-population cannot be combined with --compare.")
        if args.population_brief is None:
            raise SystemExit("--generate-population requires --population-brief.")
        output_root = args.output_dir or str(DEFAULT_OUTPUT_DIR)
        population_pack_path = args.population_pack_path or build_default_population_pack_path(
            output_root,
            brief=args.population_brief,
            generator_mode=args.population_generation_mode,
        )
        pack = generate_population_pack(
            args.population_brief,
            generator_mode=args.population_generation_mode,
            population_size=args.population_size,
            candidate_count=args.population_candidate_count,
            model_name=args.population_generation_model,
        )
        saved_path = write_population_pack(pack, population_pack_path)
        print("Population generation artifacts:")
        print(f"  Pack ID: {pack.metadata.pack_id}")
        print(f"  Population pack: {saved_path}")
        print(f"  Selected personas: {pack.metadata.selected_count}")
        print(
            "  Population size source: "
            f"{pack.metadata.population_size_source}"
        )
        return {
            "population_pack_path": saved_path,
            "pack_id": pack.metadata.pack_id,
            "population_size": pack.metadata.selected_count,
        }
    if args.compare:
        baseline_target = _build_compare_target(
            label=args.baseline_label,
            artifact_dir=args.baseline_artifact_dir,
            base_url=args.baseline_base_url,
            side_name="baseline",
        )
        candidate_target = _build_compare_target(
            label=args.candidate_label,
            artifact_dir=args.candidate_artifact_dir,
            base_url=args.candidate_base_url,
            side_name="candidate",
        )
        result = run_regression_audit(
            baseline_target=baseline_target,
            candidate_target=candidate_target,
            base_seed=args.seed,
            rerun_count=args.rerun_count,
            output_dir=args.output_dir,
            scenario_names=scenario_names,
            population_pack_path=args.population_pack_path,
            semantic_mode=args.semantic_mode,
            semantic_model=args.semantic_model,
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
        population_pack_path=args.population_pack_path,
        service_mode=args.service_mode,
        service_artifact_dir=args.service_artifact_dir,
        adapter_base_url=args.adapter_base_url,
        run_name=args.run_name,
        include_slice_membership=args.include_slice_membership,
        semantic_mode=args.semantic_mode,
        semantic_model=args.semantic_model,
    )
    print("Single-run audit artifacts:")
    print(f"  Report: {result['report_path']}")
    print(f"  Results: {result['results_path']}")
    print(f"  Traces: {result['traces_path']}")
    print(f"  Chart: {result['chart_path']}")
    return result


def _build_compare_target(
    *,
    label: str,
    artifact_dir: str | None,
    base_url: str | None,
    side_name: str,
) -> RegressionTarget:
    """Build one compare target from either an artifact bundle or an external URL."""
    has_artifact = artifact_dir is not None
    has_base_url = base_url is not None
    if has_artifact == has_base_url:
        raise SystemExit(
            f"--compare requires exactly one of --{side_name}-artifact-dir or --{side_name}-base-url."
        )
    if has_artifact:
        return RegressionTarget(
            label=label,
            mode="reference_artifact",
            service_artifact_dir=artifact_dir,
        )
    return RegressionTarget(
        label=label,
        mode="external_url",
        adapter_base_url=base_url,
    )
