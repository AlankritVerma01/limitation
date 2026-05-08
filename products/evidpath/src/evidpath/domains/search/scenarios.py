"""Runtime scenarios and built-ins for the search domain."""

from __future__ import annotations

from ...schema import AgentSeed, Observation, RunConfig, ScenarioConfig, ScenarioContext

BUILT_IN_SEARCH_SCENARIOS = (
    ScenarioConfig(
        name="navigational-query",
        max_steps=1,
        allowed_actions=("click", "skip", "abandon"),
        history_depth=0,
        description="User is trying to reach a known destination or account page.",
        scenario_id="navigational-query",
        test_goal="Check whether the top result satisfies a direct navigation intent.",
        risk_focus_tags=("intent-match", "top-result-quality"),
        runtime_profile="navigational",
        context_hint="nike login",
    ),
    ScenarioConfig(
        name="informational-long-tail-query",
        max_steps=1,
        allowed_actions=("click", "skip", "abandon"),
        history_depth=0,
        description="User asks a specific informational question with long-tail wording.",
        scenario_id="informational-long-tail-query",
        test_goal="Check whether ranked results cover the query terms with useful snippets.",
        risk_focus_tags=("long-tail-relevance", "snippet-quality"),
        runtime_profile="informational-long-tail",
        context_hint="python cache invalidation stale reads",
    ),
    ScenarioConfig(
        name="time-sensitive-query",
        max_steps=1,
        allowed_actions=("click", "skip", "abandon"),
        history_depth=0,
        description="User needs current information where freshness affects usefulness.",
        scenario_id="time-sensitive-query",
        test_goal="Check whether fresh sources rank highly for current-event intent.",
        risk_focus_tags=("freshness", "currentness"),
        runtime_profile="time-sensitive",
        context_hint="current weather alerts toronto",
    ),
    ScenarioConfig(
        name="ambiguous-query",
        max_steps=1,
        allowed_actions=("click", "skip", "abandon"),
        history_depth=0,
        description="User enters a query with multiple plausible meanings.",
        scenario_id="ambiguous-query",
        test_goal="Check whether the result list preserves useful interpretation diversity.",
        risk_focus_tags=("ambiguity", "diversity"),
        runtime_profile="ambiguous",
        context_hint="jaguar",
    ),
    ScenarioConfig(
        name="typo-query",
        max_steps=1,
        allowed_actions=("click", "skip", "abandon"),
        history_depth=0,
        description="User enters a query with a likely typo.",
        scenario_id="typo-query",
        test_goal="Check whether typo-like queries still recover useful ranked results.",
        risk_focus_tags=("typo-tolerance", "recall"),
        runtime_profile="typo",
        context_hint="pasword reset",
    ),
    ScenarioConfig(
        name="zero-result-query",
        max_steps=1,
        allowed_actions=("click", "skip", "abandon"),
        history_depth=0,
        description="User enters a query where the correct behavior may be no results.",
        scenario_id="zero-result-query",
        test_goal="Check whether no-result behavior is explicit instead of hallucinated.",
        risk_focus_tags=("zero-results", "precision"),
        runtime_profile="zero-result",
        context_hint="zzzz qqqq unavailable token",
    ),
    ScenarioConfig(
        name="personalized-vs-anonymous-query",
        max_steps=1,
        allowed_actions=("click", "skip", "abandon"),
        history_depth=2,
        description="User query can benefit from profile context but should still work anonymously.",
        scenario_id="personalized-vs-anonymous-query",
        test_goal="Check whether personalization improves relevance without collapsing variety.",
        risk_focus_tags=("personalization", "anonymous-parity"),
        runtime_profile="personalized-vs-anonymous",
        context_hint="personalized machine learning ranking",
    ),
)

BUILT_IN_SEARCH_SCENARIO_NAMES = tuple(
    scenario.name for scenario in BUILT_IN_SEARCH_SCENARIOS
)


class SearchScenario:
    """Base scenario implementation for search query archetypes."""

    def __init__(self, config: ScenarioConfig) -> None:
        self.config = config

    @property
    def name(self) -> str:
        return self.config.name

    @property
    def scenario_id(self) -> str:
        return self.config.scenario_id or self.config.name

    def initialize(self, agent_seed: AgentSeed, run_config: RunConfig) -> Observation:
        del run_config
        history_item_ids = tuple(
            f"history:{genre}" for genre in agent_seed.preferred_genres[: self.config.history_depth]
        )
        context = ScenarioContext(
            scenario_name=self.config.name,
            runtime_profile=self.config.runtime_profile or self.config.name,
            history_depth=self.config.history_depth,
            history_item_ids=history_item_ids,
            description=self.config.description,
            scenario_id=self.scenario_id,
            context_hint=self.config.context_hint,
            risk_focus_tags=self.config.risk_focus_tags,
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


def resolve_built_in_search_scenarios(
    scenario_names: tuple[str, ...] | None = None,
) -> tuple[ScenarioConfig, ...]:
    """Return validated built-in search scenario configs by name."""
    selected_names = scenario_names or BUILT_IN_SEARCH_SCENARIO_NAMES
    scenario_map = {scenario.name: scenario for scenario in BUILT_IN_SEARCH_SCENARIOS}
    unknown_scenarios = sorted(set(selected_names).difference(scenario_map))
    if unknown_scenarios:
        raise ValueError(f"Unknown scenario names: {', '.join(unknown_scenarios)}.")
    return tuple(scenario_map[name] for name in selected_names)


def build_scenarios(
    scenario_configs: tuple[ScenarioConfig, ...],
) -> tuple[SearchScenario, ...]:
    """Construct runtime search scenario objects from validated configs."""
    return tuple(SearchScenario(config) for config in scenario_configs)
