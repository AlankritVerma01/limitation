"""Stub scenario used by the Chunk 1 rollout skeleton."""

from __future__ import annotations

from ..schema import AgentSeed, Observation, RunConfig


class StubScenario:
    """A short session with click, skip, and abandon actions."""

    @property
    def scenario_id(self) -> str:
        return "stub-scenario"

    @property
    def name(self) -> str:
        return "stub-scenario"

    def initialize(self, agent_seed: AgentSeed, run_config: RunConfig) -> Observation:
        return Observation(
            session_id=f"{run_config.run_name}-{agent_seed.agent_id}",
            step_index=0,
            max_steps=run_config.scenario.max_steps,
            available_actions=run_config.scenario.allowed_actions,
        )

    def next_observation(
        self,
        previous: Observation,
        run_config: RunConfig,
    ) -> Observation:
        return Observation(
            session_id=previous.session_id,
            step_index=previous.step_index + 1,
            max_steps=run_config.scenario.max_steps,
            available_actions=run_config.scenario.allowed_actions,
        )

    def should_stop(self, observation: Observation) -> bool:
        return observation.step_index >= observation.max_steps
