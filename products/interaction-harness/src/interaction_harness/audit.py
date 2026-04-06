"""Single-run audit orchestration shared by CLI and regression flows."""

from __future__ import annotations

from pathlib import Path

from .domain_registry import get_domain_definition
from .reporting.chart import CohortChartWriter
from .reporting.json import JsonReportWriter
from .reporting.markdown import MarkdownReportWriter
from .schema import RunResult


def execute_domain_audit(
    *,
    domain_name: str = "recommender",
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
    """Run one audit through the registered in-repo domain plug-in."""
    definition = get_domain_definition(domain_name)
    if definition.runner is None:
        raise ValueError(f"Domain `{domain_name}` is missing a runner.")
    return definition.runner.execute_audit(
        seed=seed,
        output_dir=output_dir,
        scenario_names=scenario_names,
        scenario_pack_path=scenario_pack_path,
        population_pack_path=population_pack_path,
        service_mode=service_mode,
        service_artifact_dir=service_artifact_dir,
        adapter_base_url=adapter_base_url,
        run_name=run_name,
        semantic_mode=semantic_mode,
        semantic_model=semantic_model,
    )


def execute_recommender_audit(
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
    """Run one recommender audit and return the in-memory result."""
    return execute_domain_audit(
        domain_name="recommender",
        seed=seed,
        output_dir=output_dir,
        scenario_names=scenario_names,
        scenario_pack_path=scenario_pack_path,
        population_pack_path=population_pack_path,
        service_mode=service_mode,
        service_artifact_dir=service_artifact_dir,
        adapter_base_url=adapter_base_url,
        run_name=run_name,
        semantic_mode=semantic_mode,
        semantic_model=semantic_model,
    )


def write_run_artifacts(run_result: RunResult) -> dict[str, str]:
    """Write the standard artifact bundle for one audit result."""
    resolved_output_dir = Path(run_result.run_config.rollout.output_dir)
    markdown_paths = MarkdownReportWriter().write(run_result, resolved_output_dir)
    include_slice_membership = bool(
        run_result.metadata.get("include_slice_membership", False)
    )
    json_paths = JsonReportWriter(
        include_slice_membership=include_slice_membership
    ).write(run_result, resolved_output_dir)
    chart_paths = CohortChartWriter().write(run_result, resolved_output_dir)
    return {**markdown_paths, **json_paths, **chart_paths}


def run_recommender_audit(
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
    include_slice_membership: bool = False,
    semantic_mode: str = "off",
    semantic_model: str = "gpt-5",
) -> dict[str, str]:
    """Run the recommender audit and write report artifacts."""
    run_result = execute_recommender_audit(
        seed=seed,
        output_dir=output_dir,
        scenario_names=scenario_names,
        scenario_pack_path=scenario_pack_path,
        population_pack_path=population_pack_path,
        service_mode=service_mode,
        service_artifact_dir=service_artifact_dir,
        adapter_base_url=adapter_base_url,
        run_name=run_name,
        semantic_mode=semantic_mode,
        semantic_model=semantic_model,
    )
    run_result.metadata["include_slice_membership"] = include_slice_membership
    return write_run_artifacts(run_result)
