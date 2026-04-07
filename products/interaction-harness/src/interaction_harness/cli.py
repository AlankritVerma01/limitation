"""CLI-first entrypoint for the supported recommender audit workflow.

The CLI is the main user-facing surface today. It keeps the deterministic
runtime and regression flow explicit while offering optional AI-backed authoring
and advisory interpretation on top.
"""

from __future__ import annotations

import argparse
import sys
import time
from contextlib import suppress

from .audit import (
    execute_domain_audit,
    write_run_artifacts,
)
from .audit import (
    run_recommender_audit as _run_recommender_audit,
)
from .cli_progress import ProgressCallback, TerminalProgressRenderer, emit_progress
from .config import DEFAULT_OUTPUT_DIR
from .domain_registry import get_domain_definition, list_public_domain_definitions
from .population_generation import (
    build_default_population_pack_path,
    generate_population_pack,
    write_population_pack,
)
from .regression import run_domain_regression_audit
from .scenario_generation import (
    DEFAULT_PROVIDER_MODEL,
    build_default_scenario_pack_path,
    generate_scenario_pack,
    write_scenario_pack,
)
from .schema import RegressionTarget

run_recommender_audit = _run_recommender_audit


def _build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser for the supported recommender workflows."""
    parser = argparse.ArgumentParser(
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=(
            "Run interaction-harness workflows through the shared CLI.\n\n"
            "Canonical usage now includes `--domain` on every command.\n"
            "During the compatibility phase, omitted domains still default to `recommender`.\n\n"
            "Recommended paths:\n"
            "- `audit --domain recommender`: local reference recommender or an external URL\n"
            "- `compare --domain recommender`: artifact-backed baselines/candidates or external URLs\n"
            "- `generate-scenarios --domain recommender` / `generate-population --domain recommender`\n"
            "- `serve-reference --domain recommender`: explicit local reference-service workflow\n\n"
            "The runtime and regression core stay deterministic."
        ),
    )
    subparsers = parser.add_subparsers(dest="command", metavar="command")

    _build_audit_parser(subparsers)
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
        help="Run a recommender audit and write the standard artifact bundle.",
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
            "Existing recommender endpoint to audit. If omitted, the local reference "
            "service is used by default."
        ),
    )
    parser.add_argument(
        "--reference-artifact-dir",
        default=None,
        help=(
            "Optional artifact directory for the local reference recommender target. "
            "This is an advanced override for the supported local path."
        ),
    )
    parser.add_argument(
        "--use-mock",
        action="store_true",
        help="Use the mock recommender only for narrow test/debug runs.",
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


def _build_compare_parser(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> argparse.ArgumentParser:
    parser = subparsers.add_parser(
        "compare",
        help="Compare baseline and candidate recommender targets across reruns.",
        description=(
            "Run regression compare mode for artifact-backed or external-URL targets."
        ),
    )
    parser.set_defaults(handler=_handle_compare_command)
    _add_shared_run_arguments(parser)
    parser.add_argument(
        "--baseline-artifact-dir",
        default=None,
        help="Artifact directory for the baseline reference target.",
    )
    parser.add_argument(
        "--baseline-url",
        default=None,
        help="External recommender URL for the baseline target.",
    )
    parser.add_argument(
        "--candidate-artifact-dir",
        default=None,
        help="Artifact directory for the candidate reference target.",
    )
    parser.add_argument(
        "--candidate-url",
        default=None,
        help="External recommender URL for the candidate target.",
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
    return parser


def _build_generate_scenarios_parser(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> argparse.ArgumentParser:
    parser = subparsers.add_parser(
        "generate-scenarios",
        help="Generate and save a structured recommender scenario pack.",
        description=(
            "Generate a structured scenario pack for one domain. Use `provider` for "
            "richer authored workflows and `fixture` for deterministic CI/demo runs."
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
        help="Generation mode.",
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_PROVIDER_MODEL,
        help="Provider model name used when mode is `provider`.",
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
        help="Generate and save a structured recommender population pack.",
        description=(
            "Generate a structured population pack for one domain. Use `provider` for "
            "richer authored workflows and `fixture` for deterministic CI/demo runs."
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
        help="Generation mode.",
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_PROVIDER_MODEL,
        help="Provider model name used when mode is `provider`.",
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
        help="Start the local reference recommender service and print its URL.",
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
    return parser


def _add_shared_run_arguments(parser: argparse.ArgumentParser) -> None:
    _add_domain_argument(parser)
    parser.add_argument("--seed", type=int, default=0, help="Seed for deterministic rollouts.")
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Optional output directory override for the generated artifact bundle.",
    )
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
        "--semantic-model",
        default=DEFAULT_PROVIDER_MODEL,
        help="Provider model name used when semantic mode is `provider`.",
    )


def _add_domain_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--domain",
        default=None,
        choices=list_public_domain_definitions(),
        help=(
            "Supported domain for this command. Canonical usage includes this flag; "
            "omitting it still defaults to `recommender` during the compatibility phase."
        ),
    )


def main(argv: list[str] | None = None) -> dict[str, str | int]:
    """Run the CLI entrypoint and return the generated artifact paths."""
    raw_argv = list(argv) if argv is not None else sys.argv[1:]
    if not raw_argv:
        raw_argv = ["audit"]
    parser = _build_parser()
    args = parser.parse_args(raw_argv)
    handler = getattr(args, "handler", None)
    if handler is None:
        parser.print_help()
        raise SystemExit(0)

    progress = TerminalProgressRenderer()
    try:
        return handler(args, progress)
    finally:
        progress.close()


def _handle_audit_command(
    args: argparse.Namespace,
    progress_callback: ProgressCallback,
) -> dict[str, str | int]:
    domain_name = _resolve_domain_name(args.domain)
    scenario_names = _resolve_scenario_names(args.scenario)
    service_mode, service_artifact_dir, adapter_base_url = _resolve_audit_target(
        args,
        domain_name=domain_name,
    )
    run_result = execute_domain_audit(
        domain_name=domain_name,
        seed=args.seed,
        output_dir=args.output_dir,
        scenario_names=scenario_names,
        scenario_pack_path=args.scenario_pack_path,
        population_pack_path=args.population_pack_path,
        service_mode=service_mode,
        service_artifact_dir=service_artifact_dir,
        adapter_base_url=adapter_base_url,
        run_name=args.run_name,
        semantic_mode=args.semantic_mode,
        semantic_model=args.semantic_model,
        progress_callback=progress_callback,
    )
    run_result.metadata["include_slice_membership"] = args.include_slice_membership
    result = write_run_artifacts(run_result, progress_callback=progress_callback)
    _print_summary(
        "Audit complete",
        (
            ("Report", str(result["report_path"])),
            ("Results", str(result["results_path"])),
            ("Traces", str(result["traces_path"])),
            ("Chart", str(result["chart_path"])),
        ),
    )
    return result


def _handle_compare_command(
    args: argparse.Namespace,
    progress_callback: ProgressCallback,
) -> dict[str, str | int]:
    domain_name = _resolve_domain_name(args.domain)
    scenario_names = _resolve_scenario_names(args.scenario)
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
    result = run_domain_regression_audit(
        domain_name=domain_name,
        baseline_target=baseline_target,
        candidate_target=candidate_target,
        base_seed=args.seed,
        rerun_count=args.rerun_count,
        output_dir=args.output_dir,
        scenario_names=scenario_names,
        scenario_pack_path=args.scenario_pack_path,
        population_pack_path=args.population_pack_path,
        semantic_mode=args.semantic_mode,
        semantic_model=args.semantic_model,
        policy_mode=args.policy_mode,
        progress_callback=progress_callback,
    )
    _print_summary(
        "Compare complete",
        (
            ("Decision", str(result["decision_status"]).upper()),
            ("Exit code", str(result["exit_code"])),
            ("Regression report", str(result["regression_report_path"])),
            ("Regression summary", str(result["regression_summary_path"])),
            ("Regression traces", str(result["regression_traces_path"])),
        ),
    )
    return result


def _handle_generate_scenarios_command(
    args: argparse.Namespace,
    progress_callback: ProgressCallback,
) -> dict[str, str | int]:
    output_root = args.output_dir or str(DEFAULT_OUTPUT_DIR)
    domain_name = _resolve_domain_name(args.domain)
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
            ("Scenario pack", saved_path),
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
    domain_name = _resolve_domain_name(args.domain)
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
            ("Population pack", saved_path),
            ("Selected personas", str(pack.metadata.selected_count)),
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
    domain_name = _resolve_domain_name(args.domain)
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
    with definition.run_reference_service(args.artifact_dir) as (base_url, metadata):
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


def _resolve_domain_name(domain_name: str | None) -> str:
    return domain_name or "recommender"


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


def _wait_for_interrupt() -> None:
    """Keep a foreground service command alive until interrupted."""
    while True:
        time.sleep(1.0)


def _print_summary(title: str, rows: tuple[tuple[str, str], ...]) -> None:
    print(f"{title}:")
    for label, value in rows:
        if value:
            print(f"  {label}: {value}")
