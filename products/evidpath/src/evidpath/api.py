"""Python entry point for in-process recommender audits."""

from __future__ import annotations

from typing import Any

from .domain_registry import get_domain_definition
from .domains.recommender.drivers import InProcessRecommenderDriver
from .schema import RunResult


def audit(
    *,
    callable: Any,
    domain_name: str = "recommender",
    seed: int = 0,
    scenario_names: tuple[str, ...] | None = None,
    scenario_pack_path: str | None = None,
    population_pack_path: str | None = None,
    output_dir: str | None = None,
    run_name: str | None = None,
    backend_name: str | None = None,
) -> RunResult:
    """Run one audit against a Python callable, class, or class instance."""
    driver = InProcessRecommenderDriver.from_callable(
        callable, backend_name=backend_name
    )
    definition = get_domain_definition(domain_name)
    if definition.runner is None:
        raise ValueError(f"Domain `{domain_name}` is missing a runner.")
    return definition.runner.execute_audit(
        seed=seed,
        output_dir=output_dir,
        scenario_names=scenario_names,
        scenario_pack_path=scenario_pack_path,
        population_pack_path=population_pack_path,
        run_name=run_name,
        driver_instance=driver,
    )
