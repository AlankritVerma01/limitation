"""Adapter interface for systems under test."""

from __future__ import annotations

from typing import Protocol

from ..schema import AgentState, Observation, ScenarioConfig, Slate


class SystemAdapter(Protocol):
    """Returns a normalized slate for the current interaction step."""

    def get_slate(
        self,
        agent_state: AgentState,
        observation: Observation,
        scenario_config: ScenarioConfig,
    ) -> Slate: ...
