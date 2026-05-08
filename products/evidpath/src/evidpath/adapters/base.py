"""Adapter interface for systems under test."""

from __future__ import annotations

from typing import Protocol

from ..schema import AgentState, Observation, RankedList, ScenarioConfig


class SystemAdapter(Protocol):
    """Returns normalized ranked results for the current interaction step."""

    def get_ranked_list(
        self,
        agent_state: AgentState,
        observation: Observation,
        scenario_config: ScenarioConfig,
    ) -> RankedList: ...
