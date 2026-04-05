"""Recommender scenarios that adapt to mock or reference service backends."""

from __future__ import annotations

from ..catalog import history_for_genres
from ..schema import AgentSeed, Observation, RunConfig, ScenarioConfig, ScenarioContext
from ..services.reference_artifacts import (
    ensure_reference_artifacts,
    history_for_reference_genres,
)


class RecommenderScenario:
    """Base scenario implementation shared across recommender session types."""

    def __init__(self, config: ScenarioConfig) -> None:
        self.config = config

    @property
    def name(self) -> str:
        return self.config.name

    @property
    def scenario_id(self) -> str:
        return self.config.scenario_id or self.config.name

    def initialize(self, agent_seed: AgentSeed, run_config: RunConfig) -> Observation:
        if run_config.rollout.service_mode == "reference":
            artifact_dir = str(
                ensure_reference_artifacts(run_config.rollout.service_artifact_dir).parent
            )
            history_item_ids = history_for_reference_genres(
                agent_seed.preferred_genres,
                self.config.history_depth,
                artifact_dir,
            )
        else:
            history_item_ids = history_for_genres(
                agent_seed.preferred_genres,
                self.config.history_depth,
            )
        context = ScenarioContext(
            scenario_name=self.config.name,
            runtime_profile=self.config.runtime_profile or self.config.name,
            history_depth=self.config.history_depth,
            history_item_ids=history_item_ids,
            description=self.config.description,
            scenario_id=self.scenario_id,
            context_hint=self.config.context_hint,
        )
        return Observation(
            session_id=f"{self.scenario_id}-{agent_seed.agent_id}",
            step_index=0,
            max_steps=self.config.max_steps,
            available_actions=self.config.allowed_actions,
            scenario_context=context,
        )

    def next_observation(
        self,
        previous: Observation,
        run_config: RunConfig,
    ) -> Observation:
        del run_config
        return Observation(
            session_id=previous.session_id,
            step_index=previous.step_index + 1,
            max_steps=previous.max_steps,
            available_actions=previous.available_actions,
            scenario_context=previous.scenario_context,
        )

    def should_stop(self, observation: Observation) -> bool:
        return observation.step_index >= observation.max_steps


class ReturningUserHomeFeedScenario(RecommenderScenario):
    """Short returning-user session with meaningful history."""


class SparseHistoryHomeFeedScenario(RecommenderScenario):
    """Short home-feed session with limited history."""


def build_scenarios(
    scenario_configs: tuple[ScenarioConfig, ...],
) -> tuple[RecommenderScenario, ...]:
    scenario_map = {
        "returning-user-home-feed": ReturningUserHomeFeedScenario,
        "sparse-history-home-feed": SparseHistoryHomeFeedScenario,
    }
    return tuple(scenario_map.get(config.name, RecommenderScenario)(config) for config in scenario_configs)
