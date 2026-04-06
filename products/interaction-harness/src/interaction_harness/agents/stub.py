"""Seeded stub agents kept compatible with the shared Chunk 3 contracts."""

from __future__ import annotations

from dataclasses import replace
from random import Random

from ..schema import (
    Action,
    ActionDecision,
    AgentSeed,
    AgentState,
    DecisionExplanation,
    Observation,
    ScenarioConfig,
    ScenarioContext,
    Slate,
    UtilityBreakdown,
)


def build_stub_agent_seeds() -> tuple[AgentSeed, ...]:
    """Reuse the public archetype labels with simple Chunk 1-compatible values."""
    return (
        AgentSeed(
            "agent-mainstream",
            "Conservative mainstream",
            ("action",),
            0.72,
            0.25,
            0.8,
            0.55,
            0.4,
            2,
            0.6,
            0.5,
            0.12,
            0.2,
            0.1,
            0.7,
            1,
            0.65,
        ),
        AgentSeed(
            "agent-explorer",
            "Explorer / novelty-seeking",
            ("indie",),
            0.4,
            0.82,
            0.3,
            0.6,
            0.35,
            2,
            0.56,
            0.55,
            0.08,
            0.28,
            0.1,
            0.4,
            2,
            0.7,
        ),
    )


def initial_state_from_seed(agent_seed: AgentSeed) -> AgentState:
    """Build the explicit initial stub state from a seed spec."""
    return AgentState(
        agent_id=agent_seed.agent_id,
        archetype_label=agent_seed.archetype_label,
        step_index=0,
        click_threshold=0.6,
        preferred_genres=agent_seed.preferred_genres,
        popularity_preference=agent_seed.popularity_preference,
        novelty_preference=agent_seed.novelty_preference,
        repetition_tolerance=agent_seed.repetition_tolerance,
        sparse_history_confidence=agent_seed.sparse_history_confidence,
        abandonment_sensitivity=agent_seed.abandonment_sensitivity,
        engagement_baseline=agent_seed.engagement_baseline,
        quality_sensitivity=agent_seed.quality_sensitivity,
        repeat_exposure_penalty=agent_seed.repeat_exposure_penalty,
        novelty_fatigue=agent_seed.novelty_fatigue,
        frustration_recovery=agent_seed.frustration_recovery,
        history_reliance=agent_seed.history_reliance,
        skip_tolerance=agent_seed.skip_tolerance,
        abandonment_threshold=agent_seed.abandonment_threshold,
        patience_remaining=agent_seed.patience,
        last_action="start",
    )


class StubAgentPolicy:
    """Simple seeded policy that stays compatible with the richer action contract."""

    def initialize_state(
        self,
        agent_seed: AgentSeed,
        scenario_context: ScenarioContext,
    ) -> AgentState:
        """Build the deterministic starting state for one stub seeded user."""
        del scenario_context
        return initial_state_from_seed(agent_seed)

    def choose_action(
        self,
        agent_state: AgentState,
        slate: Slate,
        observation: Observation,
        scenario_config: ScenarioConfig,
        rng: Random,
    ) -> ActionDecision:
        del observation, scenario_config
        selected = None
        chosen_score = 0.0
        for item in slate.items:
            jittered_score = item.score + rng.uniform(-0.05, 0.05)
            if jittered_score >= agent_state.click_threshold:
                selected = item.item_id
                chosen_score = jittered_score
                break
        if selected is not None:
            action = Action("click", selected, "found_item_above_threshold")
        elif agent_state.patience_remaining <= 1:
            action = Action("abandon", None, "low_patience")
        else:
            action = Action("skip", None, "no_item_above_threshold")
        explanation = DecisionExplanation(
            chosen_item_id=selected,
            top_candidate_item_id=selected,
            action_threshold=agent_state.click_threshold,
            chosen_utility=round(chosen_score, 6),
            top_candidate_utility=round(chosen_score, 6),
            dominant_component="base_relevance",
            top_candidate_breakdown=UtilityBreakdown(
                base_relevance=round(chosen_score, 6),
                affinity=0.0,
                familiarity=0.0,
                novelty=0.0,
                quality=0.0,
                repetition_penalty=0.0,
                scenario_adjustment=0.0,
                confidence_adjustment=0.0,
                jitter=0.0,
                total=round(chosen_score, 6),
            ),
            reason=action.reason,
        )
        return ActionDecision(action=action, explanation=explanation)

    def update_state(
        self,
        agent_state: AgentState,
        decision: ActionDecision,
        slate: Slate,
        observation: Observation,
        rng: Random,
    ) -> AgentState:
        del slate, rng
        action = decision.action
        if action.name == "click":
            return replace(
                agent_state,
                step_index=observation.step_index + 1,
                last_action="click",
                click_count=agent_state.click_count + 1,
                satisfaction=min(1.0, agent_state.satisfaction + 0.15),
            )
        if action.name == "skip":
            return replace(
                agent_state,
                step_index=observation.step_index + 1,
                last_action="skip",
                skipped_steps=agent_state.skipped_steps + 1,
                patience_remaining=max(0, agent_state.patience_remaining - 1),
                frustration=min(1.0, agent_state.frustration + 0.08),
            )
        return replace(
            agent_state,
            step_index=observation.step_index + 1,
            last_action="abandon",
            patience_remaining=0,
            frustration=min(1.0, agent_state.frustration + 0.15),
        )

    def summarize_state_delta(
        self,
        before: AgentState,
        after: AgentState,
        decision: ActionDecision,
        observation: Observation,
    ) -> str:
        del observation
        return (
            f"action {decision.action.name}, patience {before.patience_remaining}->{after.patience_remaining}, "
            f"frustration {before.frustration:.2f}->{after.frustration:.2f}"
        )
