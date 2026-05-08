"""Deterministic seeded user policy for the search domain."""

from __future__ import annotations

from dataclasses import replace
from random import Random

from ...schema import (
    Action,
    ActionDecision,
    AgentSeed,
    AgentState,
    DecisionExplanation,
    Observation,
    RankedList,
    ScenarioConfig,
    UtilityBreakdown,
)


def build_seeded_search_archetypes() -> tuple[AgentSeed, ...]:
    """Return the default seeded search population."""
    return (
        AgentSeed(
            "agent-task-focused",
            "Task-focused searcher",
            ("help", "navigational"),
            0.72,
            0.24,
            0.6,
            0.56,
            0.48,
            2,
            0.64,
            0.72,
            0.14,
            0.18,
            0.14,
            0.68,
            1,
            0.72,
            "Wants a direct answer or destination quickly.",
            "Find the right result with minimal scanning.",
            ("task-focused", "low-friction"),
        ),
        AgentSeed(
            "agent-researcher",
            "Researcher",
            ("article", "news"),
            0.38,
            0.78,
            0.35,
            0.64,
            0.34,
            3,
            0.56,
            0.78,
            0.08,
            0.34,
            0.16,
            0.52,
            2,
            0.82,
            "Compares sources and accepts broader result lists.",
            "Surface relevant coverage without collapsing variety.",
            ("research", "diversity-seeking"),
        ),
        AgentSeed(
            "agent-current-info",
            "Current-info searcher",
            ("news", "article"),
            0.5,
            0.62,
            0.44,
            0.58,
            0.42,
            2,
            0.6,
            0.74,
            0.1,
            0.24,
            0.12,
            0.48,
            1,
            0.76,
            "Cares whether results are fresh enough to trust.",
            "Prefer fresh, clearly relevant results.",
            ("freshness-sensitive", "time-sensitive"),
        ),
    )


class SearchAgentPolicy:
    """Simple deterministic policy for search-result interactions."""

    def initialize_state(
        self,
        agent_seed: AgentSeed,
        scenario_context,
    ) -> AgentState:
        runtime_profile = (
            getattr(scenario_context, "runtime_profile", "")
            or scenario_context.scenario_name
        )
        click_threshold = 0.5 + (0.16 * agent_seed.abandonment_sensitivity)
        if runtime_profile == "navigational":
            click_threshold -= 0.08
        if runtime_profile == "zero-result":
            click_threshold += 0.1
        return AgentState(
            agent_id=agent_seed.agent_id,
            archetype_label=agent_seed.archetype_label,
            step_index=0,
            click_threshold=round(click_threshold, 3),
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
            history_item_ids=scenario_context.history_item_ids,
            trust=0.68,
            confidence=0.62,
            persona_summary=agent_seed.persona_summary,
            behavior_goal=agent_seed.behavior_goal,
            diversity_tags=agent_seed.diversity_tags,
            scenario_risk_focus_tags=getattr(
                scenario_context,
                "risk_focus_tags",
                (),
            ),
            scenario_context_hint=getattr(scenario_context, "context_hint", "") or "",
            scenario_profile=runtime_profile,
        )

    def choose_action(
        self,
        agent_state: AgentState,
        ranked_list: RankedList,
        observation: Observation,
        _scenario_config: ScenarioConfig,
        rng: Random,
    ) -> ActionDecision:
        del rng
        if not ranked_list.items:
            action = Action("abandon", None, "empty_results")
            return ActionDecision(
                action=action,
                explanation=_explanation(action, agent_state, None, 0.0),
            )
        best = max(ranked_list.items, key=lambda item: (item.score, -item.rank))
        threshold = _threshold(agent_state, observation)
        if best.score >= threshold:
            action = Action("click", best.item_id, "top_result_above_threshold")
        else:
            should_abandon = agent_state.patience_remaining <= 1
            action = Action(
                "abandon" if should_abandon else "skip",
                None,
                "no_result_above_threshold",
            )
        return ActionDecision(
            action=action,
            explanation=_explanation(action, agent_state, best, threshold),
        )

    def update_state(
        self,
        agent_state: AgentState,
        decision: ActionDecision,
        ranked_list: RankedList,
        observation: Observation,
        _rng: Random,
    ) -> AgentState:
        action = decision.action
        exposed_ids = tuple(item.item_id for item in ranked_list.items)
        recent_exposure_ids = (*agent_state.recent_exposure_ids, *exposed_ids)[-12:]
        next_step = observation.step_index + 1
        if action.name == "click":
            clicked = next(
                item for item in ranked_list.items if item.item_id == action.selected_item_id
            )
            return replace(
                agent_state,
                step_index=next_step,
                last_action="click",
                recent_exposure_ids=recent_exposure_ids,
                clicked_item_ids=(*agent_state.clicked_item_ids, clicked.item_id),
                click_count=agent_state.click_count + 1,
                skipped_steps=0,
                satisfaction=round(min(1.0, agent_state.satisfaction + clicked.score * 0.35), 4),
                frustration=round(max(0.0, agent_state.frustration - 0.18), 4),
                trust=round(min(1.0, agent_state.trust + 0.05), 4),
                confidence=round(min(1.0, agent_state.confidence + 0.04), 4),
            )
        if action.name == "skip":
            return replace(
                agent_state,
                step_index=next_step,
                last_action="skip",
                recent_exposure_ids=recent_exposure_ids,
                skipped_steps=agent_state.skipped_steps + 1,
                patience_remaining=max(0, agent_state.patience_remaining - 1),
                frustration=round(min(1.0, agent_state.frustration + 0.12), 4),
                trust=round(max(0.0, agent_state.trust - 0.04), 4),
                confidence=round(max(0.0, agent_state.confidence - 0.03), 4),
            )
        return replace(
            agent_state,
            step_index=next_step,
            last_action="abandon",
            recent_exposure_ids=recent_exposure_ids,
            patience_remaining=0,
            skipped_steps=agent_state.skipped_steps + 1,
            frustration=round(min(1.0, agent_state.frustration + 0.16), 4),
            trust=round(max(0.0, agent_state.trust - 0.12), 4),
            confidence=round(max(0.0, agent_state.confidence - 0.08), 4),
        )

    def summarize_state_delta(
        self,
        before: AgentState,
        after: AgentState,
        decision: ActionDecision,
        _observation: Observation,
    ) -> str:
        fragments = [
            f"trust {before.trust:.2f}->{after.trust:.2f}",
            f"confidence {before.confidence:.2f}->{after.confidence:.2f}",
            f"frustration {before.frustration:.2f}->{after.frustration:.2f}",
        ]
        if decision.action.name == "click" and decision.action.selected_item_id:
            fragments.append(f"clicked {decision.action.selected_item_id}")
        else:
            fragments.append(decision.action.reason)
        return ", ".join(fragments)


def _threshold(agent_state: AgentState, observation: Observation) -> float:
    threshold = agent_state.click_threshold
    if observation.scenario_context.runtime_profile == "navigational":
        threshold -= 0.04
    return max(0.1, min(0.95, threshold))


def _explanation(
    action: Action,
    agent_state: AgentState,
    best,
    threshold: float,
) -> DecisionExplanation:
    utility = float(best.score) if best is not None else 0.0
    breakdown = (
        UtilityBreakdown(
            base_relevance=utility,
            affinity=0.0,
            familiarity=0.0,
            novelty=0.0,
            quality=utility,
            repetition_penalty=0.0,
            scenario_adjustment=0.0,
            confidence_adjustment=0.0,
            jitter=0.0,
            total=utility,
        )
        if best is not None
        else None
    )
    return DecisionExplanation(
        chosen_item_id=action.selected_item_id,
        top_candidate_item_id=best.item_id if best is not None else None,
        action_threshold=threshold or agent_state.click_threshold,
        chosen_utility=utility if action.name == "click" else 0.0,
        top_candidate_utility=utility,
        dominant_component="base_relevance",
        top_candidate_breakdown=breakdown,
        reason=action.reason,
    )
