"""Deterministic seeded user policy for the recommender domain."""

from __future__ import annotations

from dataclasses import dataclass, replace
from random import Random

from ...schema import (
    Action,
    ActionDecision,
    AgentSeed,
    AgentState,
    DecisionExplanation,
    Observation,
    RuntimeItemSignals,
    ScenarioConfig,
    Slate,
    SlateItem,
    UtilityBreakdown,
)


@dataclass(frozen=True)
class CandidateEvaluation:
    """Utility view of one candidate item after runtime normalization."""

    signals: RuntimeItemSignals
    breakdown: UtilityBreakdown


def build_seeded_archetypes() -> tuple[AgentSeed, ...]:
    """Return the first seeded population with richer runtime parameters."""
    return (
        AgentSeed(
            "agent-mainstream",
            "Conservative mainstream",
            ("action", "comedy", "family"),
            0.92,
            0.18,
            0.82,
            0.55,
            0.45,
            3,
            0.66,
            0.52,
            0.18,
            0.22,
            0.14,
            0.82,
            2,
            0.68,
        ),
        AgentSeed(
            "agent-explorer",
            "Explorer / novelty-seeking",
            ("sci-fi", "thriller", "indie"),
            0.32,
            0.92,
            0.24,
            0.62,
            0.38,
            3,
            0.58,
            0.61,
            0.08,
            0.44,
            0.12,
            0.36,
            3,
            0.76,
        ),
        AgentSeed(
            "agent-niche",
            "Niche-interest",
            ("horror", "documentary", "indie"),
            0.28,
            0.78,
            0.45,
            0.41,
            0.52,
            3,
            0.54,
            0.72,
            0.15,
            0.3,
            0.11,
            0.74,
            2,
            0.71,
        ),
        AgentSeed(
            "agent-low-patience",
            "Low-patience",
            ("action", "drama", "comedy"),
            0.81,
            0.33,
            0.31,
            0.48,
            0.92,
            2,
            0.63,
            0.48,
            0.24,
            0.18,
            0.08,
            0.58,
            1,
            0.52,
        ),
    )


def initial_state_from_seed(
    agent_seed: AgentSeed,
    scenario_context,
) -> AgentState:
    """Build explicit initial state from the seed and scenario context."""
    runtime_profile = (
        getattr(scenario_context, "runtime_profile", "") or scenario_context.scenario_name
    )
    is_sparse = runtime_profile == "sparse-history-home-feed"
    click_threshold = 0.56 + (0.14 * agent_seed.abandonment_sensitivity)
    base_trust = 0.74 - (0.08 * agent_seed.abandonment_sensitivity)
    if is_sparse:
        base_trust -= 0.18
    confidence = (
        agent_seed.sparse_history_confidence
        if is_sparse
        else min(1.0, 0.55 + (0.38 * agent_seed.history_reliance))
    )
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
        trust=round(max(0.1, min(1.0, base_trust)), 4),
        confidence=round(max(0.1, min(1.0, confidence)), 4),
    )


def normalize_runtime_item_signals(slate: Slate) -> tuple[RuntimeItemSignals, ...]:
    """Map recommender slate items into runtime-consumable normalized signals."""
    return tuple(_to_runtime_signals(item) for item in slate.items)


def _to_runtime_signals(item: SlateItem) -> RuntimeItemSignals:
    """Project a slate item onto the smaller signal set used by the runtime."""
    return RuntimeItemSignals(
        item_id=item.item_id,
        rank=item.rank,
        base_relevance=item.score,
        genre=item.genre,
        familiarity_signal=item.popularity,
        novelty_signal=item.novelty,
        quality_signal=item.score,
        domain_tags=(item.genre,),
    )


class RecommenderAgentPolicy:
    """Deterministic but richer stateful policy for recommender rollouts."""

    def initialize_state(
        self,
        agent_seed: AgentSeed,
        scenario_context,
    ) -> AgentState:
        """Build the deterministic starting state for one seeded recommender user."""
        return initial_state_from_seed(agent_seed, scenario_context)

    def choose_action(
        self,
        agent_state: AgentState,
        slate: Slate,
        observation: Observation,
        _scenario_config: ScenarioConfig,
        rng: Random,
    ) -> ActionDecision:
        """Choose click, skip, or abandon from the current slate and state."""
        evaluations = self._evaluate_candidates(agent_state, slate, observation, rng)
        if not evaluations:
            action = Action("abandon", None, "empty_slate")
            return ActionDecision(
                action=action,
                explanation=DecisionExplanation(
                    chosen_item_id=None,
                    top_candidate_item_id=None,
                    action_threshold=agent_state.click_threshold,
                    chosen_utility=0.0,
                    top_candidate_utility=0.0,
                    dominant_component="none",
                    top_candidate_breakdown=None,
                    reason=action.reason,
                ),
            )

        best = evaluations[0]
        threshold = self._dynamic_threshold(agent_state, observation)
        if best.breakdown.total >= threshold:
            action = Action("click", best.signals.item_id, "best_item_above_threshold")
            return ActionDecision(
                action=action,
                explanation=self._build_explanation(
                    action=action,
                    best=best,
                    threshold=threshold,
                ),
            )

        should_abandon = (
            agent_state.frustration >= agent_state.abandonment_threshold
            or agent_state.patience_remaining <= 1
            or (
                agent_state.skipped_steps >= agent_state.skip_tolerance
                and best.breakdown.total < (threshold - 0.06)
            )
            or agent_state.trust <= 0.18
        )
        reason = "trust_collapsed" if should_abandon else "no_item_above_threshold"
        action = Action("abandon" if should_abandon else "skip", None, reason)
        return ActionDecision(
            action=action,
            explanation=self._build_explanation(
                action=action,
                best=best,
                threshold=threshold,
            ),
        )

    def update_state(
        self,
        agent_state: AgentState,
        decision: ActionDecision,
        slate: Slate,
        observation: Observation,
        _rng: Random,
    ) -> AgentState:
        """Apply the chosen action and return the next explicit user state."""
        action = decision.action
        exposed_ids = tuple(item.item_id for item in slate.items)
        recent_exposure_ids = (*agent_state.recent_exposure_ids, *exposed_ids)[-12:]
        next_step = observation.step_index + 1
        runtime_profile = (
            observation.scenario_context.runtime_profile or observation.scenario_context.scenario_name
        )
        is_sparse = runtime_profile == "sparse-history-home-feed"
        top_utility = decision.explanation.top_candidate_utility
        threshold_gap = max(0.0, decision.explanation.action_threshold - top_utility)

        if action.name == "click":
            clicked = next(
                item for item in slate.items if item.item_id == action.selected_item_id
            )
            genre_match = 1.0 if clicked.genre in agent_state.preferred_genres else 0.0
            confidence_gain = 0.05 if is_sparse else 0.02
            trust_gain = 0.07 if genre_match else 0.03
            return replace(
                agent_state,
                step_index=next_step,
                last_action="click",
                recent_exposure_ids=recent_exposure_ids,
                clicked_item_ids=(*agent_state.clicked_item_ids, clicked.item_id),
                history_item_ids=(*agent_state.history_item_ids, clicked.item_id),
                click_count=agent_state.click_count + 1,
                skipped_steps=0,
                satisfaction=round(
                    min(
                        1.0,
                        agent_state.satisfaction
                        + (0.08 * agent_state.engagement_baseline)
                        + (0.26 * clicked.score * agent_state.quality_sensitivity)
                        + (0.08 * genre_match),
                    ),
                    4,
                ),
                frustration=round(
                    max(
                        0.0,
                        agent_state.frustration - agent_state.frustration_recovery,
                    ),
                    4,
                ),
                trust=round(min(1.0, agent_state.trust + trust_gain), 4),
                confidence=round(min(1.0, agent_state.confidence + confidence_gain), 4),
            )

        if action.name == "skip":
            scenario_penalty = 0.08 if is_sparse else 0.06
            trust_penalty = 0.07 if runtime_profile == "returning-user-home-feed" else 0.05
            confidence_penalty = 0.06 if is_sparse else 0.02
            return replace(
                agent_state,
                step_index=next_step,
                last_action="skip",
                recent_exposure_ids=recent_exposure_ids,
                skipped_steps=agent_state.skipped_steps + 1,
                patience_remaining=max(0, agent_state.patience_remaining - 1),
                satisfaction=round(
                    max(0.0, agent_state.satisfaction - (0.03 + (0.04 * threshold_gap))),
                    4,
                ),
                frustration=round(
                    min(1.0, agent_state.frustration + scenario_penalty + (0.12 * threshold_gap)),
                    4,
                ),
                trust=round(max(0.0, agent_state.trust - trust_penalty), 4),
                confidence=round(max(0.0, agent_state.confidence - confidence_penalty), 4),
            )

        return replace(
            agent_state,
            step_index=next_step,
            last_action="abandon",
            recent_exposure_ids=recent_exposure_ids,
            patience_remaining=0,
            skipped_steps=agent_state.skipped_steps + 1,
            frustration=round(min(1.0, agent_state.frustration + 0.18), 4),
            trust=round(max(0.0, agent_state.trust - 0.18), 4),
            confidence=round(max(0.0, agent_state.confidence - 0.12), 4),
        )

    def summarize_state_delta(
        self,
        before: AgentState,
        after: AgentState,
        decision: ActionDecision,
        _observation: Observation,
    ) -> str:
        """Return a short human-readable summary of the state transition."""
        fragments = [
            f"trust {before.trust:.2f}->{after.trust:.2f}",
            f"confidence {before.confidence:.2f}->{after.confidence:.2f}",
            f"frustration {before.frustration:.2f}->{after.frustration:.2f}",
            f"satisfaction {before.satisfaction:.2f}->{after.satisfaction:.2f}",
        ]
        if decision.action.name == "click" and decision.action.selected_item_id is not None:
            fragments.append(f"clicked {decision.action.selected_item_id}")
        elif decision.action.name == "skip":
            fragments.append(f"skips {before.skipped_steps}->{after.skipped_steps}")
        else:
            fragments.append("session abandoned")
        return ", ".join(fragments)

    def _evaluate_candidates(
        self,
        agent_state: AgentState,
        slate: Slate,
        observation: Observation,
        rng: Random,
    ) -> list[CandidateEvaluation]:
        """Score and rank slate items from best to worst for this step."""
        evaluations: list[CandidateEvaluation] = []
        for signals in normalize_runtime_item_signals(slate):
            breakdown = self._utility_breakdown(agent_state, signals, observation, rng)
            evaluations.append(CandidateEvaluation(signals=signals, breakdown=breakdown))
        evaluations.sort(
            key=lambda candidate: (
                candidate.breakdown.total,
                -candidate.signals.rank,
            ),
            reverse=True,
        )
        return evaluations

    def _utility_breakdown(
        self,
        agent_state: AgentState,
        signals: RuntimeItemSignals,
        observation: Observation,
        rng: Random,
    ) -> UtilityBreakdown:
        """Compute the deterministic utility components for one candidate item."""
        runtime_profile = (
            observation.scenario_context.runtime_profile or observation.scenario_context.scenario_name
        )
        is_sparse = runtime_profile == "sparse-history-home-feed"
        genre_match = 1.0 if signals.genre in agent_state.preferred_genres else 0.0
        repeated_count = agent_state.recent_exposure_ids.count(signals.item_id)
        repeated_penalty = (
            repeated_count * agent_state.repeat_exposure_penalty * (1.0 - agent_state.repetition_tolerance)
        )
        novelty_fatigue = agent_state.novelty_fatigue * max(0, agent_state.click_count - 1)

        base_relevance = 0.31 * signals.base_relevance
        affinity = 0.2 * genre_match * (0.65 + (0.35 * agent_state.history_reliance))

        familiarity_multiplier = 1.15 if (is_sparse and agent_state.popularity_preference > 0.6) else 1.0
        familiarity = (
            0.18
            * signals.familiarity_signal
            * agent_state.popularity_preference
            * familiarity_multiplier
        )
        novelty = (
            0.16
            * signals.novelty_signal
            * agent_state.novelty_preference
            * max(0.35, 1.0 - novelty_fatigue)
        )
        quality = 0.17 * signals.quality_signal * agent_state.quality_sensitivity

        if runtime_profile == "returning-user-home-feed":
            scenario_adjustment = (
                (0.08 * genre_match * agent_state.history_reliance)
                - (0.06 * (1.0 - genre_match) * agent_state.history_reliance)
            )
        else:
            scenario_adjustment = (
                (0.16 * agent_state.sparse_history_confidence * agent_state.popularity_preference)
                + (0.06 * agent_state.novelty_preference)
                - (0.05 * (1.0 - agent_state.sparse_history_confidence))
            )

        confidence_adjustment = 0.14 * (agent_state.confidence - 0.5)
        jitter = rng.uniform(-0.018, 0.018)
        total = (
            base_relevance
            + affinity
            + familiarity
            + novelty
            + quality
            + scenario_adjustment
            + confidence_adjustment
            - repeated_penalty
            + jitter
        )
        return UtilityBreakdown(
            base_relevance=round(base_relevance, 6),
            affinity=round(affinity, 6),
            familiarity=round(familiarity, 6),
            novelty=round(novelty, 6),
            quality=round(quality, 6),
            repetition_penalty=round(repeated_penalty, 6),
            scenario_adjustment=round(scenario_adjustment, 6),
            confidence_adjustment=round(confidence_adjustment, 6),
            jitter=round(jitter, 6),
            total=round(total, 6),
        )

    def _dynamic_threshold(
        self,
        agent_state: AgentState,
        observation: Observation,
    ) -> float:
        """Raise or lower the click threshold based on current state and scenario."""
        runtime_profile = (
            observation.scenario_context.runtime_profile or observation.scenario_context.scenario_name
        )
        is_sparse = runtime_profile == "sparse-history-home-feed"
        threshold = (
            agent_state.click_threshold
            + (agent_state.frustration * 0.18)
            + max(0.0, 0.55 - agent_state.trust) * 0.14
            - (agent_state.satisfaction * 0.1)
            - (agent_state.engagement_baseline * 0.07)
        )
        if is_sparse:
            threshold -= (
                (0.05 * agent_state.sparse_history_confidence)
                + (0.03 * agent_state.novelty_preference)
                + (0.05 * agent_state.popularity_preference)
            )
        return round(max(0.2, threshold), 6)

    def _build_explanation(
        self,
        *,
        action: Action,
        best: CandidateEvaluation,
        threshold: float,
    ) -> DecisionExplanation:
        """Record why the runtime chose the final action for this step."""
        chosen_utility = best.breakdown.total if action.name == "click" else 0.0
        return DecisionExplanation(
            chosen_item_id=action.selected_item_id,
            top_candidate_item_id=best.signals.item_id,
            action_threshold=round(threshold, 6),
            chosen_utility=round(chosen_utility, 6),
            top_candidate_utility=best.breakdown.total,
            dominant_component=self._dominant_component(best.breakdown),
            top_candidate_breakdown=best.breakdown,
            reason=action.reason,
        )

    def _dominant_component(self, breakdown: UtilityBreakdown) -> str:
        """Return the strongest positive or negative utility component."""
        weights = {
            "base_relevance": breakdown.base_relevance,
            "affinity": breakdown.affinity,
            "familiarity": breakdown.familiarity,
            "novelty": breakdown.novelty,
            "quality": breakdown.quality,
            "scenario_adjustment": breakdown.scenario_adjustment,
            "confidence_adjustment": breakdown.confidence_adjustment,
            "repetition_penalty": -breakdown.repetition_penalty,
        }
        return max(weights, key=lambda key: abs(weights[key]))
