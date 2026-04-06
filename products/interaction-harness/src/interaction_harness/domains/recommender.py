"""Recommender-domain runner and registry wiring."""

from __future__ import annotations

import json
from contextlib import nullcontext
from datetime import datetime, timezone
from hashlib import sha1
from pathlib import Path
from urllib.parse import urlparse

from ..adapters.http import HttpRecommenderAdapter
from ..agents.recommender import RecommenderAgentPolicy
from ..analysis.recommender import RecommenderAnalyzer
from ..config import build_recommender_run_config, slugify_name
from ..judges.recommender import RecommenderJudge
from ..recommender_inputs import resolve_recommender_inputs
from ..rollout.engine import run_rollouts
from ..scenarios.recommender import build_scenarios
from ..schema import RegressionTarget, RunResult
from ..semantic_interpretation import interpret_run_semantics
from ..services.mock_recommender import run_mock_recommender_service
from ..services.reference_artifacts import ensure_reference_artifacts
from ..services.reference_recommender import run_reference_recommender_service
from .base import DomainDefinition

_AUDIT_TITLE = "Interaction Harness Recommender Audit"
_REGRESSION_TITLE = "Interaction Harness Regression Audit"


class RecommenderDomainRunner:
    """Owns recommender-specific runtime orchestration behind the domain seam."""

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
    ) -> RunResult:
        """Run one recommender audit end to end."""
        resolved_service_mode = "external" if adapter_base_url is not None else service_mode
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
        policy = RecommenderAgentPolicy()
        judge = RecommenderJudge()
        analyzer = RecommenderAnalyzer()
        scenarios = build_scenarios(run_config.scenarios)

        if adapter_base_url is not None:
            context = nullcontext((adapter_base_url, {}))
        elif resolved_service_mode == "mock":
            context = run_mock_recommender_service()
        else:
            artifact_path = ensure_reference_artifacts(run_config.rollout.service_artifact_dir)
            context = run_reference_recommender_service(str(artifact_path.parent))

        with context as context_value:
            if resolved_service_mode == "mock":
                base_url = context_value
            else:
                base_url, _metadata = context_value
            return self._execute_with_adapter(
                run_config=run_config,
                scenarios=scenarios,
                policy=policy,
                judge=judge,
                analyzer=analyzer,
                adapter_base_url=base_url,
                resolved_input_metadata=resolved_inputs.metadata,
                semantic_mode=semantic_mode,
                semantic_model=semantic_model,
            )

    def execute_target_audit(
        self,
        *,
        target: RegressionTarget,
        seed: int,
        output_dir: str,
        scenario_names: tuple[str, ...] | None = None,
        population_pack_path: str | None = None,
    ) -> RunResult:
        """Run one regression rerun against an artifact-backed or external target."""
        if target.mode == "reference_artifact":
            if not target.service_artifact_dir:
                raise ValueError("reference_artifact targets require service_artifact_dir.")
            return self.execute_audit(
                seed=seed,
                output_dir=output_dir,
                scenario_names=scenario_names,
                population_pack_path=population_pack_path,
                service_mode="reference",
                service_artifact_dir=target.service_artifact_dir,
                run_name=f"regression-{target.label}-seed-{seed}",
                semantic_mode="off",
            )
        if target.mode == "external_url":
            if not target.adapter_base_url:
                raise ValueError("external_url targets require adapter_base_url.")
            return self.execute_audit(
                seed=seed,
                output_dir=output_dir,
                scenario_names=scenario_names,
                population_pack_path=population_pack_path,
                adapter_base_url=target.adapter_base_url,
                run_name=f"regression-{target.label}-seed-{seed}",
                semantic_mode="off",
            )
        raise NotImplementedError(f"Unsupported regression target mode: {target.mode}")

    def _execute_with_adapter(
        self,
        *,
        run_config,
        scenarios,
        policy,
        judge,
        analyzer,
        adapter_base_url: str,
        resolved_input_metadata: dict[str, str | int] | None = None,
        semantic_mode: str = "off",
        semantic_model: str = "gpt-5",
    ) -> RunResult:
        """Execute one audit against an already running HTTP recommender adapter."""
        adapter = HttpRecommenderAdapter(
            adapter_base_url,
            timeout_seconds=run_config.rollout.service_timeout_seconds,
        )
        service_metadata = adapter.get_service_metadata()
        traces = run_rollouts(adapter, scenarios, policy, run_config)
        trace_scores = tuple(judge.score_trace(trace, run_config.scoring) for trace in traces)
        analysis_result = analyzer.analyze(trace_scores, traces, run_config)
        base_run_result = RunResult(
            run_config=run_config,
            traces=traces,
            trace_scores=trace_scores,
            cohort_summaries=analysis_result.cohort_summaries,
            risk_flags=analysis_result.risk_flags,
            slice_discovery=analysis_result.slice_discovery,
            semantic_interpretation=None,
            metadata={
                "run_id": _build_run_id(run_config, service_metadata),
                "generated_at_utc": datetime.now(timezone.utc)
                .replace(microsecond=0)
                .isoformat(),
                "display_name": run_config.run_name,
                "domain_name": self.definition.name,
                "audit_report_title": self.definition.audit_report_title,
                "regression_report_title": self.definition.regression_report_title,
                "adapter": "HttpRecommenderAdapter",
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
                "agent_policy": "RecommenderAgentPolicy",
                "judge": "RecommenderJudge",
                "analyzer": "RecommenderAnalyzer",
                "slice_count": len(analysis_result.slice_discovery.slice_summaries),
                "semantic_mode": semantic_mode,
                "semantic_model": semantic_model if semantic_mode != "off" else "",
                **service_metadata,
                **(resolved_input_metadata or {}),
            },
        )
        semantic_interpretation = interpret_run_semantics(
            base_run_result,
            mode=semantic_mode,
            model_name=semantic_model,
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


def build_recommender_domain_definition() -> DomainDefinition:
    """Build the internal domain definition for the recommender wedge."""
    definition = DomainDefinition(
        name="recommender",
        audit_report_title=_AUDIT_TITLE,
        regression_report_title=_REGRESSION_TITLE,
        resolve_inputs=resolve_recommender_inputs,
        build_run_config=build_recommender_run_config,
        build_target_identity=build_recommender_target_identity,
        runner=None,  # type: ignore[arg-type]
    )
    runner = RecommenderDomainRunner(definition=definition)
    return DomainDefinition(
        name=definition.name,
        audit_report_title=definition.audit_report_title,
        regression_report_title=definition.regression_report_title,
        resolve_inputs=definition.resolve_inputs,
        build_run_config=definition.build_run_config,
        build_target_identity=definition.build_target_identity,
        runner=runner,
    )


def build_recommender_target_identity(target: RegressionTarget) -> str:
    """Build a short stable identity for recommender compare and audit targets."""
    if target.mode == "external_url":
        normalized_url = (target.adapter_base_url or "").rstrip("/")
        parsed = urlparse(normalized_url)
        label = slugify_name(parsed.netloc or parsed.path or "external")
        raw_identity = normalized_url
        prefix = "url"
    else:
        artifact_dir = str(Path(target.service_artifact_dir or "")).rstrip("/")
        label = slugify_name(Path(artifact_dir).name or "artifact")
        raw_identity = artifact_dir
        prefix = "artifact"
    digest = sha1(raw_identity.encode("utf-8")).hexdigest()[:8]
    return f"{prefix}-{label}-{digest}"


def _build_run_id(run_config, service_metadata: dict[str, str | int | float]) -> str:
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
