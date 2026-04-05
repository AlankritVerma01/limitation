"""Scenario interface for interaction environments."""

from __future__ import annotations

from typing import Protocol

from ..schema import AgentSeed, Observation, RunConfig


class Scenario(Protocol):
    """Initializes observations and decides when a rollout should stop."""

    @property
    def scenario_id(self) -> str: ...

    @property
    def name(self) -> str: ...

    def initialize(self, agent_seed: AgentSeed, run_config: RunConfig) -> Observation: ...

    def next_observation(
        self,
        previous: Observation,
        run_config: RunConfig,
    ) -> Observation: ...

    def should_stop(self, observation: Observation) -> bool: ...
