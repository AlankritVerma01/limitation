"""Internal domain plug-in contracts and the minimal shared runner shell.

This module is intentionally the narrowest generic layer for domain execution.
It should own only durable harness mechanics that we expect to reuse across
many domains. Domain-specific behavior should plug in through `DomainDefinition`
hooks rather than accumulating here as conditional logic.

Practical rule:
- keep the foundation small and durable
- let real domains stay rich and cross-cutting
- do not move behavior here just because one domain uses it in many places
"""

from __future__ import annotations

import json
from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha1
from typing import Callable, Protocol

from ..adapters.base import SystemAdapter
from ..agents.base import AgentPolicy
from ..analysis.base import Analyzer
from ..cli_progress import ProgressCallback, emit_progress
from ..judges.base import Judge
from ..reporting.base import DomainReportingHooks
from ..rollout.engine import run_rollouts
from ..scenarios.base import Scenario
from ..schema import (
    AgentSeed,
    CohortSummary,
    GeneratedPersona,
    RegressionDiff,
    RegressionPolicy,
    RegressionPolicyOverride,
    RegressionTarget,
    RunConfig,
    RunResult,
    ScenarioConfig,
)
from ..semantic_interpretation import interpret_run_semantics


class MetadataAdapter(SystemAdapter, Protocol):
    """Adapter protocol with both rollout and service-metadata hooks."""

    def get_service_metadata(self) -> dict[str, str | int | float]:
        """Return stable metadata about the current system under test."""


@dataclass(frozen=True)
class ResolvedRuntimeInputs:
    """Resolved runtime inputs produced by one domain module.

    This is the boundary between domain-specific input semantics and the shared
    run-config / rollout layers.
    """

    scenarios: tuple[ScenarioConfig, ...]
    agent_seeds: tuple[AgentSeed, ...]
    metadata: dict[str, str | int]


class DomainRunner(Protocol):
    """Domain-owned execution seam used by audit and regression orchestration."""

    def execute_audit(
        self,
        *,
        seed: int = 0,
        output_dir: str | None = None,
        scenario_names: tuple[str, ...] | None = None,
        scenario_pack_path: str | None = None,
        population_pack_path: str | None = None,
        service_mode: str = "reference",
        service_artifact_dir: str | None = None,
        adapter_base_url: str | None = None,
        run_name: str | None = None,
        semantic_mode: str = "off",
        semantic_model: str = "gpt-5",
        progress_callback: ProgressCallback | None = None,
    ) -> RunResult:
        """Run one audit and return the in-memory result."""

    def execute_target_audit(
        self,
        *,
        target: RegressionTarget,
        seed: int,
        output_dir: str,
        scenario_names: tuple[str, ...] | None = None,
        scenario_pack_path: str | None = None,
        population_pack_path: str | None = None,
        progress_callback: ProgressCallback | None = None,
        ) -> RunResult:
        """Run one regression rerun against a concrete target."""


@dataclass(frozen=True)
class DomainGenerationHooks:
    """Domain-owned generation semantics used by the shared generation shell."""

    build_scenario_brief_clarification: Callable[[str], str | None] | None = None
    build_fixture_scenarios: Callable[[str, int], list[dict[str, object]]] | None = None
    build_scenario_prompt: Callable[[str, int, str], str] | None = None
    build_population_brief_clarification: Callable[[str], str | None] | None = None
    build_fixture_population_candidates: Callable[
        [str, int], tuple[dict[str, object], ...]
    ] | None = None
    build_population_prompt: Callable[[str, int, str], str] | None = None
    select_population_personas: Callable[
        [tuple[GeneratedPersona, ...], int],
        tuple[GeneratedPersona, ...],
    ] | None = None


@dataclass(frozen=True)
class DomainDefinition:
    """Static in-repo plug-in contract for one supported domain.

    The rule for this contract is:
    - shared shells may call these hooks
    - shared shells should not know how a particular domain implements them

    In practice that means new domains should mostly be added by implementing
    this contract in a new module, not by editing the shared orchestration
    layer.
    """

    name: str
    audit_report_title: str
    regression_report_title: str
    resolve_inputs: Callable[..., ResolvedRuntimeInputs]
    build_run_config: Callable[..., tuple[RunConfig, ResolvedRuntimeInputs]]
    build_target_identity: Callable[[RegressionTarget], str]
    build_target_audit_kwargs: Callable[[RegressionTarget], dict[str, object]]
    build_runtime_scenarios: Callable[[tuple[ScenarioConfig, ...]], tuple[Scenario, ...]]
    open_service_context: Callable[
        [RunConfig],
        AbstractContextManager[tuple[str, dict[str, str | int | float]]],
    ]
    build_adapter: Callable[[str, float], MetadataAdapter]
    build_policy: Callable[[], AgentPolicy]
    build_judge: Callable[[], Judge]
    build_analyzer: Callable[[], Analyzer]
    summary_metric_names: tuple[str, ...]
    summarize_run_metrics: Callable[[RunResult], dict[str, float]]
    build_default_regression_policy: Callable[
        [tuple[RegressionPolicyOverride, ...], tuple[RegressionPolicyOverride, ...]],
        RegressionPolicy,
    ]
    public: bool = True
    generation_hooks: DomainGenerationHooks | None = None
    run_reference_service: Callable[
        [str | None],
        AbstractContextManager[tuple[str, dict[str, str | int | float]]],
    ] | None = None
    reporting_hooks: DomainReportingHooks | None = None
    build_run_executive_summary: Callable[[RunResult], list[str]] | None = None
    select_representative_cohorts: Callable[
        [RunResult],
        tuple[tuple[CohortSummary, ...], tuple[CohortSummary, ...]],
    ] | None = None
    build_regression_summary: Callable[[RegressionDiff], dict[str, object]] | None = None
    build_regression_important_changes: Callable[[RegressionDiff], list[str]] | None = None
    runner: DomainRunner | None = None


class StandardDomainRunner:
    """Shared orchestration shell for in-repo domain plug-ins.

    This runner should stay small. If adding a new domain requires branching
    logic here, that is a sign the relevant behavior probably belongs behind a
    `DomainDefinition` hook instead.
    """

    def __init__(self, *, definition: DomainDefinition) -> None:
        self.definition = definition

    def execute_audit(
        self,
        *,
        seed: int = 0,
        output_dir: str | None = None,
        scenario_names: tuple[str, ...] | None = None,
        scenario_pack_path: str | None = None,
        population_pack_path: str | None = None,
        service_mode: str = "reference",
        service_artifact_dir: str | None = None,
        adapter_base_url: str | None = None,
        run_name: str | None = None,
        semantic_mode: str = "off",
        semantic_model: str = "gpt-5",
        progress_callback: ProgressCallback | None = None,
    ) -> RunResult:
        """Run one audit using only the domain-owned plug-in hooks."""
        resolved_service_mode = "external" if adapter_base_url is not None else service_mode
        emit_progress(
            progress_callback,
            phase="resolve_inputs",
            message="Resolving scenarios and population",
            stage="start",
        )
        run_config, resolved_inputs = self.definition.build_run_config(
            seed=seed,
            output_dir=output_dir,
            scenario_names=scenario_names,
            scenario_pack_path=scenario_pack_path,
            population_pack_path=population_pack_path,
            service_mode=resolved_service_mode,
            service_artifact_dir=service_artifact_dir,
            adapter_base_url=adapter_base_url,
            run_name=run_name,
        )
        policy = self.definition.build_policy()
        judge = self.definition.build_judge()
        analyzer = self.definition.build_analyzer()
        scenarios = self.definition.build_runtime_scenarios(run_config.scenarios)
        emit_progress(
            progress_callback,
            phase="resolve_inputs",
            message="Resolved scenarios and population",
            stage="finish",
        )

        emit_progress(
            progress_callback,
            phase="prepare_target",
            message="Preparing target",
            stage="start",
        )
        with self.definition.open_service_context(run_config) as (base_url, context_metadata):
            return self._execute_with_adapter(
                run_config=run_config,
                scenarios=scenarios,
                policy=policy,
                judge=judge,
                analyzer=analyzer,
                adapter_base_url=base_url,
                context_metadata=context_metadata,
                resolved_input_metadata=resolved_inputs.metadata,
                semantic_mode=semantic_mode,
                semantic_model=semantic_model,
                progress_callback=progress_callback,
            )

    def execute_target_audit(
        self,
        *,
        target: RegressionTarget,
        seed: int,
        output_dir: str,
        scenario_names: tuple[str, ...] | None = None,
        scenario_pack_path: str | None = None,
        population_pack_path: str | None = None,
        progress_callback: ProgressCallback | None = None,
    ) -> RunResult:
        """Run one regression rerun against one target using the shared shell."""
        audit_kwargs: dict[str, object] = {
            "seed": seed,
            "output_dir": output_dir,
            "scenario_names": scenario_names,
            "scenario_pack_path": scenario_pack_path,
            "population_pack_path": population_pack_path,
            "run_name": f"regression-{target.label}-seed-{seed}",
            "semantic_mode": "off",
        }
        audit_kwargs.update(self.definition.build_target_audit_kwargs(target))
        return self.execute_audit(**audit_kwargs, progress_callback=progress_callback)

    def _execute_with_adapter(
        self,
        *,
        run_config: RunConfig,
        scenarios: tuple[Scenario, ...],
        policy: AgentPolicy,
        judge: Judge,
        analyzer: Analyzer,
        adapter_base_url: str,
        context_metadata: dict[str, str | int | float] | None = None,
        resolved_input_metadata: dict[str, str | int] | None = None,
        semantic_mode: str = "off",
        semantic_model: str = "gpt-5",
        progress_callback: ProgressCallback | None = None,
    ) -> RunResult:
        """Execute one audit against an already running domain adapter."""
        adapter = self.definition.build_adapter(
            adapter_base_url,
            run_config.rollout.service_timeout_seconds,
        )
        service_metadata = adapter.get_service_metadata()
        emit_progress(
            progress_callback,
            phase="prepare_target",
            message="Prepared target",
            stage="finish",
        )
        combined_service_metadata = {
            **(context_metadata or {}),
            **service_metadata,
        }
        if service_metadata:
            combined_service_metadata["service_metadata_status"] = "available"
        elif "service_metadata_status" not in combined_service_metadata:
            combined_service_metadata["service_metadata_status"] = (
                "unavailable"
            )
        traces = run_rollouts(
            adapter,
            scenarios,
            policy,
            run_config,
            progress_callback=progress_callback,
        )
        emit_progress(
            progress_callback,
            phase="score_traces",
            message="Scoring traces",
            stage="start",
        )
        trace_scores: list = []
        for index, trace in enumerate(traces, start=1):
            trace_scores.append(judge.score_trace(trace, run_config.scoring))
            emit_progress(
                progress_callback,
                phase="score_traces",
                message="Scoring traces",
                stage="update",
                current=index,
                total=len(traces),
            )
        emit_progress(
            progress_callback,
            phase="score_traces",
            message="Scored traces",
            stage="finish",
        )
        emit_progress(
            progress_callback,
            phase="analyze_run",
            message="Analyzing cohorts and slices",
            stage="start",
        )
        analysis_result = analyzer.analyze(tuple(trace_scores), traces, run_config)
        emit_progress(
            progress_callback,
            phase="analyze_run",
            message="Analyzed cohorts and slices",
            stage="finish",
        )
        base_run_result = RunResult(
            run_config=run_config,
            traces=traces,
            trace_scores=tuple(trace_scores),
            cohort_summaries=analysis_result.cohort_summaries,
            risk_flags=analysis_result.risk_flags,
            slice_discovery=analysis_result.slice_discovery,
            semantic_interpretation=None,
            metadata={
                "run_id": _build_run_id(run_config, combined_service_metadata),
                "generated_at_utc": datetime.now(timezone.utc)
                .replace(microsecond=0)
                .isoformat(),
                "display_name": run_config.run_name,
                "domain_name": self.definition.name,
                "audit_report_title": self.definition.audit_report_title,
                "regression_report_title": self.definition.regression_report_title,
                "adapter": type(adapter).__name__,
                "adapter_base_url": adapter_base_url,
                "service_mode": run_config.rollout.service_mode,
                "service_artifact_dir": run_config.rollout.service_artifact_dir or "",
                "target_mode": (
                    "external_url"
                    if run_config.rollout.adapter_base_url is not None
                    else "reference_artifact"
                ),
                "target_identity": self.definition.build_target_identity(
                    RegressionTarget(
                        label=run_config.run_name,
                        mode=(
                            "external_url"
                            if run_config.rollout.adapter_base_url is not None
                            else "reference_artifact"
                        ),
                        service_artifact_dir=run_config.rollout.service_artifact_dir,
                        adapter_base_url=run_config.rollout.adapter_base_url,
                    )
                ),
                "scenarios": ",".join(config.name for config in run_config.scenarios),
                "agent_count": len(run_config.agent_seeds),
                "agent_policy": type(policy).__name__,
                "judge": type(judge).__name__,
                "analyzer": type(analyzer).__name__,
                "slice_count": len(analysis_result.slice_discovery.slice_summaries),
                "semantic_mode": semantic_mode,
                "semantic_model": semantic_model if semantic_mode != "off" else "",
                "artifact_contract_version": "v1",
                **combined_service_metadata,
                **(resolved_input_metadata or {}),
            },
        )
        emit_progress(
            progress_callback,
            phase="interpret_semantics",
            message="Interpreting semantics",
            stage="start",
        )
        semantic_interpretation = interpret_run_semantics(
            base_run_result,
            mode=semantic_mode,
            model_name=semantic_model,
        )
        emit_progress(
            progress_callback,
            phase="interpret_semantics",
            message=(
                "Semantic interpretation skipped"
                if semantic_mode == "off"
                else "Interpreted semantics"
            ),
            stage="finish",
        )
        return RunResult(
            run_config=base_run_result.run_config,
            traces=base_run_result.traces,
            trace_scores=base_run_result.trace_scores,
            cohort_summaries=base_run_result.cohort_summaries,
            risk_flags=base_run_result.risk_flags,
            slice_discovery=base_run_result.slice_discovery,
            semantic_interpretation=semantic_interpretation,
            metadata={
                **base_run_result.metadata,
                "semantic_provider_name": (
                    semantic_interpretation.provider_name if semantic_interpretation else ""
                ),
            },
        )


def _build_run_id(run_config: RunConfig, service_metadata: dict[str, str | int | float]) -> str:
    """Build a short stable run identifier from config and service metadata."""
    payload = {
        "run_name": run_config.run_name,
        "seed": run_config.rollout.seed,
        "scenarios": [scenario.name for scenario in run_config.scenarios],
        "agent_ids": [seed.agent_id for seed in run_config.agent_seeds],
        "service_mode": run_config.rollout.service_mode,
        "artifact_id": service_metadata.get("artifact_id", ""),
        "backend_name": service_metadata.get("backend_name", ""),
    }
    digest = sha1(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()[:12]
    return f"run-{digest}"
