"""Structured advisory semantic interpretation above deterministic evidence."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Protocol

from .generation_support import (
    DEFAULT_PROVIDER_MODEL,
    DEFAULT_PROVIDER_NAME,
    build_responses_endpoint,
    extract_response_text,
    load_dotenv_if_present,
    read_retry_count,
    read_timeout_seconds,
    request_provider_payload,
)
from .schema import (
    RegressionDiff,
    RunResult,
    SemanticRegressionInterpretation,
    SemanticRunInterpretation,
    SemanticTraceExplanation,
)


class SemanticInterpreter(Protocol):
    """Interpret deterministic evidence into structured advisory outputs."""

    def interpret_run(self, run_result: RunResult) -> SemanticRunInterpretation: ...

    def interpret_regression(
        self,
        regression_diff: RegressionDiff,
    ) -> SemanticRegressionInterpretation: ...


class FixtureSemanticInterpreter:
    """Deterministic semantic interpreter for tests, CI, and offline demos."""

    def interpret_run(self, run_result: RunResult) -> SemanticRunInterpretation:
        contexts = _run_trace_contexts(run_result)
        explanations = tuple(_fixture_run_trace_explanation(context) for context in contexts)
        return SemanticRunInterpretation(
            mode="fixture",
            advisory_summary=_fixture_run_summary(run_result, explanations),
            trace_explanations=explanations,
            generated_at_utc=_now_utc(),
        )

    def interpret_regression(
        self,
        regression_diff: RegressionDiff,
    ) -> SemanticRegressionInterpretation:
        contexts = _regression_trace_contexts(regression_diff)
        explanations = tuple(
            _fixture_regression_trace_explanation(context) for context in contexts
        )
        return SemanticRegressionInterpretation(
            mode="fixture",
            advisory_summary=_fixture_regression_summary(regression_diff, explanations),
            trace_explanations=explanations,
            generated_at_utc=_now_utc(),
        )


class ProviderSemanticInterpreter:
    """Provider-backed semantic interpreter that returns structured JSON only."""

    def __init__(
        self,
        *,
        provider_name: str = DEFAULT_PROVIDER_NAME,
        model_name: str = DEFAULT_PROVIDER_MODEL,
        api_key_env: str = "OPENAI_API_KEY",
        base_url_env: str = "OPENAI_BASE_URL",
        timeout_seconds_env: str = "OPENAI_TIMEOUT_SECONDS",
        retry_count_env: str = "OPENAI_RETRY_COUNT",
    ) -> None:
        self.provider_name = provider_name
        self.model_name = model_name
        self.api_key_env = api_key_env
        self.base_url_env = base_url_env
        self.timeout_seconds_env = timeout_seconds_env
        self.retry_count_env = retry_count_env

    def interpret_run(self, run_result: RunResult) -> SemanticRunInterpretation:
        contexts = _run_trace_contexts(run_result)
        prompt = self._build_run_prompt(run_result, contexts)
        parsed = self._request_json(prompt, purpose="semantic run interpretation")
        return _build_run_interpretation_from_provider(
            parsed=parsed,
            expected_trace_ids=tuple(context["trace_id"] for context in contexts),
            provider_name=self.provider_name,
            model_name=self.model_name,
        )

    def interpret_regression(
        self,
        regression_diff: RegressionDiff,
    ) -> SemanticRegressionInterpretation:
        contexts = _regression_trace_contexts(regression_diff)
        prompt = self._build_regression_prompt(regression_diff, contexts)
        parsed = self._request_json(prompt, purpose="semantic regression interpretation")
        return _build_regression_interpretation_from_provider(
            parsed=parsed,
            expected_trace_ids=tuple(context["trace_id"] for context in contexts),
            provider_name=self.provider_name,
            model_name=self.model_name,
        )

    def _request_json(self, prompt: str, *, purpose: str) -> dict[str, object]:
        import os

        load_dotenv_if_present()
        api_key = os.getenv(self.api_key_env)
        if not api_key:
            raise RuntimeError(
                f"{self.api_key_env} is required for provider-backed semantic interpretation."
            )
        endpoint = build_responses_endpoint(os.getenv(self.base_url_env))
        payload = request_provider_payload(
            endpoint=endpoint,
            api_key=api_key,
            model_name=self.model_name,
            prompt=prompt,
            timeout_seconds=read_timeout_seconds(self.timeout_seconds_env),
            retry_count=read_retry_count(self.retry_count_env),
            purpose=purpose,
        )
        raw_text = extract_response_text(payload)
        try:
            parsed = json.loads(raw_text)
        except json.JSONDecodeError as exc:
            raise ValueError(
                "Provider returned malformed JSON for semantic interpretation."
            ) from exc
        if not isinstance(parsed, dict):
            raise ValueError("Provider semantic interpretation must return a JSON object.")
        return parsed

    def _build_run_prompt(
        self,
        run_result: RunResult,
        trace_contexts: tuple[dict[str, object], ...],
    ) -> str:
        payload = {
            "run": {
                "run_id": str(run_result.metadata.get("run_id", "")),
                "display_name": str(
                    run_result.metadata.get("display_name", run_result.run_config.run_name)
                ),
                "high_risk_cohort_count": sum(
                    1 for cohort in run_result.cohort_summaries if cohort.risk_level == "high"
                ),
                "risk_flag_count": len(run_result.risk_flags),
                "slice_count": len(run_result.slice_discovery.slice_summaries),
            },
            "trace_contexts": trace_contexts,
        }
        return (
            "You generate structured advisory explanations for deterministic interaction audits.\n"
            "Return JSON only. Do not add markdown. Do not invent evidence.\n"
            "Use only the supplied deterministic evidence.\n"
            "Return this exact shape:\n"
            "{\n"
            '  "advisory_summary": "string",\n'
            '  "trace_explanations": [\n'
            "    {\n"
            '      "trace_id": "string",\n'
            '      "explanation_summary": "string",\n'
            '      "issue_theme": "string",\n'
            '      "recommended_follow_up": "string",\n'
            '      "grounding_references": ["string"]\n'
            "    }\n"
            "  ]\n"
            "}\n"
            "Explain each requested trace exactly once. Keep the writing compact and grounded.\n"
            f"Evidence: {json.dumps(payload, sort_keys=True)}"
        )

    def _build_regression_prompt(
        self,
        regression_diff: RegressionDiff,
        trace_contexts: tuple[dict[str, object], ...],
    ) -> str:
        payload = {
            "regression": {
                "regression_id": str(regression_diff.metadata.get("regression_id", "")),
                "baseline_label": regression_diff.baseline_summary.target.label,
                "candidate_label": regression_diff.candidate_summary.target.label,
                "decision": regression_diff.decision.status if regression_diff.decision else "pass",
                "slice_change_count": len(
                    [delta for delta in regression_diff.slice_deltas if delta.change_type != "stable"]
                ),
                "risk_change_count": len(
                    [
                        delta
                        for delta in regression_diff.risk_flag_deltas
                        if delta.baseline_count != delta.candidate_count
                    ]
                ),
            },
            "trace_contexts": trace_contexts,
        }
        return (
            "You generate structured advisory explanations for deterministic regression audits.\n"
            "Return JSON only. Do not add markdown. Do not invent evidence.\n"
            "Use only the supplied deterministic evidence.\n"
            "Return this exact shape:\n"
            "{\n"
            '  "advisory_summary": "string",\n'
            '  "trace_explanations": [\n'
            "    {\n"
            '      "trace_id": "string",\n'
            '      "explanation_summary": "string",\n'
            '      "issue_theme": "string",\n'
            '      "recommended_follow_up": "string",\n'
            '      "grounding_references": ["string"]\n'
            "    }\n"
            "  ]\n"
            "}\n"
            "Explain each requested trace exactly once. Keep the writing compact and grounded.\n"
            f"Evidence: {json.dumps(payload, sort_keys=True)}"
        )


def interpret_run_semantics(
    run_result: RunResult,
    *,
    mode: str,
    model_name: str = DEFAULT_PROVIDER_MODEL,
) -> SemanticRunInterpretation | None:
    """Interpret one run when semantic mode is explicitly enabled."""
    if mode == "off":
        return None
    interpreter: SemanticInterpreter
    if mode == "fixture":
        interpreter = FixtureSemanticInterpreter()
    elif mode == "provider":
        interpreter = ProviderSemanticInterpreter(model_name=model_name)
    else:
        raise ValueError(f"Unsupported semantic mode `{mode}`.")
    return interpreter.interpret_run(run_result)


def interpret_regression_semantics(
    regression_diff: RegressionDiff,
    *,
    mode: str,
    model_name: str = DEFAULT_PROVIDER_MODEL,
) -> SemanticRegressionInterpretation | None:
    """Interpret one regression diff when semantic mode is explicitly enabled."""
    if mode == "off":
        return None
    interpreter: SemanticInterpreter
    if mode == "fixture":
        interpreter = FixtureSemanticInterpreter()
    elif mode == "provider":
        interpreter = ProviderSemanticInterpreter(model_name=model_name)
    else:
        raise ValueError(f"Unsupported semantic mode `{mode}`.")
    return interpreter.interpret_regression(regression_diff)


def _run_trace_contexts(run_result: RunResult) -> tuple[dict[str, object], ...]:
    trace_lookup = {trace.trace_id: trace for trace in run_result.traces}
    score_lookup = {score.trace_id: score for score in run_result.trace_scores}
    selected_trace_ids: list[str] = []
    failure_ids = [
        cohort.representative_failure_trace_id
        for cohort in run_result.cohort_summaries
        if cohort.representative_failure_trace_id is not None
    ]
    for trace_id in failure_ids:
        if trace_id not in selected_trace_ids:
            selected_trace_ids.append(trace_id)
        if len(selected_trace_ids) >= 2:
            break
    success_id = next(
        (
            cohort.representative_success_trace_id
            for cohort in run_result.cohort_summaries
            if cohort.representative_success_trace_id is not None
            and cohort.representative_success_trace_id not in selected_trace_ids
        ),
        None,
    )
    if success_id is not None:
        selected_trace_ids.append(success_id)
    contexts = []
    for trace_id in selected_trace_ids[:3]:
        trace = trace_lookup.get(trace_id)
        score = score_lookup.get(trace_id)
        if trace is None or score is None:
            continue
        contexts.append(
            {
                "trace_id": trace.trace_id,
                "scenario_name": trace.scenario_name,
                "scenario_profile": _scenario_profile(trace),
                "archetype_label": trace.agent_seed.archetype_label,
                "dominant_failure_mode": score.dominant_failure_mode,
                "session_utility": score.session_utility,
                "trust_delta": score.trust_delta,
                "skip_rate": score.skip_rate,
                "abandoned": score.abandoned,
                "failure_evidence_summary": score.failure_evidence_summary,
                "slice_signatures": _trace_slice_signatures(run_result, trace.trace_id),
                "step_snippets": _trace_step_snippets(trace),
            }
        )
    return tuple(contexts)


def _regression_trace_contexts(
    regression_diff: RegressionDiff,
) -> tuple[dict[str, object], ...]:
    contexts = []
    for trace_delta in regression_diff.notable_trace_deltas[:3]:
        contexts.append(
            {
                "trace_id": trace_delta.trace_id,
                "scenario_name": trace_delta.scenario_name,
                "archetype_label": trace_delta.archetype_label,
                "session_utility_delta": trace_delta.session_utility_delta,
                "trace_risk_score_delta": trace_delta.trace_risk_score_delta,
                "baseline_failure_mode": trace_delta.baseline_failure_mode,
                "candidate_failure_mode": trace_delta.candidate_failure_mode,
                "slice_changes": [
                    ", ".join(slice_delta.feature_signature)
                    for slice_delta in regression_diff.slice_deltas
                    if slice_delta.change_type != "stable"
                ][:3],
            }
        )
    return tuple(contexts)


def _build_run_interpretation_from_provider(
    *,
    parsed: dict[str, object],
    expected_trace_ids: tuple[str, ...],
    provider_name: str,
    model_name: str,
) -> SemanticRunInterpretation:
    advisory_summary = _require_string(parsed, "advisory_summary")
    explanations = _parse_trace_explanations(parsed, expected_trace_ids)
    return SemanticRunInterpretation(
        mode="provider",
        advisory_summary=advisory_summary,
        trace_explanations=explanations,
        generated_at_utc=_now_utc(),
        provider_name=provider_name,
        model_name=model_name,
    )


def _build_regression_interpretation_from_provider(
    *,
    parsed: dict[str, object],
    expected_trace_ids: tuple[str, ...],
    provider_name: str,
    model_name: str,
) -> SemanticRegressionInterpretation:
    advisory_summary = _require_string(parsed, "advisory_summary")
    explanations = _parse_trace_explanations(parsed, expected_trace_ids)
    return SemanticRegressionInterpretation(
        mode="provider",
        advisory_summary=advisory_summary,
        trace_explanations=explanations,
        generated_at_utc=_now_utc(),
        provider_name=provider_name,
        model_name=model_name,
    )


def _parse_trace_explanations(
    parsed: dict[str, object],
    expected_trace_ids: tuple[str, ...],
) -> tuple[SemanticTraceExplanation, ...]:
    raw_explanations = parsed.get("trace_explanations")
    if not isinstance(raw_explanations, list):
        raise ValueError("Semantic interpretation output must include `trace_explanations`.")
    explanations = []
    seen_trace_ids: list[str] = []
    for raw in raw_explanations:
        if not isinstance(raw, dict):
            raise ValueError("Each semantic trace explanation must be a JSON object.")
        trace_id = _require_string(raw, "trace_id")
        grounding_references = raw.get("grounding_references")
        if not isinstance(grounding_references, list) or not all(
            isinstance(value, str) for value in grounding_references
        ):
            raise ValueError("`grounding_references` must be a list of strings.")
        explanations.append(
            SemanticTraceExplanation(
                trace_id=trace_id,
                explanation_summary=_require_string(raw, "explanation_summary"),
                issue_theme=_require_string(raw, "issue_theme"),
                recommended_follow_up=_require_string(raw, "recommended_follow_up"),
                grounding_references=tuple(grounding_references),
            )
        )
        seen_trace_ids.append(trace_id)
    if tuple(seen_trace_ids) != expected_trace_ids:
        raise ValueError(
            "Semantic interpretation must explain exactly the requested trace ids in order."
        )
    return tuple(explanations)


def _fixture_run_trace_explanation(context: dict[str, object]) -> SemanticTraceExplanation:
    trace_id = str(context["trace_id"])
    failure_mode = str(context["dominant_failure_mode"])
    scenario_name = str(context["scenario_name"])
    archetype = str(context["archetype_label"])
    utility = float(context["session_utility"])
    trust_delta = float(context["trust_delta"])
    skip_rate = float(context["skip_rate"])
    abandoned = bool(context["abandoned"])
    if failure_mode == "no_major_failure":
        issue_theme = "healthy engagement"
        explanation_summary = (
            f"{archetype} stayed comparatively healthy in {scenario_name}, with stable trust and usable utility."
        )
        recommended_follow_up = (
            "Use this trace as a contrast case when comparing weaker cohorts and slices."
        )
    else:
        issue_theme = failure_mode.replace("_", " ")
        abandonment_note = " and abandoned early" if abandoned else ""
        explanation_summary = (
            f"{archetype} shows {issue_theme} in {scenario_name}{abandonment_note}, "
            f"with utility {utility:.3f}, trust delta {trust_delta:.3f}, and skip rate {skip_rate:.3f}."
        )
        recommended_follow_up = (
            f"Inspect how the ranked slate and scenario context are pushing this trace toward {issue_theme}."
        )
    return SemanticTraceExplanation(
        trace_id=trace_id,
        explanation_summary=explanation_summary,
        issue_theme=issue_theme,
        recommended_follow_up=recommended_follow_up,
        grounding_references=_grounding_references(context),
    )


def _fixture_regression_trace_explanation(
    context: dict[str, object],
) -> SemanticTraceExplanation:
    trace_id = str(context["trace_id"])
    utility_delta = float(context["session_utility_delta"])
    risk_delta = float(context["trace_risk_score_delta"])
    baseline_failure = str(context["baseline_failure_mode"])
    candidate_failure = str(context["candidate_failure_mode"])
    direction = "regressed" if utility_delta < 0 or risk_delta > 0 else "improved"
    issue_theme = "comparison shift"
    explanation_summary = (
        f"Trace {trace_id} {direction}: utility changed by {utility_delta:+.3f}, risk changed by {risk_delta:+.3f}, "
        f"and failure mode moved from {baseline_failure} to {candidate_failure}."
    )
    recommended_follow_up = (
        "Review the candidate changes against the trace-level shift and the related discovered slice changes."
    )
    return SemanticTraceExplanation(
        trace_id=trace_id,
        explanation_summary=explanation_summary,
        issue_theme=issue_theme,
        recommended_follow_up=recommended_follow_up,
        grounding_references=_grounding_references(context),
    )


def _fixture_run_summary(
    run_result: RunResult,
    explanations: tuple[SemanticTraceExplanation, ...],
) -> str:
    high_risk = sum(1 for cohort in run_result.cohort_summaries if cohort.risk_level == "high")
    if not explanations:
        return "No semantic advisory was generated because no representative traces were available."
    if high_risk:
        return (
            f"The main advisory concern is concentrated in {high_risk} high-risk cohort(s), and the selected traces show how deterministic failures are surfacing at the session level."
        )
    return (
        "The selected traces mostly act as contrast cases: deterministic evidence looks stable overall, with semantic notes focused on why the strongest and weakest sessions differ."
    )


def _fixture_regression_summary(
    regression_diff: RegressionDiff,
    explanations: tuple[SemanticTraceExplanation, ...],
) -> str:
    if not explanations:
        return "No semantic advisory was generated because no notable changed traces were available."
    decision = regression_diff.decision.status if regression_diff.decision else "pass"
    changed_slices = len([delta for delta in regression_diff.slice_deltas if delta.change_type != "stable"])
    return (
        f"The comparison is still grounded in a deterministic `{decision}` decision; the semantic advisory highlights trace-level changes that align with {changed_slices} discovered slice change(s)."
    )


def _trace_slice_signatures(run_result: RunResult, trace_id: str) -> list[str]:
    slice_lookup = {
        summary.slice_id: ", ".join(summary.feature_signature)
        for summary in run_result.slice_discovery.slice_summaries
    }
    return [
        slice_lookup[membership.slice_id]
        for membership in run_result.slice_discovery.memberships
        if membership.trace_id == trace_id and membership.slice_id in slice_lookup
    ][:3]


def _trace_step_snippets(trace) -> list[str]:
    snippets: list[str] = []
    for step in trace.steps[:3]:
        selected_item = step.action.selected_item_id or "none"
        snippets.append(
            f"step {step.step_index + 1}: {step.action.name} ({selected_item}) because {step.action.reason}"
        )
    return snippets


def _grounding_references(context: dict[str, object]) -> tuple[str, ...]:
    references = []
    if "dominant_failure_mode" in context:
        references.append(f"dominant_failure_mode={context['dominant_failure_mode']}")
    if "session_utility" in context:
        references.append(f"session_utility={float(context['session_utility']):.3f}")
    if "trust_delta" in context:
        references.append(f"trust_delta={float(context['trust_delta']):.3f}")
    if "skip_rate" in context:
        references.append(f"skip_rate={float(context['skip_rate']):.3f}")
    if "session_utility_delta" in context:
        references.append(
            f"session_utility_delta={float(context['session_utility_delta']):+.3f}"
        )
    if "trace_risk_score_delta" in context:
        references.append(
            f"trace_risk_score_delta={float(context['trace_risk_score_delta']):+.3f}"
        )
    if "slice_signatures" in context:
        references.extend(f"slice={signature}" for signature in context["slice_signatures"])
    if "slice_changes" in context:
        references.extend(f"slice_change={signature}" for signature in context["slice_changes"])
    return tuple(references[:5])


def _scenario_profile(trace) -> str:
    if not trace.steps:
        return "unspecified"
    return trace.steps[0].observation.scenario_context.runtime_profile or "unspecified"


def _require_string(payload: dict[str, object], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Semantic interpretation output must include a non-empty `{key}`.")
    return value.strip()


def _now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
