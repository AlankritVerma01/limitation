"""Internal domain registry contracts for audit and regression orchestration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Protocol

from ..schema import RegressionTarget, RunResult


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
    ) -> RunResult:
        """Run one audit and return the in-memory result."""

    def execute_target_audit(
        self,
        *,
        target: RegressionTarget,
        seed: int,
        output_dir: str,
        scenario_names: tuple[str, ...] | None = None,
        population_pack_path: str | None = None,
    ) -> RunResult:
        """Run one regression rerun against a concrete target."""


@dataclass(frozen=True)
class DomainDefinition:
    """Static internal wiring for one supported domain."""

    name: str
    audit_report_title: str
    regression_report_title: str
    resolve_inputs: Callable[..., object]
    build_run_config: Callable[..., object]
    build_target_identity: Callable[[RegressionTarget], str]
    runner: DomainRunner
