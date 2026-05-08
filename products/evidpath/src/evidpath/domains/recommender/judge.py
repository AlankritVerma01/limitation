"""Deterministic trace scoring for recommender interaction audits."""

from __future__ import annotations

from ...schema import FailureMode, ScoringConfig, SessionTrace, TraceScore


class RecommenderJudge:
    """Scores a completed trace using deterministic behavioral diagnostics."""

    def score_trace(
        self,
        session_trace: SessionTrace,
        scoring_config: ScoringConfig,
    ) -> TraceScore:
        exposures = [
            item for step in session_trace.steps for item in step.ranked_list.items
        ]
        exposure_ids = [item.item_id for item in exposures]
        repeated_exposures = len(exposure_ids) - len(set(exposure_ids))
        repetition = repeated_exposures / len(exposures) if exposures else 0.0

        top_candidate_ids = [
            step.decision_explanation.top_candidate_item_id
            for step in session_trace.steps
            if step.decision_explanation is not None
            and step.decision_explanation.top_candidate_item_id is not None
        ]
        stale_top_candidates = len(top_candidate_ids) - len(set(top_candidate_ids))
        stale_exposure_rate = (
            stale_top_candidates / len(top_candidate_ids) if top_candidate_ids else 0.0
        )

        concentration = 0.0
        if exposures:
            concentration = sum(
                item.popularity >= scoring_config.high_popularity_threshold
                for item in exposures
            ) / len(exposures)

        click_items = []
        click_scores = []
        click_novelties = []
        click_steps = []
        for step in session_trace.steps:
            if step.action.selected_item_id is None:
                continue
            clicked = next(
                (
                    item
                    for item in step.ranked_list.items
                    if item.item_id == step.action.selected_item_id
                ),
                None,
            )
            if clicked is None:
                continue
            click_items.append(clicked)
            click_scores.append(clicked.score)
            click_novelties.append(clicked.novelty)
            click_steps.append(step.step_index + 1)

        top_candidate_utilities = [
            step.decision_explanation.top_candidate_utility
            for step in session_trace.steps
            if step.decision_explanation is not None
        ]
        top_candidate_novelties = [
            self._top_candidate_novelty(step)
            for step in session_trace.steps
            if step.decision_explanation is not None
        ]
        top_candidate_novelties = [value for value in top_candidate_novelties if value is not None]

        click_count = sum(step.action.name == "click" for step in session_trace.steps)
        skip_count = sum(step.action.name == "skip" for step in session_trace.steps)
        engagement = click_count / session_trace.completed_steps if session_trace.completed_steps else 0.0
        skip_rate = skip_count / session_trace.completed_steps if session_trace.completed_steps else 0.0
        runtime_profile = (
            session_trace.steps[0].observation.scenario_context.runtime_profile
            if session_trace.steps
            else ""
        )

        final_state = session_trace.steps[-1].agent_state_after if session_trace.steps else None
        initial_state = session_trace.steps[0].agent_state_before if session_trace.steps else None
        frustration = final_state.frustration if final_state else 0.0
        satisfaction = final_state.satisfaction if final_state else 0.0
        initial_frustration = initial_state.frustration if initial_state else 0.0
        initial_trust = initial_state.trust if initial_state else 0.0
        initial_confidence = initial_state.confidence if initial_state else 0.0
        trust_delta = (final_state.trust - initial_trust) if final_state and initial_state else 0.0
        confidence_delta = (
            final_state.confidence - initial_confidence
            if final_state and initial_state
            else 0.0
        )
        frustration_delta = (
            final_state.frustration - initial_frustration
            if final_state and initial_state
            else 0.0
        )

        mean_click_quality = sum(click_scores) / len(click_scores) if click_scores else 0.0
        mean_top_candidate_utility = (
            sum(top_candidate_utilities) / len(top_candidate_utilities)
            if top_candidate_utilities
            else 0.0
        )
        genre_alignment_rate = (
            sum(
                clicked.genre in session_trace.agent_seed.preferred_genres
                for clicked in click_items
            )
            / len(click_items)
            if click_items
            else 0.0
        )
        novelty_source = click_novelties if click_novelties else top_candidate_novelties
        novelty_intensity = (
            sum(novelty_source) / len(novelty_source)
            if novelty_source
            else 0.0
        )
        click_depth = (
            sum(step / session_trace.completed_steps for step in click_steps) / len(click_steps)
            if click_steps and session_trace.completed_steps
            else 0.0
        )
        first_impression_score = self._first_impression_score(session_trace)
        exploration_acceptance_rate = self._exploration_acceptance_rate(session_trace)
        trust_erosion = max(0.0, -trust_delta)
        recovery_strength = self._recovery_strength(session_trace)
        cold_start_quality = self._cold_start_quality(
            runtime_profile=runtime_profile,
            mean_top_candidate_utility=mean_top_candidate_utility,
            first_impression_score=first_impression_score,
        )
        abandonment_pressure = self._abandonment_pressure(
            session_trace=session_trace,
            frustration_delta=frustration_delta,
        )

        session_utility = (
            (scoring_config.utility_weight * (mean_click_quality + satisfaction))
            + (0.15 * max(0.0, trust_delta))
            - (scoring_config.frustration_weight * frustration)
            - (0.12 if session_trace.abandoned else 0.0)
        )
        abandonment_step = (
            session_trace.completed_steps if session_trace.abandoned else None
        )
        dominant_failure_mode = self._classify_failure_mode(
            session_trace=session_trace,
            session_utility=session_utility,
            mean_top_candidate_utility=mean_top_candidate_utility,
            concentration=concentration,
            repetition=repetition,
            stale_exposure_rate=stale_exposure_rate,
            genre_alignment_rate=genre_alignment_rate,
            novelty_intensity=novelty_intensity,
            trust_delta=trust_delta,
            frustration_delta=frustration_delta,
            abandonment_step=abandonment_step,
            first_impression_score=first_impression_score,
            abandonment_pressure=abandonment_pressure,
        )
        trace_risk_score = self._trace_risk_score(
            session_trace=session_trace,
            session_utility=session_utility,
            concentration=concentration,
            stale_exposure_rate=stale_exposure_rate,
            trust_delta=trust_delta,
            frustration_delta=frustration_delta,
            dominant_failure_mode=dominant_failure_mode,
            first_impression_score=first_impression_score,
            abandonment_pressure=abandonment_pressure,
        )
        evidence_summary = self._failure_evidence_summary(
            session_trace=session_trace,
            dominant_failure_mode=dominant_failure_mode,
            abandonment_step=abandonment_step,
            trust_delta=trust_delta,
            confidence_delta=confidence_delta,
            frustration_delta=frustration_delta,
            stale_exposure_rate=stale_exposure_rate,
            concentration=concentration,
            genre_alignment_rate=genre_alignment_rate,
            novelty_intensity=novelty_intensity,
            mean_top_candidate_utility=mean_top_candidate_utility,
            first_impression_score=first_impression_score,
            abandonment_pressure=abandonment_pressure,
        )

        rounded_metrics = {
            "click_count": click_count,
            "session_utility": round(session_utility, 6),
            "repetition": round(repetition, 6),
            "concentration": round(concentration, 6),
            "engagement": round(engagement, 6),
            "frustration": round(frustration, 6),
            "mean_click_quality": round(mean_click_quality, 6),
            "mean_top_candidate_utility": round(mean_top_candidate_utility, 6),
            "trust_delta": round(trust_delta, 6),
            "confidence_delta": round(confidence_delta, 6),
            "frustration_delta": round(frustration_delta, 6),
            "skip_rate": round(skip_rate, 6),
            "click_depth": round(click_depth, 6),
            "stale_exposure_rate": round(stale_exposure_rate, 6),
            "genre_alignment_rate": round(genre_alignment_rate, 6),
            "novelty_intensity": round(novelty_intensity, 6),
            "first_impression_score": round(first_impression_score, 6),
            "exploration_acceptance_rate": round(exploration_acceptance_rate, 6),
            "trust_erosion": round(trust_erosion, 6),
            "recovery_strength": round(recovery_strength, 6),
            "cold_start_quality": round(cold_start_quality, 6),
            "abandonment_pressure": round(abandonment_pressure, 6),
            "dominant_failure_mode": dominant_failure_mode,
            "trace_risk_score": round(trace_risk_score, 6),
        }
        return TraceScore(
            trace_id=session_trace.trace_id,
            scenario_name=session_trace.scenario_name,
            archetype_label=session_trace.agent_seed.archetype_label,
            steps_completed=session_trace.completed_steps,
            abandoned=session_trace.abandoned,
            click_count=int(rounded_metrics["click_count"]),
            session_utility=float(rounded_metrics["session_utility"]),
            repetition=float(rounded_metrics["repetition"]),
            concentration=float(rounded_metrics["concentration"]),
            engagement=float(rounded_metrics["engagement"]),
            frustration=float(rounded_metrics["frustration"]),
            abandonment_step=abandonment_step,
            mean_click_quality=float(rounded_metrics["mean_click_quality"]),
            mean_top_candidate_utility=float(
                rounded_metrics["mean_top_candidate_utility"]
            ),
            trust_delta=float(rounded_metrics["trust_delta"]),
            confidence_delta=float(rounded_metrics["confidence_delta"]),
            frustration_delta=float(rounded_metrics["frustration_delta"]),
            skip_rate=float(rounded_metrics["skip_rate"]),
            click_depth=float(rounded_metrics["click_depth"]),
            stale_exposure_rate=float(rounded_metrics["stale_exposure_rate"]),
            genre_alignment_rate=float(rounded_metrics["genre_alignment_rate"]),
            novelty_intensity=float(rounded_metrics["novelty_intensity"]),
            first_impression_score=float(rounded_metrics["first_impression_score"]),
            exploration_acceptance_rate=float(
                rounded_metrics["exploration_acceptance_rate"]
            ),
            trust_erosion=float(rounded_metrics["trust_erosion"]),
            recovery_strength=float(rounded_metrics["recovery_strength"]),
            cold_start_quality=float(rounded_metrics["cold_start_quality"]),
            abandonment_pressure=float(rounded_metrics["abandonment_pressure"]),
            dominant_failure_mode=dominant_failure_mode,
            trace_risk_score=float(rounded_metrics["trace_risk_score"]),
            failure_evidence_summary=evidence_summary,
            domain_metrics=rounded_metrics,
        )

    def _classify_failure_mode(
        self,
        *,
        session_trace: SessionTrace,
        session_utility: float,
        mean_top_candidate_utility: float,
        concentration: float,
        repetition: float,
        stale_exposure_rate: float,
        genre_alignment_rate: float,
        novelty_intensity: float,
        trust_delta: float,
        frustration_delta: float,
        abandonment_step: int | None,
        first_impression_score: float,
        abandonment_pressure: float,
    ) -> FailureMode:
        """Pick one deterministic failure label using the trace evidence precedence."""
        if session_trace.abandoned and abandonment_step is not None and abandonment_step <= 2:
            return "early_abandonment"
        if first_impression_score < 0.33 and abandonment_pressure >= 0.42:
            return "early_abandonment"
        if (
            session_trace.abandoned
            and (trust_delta <= -0.22 or frustration_delta >= 0.25)
        ) or (
            trust_delta <= -0.3 and frustration_delta >= 0.18
        ):
            return "trust_collapse"
        if mean_top_candidate_utility < 0.48 and session_utility < 0.45:
            return "low_relevance"
        if stale_exposure_rate >= 0.34 or repetition >= 0.34:
            return "over_repetition"
        if concentration >= 0.65 and session_utility < 0.58:
            return "head_item_concentration"
        if session_trace.agent_seed.novelty_preference >= 0.65 and novelty_intensity <= 0.38:
            return "novelty_mismatch"
        if click_count := sum(step.action.name == "click" for step in session_trace.steps):
            if genre_alignment_rate < 0.35 and click_count > 0 and session_utility < 0.58:
                return "poor_genre_alignment"
        return "no_major_failure"

    def _trace_risk_score(
        self,
        *,
        session_trace: SessionTrace,
        session_utility: float,
        concentration: float,
        stale_exposure_rate: float,
        trust_delta: float,
        frustration_delta: float,
        dominant_failure_mode: FailureMode,
        first_impression_score: float,
        abandonment_pressure: float,
    ) -> float:
        """Convert trace-level failures into one bounded risk score."""
        score = 0.0
        if session_trace.abandoned:
            score += 0.34
        score += max(0.0, 0.55 - session_utility) * 0.55
        score += max(0.0, -trust_delta) * 0.35
        score += max(0.0, frustration_delta) * 0.28
        score += max(0.0, stale_exposure_rate - 0.18) * 0.32
        score += max(0.0, 0.45 - first_impression_score) * 0.22
        score += abandonment_pressure * 0.18
        if session_utility < 0.58:
            score += max(0.0, concentration - 0.5) * 0.24
        if dominant_failure_mode not in {"no_major_failure"}:
            score += 0.08
        return max(0.0, min(1.0, score))

    def _failure_evidence_summary(
        self,
        *,
        session_trace: SessionTrace,
        dominant_failure_mode: FailureMode,
        abandonment_step: int | None,
        trust_delta: float,
        confidence_delta: float,
        frustration_delta: float,
        stale_exposure_rate: float,
        concentration: float,
        genre_alignment_rate: float,
        novelty_intensity: float,
        mean_top_candidate_utility: float,
        first_impression_score: float,
        abandonment_pressure: float,
    ) -> str:
        """Return a short evidence string that explains the dominant failure label."""
        if dominant_failure_mode == "early_abandonment":
            return (
                f"abandoned at step {abandonment_step} after "
                f"{sum(step.action.name == 'skip' for step in session_trace.steps)} consecutive skips"
            )
        if dominant_failure_mode == "trust_collapse":
            before = session_trace.steps[0].agent_state_before if session_trace.steps else None
            after = session_trace.steps[-1].agent_state_after if session_trace.steps else None
            if before is not None and after is not None:
                return (
                    f"abandoned at step {abandonment_step} after trust fell "
                    f"{before.trust:.2f}->{after.trust:.2f} and confidence "
                    f"{before.confidence:.2f}->{after.confidence:.2f}"
                )
        if dominant_failure_mode == "low_relevance":
            return f"top-candidate utility stayed low at {mean_top_candidate_utility:.2f}"
        if dominant_failure_mode == "over_repetition":
            return f"stale exposure rate reached {stale_exposure_rate:.2f}"
        if dominant_failure_mode == "head_item_concentration":
            return f"head-item concentration reached {concentration:.2f} under weak utility"
        if dominant_failure_mode == "poor_genre_alignment":
            return f"genre alignment held at only {genre_alignment_rate:.2f}"
        if dominant_failure_mode == "novelty_mismatch":
            return f"novelty intensity landed at {novelty_intensity:.2f} for a novelty-seeking cohort"
        if first_impression_score < 0.45:
            return (
                f"first impression weakened to {first_impression_score:.2f} with "
                f"abandonment pressure {abandonment_pressure:.2f}"
            )
        return (
            f"trust delta {trust_delta:.2f}, confidence delta {confidence_delta:.2f}, "
            f"frustration delta {frustration_delta:.2f}"
        )

    def _first_impression_score(self, session_trace: SessionTrace) -> float:
        """Summarize how strong the first two steps felt to the user."""
        first_steps = session_trace.steps[:2]
        if not first_steps:
            return 0.0
        values: list[float] = []
        for step in first_steps:
            top_utility = (
                step.decision_explanation.top_candidate_utility
                if step.decision_explanation is not None
                else 0.0
            )
            value = top_utility
            if step.action.name == "click":
                value += 0.08
            elif step.action.name == "skip":
                value -= 0.08
            elif step.action.name == "abandon":
                value -= 0.18
            values.append(max(0.0, min(1.0, value)))
        return sum(values) / len(values)

    def _exploration_acceptance_rate(self, session_trace: SessionTrace) -> float:
        """Measure acceptance of high-novelty opportunities."""
        opportunities = 0
        acceptances = 0
        for step in session_trace.steps:
            high_novelty_items = [
                item for item in step.ranked_list.items if item.novelty >= 0.65
            ]
            if not high_novelty_items:
                continue
            opportunities += 1
            if (
                step.action.name == "click"
                and step.action.selected_item_id is not None
                and any(item.item_id == step.action.selected_item_id for item in high_novelty_items)
            ):
                acceptances += 1
        if opportunities == 0:
            return 0.0
        return acceptances / opportunities

    def _recovery_strength(self, session_trace: SessionTrace) -> float:
        """Measure whether the user recovered after earlier friction."""
        if not session_trace.steps:
            return 0.0
        initial = session_trace.steps[0].agent_state_before
        final = session_trace.steps[-1].agent_state_after
        peak_frustration = max(step.agent_state_after.frustration for step in session_trace.steps)
        frustration_recovery = max(0.0, peak_frustration - final.frustration)
        trust_recovery = max(0.0, final.trust - initial.trust)
        return max(0.0, min(1.0, frustration_recovery + (0.5 * trust_recovery)))

    def _cold_start_quality(
        self,
        *,
        runtime_profile: str,
        mean_top_candidate_utility: float,
        first_impression_score: float,
    ) -> float:
        """Estimate recommendation quality under sparse or onboarding conditions."""
        if runtime_profile not in {
            "sparse-history-home-feed",
            "taste-elicitation-home-feed",
        }:
            return 0.0
        return max(
            0.0,
            min(1.0, (0.6 * first_impression_score) + (0.4 * mean_top_candidate_utility)),
        )

    def _abandonment_pressure(
        self,
        *,
        session_trace: SessionTrace,
        frustration_delta: float,
    ) -> float:
        """Measure how strongly the session drifted toward abandonment."""
        if not session_trace.steps:
            return 0.0
        threshold_gaps = [
            max(
                0.0,
                step.decision_explanation.action_threshold
                - step.decision_explanation.top_candidate_utility,
            )
            for step in session_trace.steps
            if step.decision_explanation is not None
        ]
        mean_gap = sum(threshold_gaps) / len(threshold_gaps) if threshold_gaps else 0.0
        skip_rate = (
            sum(step.action.name == "skip" for step in session_trace.steps)
            / len(session_trace.steps)
        )
        pressure = (0.45 * mean_gap) + (0.3 * skip_rate) + (0.25 * max(0.0, frustration_delta))
        if session_trace.abandoned:
            pressure += 0.2
        return max(0.0, min(1.0, pressure))

    def _top_candidate_novelty(self, step) -> float | None:
        """Look up novelty for the top-ranked candidate referenced in the explanation."""
        top_item_id = (
            step.decision_explanation.top_candidate_item_id
            if step.decision_explanation is not None
            else None
        )
        if top_item_id is None:
            return None
        top_item = next(
            (item for item in step.ranked_list.items if item.item_id == top_item_id),
            None,
        )
        return top_item.novelty if top_item is not None else None
