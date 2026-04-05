"""Single-run audit orchestration shared by CLI and regression flows."""

from __future__ import annotations

import json
from contextlib import nullcontext
from datetime import datetime, timezone
from hashlib import sha1
from pathlib import Path

from .adapters.http import HttpRecommenderAdapter
from .agents.recommender import RecommenderAgentPolicy
from .analysis.recommender import RecommenderAnalyzer
from .config import build_default_run_config
from .judges.recommender import RecommenderJudge
from .reporting.chart import CohortChartWriter
from .reporting.json import JsonReportWriter
from .reporting.markdown import MarkdownReportWriter
from .rollout.engine import run_rollouts
from .scenarios.recommender import build_scenarios
from .schema import RunResult
from .services.mock_recommender import run_mock_recommender_service
from .services.reference_artifacts import ensure_reference_artifacts
from .services.reference_recommender import run_reference_recommender_service


def execute_recommender_audit(
    *,
    seed: int = 0,
    output_dir: str | None = None,
    scenario_names: tuple[str, ...] | None = None,
    service_mode: str = "reference",
    service_artifact_dir: str | None = None,
    adapter_base_url: str | None = None,
    run_name: str | None = None,
) -> RunResult:
    """Run one recommender audit and return the in-memory result."""
    resolved_service_mode = "external" if adapter_base_url is not None else service_mode
    run_config = build_default_run_config(
        seed=seed,
        output_dir=output_dir,
        scenario_names=scenario_names,
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
        return _execute_with_adapter(
            run_config=run_config,
            scenarios=scenarios,
            policy=policy,
            judge=judge,
            analyzer=analyzer,
            adapter_base_url=base_url,
        )


def write_run_artifacts(run_result: RunResult) -> dict[str, str]:
    """Write the standard artifact bundle for one audit result."""
    resolved_output_dir = Path(run_result.run_config.rollout.output_dir)
    markdown_paths = MarkdownReportWriter().write(run_result, resolved_output_dir)
    json_paths = JsonReportWriter().write(run_result, resolved_output_dir)
    chart_paths = CohortChartWriter().write(run_result, resolved_output_dir)
    return {**markdown_paths, **json_paths, **chart_paths}


def run_recommender_audit(
    *,
    seed: int = 0,
    output_dir: str | None = None,
    scenario_names: tuple[str, ...] | None = None,
    service_mode: str = "reference",
    service_artifact_dir: str | None = None,
    adapter_base_url: str | None = None,
    run_name: str | None = None,
) -> dict[str, str]:
    """Run the recommender audit and write report artifacts."""
    run_result = execute_recommender_audit(
        seed=seed,
        output_dir=output_dir,
        scenario_names=scenario_names,
        service_mode=service_mode,
        service_artifact_dir=service_artifact_dir,
        adapter_base_url=adapter_base_url,
        run_name=run_name,
    )
    return write_run_artifacts(run_result)


def _execute_with_adapter(
    *,
    run_config,
    scenarios,
    policy,
    judge,
    analyzer,
    adapter_base_url: str,
) -> RunResult:
    """Execute one audit end-to-end against an already running adapter."""
    adapter = HttpRecommenderAdapter(
        adapter_base_url,
        timeout_seconds=run_config.rollout.service_timeout_seconds,
    )
    service_metadata = adapter.get_service_metadata()
    traces = run_rollouts(adapter, scenarios, policy, run_config)
    trace_scores = tuple(judge.score_trace(trace, run_config.scoring) for trace in traces)
    analysis_result = analyzer.analyze(trace_scores, traces, run_config)
    return RunResult(
        run_config=run_config,
        traces=traces,
        trace_scores=trace_scores,
        cohort_summaries=analysis_result.cohort_summaries,
        risk_flags=analysis_result.risk_flags,
        metadata={
            "run_id": _build_run_id(run_config, service_metadata),
            "generated_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
            "display_name": run_config.run_name,
            "adapter": "HttpRecommenderAdapter",
            "adapter_base_url": adapter_base_url,
            "service_mode": run_config.rollout.service_mode,
            "service_artifact_dir": run_config.rollout.service_artifact_dir or "",
            "scenarios": ",".join(config.name for config in run_config.scenarios),
            "agent_policy": "RecommenderAgentPolicy",
            "judge": "RecommenderJudge",
            "analyzer": "RecommenderAnalyzer",
            **service_metadata,
        },
    )


def _build_run_id(run_config, service_metadata: dict[str, str | int | float]) -> str:
    """Build a short stable run identifier from config and service metadata."""
    payload = {
        "run_name": run_config.run_name,
        "seed": run_config.rollout.seed,
        "scenarios": [scenario.name for scenario in run_config.scenarios],
        "service_mode": run_config.rollout.service_mode,
        "artifact_id": service_metadata.get("artifact_id", ""),
        "backend_name": service_metadata.get("backend_name", ""),
    }
    digest = sha1(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()[:12]
    return f"run-{digest}"
