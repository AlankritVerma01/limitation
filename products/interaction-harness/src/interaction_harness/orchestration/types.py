"""Normalized orchestration request and result types."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..artifacts.run_plan import PlannedWorkflow
from ..schema import RegressionTarget, RunResult


@dataclass(frozen=True)
class AuditPlanRequest:
    domain_name: str
    output_root: str
    target_config: dict[str, str]
    explicit_inputs: dict[str, Any]
    scenario_name: str
    scenario_pack_path: str | None
    population_pack_path: str | None
    semantic_mode: str
    semantic_model: str | None
    semantic_profile: str
    include_slice_membership: bool = False


@dataclass(frozen=True)
class RunSwarmPlanRequest:
    domain_name: str
    brief: str
    generation_mode: str
    output_root: str
    target_config: dict[str, str]
    explicit_inputs: dict[str, Any]
    scenario_pack_path: str | None
    population_pack_path: str | None
    scenario_count: int
    population_size: int | None
    population_candidate_count: int | None
    ai_profile: str
    semantic_mode: str
    semantic_model: str | None
    semantic_profile: str
    default_scenario_pack_path: str
    default_population_pack_path: str


@dataclass(frozen=True)
class ComparePlanRequest:
    domain_name: str
    brief: str | None
    generation_mode: str
    output_root: str
    baseline_target_config: dict[str, str]
    candidate_target_config: dict[str, str]
    explicit_inputs: dict[str, Any]
    scenario_pack_path: str | None
    population_pack_path: str | None
    scenario_count: int
    population_size: int | None
    population_candidate_count: int | None
    ai_profile: str
    semantic_mode: str
    semantic_model: str | None
    semantic_profile: str
    rerun_count: int
    default_scenario_pack_path: str | None
    default_population_pack_path: str | None
    scenario_name: str
    baseline_target: RegressionTarget
    candidate_target: RegressionTarget


@dataclass(frozen=True)
class RunSwarmPlanContext:
    plan: PlannedWorkflow
    service_mode: str
    service_artifact_dir: str | None
    adapter_base_url: str | None
    output_root: str


@dataclass(frozen=True)
class ComparePlanContext:
    plan: PlannedWorkflow
    baseline_target: RegressionTarget
    candidate_target: RegressionTarget
    output_root: str


@dataclass(frozen=True)
class AuditPlanContext:
    plan: PlannedWorkflow
    service_mode: str
    service_artifact_dir: str | None
    adapter_base_url: str | None
    output_root: str


@dataclass(frozen=True)
class AuditExecutionRequest:
    domain_name: str
    output_root: str
    service_mode: str
    service_artifact_dir: str | None
    adapter_base_url: str | None
    seed: int
    output_dir: str | None
    run_name: str | None
    include_slice_membership: bool = False


@dataclass(frozen=True)
class RunSwarmExecutionRequest:
    domain_name: str
    brief: str
    output_root: str
    service_mode: str
    service_artifact_dir: str | None
    adapter_base_url: str | None
    seed: int
    output_dir: str | None
    run_name: str | None


@dataclass(frozen=True)
class CompareExecutionRequest:
    domain_name: str
    brief: str | None
    output_root: str
    baseline_target: RegressionTarget
    candidate_target: RegressionTarget
    seed: int
    output_dir: str | None
    policy_mode: str
    scenario_name: str


@dataclass(frozen=True)
class AuditExecutionOutcome:
    result: dict[str, str | int]
    run_result: RunResult
    scenario_pack_path: str | None
    population_pack_path: str | None
    coverage_source: str
    scenario_generation_mode: str
    swarm_generation_mode: str
    manifest_path: str


@dataclass(frozen=True)
class RunSwarmExecutionOutcome:
    result: dict[str, str | int]
    run_result: RunResult
    scenario_pack_path: str
    population_pack_path: str
    coverage_source: str
    scenario_generation_mode: str
    swarm_generation_mode: str
    manifest_path: str


@dataclass(frozen=True)
class CompareExecutionOutcome:
    result: dict[str, str | int]
    scenario_pack_path: str | None
    population_pack_path: str | None
    coverage_source: str
    scenario_generation_mode: str
    swarm_generation_mode: str
