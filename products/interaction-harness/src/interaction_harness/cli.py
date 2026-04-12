"""CLI-first entrypoint for the interaction harness."""

from __future__ import annotations

import argparse
import json
import sys
import time
from contextlib import suppress
from pathlib import Path

from .audit import execute_domain_audit, write_run_artifacts
from .cli_progress import ProgressCallback, TerminalProgressRenderer, emit_progress
from .config import DEFAULT_OUTPUT_DIR
from .domain_registry import get_domain_definition, list_public_domain_definitions
from .generation_support import (
    DEFAULT_POPULATION_PROVIDER_MODEL,
    DEFAULT_PROVIDER_PROFILE,
    DEFAULT_SCENARIO_PROVIDER_MODEL,
    DEFAULT_SEMANTIC_PROVIDER_MODEL,
    list_provider_profiles,
)
from .orchestration import (
    AuditExecutionRequest,
    AuditPlanRequest,
    CompareExecutionRequest,
    ComparePlanRequest,
    RunSwarmExecutionRequest,
    RunSwarmPlanRequest,
    execute_audit_plan,
    execute_compare_plan,
    execute_run_swarm_plan,
    execute_saved_audit_plan,
    execute_saved_compare_plan,
    execute_saved_run_swarm_plan,
    plan_audit,
    plan_compare,
    plan_run_swarm,
)
from .population_generation import (
    build_default_population_pack_path,
    generate_population_pack,
    write_population_pack,
)
from .regression import run_domain_regression_audit
from .run_manifest import write_run_manifest
from .run_plan import load_run_plan
from .scenario_generation import (
    build_default_scenario_pack_path,
    generate_scenario_pack,
    write_scenario_pack,
)
from .schema import RegressionTarget


def _build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser for the supported interaction-harness workflows."""
    parser = argparse.ArgumentParser(
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=(
            "Run interaction-harness workflows through the shared CLI.\n\n"
            "Recommended v1 paths:\n"
            "- `run-swarm --domain recommender --target-url ... --brief ...`: one-command intent-driven swarm run\n"
            "- `plan-run --workflow run-swarm|compare|audit ...` then `execute-plan --run-plan-path ...`: explicit plan-first workflow\n"
            "- `audit --domain recommender`: local reference target or an external URL\n"
            "- `check-target --domain recommender --target-url ...`: validate a customer endpoint before a full run\n"
            "- `compare --domain recommender`: artifact-backed baselines/candidates or external URLs\n"
            "- `generate-scenarios --domain recommender` / `generate-population --domain recommender`\n"
            "- `serve-reference --domain recommender`: explicit local reference-service workflow\n\n"
            "AI-backed generation expands coverage. The runtime and regression core stay deterministic."
        ),
    )
    subparsers = parser.add_subparsers(dest="command", metavar="command")

    _build_audit_parser(subparsers)
    _build_run_swarm_parser(subparsers)
    _build_plan_run_parser(subparsers)
    _build_execute_plan_parser(subparsers)
    _build_check_target_parser(subparsers)
    _build_compare_parser(subparsers)
    _build_generate_scenarios_parser(subparsers)
    _build_generate_population_parser(subparsers)
    _build_serve_reference_parser(subparsers)
    return parser


def _build_audit_parser(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> argparse.ArgumentParser:
    parser = subparsers.add_parser(
        "audit",
        help="Run one domain audit and write the standard artifact bundle.",
        description=(
            "Run one domain audit against a supported local reference target "
            "or an external URL."
        ),
    )
    parser.set_defaults(handler=_handle_audit_command)
    _add_shared_run_arguments(parser)
    parser.add_argument(
        "--target-url",
        default=None,
        help=(
            "Existing system endpoint to audit for the selected domain. "
            "If omitted, the supported local reference target is used."
        ),
    )
    parser.add_argument(
        "--reference-artifact-dir",
        default=None,
        help=(
            "Optional artifact directory for the selected domain's local reference "
            "target. This is an advanced override for the supported local path."
        ),
    )
    parser.add_argument(
        "--use-mock",
        action="store_true",
        help="Use a domain-specific mock target only for narrow test/debug runs.",
    )
    parser.add_argument(
        "--run-name",
        default=None,
        help="Optional display name override for the audit.",
    )
    parser.add_argument(
        "--include-slice-membership",
        action="store_true",
        help="Include full discovered-slice membership in results.json.",
    )
    return parser


def _build_run_swarm_parser(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> argparse.ArgumentParser:
    parser = subparsers.add_parser(
        "run-swarm",
        help="Generate coverage from one brief, run the swarm, and write one audit bundle.",
        description=(
            "Generate scenarios and a saved swarm from one brief, then run a domain audit "
            "against a supported local reference target or an external URL."
        ),
    )
    parser.set_defaults(handler=_handle_run_swarm_command)
    _add_run_swarm_arguments(parser)
    parser.add_argument(
        "--target-url",
        default=None,
        help=(
            "Existing system endpoint to audit for the selected domain. "
            "If omitted, the supported local reference target is used."
        ),
    )
    parser.add_argument(
        "--reference-artifact-dir",
        default=None,
        help=(
            "Optional artifact directory for the selected domain's local reference "
            "target. This is an advanced override for the supported local path."
        ),
    )
    parser.add_argument(
        "--use-mock",
        action="store_true",
        help="Use a domain-specific mock target only for narrow test/debug runs.",
    )
    parser.add_argument(
        "--run-name",
        default=None,
        help="Optional display name override for the audit.",
    )
    return parser


def _build_compare_parser(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> argparse.ArgumentParser:
    parser = subparsers.add_parser(
        "compare",
        help="Compare baseline and candidate domain targets across reruns.",
        description=(
            "Run regression compare mode for artifact-backed or external-URL targets."
        ),
    )
    parser.set_defaults(handler=_handle_compare_command)
    _add_shared_run_arguments(parser)
    parser.add_argument(
        "--brief",
        default=None,
        help="Optional shared brief used to plan shared coverage for both baseline and candidate.",
    )
    parser.add_argument(
        "--baseline-artifact-dir",
        default=None,
        help="Artifact directory for the baseline reference target.",
    )
    parser.add_argument(
        "--baseline-url",
        default=None,
        help="External URL for the baseline target.",
    )
    parser.add_argument(
        "--candidate-artifact-dir",
        default=None,
        help="Artifact directory for the candidate reference target.",
    )
    parser.add_argument(
        "--candidate-url",
        default=None,
        help="External URL for the candidate target.",
    )
    parser.add_argument(
        "--rerun-count",
        type=int,
        default=3,
        help="Number of reruns per target.",
    )
    parser.add_argument(
        "--baseline-label",
        default="baseline",
        help="Display label for the baseline target.",
    )
    parser.add_argument(
        "--candidate-label",
        default="candidate",
        help="Display label for the candidate target.",
    )
    parser.add_argument(
        "--policy-mode",
        default="default",
        choices=("default", "report_only"),
        help="Regression policy mode.",
    )
    parser.add_argument(
        "--generation-mode",
        default="fixture",
        choices=("fixture", "provider"),
        help="Coverage-generation mode used when compare plans shared generated coverage.",
    )
    parser.add_argument(
        "--ai-profile",
        default=DEFAULT_PROVIDER_PROFILE,
        choices=list_provider_profiles(),
        help="Named AI profile used when compare plans provider-backed shared coverage.",
    )
    parser.add_argument(
        "--scenario-count",
        type=int,
        default=3,
        help="Number of generated scenarios when compare plans shared scenario coverage.",
    )
    parser.add_argument(
        "--population-size",
        type=int,
        default=None,
        help="Optional explicit final swarm size when compare plans shared swarm coverage.",
    )
    parser.add_argument(
        "--population-candidate-count",
        type=int,
        default=None,
        help="Optional candidate count before deterministic swarm selection in compare planning.",
    )
    return parser


def _build_plan_run_parser(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> argparse.ArgumentParser:
    parser = subparsers.add_parser(
        "plan-run",
        help="Create a durable run plan without executing it.",
        description=(
            "Create a reusable `run_plan.json` for `run-swarm` or `compare` without "
            "running the audit yet."
        ),
    )
    parser.set_defaults(handler=_handle_plan_run_command)
    parser.add_argument(
        "--workflow",
        required=True,
        choices=("run-swarm", "compare", "audit"),
        help="Workflow to plan.",
    )
    _add_shared_execution_arguments(parser)
    parser.add_argument(
        "--brief",
        default=None,
        help="Brief used to plan run-swarm coverage or optional shared compare coverage.",
    )
    parser.add_argument(
        "--scenario",
        default="all",
        help="Optional built-in scenario selection used by compare plans without a shared brief.",
    )
    parser.add_argument(
        "--scenario-pack-path",
        default=None,
        help="Optional saved scenario-pack path to lock into the run plan.",
    )
    parser.add_argument(
        "--population-pack-path",
        default=None,
        help="Optional saved population-pack path to lock into the run plan.",
    )
    parser.add_argument(
        "--include-slice-membership",
        action="store_true",
        help="Include full discovered-slice membership in the realized results when the plan executes.",
    )
    parser.add_argument(
        "--generation-mode",
        default="fixture",
        choices=("fixture", "provider"),
        help="Coverage-generation mode used for planned fresh coverage.",
    )
    parser.add_argument(
        "--ai-profile",
        default=DEFAULT_PROVIDER_PROFILE,
        choices=list_provider_profiles(),
        help="Named AI profile used for planned provider-backed coverage.",
    )
    parser.add_argument(
        "--scenario-count",
        type=int,
        default=3,
        help="Planned generated scenario count.",
    )
    parser.add_argument(
        "--population-size",
        type=int,
        default=None,
        help="Planned final swarm size when the plan generates a new swarm.",
    )
    parser.add_argument(
        "--population-candidate-count",
        type=int,
        default=None,
        help="Planned candidate count before deterministic swarm selection.",
    )
    parser.add_argument(
        "--target-url",
        default=None,
        help="Target URL for `run-swarm` planning.",
    )
    parser.add_argument(
        "--reference-artifact-dir",
        default=None,
        help="Reference artifact directory for `run-swarm` planning.",
    )
    parser.add_argument(
        "--use-mock",
        action="store_true",
        help="Use the mock recommender target for `run-swarm` planning.",
    )
    parser.add_argument(
        "--run-name",
        default=None,
        help="Optional display name to persist in a `run-swarm` plan.",
    )
    parser.add_argument(
        "--baseline-artifact-dir",
        default=None,
        help="Artifact directory for the compare baseline target.",
    )
    parser.add_argument(
        "--baseline-url",
        default=None,
        help="External URL for the compare baseline target.",
    )
    parser.add_argument(
        "--candidate-artifact-dir",
        default=None,
        help="Artifact directory for the compare candidate target.",
    )
    parser.add_argument(
        "--candidate-url",
        default=None,
        help="External URL for the compare candidate target.",
    )
    parser.add_argument(
        "--rerun-count",
        type=int,
        default=3,
        help="Planned rerun count for compare.",
    )
    parser.add_argument(
        "--baseline-label",
        default="baseline",
        help="Display label for the compare baseline target.",
    )
    parser.add_argument(
        "--candidate-label",
        default="candidate",
        help="Display label for the compare candidate target.",
    )
    parser.add_argument(
        "--policy-mode",
        default="default",
        choices=("default", "report_only"),
        help="Regression policy mode to persist in a compare plan.",
    )
    return parser


def _build_execute_plan_parser(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> argparse.ArgumentParser:
    parser = subparsers.add_parser(
        "execute-plan",
        help="Execute one saved run plan deterministically.",
        description=(
            "Load a saved `run_plan.json` and execute it without running a fresh planning pass."
        ),
    )
    parser.set_defaults(handler=_handle_execute_plan_command)
    parser.add_argument(
        "--run-plan-path",
        required=True,
        help="Path to the saved `run_plan.json` to execute.",
    )
    return parser


def _build_check_target_parser(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> argparse.ArgumentParser:
    parser = subparsers.add_parser(
        "check-target",
        help="Validate one external target before running a full audit.",
        description=(
            "Run a lightweight contract check against an external target for the selected domain."
        ),
    )
    parser.set_defaults(handler=_handle_check_target_command)
    _add_domain_argument(parser)
    parser.add_argument(
        "--target-url",
        required=True,
        help="External system endpoint to validate.",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=float,
        default=2.0,
        help="Per-request timeout used during the target check.",
    )
    return parser


def _build_generate_scenarios_parser(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> argparse.ArgumentParser:
    parser = subparsers.add_parser(
        "generate-scenarios",
        help="Generate and save a structured scenario pack for one domain.",
        description=(
            "Generate a structured scenario pack for one domain. Use `provider` for "
            "the recommended AI-authored coverage workflow and `fixture` for deterministic CI/demo runs. "
            "The default `fast` AI profile favors lower cost and latency."
        ),
    )
    parser.set_defaults(handler=_handle_generate_scenarios_command)
    _add_domain_argument(parser)
    parser.add_argument(
        "--brief",
        required=True,
        help="Short brief used to generate the scenario pack.",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Optional output directory override for the generated pack.",
    )
    parser.add_argument(
        "--scenario-pack-path",
        default=None,
        help="Optional explicit output path for the generated scenario pack.",
    )
    parser.add_argument(
        "--mode",
        default="fixture",
        choices=("fixture", "provider"),
        help="Generation mode. `provider` is recommended for richer launch-grade coverage.",
    )
    parser.add_argument(
        "--ai-profile",
        default=DEFAULT_PROVIDER_PROFILE,
        choices=list_provider_profiles(),
        help=(
            "Named AI profile used when `--mode provider` and no explicit `--model` override is set."
        ),
    )
    parser.add_argument(
        "--model",
        default=None,
        help=(
            "Optional explicit provider model override for scenario generation. "
            f"Defaults to `{DEFAULT_SCENARIO_PROVIDER_MODEL}` through the selected AI profile."
        ),
    )
    parser.add_argument(
        "--scenario-count",
        type=int,
        default=3,
        help="Number of scenarios to generate.",
    )
    return parser


def _build_generate_population_parser(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> argparse.ArgumentParser:
    parser = subparsers.add_parser(
        "generate-population",
        help="Generate and save a structured population pack for one domain.",
        description=(
            "Generate a structured population pack for one domain. Use `provider` for "
            "the recommended AI-authored swarm workflow and `fixture` for deterministic CI/demo runs. "
            "The default `fast` AI profile favors lower cost and latency."
        ),
    )
    parser.set_defaults(handler=_handle_generate_population_command)
    _add_domain_argument(parser)
    parser.add_argument(
        "--brief",
        required=True,
        help="Short brief used to generate the population pack.",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Optional output directory override for the generated pack.",
    )
    parser.add_argument(
        "--population-pack-path",
        default=None,
        help="Optional explicit output path for the generated population pack.",
    )
    parser.add_argument(
        "--mode",
        default="fixture",
        choices=("fixture", "provider"),
        help="Generation mode. `provider` is recommended for richer launch-grade coverage.",
    )
    parser.add_argument(
        "--ai-profile",
        default=DEFAULT_PROVIDER_PROFILE,
        choices=list_provider_profiles(),
        help=(
            "Named AI profile used when `--mode provider` and no explicit `--model` override is set."
        ),
    )
    parser.add_argument(
        "--model",
        default=None,
        help=(
            "Optional explicit provider model override for population generation. "
            f"Defaults to `{DEFAULT_POPULATION_PROVIDER_MODEL}` through the selected AI profile."
        ),
    )
    parser.add_argument(
        "--population-size",
        type=int,
        default=None,
        help="Optional explicit final swarm size.",
    )
    parser.add_argument(
        "--population-candidate-count",
        type=int,
        default=None,
        help="Optional candidate count before deterministic diversity filtering.",
    )
    return parser


def _build_serve_reference_parser(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> argparse.ArgumentParser:
    parser = subparsers.add_parser(
        "serve-reference",
        help="Start a local reference service for one domain and print its URL.",
        description=(
            "Start the local reference service for one domain when supported."
        ),
    )
    parser.set_defaults(handler=_handle_serve_reference_command)
    _add_domain_argument(parser)
    parser.add_argument(
        "--artifact-dir",
        default=None,
        help="Optional artifact directory override for the local reference service.",
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Host interface to bind for the local reference service.",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=0,
        help="Port to bind for the local reference service. Use `0` for any free port.",
    )
    return parser


def _add_shared_run_arguments(parser: argparse.ArgumentParser) -> None:
    _add_shared_execution_arguments(parser)
    parser.add_argument(
        "--scenario",
        default="all",
        help="Optional built-in scenario selection for the chosen domain. Use `all` for all built-ins.",
    )
    parser.add_argument(
        "--scenario-pack-path",
        default=None,
        help="Saved scenario-pack path used for the run.",
    )
    parser.add_argument(
        "--population-pack-path",
        default=None,
        help="Saved population-pack path used for the run.",
    )


def _add_shared_execution_arguments(parser: argparse.ArgumentParser) -> None:
    _add_domain_argument(parser)
    parser.add_argument("--seed", type=int, default=0, help="Seed for deterministic rollouts.")
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Optional output directory override for the generated artifact bundle.",
    )
    parser.add_argument(
        "--semantic-mode",
        default="off",
        choices=("off", "fixture", "provider"),
        help=(
            "Optional advisory semantic interpretation mode. Use `provider` for "
            "richer explanations; the runtime and regression core stay deterministic."
        ),
    )
    parser.add_argument(
        "--semantic-profile",
        default=DEFAULT_PROVIDER_PROFILE,
        choices=list_provider_profiles(),
        help=(
            "Named AI profile used when `--semantic-mode provider` and no explicit "
            "`--semantic-model` override is set."
        ),
    )
    parser.add_argument(
        "--semantic-model",
        default=None,
        help=(
            "Optional explicit provider model override for semantic interpretation. "
            f"Defaults to `{DEFAULT_SEMANTIC_PROVIDER_MODEL}` through the selected semantic profile."
        ),
    )


def _add_run_swarm_arguments(parser: argparse.ArgumentParser) -> None:
    _add_shared_execution_arguments(parser)
    parser.add_argument(
        "--brief",
        required=True,
        help="Short brief used to generate scenarios and the saved swarm for this run.",
    )
    parser.add_argument(
        "--scenario-pack-path",
        default=None,
        help="Optional explicit saved scenario-pack path to reuse for this run.",
    )
    parser.add_argument(
        "--population-pack-path",
        default=None,
        help="Optional explicit saved population-pack path to reuse for this run.",
    )
    parser.add_argument(
        "--generation-mode",
        default="fixture",
        choices=("fixture", "provider"),
        help="Coverage-generation mode for both scenario and swarm generation.",
    )
    parser.add_argument(
        "--ai-profile",
        default=DEFAULT_PROVIDER_PROFILE,
        choices=list_provider_profiles(),
        help=(
            "Named AI profile used for both scenario and swarm generation when provider "
            "generation is selected and no explicit model override is set."
        ),
    )
    parser.add_argument(
        "--scenario-count",
        type=int,
        default=3,
        help="Number of generated scenarios when a saved scenario pack is not provided.",
    )
    parser.add_argument(
        "--population-size",
        type=int,
        default=None,
        help="Optional explicit final swarm size when a saved population pack is not provided.",
    )
    parser.add_argument(
        "--population-candidate-count",
        type=int,
        default=None,
        help="Optional candidate count before deterministic swarm selection.",
    )


def _add_domain_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--domain",
        required=True,
        choices=list_public_domain_definitions(),
        help="Supported domain for this command.",
    )


def main(argv: list[str] | None = None) -> dict[str, str | int]:
    """Run the CLI entrypoint and return the generated artifact paths."""
    raw_argv = list(argv) if argv is not None else sys.argv[1:]
    parser = _build_parser()
    args = parser.parse_args(raw_argv)
    args.provided_options = {token for token in raw_argv if token.startswith("--")}
    handler = getattr(args, "handler", None)
    if handler is None:
        parser.print_help()
        raise SystemExit(0)

    progress = TerminalProgressRenderer()
    try:
        return handler(args, progress)
    finally:
        progress.close()


def _handle_plan_run_command(
    args: argparse.Namespace,
    progress_callback: ProgressCallback,
) -> dict[str, str | int]:
    if args.workflow == "audit":
        _validate_audit_plan_arguments(args)
        context = _build_audit_plan_from_args(args)
        plan = context.plan
        _print_summary(
            "Run plan ready",
            (
                ("Workflow", "audit"),
                ("Coverage source", plan.coverage_source),
                ("Scenario coverage", plan.scenario_generation_mode),
                ("Swarm coverage", plan.swarm_generation_mode),
                ("Planner mode", plan.planner_mode),
                ("Planned scenario pack", plan.scenario_pack_path or ""),
                ("Planned swarm pack", plan.population_pack_path or ""),
                ("Run plan", plan.plan_path),
            ),
        )
        return {"run_plan_path": plan.plan_path, "plan_id": plan.plan_id}
    if args.workflow == "run-swarm":
        context = _build_run_swarm_plan_from_args(args)
        plan = context.plan
        _print_summary(
            "Run plan ready",
            (
                ("Workflow", "run-swarm"),
                ("Coverage source", plan.coverage_source),
                ("Scenario generation", plan.scenario_generation_mode),
                ("Swarm generation", plan.swarm_generation_mode),
                ("Planner mode", plan.planner_mode),
                (
                    "Planner model",
                    _planner_model_summary(
                        plan.planner_provider_name,
                        plan.planner_model_name,
                        plan.planner_model_profile,
                    ),
                ),
                ("Planned scenario pack", plan.scenario_pack_path or ""),
                ("Planned swarm pack", plan.population_pack_path or ""),
                ("Run plan", plan.plan_path),
            ),
        )
        return {"run_plan_path": plan.plan_path, "plan_id": plan.plan_id}
    if args.workflow == "compare":
        context = _build_compare_plan_from_args(args)
        plan = context.plan
        _print_summary(
            "Run plan ready",
            (
                ("Workflow", "compare"),
                ("Coverage source", plan.coverage_source),
                ("Scenario generation", plan.scenario_generation_mode),
                ("Swarm generation", plan.swarm_generation_mode),
                ("Planner mode", plan.planner_mode),
                (
                    "Planner model",
                    _planner_model_summary(
                        plan.planner_provider_name,
                        plan.planner_model_name,
                        plan.planner_model_profile,
                    ),
                ),
                ("Planned scenario pack", plan.scenario_pack_path or ""),
                ("Planned swarm pack", plan.population_pack_path or ""),
                ("Run plan", plan.plan_path),
            ),
        )
        return {"run_plan_path": plan.plan_path, "plan_id": plan.plan_id}
    raise SystemExit(f"Unsupported workflow `{args.workflow}` for `plan-run`.")


def _handle_execute_plan_command(
    args: argparse.Namespace,
    progress_callback: ProgressCallback,
) -> dict[str, str | int]:
    plan = load_run_plan(args.run_plan_path)
    workflow_type = str(plan.payload.get("workflow_type", ""))
    if workflow_type == "run-swarm":
        outcome = execute_saved_run_swarm_plan(
            args.run_plan_path,
            progress_callback=progress_callback,
        )
        return outcome.result
    if workflow_type == "audit":
        outcome = execute_saved_audit_plan(
            args.run_plan_path,
            progress_callback=progress_callback,
        )
        return outcome.result
    if workflow_type == "compare":
        outcome = execute_saved_compare_plan(
            args.run_plan_path,
            progress_callback=progress_callback,
        )
        return outcome.result
    raise SystemExit(f"Unsupported workflow `{workflow_type}` in saved run plan.")


def _handle_audit_command(
    args: argparse.Namespace,
    progress_callback: ProgressCallback,
) -> dict[str, str | int]:
    context = _build_audit_plan_from_args(args)
    outcome = execute_audit_plan(
        context.plan,
        AuditExecutionRequest(
            domain_name=args.domain,
            output_root=context.output_root,
            service_mode=context.service_mode,
            service_artifact_dir=context.service_artifact_dir,
            adapter_base_url=context.adapter_base_url,
            seed=args.seed,
            output_dir=args.output_dir,
            run_name=args.run_name,
            include_slice_membership=args.include_slice_membership,
        ),
        progress_callback=progress_callback,
    )
    run_result = outcome.run_result
    result = outcome.result
    _print_summary(
        "Audit complete",
        (
            ("Launch status", _audit_launch_status(run_result)),
            ("High-risk cohorts", str(_count_high_risk_cohorts(run_result))),
            ("Risk flags", str(len(run_result.risk_flags))),
            ("Service kind", str(run_result.metadata.get("service_kind", ""))),
            ("Dataset", str(run_result.metadata.get("dataset", ""))),
            ("Model kind", str(run_result.metadata.get("model_kind", ""))),
            ("Model ID", str(run_result.metadata.get("model_id", ""))),
            ("Run plan", str(result["run_plan_path"])),
            ("Open report", str(result["report_path"])),
            ("Machine-readable results", str(result["results_path"])),
            ("Full traces", str(result["traces_path"])),
            ("Chart", str(result["chart_path"])),
            ("Run manifest", str(result["run_manifest_path"])),
        ),
    )
    return result


def _handle_run_swarm_command(
    args: argparse.Namespace,
    progress_callback: ProgressCallback,
) -> dict[str, str | int]:
    context = _build_run_swarm_plan_from_args(args)
    outcome = execute_run_swarm_plan(
        context.plan,
        RunSwarmExecutionRequest(
            domain_name=args.domain,
            brief=args.brief,
            output_root=context.output_root,
            service_mode=context.service_mode,
            service_artifact_dir=context.service_artifact_dir,
            adapter_base_url=context.adapter_base_url,
            seed=args.seed,
            output_dir=args.output_dir,
            run_name=args.run_name,
        ),
        progress_callback=progress_callback,
    )
    return _summarize_run_swarm_outcome(context.plan, outcome)


def _handle_check_target_command(
    args: argparse.Namespace,
    progress_callback: ProgressCallback,
) -> dict[str, str | int | float]:
    definition = get_domain_definition(args.domain)
    if definition.check_target is None:
        raise SystemExit(f"`check-target` is not supported for domain `{args.domain}`.")
    emit_progress(
        progress_callback,
        phase="check_target",
        message="Checking external target",
        stage="start",
    )
    result = definition.check_target(args.target_url, args.timeout_seconds)
    emit_progress(
        progress_callback,
        phase="check_target",
        message="Checked external target",
        stage="finish",
    )
    _print_summary(
        "Target check complete",
        (
            ("Status", str(result.get("probe_status", ""))),
            ("Target URL", str(result.get("target_url", ""))),
            ("Service kind", str(result.get("service_kind", ""))),
            ("Backend", str(result.get("backend_name", ""))),
            ("Dataset", str(result.get("dataset", ""))),
            ("Model kind", str(result.get("model_kind", ""))),
            ("Model ID", str(result.get("model_id", ""))),
            ("Probe scenario", str(result.get("probe_scenario", ""))),
            ("Top item", str(result.get("top_item_title", ""))),
        ),
    )
    return result


def _handle_compare_command(
    args: argparse.Namespace,
    progress_callback: ProgressCallback,
) -> dict[str, str | int]:
    context = _build_compare_plan_from_args(args)
    outcome = execute_compare_plan(
        context.plan,
        CompareExecutionRequest(
            domain_name=args.domain,
            brief=args.brief,
            output_root=context.output_root,
            baseline_target=context.baseline_target,
            candidate_target=context.candidate_target,
            seed=args.seed,
            output_dir=args.output_dir,
            policy_mode=args.policy_mode,
            scenario_name=args.scenario,
        ),
        progress_callback=progress_callback,
    )
    return _summarize_compare_outcome(context.plan, outcome)


def _build_run_swarm_plan_from_args(
    args: argparse.Namespace,
) -> object:
    if not args.brief:
        raise SystemExit("`plan-run --workflow run-swarm` requires `--brief`.")
    service_mode, service_artifact_dir, adapter_base_url = _resolve_audit_target(
        args,
        domain_name=args.domain,
    )
    output_root = args.output_dir or str(DEFAULT_OUTPUT_DIR)
    default_scenario_pack_path = build_default_scenario_pack_path(
        output_root,
        brief=args.brief,
        generator_mode=args.generation_mode,
    )
    default_population_pack_path = build_default_population_pack_path(
        output_root,
        brief=args.brief,
        generator_mode=args.generation_mode,
    )
    return plan_run_swarm(
        RunSwarmPlanRequest(
            domain_name=args.domain,
            brief=args.brief,
            generation_mode=args.generation_mode,
            output_root=output_root,
            target_config=_build_target_plan_config(
                service_mode=service_mode,
                service_artifact_dir=service_artifact_dir,
                adapter_base_url=adapter_base_url,
            ),
            explicit_inputs=_collect_explicit_run_swarm_inputs(args),
            scenario_pack_path=args.scenario_pack_path,
            population_pack_path=args.population_pack_path,
            scenario_count=args.scenario_count,
            population_size=args.population_size,
            population_candidate_count=args.population_candidate_count,
            ai_profile=args.ai_profile,
            semantic_mode=args.semantic_mode,
            semantic_model=args.semantic_model,
            semantic_profile=args.semantic_profile,
            default_scenario_pack_path=default_scenario_pack_path,
            default_population_pack_path=default_population_pack_path,
        )
    )


def _build_audit_plan_from_args(
    args: argparse.Namespace,
) -> object:
    service_mode, service_artifact_dir, adapter_base_url = _resolve_audit_target(
        args,
        domain_name=args.domain,
    )
    output_root = args.output_dir or str(DEFAULT_OUTPUT_DIR)
    return plan_audit(
        AuditPlanRequest(
            domain_name=args.domain,
            output_root=output_root,
            target_config=_build_target_plan_config(
                service_mode=service_mode,
                service_artifact_dir=service_artifact_dir,
                adapter_base_url=adapter_base_url,
            ),
            explicit_inputs=_collect_explicit_audit_inputs(args),
            scenario_name=args.scenario,
            scenario_pack_path=args.scenario_pack_path,
            population_pack_path=args.population_pack_path,
            semantic_mode=args.semantic_mode,
            semantic_model=args.semantic_model,
            semantic_profile=args.semantic_profile,
            include_slice_membership=args.include_slice_membership,
        )
    )


def _build_compare_plan_from_args(
    args: argparse.Namespace,
) -> object:
    baseline_target = _build_compare_target(
        label=args.baseline_label,
        artifact_dir=args.baseline_artifact_dir,
        url=args.baseline_url,
        side_name="baseline",
    )
    candidate_target = _build_compare_target(
        label=args.candidate_label,
        artifact_dir=args.candidate_artifact_dir,
        url=args.candidate_url,
        side_name="candidate",
    )
    output_root = args.output_dir or str(DEFAULT_OUTPUT_DIR)
    default_scenario_pack_path = (
        build_default_scenario_pack_path(
            output_root,
            brief=args.brief,
            generator_mode=args.generation_mode,
        )
        if args.brief
        else None
    )
    default_population_pack_path = (
        build_default_population_pack_path(
            output_root,
            brief=args.brief,
            generator_mode=args.generation_mode,
        )
        if args.brief
        else None
    )
    return plan_compare(
        ComparePlanRequest(
            domain_name=args.domain,
            brief=args.brief,
            generation_mode=args.generation_mode,
            output_root=output_root,
            baseline_target_config=_build_compare_plan_target_config(baseline_target),
            candidate_target_config=_build_compare_plan_target_config(candidate_target),
            explicit_inputs=_collect_explicit_compare_inputs(args),
            scenario_pack_path=args.scenario_pack_path,
            population_pack_path=args.population_pack_path,
            scenario_count=args.scenario_count,
            population_size=args.population_size,
            population_candidate_count=args.population_candidate_count,
            ai_profile=args.ai_profile,
            semantic_mode=args.semantic_mode,
            semantic_model=args.semantic_model,
            semantic_profile=args.semantic_profile,
            rerun_count=args.rerun_count,
            default_scenario_pack_path=default_scenario_pack_path,
            default_population_pack_path=default_population_pack_path,
            scenario_name=args.scenario,
            baseline_target=baseline_target,
            candidate_target=candidate_target,
        )
    )


def _summarize_run_swarm_outcome(plan, outcome) -> dict[str, str | int]:
    run_result = outcome.run_result
    _print_summary(
        "Swarm run complete",
        (
            ("Coverage source", outcome.coverage_source),
            ("Scenario generation", outcome.scenario_generation_mode),
            ("Swarm generation", outcome.swarm_generation_mode),
            ("AI profile", plan.ai_profile if outcome.coverage_source != "reused" else "n/a"),
            ("Planner mode", plan.planner_mode),
            (
                "Planner model",
                _planner_model_summary(
                    plan.planner_provider_name,
                    plan.planner_model_name,
                    plan.planner_model_profile,
                ),
            ),
            ("Launch status", _audit_launch_status(run_result)),
            ("High-risk cohorts", str(_count_high_risk_cohorts(run_result))),
            ("Service kind", str(run_result.metadata.get("service_kind", ""))),
            ("Dataset", str(run_result.metadata.get("dataset", ""))),
            ("Model kind", str(run_result.metadata.get("model_kind", ""))),
            ("Model ID", str(run_result.metadata.get("model_id", ""))),
            ("Saved scenario pack", outcome.scenario_pack_path),
            ("Saved swarm pack", outcome.population_pack_path),
            ("Run plan", plan.plan_path),
            ("Open report", str(outcome.result["report_path"])),
            ("Machine-readable results", str(outcome.result["results_path"])),
            ("Full traces", str(outcome.result["traces_path"])),
            ("Run manifest", outcome.manifest_path),
        ),
    )
    return outcome.result


def _summarize_compare_outcome(compare_plan, outcome) -> dict[str, str | int]:
    regression_summary = _load_json_summary(str(outcome.result["regression_summary_path"]))
    summary_block = regression_summary.get("summary", {}) if isinstance(regression_summary, dict) else {}
    _print_summary(
        "Compare complete",
        (
            ("Decision", str(outcome.result["decision_status"]).upper()),
            ("Overall direction", str(summary_block.get("overall_direction", ""))),
            ("Risk flags added", str(summary_block.get("added_risk_flag_count", ""))),
            ("Coverage source", outcome.coverage_source),
            ("Scenario generation", outcome.scenario_generation_mode),
            ("Swarm generation", outcome.swarm_generation_mode),
            ("Planner mode", compare_plan.planner_mode),
            (
                "Planner model",
                _planner_model_summary(
                    compare_plan.planner_provider_name,
                    compare_plan.planner_model_name,
                    compare_plan.planner_model_profile,
                ),
            ),
            ("Exit code", str(outcome.result["exit_code"])),
            ("Run plan", compare_plan.plan_path),
            ("Open regression report", str(outcome.result["regression_report_path"])),
            ("Machine-readable summary", str(outcome.result["regression_summary_path"])),
            ("Regression traces", str(outcome.result["regression_traces_path"])),
            ("Run manifest", str(outcome.result["run_manifest_path"])),
        ),
    )
    return outcome.result


def _execute_saved_run_swarm_plan(
    plan,
    *,
    progress_callback: ProgressCallback,
) -> dict[str, str | int]:
    payload = plan.payload
    target = payload["target"]
    run_shaping = payload["run_shaping"]
    return _execute_run_swarm_plan(
        plan,
        domain_name=str(payload["domain"]),
        brief=str(payload["brief"]),
        output_root=str(payload["planned_artifacts"]["output_dir"]),
        service_mode=str(target.get("service_mode", "")),
        service_artifact_dir=_optional_text(target.get("service_artifact_dir")),
        adapter_base_url=_optional_text(target.get("adapter_base_url")),
        seed=int(run_shaping["seed"]),
        output_dir=str(payload["planned_artifacts"]["output_dir"]),
        run_name=_optional_text(run_shaping.get("run_name")),
        progress_callback=progress_callback,
    )


def _execute_run_swarm_plan(
    plan,
    *,
    domain_name: str,
    brief: str,
    output_root: str,
    service_mode: str,
    service_artifact_dir: str | None,
    adapter_base_url: str | None,
    seed: int,
    output_dir: str | None,
    run_name: str | None,
    progress_callback: ProgressCallback,
) -> dict[str, str | int]:
    explicit_inputs = plan.payload.get("explicit_user_inputs", {})
    if not isinstance(explicit_inputs, dict):
        explicit_inputs = {}
    explicit_scenario_pack_path = explicit_inputs.get("scenario_pack_path")
    explicit_population_pack_path = explicit_inputs.get("population_pack_path")
    if explicit_scenario_pack_path is None and plan.scenario_generation_mode == "reused":
        explicit_scenario_pack_path = plan.scenario_pack_path
    if explicit_population_pack_path is None and plan.swarm_generation_mode == "reused":
        explicit_population_pack_path = plan.population_pack_path
    emit_progress(
        progress_callback,
        phase="resolve_generation_mode",
        message=f"Using generation mode: {plan.generation_mode}",
        stage="finish",
    )
    (
        scenario_pack_path,
        population_pack_path,
        coverage_source,
        scenario_generation_mode,
        swarm_generation_mode,
    ) = _resolve_run_swarm_packs(
        brief=brief,
        explicit_scenario_pack_path=_optional_text(explicit_scenario_pack_path),
        explicit_population_pack_path=_optional_text(explicit_population_pack_path),
        domain_name=domain_name,
        output_root=output_root,
        generation_mode=plan.generation_mode,
        scenario_action=plan.scenario_action,
        population_action=plan.population_action,
        ai_profile=plan.ai_profile,
        scenario_count=plan.scenario_count,
        population_size=plan.population_size,
        population_candidate_count=plan.population_candidate_count,
        planned_scenario_pack_path=plan.scenario_pack_path,
        planned_population_pack_path=plan.population_pack_path,
        progress_callback=progress_callback,
    )
    run_result = execute_domain_audit(
        domain_name=domain_name,
        seed=seed,
        output_dir=output_dir,
        scenario_pack_path=scenario_pack_path,
        population_pack_path=population_pack_path,
        service_mode=service_mode,
        service_artifact_dir=service_artifact_dir,
        adapter_base_url=adapter_base_url,
        run_name=run_name,
        semantic_mode=plan.semantic_mode,
        semantic_model=plan.semantic_model,
        semantic_profile=plan.semantic_profile,
        progress_callback=progress_callback,
    )
    run_result.metadata["run_plan_path"] = plan.plan_path
    run_result.metadata["run_plan_id"] = plan.plan_id
    run_result.metadata["planner_mode"] = plan.planner_mode
    run_result.metadata["planner_provider_name"] = plan.planner_provider_name
    run_result.metadata["planner_model_name"] = plan.planner_model_name
    run_result.metadata["planner_model_profile"] = plan.planner_model_profile
    run_result.metadata["planner_summary"] = plan.planner_summary
    run_result.metadata["run_manifest_path"] = str(
        Path(run_result.run_config.rollout.output_dir) / "run_manifest.json"
    )
    result = write_run_artifacts(run_result, progress_callback=progress_callback)
    manifest_path = write_run_manifest(
        run_result,
        artifact_paths=result,
        workflow_type="run-swarm",
        workflow_metadata={
            "coverage_source": coverage_source,
            "scenario_generation_mode": scenario_generation_mode,
            "swarm_generation_mode": swarm_generation_mode,
            "brief": brief,
            "scenario_pack_path": scenario_pack_path,
            "population_pack_path": population_pack_path,
            "ai_profile": plan.ai_profile if coverage_source != "reused" else "",
            "run_plan_path": plan.plan_path,
            "run_plan_id": plan.plan_id,
        },
    )
    _print_summary(
        "Swarm run complete",
        (
            ("Coverage source", coverage_source),
            ("Scenario generation", scenario_generation_mode),
            ("Swarm generation", swarm_generation_mode),
            ("AI profile", plan.ai_profile if coverage_source != "reused" else "n/a"),
            ("Planner mode", plan.planner_mode),
            (
                "Planner model",
                _planner_model_summary(
                    plan.planner_provider_name,
                    plan.planner_model_name,
                    plan.planner_model_profile,
                ),
            ),
            ("Launch status", _audit_launch_status(run_result)),
            ("High-risk cohorts", str(_count_high_risk_cohorts(run_result))),
            ("Service kind", str(run_result.metadata.get("service_kind", ""))),
            ("Dataset", str(run_result.metadata.get("dataset", ""))),
            ("Model kind", str(run_result.metadata.get("model_kind", ""))),
            ("Model ID", str(run_result.metadata.get("model_id", ""))),
            ("Saved scenario pack", scenario_pack_path),
            ("Saved swarm pack", population_pack_path),
            ("Run plan", plan.plan_path),
            ("Open report", str(result["report_path"])),
            ("Machine-readable results", str(result["results_path"])),
            ("Full traces", str(result["traces_path"])),
            ("Run manifest", manifest_path),
        ),
    )
    return {
        **result,
        "scenario_pack_path": scenario_pack_path,
        "population_pack_path": population_pack_path,
        "coverage_source": coverage_source,
        "scenario_generation_mode": scenario_generation_mode,
        "swarm_generation_mode": swarm_generation_mode,
        "run_plan_path": plan.plan_path,
        "run_manifest_path": manifest_path,
    }


def _execute_saved_compare_plan(
    plan,
    *,
    progress_callback: ProgressCallback,
) -> dict[str, str | int]:
    payload = plan.payload
    run_shaping = payload["run_shaping"]
    targets = payload["targets"]
    baseline_target = _regression_target_from_plan(targets["baseline"])
    candidate_target = _regression_target_from_plan(targets["candidate"])
    scenario_name = str(payload["coverage_intent"]["scenario"].get("built_in_selection", "all") or "all")
    return _execute_compare_plan(
        plan,
        domain_name=str(payload["domain"]),
        brief=_optional_text(payload.get("brief")),
        output_root=str(payload["planned_artifacts"]["output_dir"]),
        baseline_target=baseline_target,
        candidate_target=candidate_target,
        seed=int(run_shaping["seed"]),
        output_dir=str(payload["planned_artifacts"]["output_dir"]),
        policy_mode=str(run_shaping.get("policy_mode", "default")),
        scenario_name=scenario_name,
        progress_callback=progress_callback,
    )


def _execute_compare_plan(
    compare_plan,
    *,
    domain_name: str,
    brief: str | None,
    output_root: str,
    baseline_target: RegressionTarget,
    candidate_target: RegressionTarget,
    seed: int,
    output_dir: str | None,
    policy_mode: str,
    scenario_name: str,
    progress_callback: ProgressCallback,
) -> dict[str, str | int]:
    scenario_pack_path = compare_plan.scenario_pack_path
    population_pack_path = compare_plan.population_pack_path
    scenario_names = _resolve_scenario_names(scenario_name)
    if brief:
        if scenario_pack_path is None or population_pack_path is None:
            raise SystemExit("compare planning requires planned shared coverage paths when a brief is provided.")
        if compare_plan.scenario_generation_mode not in {"reused", "planner-reused"}:
            scenario_pack_path = _generate_compare_scenario_pack(
                brief=brief,
                output_root=output_root,
                domain_name=domain_name,
                generation_mode=compare_plan.generation_mode,
                ai_profile=compare_plan.ai_profile,
                scenario_count=compare_plan.scenario_count,
                planned_path=scenario_pack_path,
                progress_callback=progress_callback,
            )
        else:
            _ensure_reused_artifact(
                scenario_pack_path,
                label="shared compare scenario pack",
            )
            emit_progress(
                progress_callback,
                phase="reuse_scenario_pack",
                message="Reusing shared compare scenario pack",
                stage="finish",
            )
        if compare_plan.swarm_generation_mode not in {"reused", "planner-reused"}:
            population_pack_path = _generate_compare_population_pack(
                brief=brief,
                output_root=output_root,
                domain_name=domain_name,
                generation_mode=compare_plan.generation_mode,
                ai_profile=compare_plan.ai_profile,
                population_size=compare_plan.population_size,
                population_candidate_count=compare_plan.population_candidate_count,
                planned_path=population_pack_path,
                progress_callback=progress_callback,
            )
        else:
            _ensure_reused_artifact(
                population_pack_path,
                label="shared compare swarm pack",
            )
            emit_progress(
                progress_callback,
                phase="reuse_population_pack",
                message="Reusing shared compare swarm pack",
                stage="finish",
            )
    else:
        if scenario_pack_path is not None:
            _ensure_reused_artifact(
                scenario_pack_path,
                label="compare scenario pack",
            )
        if population_pack_path is not None:
            _ensure_reused_artifact(
                population_pack_path,
                label="compare swarm pack",
            )
    result = run_domain_regression_audit(
        domain_name=domain_name,
        baseline_target=baseline_target,
        candidate_target=candidate_target,
        base_seed=seed,
        rerun_count=compare_plan.rerun_count or 1,
        output_dir=output_dir,
        scenario_names=scenario_names,
        scenario_pack_path=scenario_pack_path,
        population_pack_path=population_pack_path,
        semantic_mode=compare_plan.semantic_mode,
        semantic_model=compare_plan.semantic_model,
        semantic_profile=compare_plan.semantic_profile,
        policy_mode=policy_mode,
        planning_metadata={
            "run_plan_path": compare_plan.plan_path,
            "run_plan_id": compare_plan.plan_id,
            "planner_mode": compare_plan.planner_mode,
            "planner_provider_name": compare_plan.planner_provider_name,
            "planner_model_name": compare_plan.planner_model_name,
            "planner_model_profile": compare_plan.planner_model_profile,
            "planner_summary": compare_plan.planner_summary,
            "scenario_generation_mode": compare_plan.scenario_generation_mode,
            "swarm_generation_mode": compare_plan.swarm_generation_mode,
            "coverage_source": compare_plan.coverage_source,
        },
        progress_callback=progress_callback,
    )
    regression_summary = _load_json_summary(str(result["regression_summary_path"]))
    summary_block = regression_summary.get("summary", {}) if isinstance(regression_summary, dict) else {}
    _print_summary(
        "Compare complete",
        (
            ("Decision", str(result["decision_status"]).upper()),
            ("Overall direction", str(summary_block.get("overall_direction", ""))),
            ("Risk flags added", str(summary_block.get("added_risk_flag_count", ""))),
            ("Coverage source", compare_plan.coverage_source),
            ("Scenario generation", compare_plan.scenario_generation_mode),
            ("Swarm generation", compare_plan.swarm_generation_mode),
            ("Planner mode", compare_plan.planner_mode),
            (
                "Planner model",
                _planner_model_summary(
                    compare_plan.planner_provider_name,
                    compare_plan.planner_model_name,
                    compare_plan.planner_model_profile,
                ),
            ),
            ("Exit code", str(result["exit_code"])),
            ("Run plan", compare_plan.plan_path),
            ("Open regression report", str(result["regression_report_path"])),
            ("Machine-readable summary", str(result["regression_summary_path"])),
            ("Regression traces", str(result["regression_traces_path"])),
            ("Run manifest", str(result["run_manifest_path"])),
        ),
    )
    return {**result, "run_plan_path": compare_plan.plan_path}


def _handle_generate_scenarios_command(
    args: argparse.Namespace,
    progress_callback: ProgressCallback,
) -> dict[str, str | int]:
    output_root = args.output_dir or str(DEFAULT_OUTPUT_DIR)
    domain_name = args.domain
    scenario_pack_path = args.scenario_pack_path or build_default_scenario_pack_path(
        output_root,
        brief=args.brief,
        generator_mode=args.mode,
    )
    pack = generate_scenario_pack(
        args.brief,
        generator_mode=args.mode,
        scenario_count=args.scenario_count,
        domain_label=domain_name,
        model_name=args.model,
        model_profile=args.ai_profile,
        progress_callback=progress_callback,
    )
    emit_progress(
        progress_callback,
        phase="write_pack",
        message="Writing scenario pack",
        stage="start",
    )
    saved_path = write_scenario_pack(pack, scenario_pack_path)
    emit_progress(
        progress_callback,
        phase="write_pack",
        message="Wrote scenario pack",
        stage="finish",
    )
    _print_summary(
        "Scenario generation complete",
        (
            ("Pack ID", pack.metadata.pack_id),
            ("Generation mode", pack.metadata.generator_mode),
            ("AI profile", pack.metadata.model_profile or "n/a"),
            ("Provider model", pack.metadata.model_name),
            ("Saved scenario pack", saved_path),
            ("Scenario count", str(len(pack.scenarios))),
        ),
    )
    return {
        "scenario_pack_path": saved_path,
        "pack_id": pack.metadata.pack_id,
        "scenario_count": len(pack.scenarios),
    }


def _handle_generate_population_command(
    args: argparse.Namespace,
    progress_callback: ProgressCallback,
) -> dict[str, str | int]:
    output_root = args.output_dir or str(DEFAULT_OUTPUT_DIR)
    domain_name = args.domain
    population_pack_path = args.population_pack_path or build_default_population_pack_path(
        output_root,
        brief=args.brief,
        generator_mode=args.mode,
    )
    pack = generate_population_pack(
        args.brief,
        generator_mode=args.mode,
        population_size=args.population_size,
        candidate_count=args.population_candidate_count,
        domain_label=domain_name,
        model_name=args.model,
        model_profile=args.ai_profile,
        progress_callback=progress_callback,
    )
    emit_progress(
        progress_callback,
        phase="write_pack",
        message="Writing population pack",
        stage="start",
    )
    saved_path = write_population_pack(pack, population_pack_path)
    emit_progress(
        progress_callback,
        phase="write_pack",
        message="Wrote population pack",
        stage="finish",
    )
    _print_summary(
        "Population generation complete",
        (
            ("Pack ID", pack.metadata.pack_id),
            ("Generation mode", pack.metadata.generator_mode),
            ("AI profile", pack.metadata.model_profile or "n/a"),
            ("Provider model", pack.metadata.model_name),
            ("Saved population pack", saved_path),
            ("Selected swarm members", str(pack.metadata.selected_count)),
            ("Population size source", pack.metadata.population_size_source),
        ),
    )
    return {
        "population_pack_path": saved_path,
        "pack_id": pack.metadata.pack_id,
        "population_size": pack.metadata.selected_count,
    }


def _handle_serve_reference_command(
    args: argparse.Namespace,
    progress_callback: ProgressCallback,
) -> dict[str, str | int]:
    domain_name = args.domain
    definition = get_domain_definition(domain_name)
    if definition.run_reference_service is None:
        raise SystemExit(
            f"`serve-reference` is not supported for domain `{domain_name}`."
        )
    emit_progress(
        progress_callback,
        phase="prepare_reference_service",
        message="Preparing reference artifacts",
        stage="start",
    )
    with definition.run_reference_service(
        args.artifact_dir,
        args.host,
        args.port,
    ) as (base_url, metadata):
        emit_progress(
            progress_callback,
            phase="prepare_reference_service",
            message="Prepared reference artifacts",
            stage="finish",
        )
        emit_progress(
            progress_callback,
            phase="start_reference_service",
            message="Starting reference service",
            stage="start",
        )
        emit_progress(
            progress_callback,
            phase="start_reference_service",
            message="Reference service ready",
            stage="finish",
        )
        _print_summary(
            "Reference service ready",
            (
                ("Base URL", base_url),
                ("Health URL", f"{base_url}/health"),
                ("Metadata URL", f"{base_url}/metadata"),
                ("Artifact ID", str(metadata.get("artifact_id", ""))),
                ("Service kind", str(metadata.get("service_kind", ""))),
                (
                    "Contract version",
                    str(metadata.get("artifact_contract_version", "")),
                ),
            ),
        )
        with suppress(KeyboardInterrupt):
            _wait_for_interrupt()
    return {
        "base_url": base_url,
        "artifact_id": str(metadata.get("artifact_id", "")),
        "service_kind": str(metadata.get("service_kind", "")),
        "artifact_contract_version": str(
            metadata.get("artifact_contract_version", "")
        ),
    }


def _resolve_scenario_names(scenario_name: str) -> tuple[str, ...] | None:
    return None if scenario_name == "all" else (scenario_name,)


def _resolve_audit_target(
    args: argparse.Namespace,
    *,
    domain_name: str,
) -> tuple[str, str | None, str | None]:
    if args.target_url is not None and args.use_mock:
        raise SystemExit("--target-url cannot be combined with --use-mock.")
    if args.target_url is not None and args.reference_artifact_dir is not None:
        raise SystemExit(
            "--target-url cannot be combined with --reference-artifact-dir."
        )
    if args.use_mock:
        if domain_name != "recommender":
            raise SystemExit("--use-mock is only supported for the recommender domain.")
        return "mock", None, None
    if args.target_url is not None:
        return "reference", None, args.target_url
    return "reference", args.reference_artifact_dir, None


def _resolve_run_swarm_packs(
    *,
    brief: str,
    explicit_scenario_pack_path: str | None,
    explicit_population_pack_path: str | None,
    domain_name: str,
    output_root: str,
    generation_mode: str,
    scenario_action: str,
    population_action: str,
    ai_profile: str,
    scenario_count: int | None,
    population_size: int | None,
    population_candidate_count: int | None,
    planned_scenario_pack_path: str | None,
    planned_population_pack_path: str | None,
    progress_callback: ProgressCallback | None = None,
) -> tuple[str, str, str, str, str]:
    scenario_pack_path = _optional_text(explicit_scenario_pack_path)
    population_pack_path = _optional_text(explicit_population_pack_path)
    generated_any = False
    reused_any = False
    scenario_generation_mode = "reused" if scenario_pack_path is not None else (
        "planner-reused" if scenario_action == "planner_reuse_existing" else generation_mode
    )
    swarm_generation_mode = "reused" if population_pack_path is not None else (
        "planner-reused" if population_action == "planner_reuse_existing" else generation_mode
    )

    if scenario_pack_path is None:
        if scenario_action == "planner_reuse_existing" and planned_scenario_pack_path is not None:
            _ensure_reused_artifact(
                planned_scenario_pack_path,
                label="planner-selected scenario pack",
            )
            scenario_pack_path = planned_scenario_pack_path
            emit_progress(
                progress_callback,
                phase="reuse_scenario_pack",
                message="Reusing planner-selected scenario pack",
                stage="finish",
            )
            reused_any = True
        else:
            scenario_pack_path = _generate_run_swarm_scenario_pack(
                brief=brief,
                output_root=output_root,
                domain_name=domain_name,
                generation_mode=generation_mode,
                ai_profile=ai_profile,
                scenario_count=scenario_count or 3,
                planned_path=planned_scenario_pack_path,
                progress_callback=progress_callback,
            )
            generated_any = True
    else:
        _ensure_reused_artifact(
            scenario_pack_path,
            label="scenario pack",
        )
        emit_progress(
            progress_callback,
            phase="reuse_scenario_pack",
            message="Reusing scenario pack",
            stage="finish",
        )
        reused_any = True

    if population_pack_path is None:
        if population_action == "planner_reuse_existing" and planned_population_pack_path is not None:
            _ensure_reused_artifact(
                planned_population_pack_path,
                label="planner-selected swarm pack",
            )
            population_pack_path = planned_population_pack_path
            emit_progress(
                progress_callback,
                phase="reuse_population_pack",
                message="Reusing planner-selected swarm pack",
                stage="finish",
            )
            reused_any = True
        else:
            population_pack_path = _generate_run_swarm_population_pack(
                brief=brief,
                output_root=output_root,
                domain_name=domain_name,
                generation_mode=generation_mode,
                ai_profile=ai_profile,
                population_size=population_size,
                population_candidate_count=population_candidate_count,
                planned_path=planned_population_pack_path,
                progress_callback=progress_callback,
            )
            generated_any = True
    else:
        _ensure_reused_artifact(
            population_pack_path,
            label="swarm pack",
        )
        emit_progress(
            progress_callback,
            phase="reuse_population_pack",
            message="Reusing swarm pack",
            stage="finish",
        )
        reused_any = True

    if generated_any and reused_any:
        coverage_source = "mixed"
    elif generated_any:
        coverage_source = "generated"
    else:
        coverage_source = "reused"
    return (
        scenario_pack_path,
        population_pack_path,
        coverage_source,
        scenario_generation_mode,
        swarm_generation_mode,
    )


def _generate_run_swarm_scenario_pack(
    *,
    brief: str,
    output_root: str,
    domain_name: str,
    generation_mode: str,
    ai_profile: str,
    scenario_count: int,
    planned_path: str | None,
    progress_callback: ProgressCallback | None = None,
) -> str:
    pack = generate_scenario_pack(
        brief,
        generator_mode=generation_mode,
        scenario_count=scenario_count,
        domain_label=domain_name,
        model_profile=ai_profile,
        progress_callback=progress_callback,
    )
    scenario_pack_path = planned_path or build_default_scenario_pack_path(
        output_root,
        brief=brief,
        generator_mode=generation_mode,
    )
    emit_progress(
        progress_callback,
        phase="write_pack",
        message="Writing scenario pack",
        stage="start",
    )
    saved_path = write_scenario_pack(pack, scenario_pack_path)
    emit_progress(
        progress_callback,
        phase="write_pack",
        message="Wrote scenario pack",
        stage="finish",
    )
    return saved_path


def _generate_run_swarm_population_pack(
    *,
    brief: str,
    output_root: str,
    domain_name: str,
    generation_mode: str,
    ai_profile: str,
    population_size: int | None,
    population_candidate_count: int | None,
    planned_path: str | None,
    progress_callback: ProgressCallback | None = None,
) -> str:
    pack = generate_population_pack(
        brief,
        generator_mode=generation_mode,
        population_size=population_size,
        candidate_count=population_candidate_count,
        domain_label=domain_name,
        model_profile=ai_profile,
        progress_callback=progress_callback,
    )
    population_pack_path = planned_path or build_default_population_pack_path(
        output_root,
        brief=brief,
        generator_mode=generation_mode,
    )
    emit_progress(
        progress_callback,
        phase="write_pack",
        message="Writing population pack",
        stage="start",
    )
    saved_path = write_population_pack(pack, population_pack_path)
    emit_progress(
        progress_callback,
        phase="write_pack",
        message="Wrote population pack",
        stage="finish",
    )
    return saved_path


def _build_compare_target(
    *,
    label: str,
    artifact_dir: str | None,
    url: str | None,
    side_name: str,
) -> RegressionTarget:
    """Build one compare target from either an artifact bundle or an external URL."""
    has_artifact = artifact_dir is not None
    has_url = url is not None
    if has_artifact == has_url:
        raise SystemExit(
            f"compare requires exactly one of --{side_name}-artifact-dir or --{side_name}-url."
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
        adapter_base_url=url,
    )


def _generate_compare_scenario_pack(
    *,
    brief: str,
    output_root: str,
    domain_name: str,
    generation_mode: str,
    ai_profile: str,
    scenario_count: int,
    planned_path: str,
    progress_callback: ProgressCallback | None = None,
) -> str:
    return _generate_run_swarm_scenario_pack(
        brief=brief,
        output_root=output_root,
        domain_name=domain_name,
        generation_mode=generation_mode,
        ai_profile=ai_profile,
        scenario_count=scenario_count,
        planned_path=planned_path,
        progress_callback=progress_callback,
    )


def _generate_compare_population_pack(
    *,
    brief: str,
    output_root: str,
    domain_name: str,
    generation_mode: str,
    ai_profile: str,
    population_size: int | None,
    population_candidate_count: int | None,
    planned_path: str,
    progress_callback: ProgressCallback | None = None,
) -> str:
    return _generate_run_swarm_population_pack(
        brief=brief,
        output_root=output_root,
        domain_name=domain_name,
        generation_mode=generation_mode,
        ai_profile=ai_profile,
        population_size=population_size,
        population_candidate_count=population_candidate_count,
        planned_path=planned_path,
        progress_callback=progress_callback,
    )


def _build_target_plan_config(
    *,
    service_mode: str,
    service_artifact_dir: str | None,
    adapter_base_url: str | None,
) -> dict[str, str]:
    return {
        "service_mode": service_mode,
        "service_artifact_dir": service_artifact_dir or "",
        "adapter_base_url": adapter_base_url or "",
    }


def _build_compare_plan_target_config(target: RegressionTarget) -> dict[str, str]:
    return {
        "label": target.label,
        "mode": target.mode,
        "service_artifact_dir": target.service_artifact_dir or "",
        "adapter_base_url": target.adapter_base_url or "",
    }


def _collect_explicit_run_swarm_inputs(args: argparse.Namespace) -> dict[str, object]:
    inputs: dict[str, object] = {"brief": args.brief}
    for flag, key in (
        ("--scenario-pack-path", "scenario_pack_path"),
        ("--population-pack-path", "population_pack_path"),
        ("--generation-mode", "generation_mode"),
        ("--ai-profile", "ai_profile"),
        ("--scenario-count", "scenario_count"),
        ("--population-size", "population_size"),
        ("--population-candidate-count", "population_candidate_count"),
        ("--semantic-mode", "semantic_mode"),
        ("--semantic-model", "semantic_model"),
        ("--semantic-profile", "semantic_profile"),
        ("--seed", "seed"),
        ("--target-url", "target_url"),
        ("--reference-artifact-dir", "reference_artifact_dir"),
        ("--use-mock", "use_mock"),
        ("--run-name", "run_name"),
        ("--include-slice-membership", "include_slice_membership"),
    ):
        if flag in args.provided_options:
            inputs[key] = getattr(args, key, True if key == "use_mock" else None)
    return inputs


def _collect_explicit_audit_inputs(args: argparse.Namespace) -> dict[str, object]:
    inputs: dict[str, object] = {}
    for flag, key in (
        ("--scenario", "scenario"),
        ("--scenario-pack-path", "scenario_pack_path"),
        ("--population-pack-path", "population_pack_path"),
        ("--semantic-mode", "semantic_mode"),
        ("--semantic-model", "semantic_model"),
        ("--semantic-profile", "semantic_profile"),
        ("--seed", "seed"),
        ("--target-url", "target_url"),
        ("--reference-artifact-dir", "reference_artifact_dir"),
        ("--use-mock", "use_mock"),
        ("--run-name", "run_name"),
    ):
        if flag in args.provided_options:
            inputs[key] = getattr(args, key, True if key == "use_mock" else None)
    return inputs


def _collect_explicit_compare_inputs(args: argparse.Namespace) -> dict[str, object]:
    inputs: dict[str, object] = {}
    for flag, key in (
        ("--brief", "brief"),
        ("--scenario-pack-path", "scenario_pack_path"),
        ("--population-pack-path", "population_pack_path"),
        ("--generation-mode", "generation_mode"),
        ("--ai-profile", "ai_profile"),
        ("--scenario-count", "scenario_count"),
        ("--population-size", "population_size"),
        ("--population-candidate-count", "population_candidate_count"),
        ("--semantic-mode", "semantic_mode"),
        ("--semantic-model", "semantic_model"),
        ("--semantic-profile", "semantic_profile"),
        ("--seed", "seed"),
        ("--rerun-count", "rerun_count"),
        ("--baseline-artifact-dir", "baseline_artifact_dir"),
        ("--baseline-url", "baseline_url"),
        ("--candidate-artifact-dir", "candidate_artifact_dir"),
        ("--candidate-url", "candidate_url"),
        ("--baseline-label", "baseline_label"),
        ("--candidate-label", "candidate_label"),
        ("--policy-mode", "policy_mode"),
        ("--scenario", "scenario"),
    ):
        if flag in args.provided_options:
            inputs[key] = getattr(args, key)
    return inputs


def _validate_audit_plan_arguments(args: argparse.Namespace) -> None:
    disallowed_flags = (
        "--brief",
        "--generation-mode",
        "--ai-profile",
        "--scenario-count",
        "--population-size",
        "--population-candidate-count",
        "--rerun-count",
        "--baseline-artifact-dir",
        "--baseline-url",
        "--candidate-artifact-dir",
        "--candidate-url",
        "--baseline-label",
        "--candidate-label",
        "--policy-mode",
    )
    for flag in disallowed_flags:
        if flag in args.provided_options:
            raise SystemExit(
                f"`plan-run --workflow audit` does not support `{flag}`."
            )


def _planner_model_summary(
    provider_name: str,
    model_name: str,
    model_profile: str,
) -> str:
    if not model_name:
        return "n/a"
    profile = model_profile or "custom"
    if provider_name:
        return f"{provider_name}/{model_name} ({profile})"
    return f"{model_name} ({profile})"


def _ensure_reused_artifact(path: str | None, *, label: str) -> None:
    resolved = _optional_text(path)
    if not resolved:
        raise SystemExit(f"Saved plan requires a {label}, but no path was provided.")
    if not Path(resolved).exists():
        raise SystemExit(
            f"Saved plan requires {label} at `{resolved}`, but that path does not exist."
        )


def _regression_target_from_plan(payload: dict[str, object]) -> RegressionTarget:
    mode = str(payload.get("mode", ""))
    if mode not in {"reference_artifact", "external_url"}:
        raise SystemExit(f"Saved plan has unsupported compare target mode `{mode}`.")
    return RegressionTarget(
        label=str(payload.get("label", "")),
        mode=mode,
        service_artifact_dir=_optional_text(payload.get("service_artifact_dir")),
        adapter_base_url=_optional_text(payload.get("adapter_base_url")),
    )


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _wait_for_interrupt() -> None:
    """Keep a foreground service command alive until interrupted."""
    while True:
        time.sleep(1.0)


def _count_high_risk_cohorts(run_result) -> int:
    return sum(1 for cohort in run_result.cohort_summaries if cohort.risk_level == "high")


def _audit_launch_status(run_result) -> str:
    high_risk_count = _count_high_risk_cohorts(run_result)
    medium_risk_count = sum(
        1 for cohort in run_result.cohort_summaries if cohort.risk_level == "medium"
    )
    if high_risk_count > 0:
        return "needs review"
    if medium_risk_count > 0 or run_result.risk_flags:
        return "watch"
    return "clear"


def _load_json_summary(path: str) -> dict[str, object]:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _print_summary(title: str, rows: tuple[tuple[str, str], ...]) -> None:
    print(f"{title}:")
    for label, value in rows:
        if value:
            print(f"  {label}: {value}")
