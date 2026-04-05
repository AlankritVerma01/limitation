"""Deterministic stub adapter used by Chunk 1."""

from __future__ import annotations

from ..schema import AgentState, Observation, ScenarioConfig, Slate, SlateItem


class StubSystemAdapter:
    """Returns a tiny fixed slate so the architecture can be tested in isolation."""

    def get_slate(
        self,
        agent_state: AgentState,
        observation: Observation,
        scenario_config: ScenarioConfig,
    ) -> Slate:
        del scenario_config
        step_penalty = observation.step_index * 0.08
        items = (
            SlateItem("item-1", "Safe Hit", round(0.74 - step_penalty, 3), 1),
            SlateItem("item-2", "Niche Gem", round(0.61 - step_penalty, 3), 2),
            SlateItem("item-3", "Long Tail Pick", round(0.42 - step_penalty, 3), 3),
        )
        return Slate(
            slate_id=f"{agent_state.agent_id}-step-{observation.step_index}",
            step_index=observation.step_index,
            items=items,
        )
