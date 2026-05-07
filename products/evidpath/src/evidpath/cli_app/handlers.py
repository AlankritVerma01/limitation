"""Command handlers and CLI-to-request mapping for the public CLI."""

from __future__ import annotations

import argparse
from contextlib import suppress

from ..artifacts.run_plan import load_run_plan
from ..config import default_output_dir
from ..domain_registry import get_domain_definition
from ..orchestration import (
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
from ..population_generation import (
    build_default_population_pack_path,
    generate_population_pack,
    write_population_pack,
)
from ..scenario_generation import (
    build_default_scenario_pack_path,
    generate_scenario_pack,
    write_scenario_pack,
)
from ..schema import RegressionTarget
from .progress import ProgressCallback, emit_progress
from .support import (
    audit_launch_status,
    count_high_risk_cohorts,
    load_json_summary,
    planner_model_summary,
    print_summary,
    wait_for_interrupt,
)


def _plan_ready_rows(workflow: str, plan) -> tuple[tuple[str, str], ...]:
    rows: list[tuple[str, str]] = [
        ("Workflow", workflow),
        ("Coverage source", plan.coverage_source),
        ("Scenario generation", plan.scenario_generation_mode),
        ("Swarm generation", plan.swarm_generation_mode),
        ("Planner mode", plan.planner_mode),
    ]
    if workflow != "audit":
        rows.append(
            (
                "Planner model",
                planner_model_summary(
                    plan.planner_provider_name,
                    plan.planner_model_name,
                    plan.planner_model_profile,
                ),
            )
        )
    rows.extend(
        [
            ("Planned scenario pack", plan.scenario_pack_path or ""),
            ("Planned swarm pack", plan.population_pack_path or ""),
            ("Run plan", plan.plan_path),
        ]
    )
    return tuple(rows)


def handle_plan_run_command(
    args: argparse.Namespace,
    progress_callback: ProgressCallback,
) -> dict[str, str | int]:
    if args.workflow == "audit":
        _validate_audit_plan_arguments(args)
        context = _build_audit_plan_from_args(args)
        plan = context.plan
        print_summary("Run plan ready", _plan_ready_rows("audit", plan))
        return {"run_plan_path": plan.plan_path, "plan_id": plan.plan_id}
    if args.workflow == "run-swarm":
        context = _build_run_swarm_plan_from_args(args)
        plan = context.plan
        print_summary("Run plan ready", _plan_ready_rows("run-swarm", plan))
        return {"run_plan_path": plan.plan_path, "plan_id": plan.plan_id}
    if args.workflow == "compare":
        context = _build_compare_plan_from_args(args)
        plan = context.plan
        print_summary("Run plan ready", _plan_ready_rows("compare", plan))
        return {"run_plan_path": plan.plan_path, "plan_id": plan.plan_id}
    raise SystemExit(f"Unsupported workflow `{args.workflow}` for `plan-run`.")


def handle_execute_plan_command(
    args: argparse.Namespace,
    progress_callback: ProgressCallback,
) -> dict[str, str | int]:
    plan = load_run_plan(args.run_plan_path)
    workflow_type = str(plan.payload.get("workflow_type", ""))
    if workflow_type == "run-swarm":
        return execute_saved_run_swarm_plan(
            args.run_plan_path,
            progress_callback=progress_callback,
        ).result
    if workflow_type == "audit":
        return execute_saved_audit_plan(
            args.run_plan_path,
            progress_callback=progress_callback,
        ).result
    if workflow_type == "compare":
        return execute_saved_compare_plan(
            args.run_plan_path,
            progress_callback=progress_callback,
        ).result
    raise SystemExit(f"Unsupported workflow `{workflow_type}` in saved run plan.")


def handle_audit_command(
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
    print_summary(
        "Audit complete",
        (
            ("Launch status", audit_launch_status(run_result)),
            ("High-risk cohorts", str(count_high_risk_cohorts(run_result))),
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


def handle_run_swarm_command(
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
    run_result = outcome.run_result
    print_summary(
        "Swarm run complete",
        (
            ("Coverage source", outcome.coverage_source),
            ("Scenario generation", outcome.scenario_generation_mode),
            ("Swarm generation", outcome.swarm_generation_mode),
            ("AI profile", context.plan.ai_profile if outcome.coverage_source != "reused" else "n/a"),
            ("Planner mode", context.plan.planner_mode),
            (
                "Planner model",
                planner_model_summary(
                    context.plan.planner_provider_name,
                    context.plan.planner_model_name,
                    context.plan.planner_model_profile,
                ),
            ),
            ("Launch status", audit_launch_status(run_result)),
            ("High-risk cohorts", str(count_high_risk_cohorts(run_result))),
            ("Service kind", str(run_result.metadata.get("service_kind", ""))),
            ("Dataset", str(run_result.metadata.get("dataset", ""))),
            ("Model kind", str(run_result.metadata.get("model_kind", ""))),
            ("Model ID", str(run_result.metadata.get("model_id", ""))),
            ("Saved scenario pack", outcome.scenario_pack_path),
            ("Saved swarm pack", outcome.population_pack_path),
            ("Run plan", context.plan.plan_path),
            ("Open report", str(outcome.result["report_path"])),
            ("Machine-readable results", str(outcome.result["results_path"])),
            ("Full traces", str(outcome.result["traces_path"])),
            ("Run manifest", outcome.manifest_path),
        ),
    )
    return outcome.result


def handle_check_target_command(
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
    print_summary(
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


def handle_compare_command(
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
    regression_summary = load_json_summary(str(outcome.result["regression_summary_path"]))
    summary_block = regression_summary.get("summary", {}) if isinstance(regression_summary, dict) else {}
    print_summary(
        "Compare complete",
        (
            ("Decision", str(outcome.result["decision_status"]).upper()),
            ("Overall direction", str(summary_block.get("overall_direction", ""))),
            ("Risk flags added", str(summary_block.get("added_risk_flag_count", ""))),
            ("Coverage source", outcome.coverage_source),
            ("Scenario generation", outcome.scenario_generation_mode),
            ("Swarm generation", outcome.swarm_generation_mode),
            ("Planner mode", context.plan.planner_mode),
            (
                "Planner model",
                planner_model_summary(
                    context.plan.planner_provider_name,
                    context.plan.planner_model_name,
                    context.plan.planner_model_profile,
                ),
            ),
            ("Exit code", str(outcome.result["exit_code"])),
            ("Run plan", context.plan.plan_path),
            ("Open regression report", str(outcome.result["regression_report_path"])),
            ("Machine-readable summary", str(outcome.result["regression_summary_path"])),
            ("Regression traces", str(outcome.result["regression_traces_path"])),
            ("Run manifest", str(outcome.result["run_manifest_path"])),
        ),
    )
    return outcome.result


def handle_generate_scenarios_command(
    args: argparse.Namespace,
    progress_callback: ProgressCallback,
) -> dict[str, str | int]:
    output_root = args.output_dir or str(default_output_dir())
    scenario_pack_path = args.scenario_pack_path or build_default_scenario_pack_path(
        output_root,
        brief=args.brief,
        generator_mode=args.mode,
    )
    pack = generate_scenario_pack(
        args.brief,
        generator_mode=args.mode,
        scenario_count=args.scenario_count,
        domain_label=args.domain,
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
    print_summary(
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


def handle_generate_population_command(
    args: argparse.Namespace,
    progress_callback: ProgressCallback,
) -> dict[str, str | int]:
    output_root = args.output_dir or str(default_output_dir())
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
        domain_label=args.domain,
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
    print_summary(
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


def handle_serve_reference_command(
    args: argparse.Namespace,
    progress_callback: ProgressCallback,
) -> dict[str, str | int]:
    definition = get_domain_definition(args.domain)
    if definition.run_reference_service is None:
        raise SystemExit(f"`serve-reference` is not supported for domain `{args.domain}`.")
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
        print_summary(
            "Reference service ready",
            (
                ("Base URL", base_url),
                ("Health URL", f"{base_url}/health"),
                ("Metadata URL", f"{base_url}/metadata"),
                ("Artifact ID", str(metadata.get("artifact_id", ""))),
                ("Service kind", str(metadata.get("service_kind", ""))),
                ("Contract version", str(metadata.get("artifact_contract_version", ""))),
            ),
        )
        with suppress(KeyboardInterrupt):
            wait_for_interrupt()
    return {
        "base_url": base_url,
        "artifact_id": str(metadata.get("artifact_id", "")),
        "service_kind": str(metadata.get("service_kind", "")),
        "artifact_contract_version": str(metadata.get("artifact_contract_version", "")),
    }


def _build_run_swarm_plan_from_args(args: argparse.Namespace):
    if not args.brief:
        raise SystemExit("`plan-run --workflow run-swarm` requires `--brief`.")
    service_mode, service_artifact_dir, adapter_base_url = _resolve_target_selection(
        args,
        domain_name=args.domain,
    )
    output_root = args.output_dir or str(default_output_dir())
    return plan_run_swarm(
        RunSwarmPlanRequest(
            domain_name=args.domain,
            brief=args.brief,
            generation_mode=args.generation_mode,
            output_root=output_root,
            target_config=_build_direct_target_plan_config(
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
            default_scenario_pack_path=build_default_scenario_pack_path(
                output_root,
                brief=args.brief,
                generator_mode=args.generation_mode,
            ),
            default_population_pack_path=build_default_population_pack_path(
                output_root,
                brief=args.brief,
                generator_mode=args.generation_mode,
            ),
        )
    )


def _build_audit_plan_from_args(args: argparse.Namespace):
    service_mode, service_artifact_dir, adapter_base_url = _resolve_target_selection(
        args,
        domain_name=args.domain,
    )
    output_root = args.output_dir or str(default_output_dir())
    return plan_audit(
        AuditPlanRequest(
            domain_name=args.domain,
            output_root=output_root,
            target_config=_build_direct_target_plan_config(
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


def _build_compare_plan_from_args(args: argparse.Namespace):
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
    output_root = args.output_dir or str(default_output_dir())
    return plan_compare(
        ComparePlanRequest(
            domain_name=args.domain,
            brief=args.brief,
            generation_mode=args.generation_mode,
            output_root=output_root,
            baseline_target_config=_build_compare_target_plan_config(baseline_target),
            candidate_target_config=_build_compare_target_plan_config(candidate_target),
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
            default_scenario_pack_path=(
                build_default_scenario_pack_path(
                    output_root,
                    brief=args.brief,
                    generator_mode=args.generation_mode,
                )
                if args.brief
                else None
            ),
            default_population_pack_path=(
                build_default_population_pack_path(
                    output_root,
                    brief=args.brief,
                    generator_mode=args.generation_mode,
                )
                if args.brief
                else None
            ),
            scenario_name=args.scenario,
            baseline_target=baseline_target,
            candidate_target=candidate_target,
        )
    )


def _resolve_target_selection(
    args: argparse.Namespace,
    *,
    domain_name: str,
) -> tuple[str, str | None, str | None]:
    if args.target_url is not None and args.use_mock:
        raise SystemExit("--target-url cannot be combined with --use-mock.")
    if args.target_url is not None and args.reference_artifact_dir is not None:
        raise SystemExit("--target-url cannot be combined with --reference-artifact-dir.")
    if args.use_mock:
        if domain_name != "recommender":
            raise SystemExit("--use-mock is only supported for the recommender domain.")
        return "mock", None, None
    if args.target_url is not None:
        # The domain runtime still represents external HTTP targets as the
        # reference service mode plus an adapter URL. Keep that runtime contract
        # unchanged while keeping the CLI wording explicit about the customer path.
        return "reference", None, args.target_url
    return "reference", args.reference_artifact_dir, None


def _build_compare_target(
    *,
    label: str,
    artifact_dir: str | None,
    url: str | None,
    side_name: str,
) -> RegressionTarget:
    has_artifact = artifact_dir is not None
    has_url = url is not None
    if has_artifact == has_url:
        raise SystemExit(
            f"compare requires exactly one of --{side_name}-artifact-dir or --{side_name}-url."
        )
    if has_artifact:
        return RegressionTarget(
            label=label,
            driver_kind="http_native_reference",
            driver_config={"artifact_dir": artifact_dir or ""},
        )
    return RegressionTarget(
        label=label,
        driver_kind="http_native_external",
        driver_config={"base_url": url or ""},
    )


def _build_direct_target_plan_config(
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


def _build_compare_target_plan_config(target: RegressionTarget) -> dict[str, object]:
    return {
        "label": target.label,
        "driver_kind": target.driver_kind,
        "driver_config": dict(target.driver_config),
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
    for flag in (
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
    ):
        if flag in args.provided_options:
            raise SystemExit(f"`plan-run --workflow audit` does not support `{flag}`.")


COMMAND_HANDLERS = {
    "audit": handle_audit_command,
    "run_swarm": handle_run_swarm_command,
    "compare": handle_compare_command,
    "plan_run": handle_plan_run_command,
    "execute_plan": handle_execute_plan_command,
    "check_target": handle_check_target_command,
    "generate_scenarios": handle_generate_scenarios_command,
    "generate_population": handle_generate_population_command,
    "serve_reference": handle_serve_reference_command,
}
