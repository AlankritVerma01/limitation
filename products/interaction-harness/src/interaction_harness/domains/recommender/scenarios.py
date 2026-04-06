"""Runtime scenarios and built-ins for the recommender domain."""

from __future__ import annotations

from ...catalog import history_for_genres
from ...schema import AgentSeed, Observation, RunConfig, ScenarioConfig, ScenarioContext
from ...services.reference_artifacts import (
    ensure_reference_artifacts,
    history_for_reference_genres,
)

BUILT_IN_RECOMMENDER_SCENARIOS = (
    ScenarioConfig(
        name="returning-user-home-feed",
        max_steps=5,
        allowed_actions=("click", "skip", "abandon"),
        history_depth=4,
        description="Returning user home-feed session with meaningful prior history.",
        scenario_id="returning-user-home-feed",
        test_goal="Check relevance and repetition behavior for users with established preferences.",
        risk_focus_tags=("staleness", "over-specialization"),
        runtime_profile="returning-user-home-feed",
    ),
    ScenarioConfig(
        name="sparse-history-home-feed",
        max_steps=5,
        allowed_actions=("click", "skip", "abandon"),
        history_depth=1,
        description="Sparse-history home-feed session with limited prior behavior.",
        scenario_id="sparse-history-home-feed",
        test_goal="Check cold-start behavior when the system has limited prior evidence.",
        risk_focus_tags=("cold-start", "popularity-bias"),
        runtime_profile="sparse-history-home-feed",
    ),
)
BUILT_IN_RECOMMENDER_SCENARIO_NAMES = tuple(
    scenario.name for scenario in BUILT_IN_RECOMMENDER_SCENARIOS
)
# Compatibility alias retained while older module paths are still supported.
BUILT_IN_RECOMMENDER_SCENARIO_CONFIGS = BUILT_IN_RECOMMENDER_SCENARIOS


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


def resolve_built_in_recommender_scenarios(
    scenario_names: tuple[str, ...] | None = None,
) -> tuple[ScenarioConfig, ...]:
    """Return validated built-in recommender scenario configs by name."""
    selected_names = scenario_names or BUILT_IN_RECOMMENDER_SCENARIO_NAMES
    scenario_map = {
        scenario.name: scenario for scenario in BUILT_IN_RECOMMENDER_SCENARIOS
    }
    unknown_scenarios = sorted(set(selected_names).difference(scenario_map))
    if unknown_scenarios:
        raise ValueError(f"Unknown scenario names: {', '.join(unknown_scenarios)}.")
    return tuple(scenario_map[name] for name in selected_names)


def build_scenarios(
    scenario_configs: tuple[ScenarioConfig, ...],
) -> tuple[RecommenderScenario, ...]:
    """Construct runtime scenario objects from validated configs."""
    return tuple(RecommenderScenario(config) for config in scenario_configs)
