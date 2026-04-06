"""Markdown artifact writer for the polished recommender audit."""

from __future__ import annotations

from pathlib import Path

from ..contracts.core import RunResult

_RISK_ORDER = {"low": 0, "medium": 1, "high": 2}


class MarkdownReportWriter:
    """Writes a clearer behavioral audit report from precomputed results."""

    def write(self, run_result: RunResult, output_dir: Path) -> dict[str, str]:
        """Write the human-facing markdown audit report for one run."""
        output_dir.mkdir(parents=True, exist_ok=True)
        report_path = output_dir / "report.md"
        report_title = str(
            run_result.metadata.get("audit_report_title", "Interaction Harness Recommender Audit")
        )
        lines = [f"# {report_title}"]
        lines.extend(self._run_summary_lines(run_result))
        lines.extend(self._launch_risk_lines(run_result))
        lines.extend(self._scenario_coverage_lines(run_result))
        lines.extend(self._cohort_summary_lines(run_result))
        lines.extend(self._discovered_slice_lines(run_result))
        lines.extend(self._representative_trace_lines(run_result))
        lines.extend(self._semantic_advisory_lines(run_result))
        lines.extend(self._metadata_lines(run_result))
        lines.extend(self._trace_score_lines(run_result))

        report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return {"report_path": str(report_path)}

    def _run_summary_lines(self, run_result: RunResult) -> list[str]:
        """Render the opening run metadata and summary section."""
        scenario_names = ", ".join(
            scenario.name for scenario in run_result.run_config.scenarios
        )
        service_kind = str(run_result.metadata.get("service_kind", "unknown"))
        lines = [
            "",
            "## Run Summary",
            "",
            f"- Run: `{run_result.run_config.run_name}`",
            f"- Run ID: `{run_result.metadata.get('run_id', 'unknown')}`",
            f"- Generated: `{run_result.metadata.get('generated_at_utc', 'unknown')}`",
            f"- Seed: `{run_result.run_config.rollout.seed}`",
            f"- Scenarios: `{scenario_names}`",
            f"- Traces: `{len(run_result.traces)}`",
            f"- Agent seeds: `{run_result.metadata.get('agent_count', len(run_result.run_config.agent_seeds))}`",
            f"- Service kind: `{service_kind}`",
            "",
            "## Executive Summary",
            "",
        ]
        lines.extend(f"- {line}" for line in self._executive_summary(run_result))
        return lines

    def _launch_risk_lines(self, run_result: RunResult) -> list[str]:
        """Render the risk section shown near the top of the report."""
        lines = ["", "## Launch Risks", ""]
        if not run_result.risk_flags:
            lines.append("- No medium or high risk cohorts were detected in this run.")
            return lines
        for flag in run_result.risk_flags:
            lines.append(
                f"- `{flag.severity}` {flag.scenario_name} / {flag.archetype_label}: "
                f"{flag.message} Evidence: {flag.evidence_summary}"
            )
        return lines

    def _scenario_coverage_lines(self, run_result: RunResult) -> list[str]:
        """Render the scenario pack used for this run."""
        lines = ["", "## Scenario Coverage", ""]
        for scenario in run_result.run_config.scenarios:
            risk_tags = ", ".join(scenario.risk_focus_tags) or "n/a"
            context_hint = scenario.context_hint or "n/a"
            lines.append(
                f"- `{scenario.name}`: {scenario.description} "
                f"(history depth `{scenario.history_depth}`, max steps `{scenario.max_steps}`, "
                f"goal `{scenario.test_goal or 'n/a'}`, risk tags `{risk_tags}`, "
                f"context hint `{context_hint}`)"
            )
        return lines

    def _cohort_summary_lines(self, run_result: RunResult) -> list[str]:
        """Render the cohort summary table."""
        lines = [
            "",
            "## Cohort Summary",
            "",
            "| Scenario | Archetype | Risk | Failure Mode | Utility | Trust Δ | Skip Rate |",
            "| --- | --- | --- | --- | --- | --- | --- |",
        ]
        for cohort in run_result.cohort_summaries:
            lines.append(
                f"| {cohort.scenario_name} | {cohort.archetype_label} | "
                f"{cohort.risk_level} | {cohort.dominant_failure_mode} | "
                f"{cohort.mean_session_utility:.3f} | {cohort.mean_trust_delta:.3f} | "
                f"{cohort.mean_skip_rate:.3f} |"
            )
        return lines

    def _representative_trace_lines(self, run_result: RunResult) -> list[str]:
        """Render a compact set of failure and success traces to inspect."""
        trace_lookup = {trace.trace_id: trace for trace in run_result.traces}
        failure_cohorts, success_cohorts = self._select_representative_cohorts(run_result)
        lines = ["", "## Representative Traces To Inspect", ""]
        if failure_cohorts:
            lines.extend(["", "### Highest-Risk Cohorts", ""])
            for cohort in failure_cohorts:
                trace = trace_lookup.get(cohort.representative_failure_trace_id)
                if trace is None:
                    continue
                lines.append(f"Failure trace: `{cohort.representative_failure_trace_id}`")
                lines.append(
                    f"`{cohort.scenario_name}` / `{cohort.archetype_label}` "
                    f"({cohort.dominant_failure_mode})"
                )
                lines.extend(self._render_trace_steps(trace))
                lines.append("")
        if success_cohorts:
            lines.extend(["### Strongest Cohorts", ""])
            for cohort in success_cohorts:
                trace = trace_lookup.get(cohort.representative_success_trace_id)
                if trace is None:
                    continue
                lines.append(f"Success trace: `{cohort.representative_success_trace_id}`")
                lines.append(
                    f"`{cohort.scenario_name}` / `{cohort.archetype_label}` "
                    f"(utility `{cohort.mean_session_utility:.3f}`)"
                )
                lines.extend(self._render_trace_steps(trace))
                lines.append("")
        if not failure_cohorts and not success_cohorts:
            lines.append("- No representative traces selected.")
        return lines

    def _metadata_lines(self, run_result: RunResult) -> list[str]:
        """Render the reproducibility and metadata section."""
        return [
            "",
            "## Reproducibility And Metadata",
            "",
            "- Runs are deterministic for a fixed seed and scenario selection.",
            "- The judge consumes completed traces only and does not call the system under test.",
            f"- Service artifact dir: `{run_result.metadata.get('service_artifact_dir', '') or 'n/a'}`",
            f"- Artifact ID: `{run_result.metadata.get('artifact_id', 'unknown')}`",
            f"- Scenario source: `{run_result.metadata.get('scenario_source', 'built_in')}`",
            f"- Scenario pack ID: `{run_result.metadata.get('scenario_pack_id', 'n/a')}`",
            f"- Population source: `{run_result.metadata.get('population_source', 'built_in_seeds')}`",
            f"- Population pack ID: `{run_result.metadata.get('population_pack_id', 'n/a')}`",
            f"- Population size source: `{run_result.metadata.get('population_size_source', 'built_in')}`",
            f"- Discovered slices: `{run_result.metadata.get('slice_count', len(run_result.slice_discovery.slice_summaries))}`",
            f"- Semantic mode: `{run_result.metadata.get('semantic_mode', 'off')}`",
        ]

    def _semantic_advisory_lines(self, run_result: RunResult) -> list[str]:
        """Render the optional advisory semantic interpretation section."""
        interpretation = run_result.semantic_interpretation
        lines = ["", "## Semantic Advisory", ""]
        if interpretation is None:
            lines.append("- Semantic interpretation was not enabled for this run.")
            return lines
        lines.append(f"- Mode: `{interpretation.mode}`")
        if interpretation.provider_name:
            lines.append(
                f"- Provider: `{interpretation.provider_name}` / `{interpretation.model_name or 'unknown'}`"
            )
        lines.append(f"- Advisory summary: {interpretation.advisory_summary}")
        for explanation in interpretation.trace_explanations:
            lines.append(
                f"- `{explanation.trace_id}`: {explanation.explanation_summary} "
                f"(theme `{explanation.issue_theme}`)"
            )
            lines.append(f"  follow-up: {explanation.recommended_follow_up}")
        return lines

    def _discovered_slice_lines(self, run_result: RunResult) -> list[str]:
        """Render the top discovered deterministic failure slices."""
        lines = [
            "",
            "## Discovered Failure Slices",
            "",
        ]
        slices = run_result.slice_discovery.slice_summaries[:5]
        if not slices:
            lines.append("- No deterministic failure slices met the support threshold in this run.")
            return lines
        for slice_summary in slices:
            signature = ", ".join(slice_summary.feature_signature)
            representative_traces = ", ".join(slice_summary.representative_trace_ids) or "n/a"
            lines.append(
                f"- `{slice_summary.slice_id}`: `{signature}` "
                f"(traces `{slice_summary.trace_count}`, risk `{slice_summary.risk_level}`, "
                f"failure `{slice_summary.dominant_failure_mode}`, utility `{slice_summary.mean_session_utility:.3f}`, "
                f"trust Δ `{slice_summary.mean_trust_delta:.3f}`, skip `{slice_summary.mean_skip_rate:.3f}`)"
            )
            lines.append(f"  representative traces: `{representative_traces}`")
        return lines

    def _trace_score_lines(self, run_result: RunResult) -> list[str]:
        """Render the compact per-trace score table."""
        lines = [
            "",
            "## Trace Scores",
            "",
            "| Trace | Scenario | Archetype | Utility | Failure Mode | Trust Δ | Skip Rate | Abandoned |",
            "| --- | --- | --- | --- | --- | --- | --- | --- |",
        ]
        for score in run_result.trace_scores:
            lines.append(
                f"| {score.trace_id} | {score.scenario_name} | {score.archetype_label} | "
                f"{score.session_utility:.3f} | {score.dominant_failure_mode} | "
                f"{score.trust_delta:.3f} | {score.skip_rate:.3f} | "
                f"{score.abandoned} |"
            )
        return lines

    def _executive_summary(self, run_result: RunResult) -> list[str]:
        """Return the short top-of-report summary lines."""
        high_risk = [cohort for cohort in run_result.cohort_summaries if cohort.risk_level == "high"]
        medium_risk = [cohort for cohort in run_result.cohort_summaries if cohort.risk_level == "medium"]
        strongest = max(
            run_result.cohort_summaries,
            key=lambda cohort: cohort.mean_session_utility,
            default=None,
        )
        weakest = min(
            run_result.cohort_summaries,
            key=lambda cohort: cohort.mean_session_utility,
            default=None,
        )
        lines: list[str] = []
        if high_risk:
            lines.append(
                f"Overall status is `mixed`: {len(high_risk)} high-risk cohort(s) and {len(medium_risk)} medium-risk cohort(s) were detected."
            )
        elif medium_risk:
            lines.append(
                f"Overall status is `watch`: no high-risk cohorts were detected, but {len(medium_risk)} medium-risk cohort(s) need follow-up."
            )
        else:
            lines.append("Overall status is `healthy`: no medium or high-risk cohorts were detected in this run.")
        if strongest is not None:
            lines.append(
                f"Strongest cohort: `{strongest.scenario_name}` / `{strongest.archetype_label}` with utility `{strongest.mean_session_utility:.3f}`."
            )
        if weakest is not None:
            lines.append(
                f"Main concern: `{weakest.scenario_name}` / `{weakest.archetype_label}` with failure mode `{weakest.dominant_failure_mode}` and utility `{weakest.mean_session_utility:.3f}`."
            )
        if high_risk:
            inspect = ", ".join(
                f"{cohort.scenario_name} / {cohort.archetype_label}" for cohort in high_risk[:2]
            )
            lines.append(f"Inspect next: representative failure traces for {inspect}.")
        elif strongest is not None:
            lines.append(
                f"Inspect next: compare the strongest trace from `{strongest.archetype_label}` against lower-utility cohorts for hidden failure patterns."
            )
        return lines[:4]

    def _select_representative_cohorts(self, run_result: RunResult):
        """Choose the small set of cohorts worth showing in the report body."""
        failure_cohorts = [
            cohort
            for cohort in run_result.cohort_summaries
            if cohort.representative_failure_trace_id is not None
        ]
        failure_cohorts.sort(
            key=lambda cohort: (
                -_RISK_ORDER.get(cohort.risk_level, -1),
                cohort.mean_session_utility,
            )
        )
        success_cohorts = [
            cohort
            for cohort in run_result.cohort_summaries
            if cohort.representative_success_trace_id is not None
        ]
        success_cohorts.sort(
            key=lambda cohort: (
                _RISK_ORDER.get(cohort.risk_level, -1),
                -cohort.mean_session_utility,
            )
        )
        return failure_cohorts[:2], success_cohorts[:2]

    def _render_trace_steps(self, trace) -> list[str]:
        """Render only the first few trace steps so the report stays skimmable."""
        if not trace.steps:
            return ["- No steps recorded."]
        lines: list[str] = []
        for step in trace.steps[:3]:
            selected = step.action.selected_item_id or "none"
            top_titles = ", ".join(item.title for item in step.slate.items[:3])
            explanation = step.decision_explanation
            reason = explanation.reason if explanation is not None else step.action.reason
            dominant = (
                explanation.dominant_component
                if explanation is not None
                else "unknown_component"
            )
            lines.append(
                f"- Step {step.step_index + 1}: action `{step.action.name}` "
                f"(`{selected}`), top slate: {top_titles}"
            )
            lines.append(
                f"  reason: `{reason}` via `{dominant}`; {step.state_delta_summary}"
            )
        if len(trace.steps) > 3:
            lines.append(f"- ... {len(trace.steps) - 3} additional step(s) omitted for brevity")
        return lines
