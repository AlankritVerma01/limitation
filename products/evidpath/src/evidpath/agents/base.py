"""Agent policy interface for stateful seeded users."""

from __future__ import annotations

from random import Random
from typing import Protocol

from ..schema import (
    ActionDecision,
    AgentSeed,
    AgentState,
    Observation,
    RankedList,
    ScenarioConfig,
    ScenarioContext,
)


class AgentPolicy(Protocol):
    """Chooses actions and updates state during a rollout."""

    def initialize_state(
        self,
        agent_seed: AgentSeed,
        scenario_context: ScenarioContext,
    ) -> AgentState: ...

    def choose_action(
        self,
        agent_state: AgentState,
        ranked_list: RankedList,
        observation: Observation,
        scenario_config: ScenarioConfig,
        rng: Random,
    ) -> ActionDecision: ...

    def update_state(
        self,
        agent_state: AgentState,
        decision: ActionDecision,
        ranked_list: RankedList,
        observation: Observation,
        rng: Random,
    ) -> AgentState: ...

    def summarize_state_delta(
        self,
        before: AgentState,
        after: AgentState,
        decision: ActionDecision,
        observation: Observation,
    ) -> str: ...
