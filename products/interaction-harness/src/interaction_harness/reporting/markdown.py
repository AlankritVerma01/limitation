"""Markdown artifact writer for the polished recommender audit."""

from __future__ import annotations

from pathlib import Path

from ..schema import RunResult

_RISK_ORDER = {"low": 0, "medium": 1, "high": 2}


class MarkdownReportWriter:
    """Writes a clearer behavioral audit report from precomputed results."""

    def write(self, run_result: RunResult, output_dir: Path) -> dict[str, str]:
        output_dir.mkdir(parents=True, exist_ok=True)
        report_path = output_dir / "report.md"
        trace_lookup = {trace.trace_id: trace for trace in run_result.traces}
        scenario_names = ", ".join(
            scenario.name for scenario in run_result.run_config.scenarios
        )
        summary_lines = self._executive_summary(run_result)
        failure_cohorts, success_cohorts = self._select_representative_cohorts(run_result)
        service_kind = str(run_result.metadata.get("service_kind", "unknown"))
        lines = [
            "# Interaction Harness Recommender Audit",
            "",
            "## Run Summary",
            "",
            f"- Run: `{run_result.run_config.run_name}`",
            f"- Run ID: `{run_result.metadata.get('run_id', 'unknown')}`",
            f"- Generated: `{run_result.metadata.get('generated_at_utc', 'unknown')}`",
            f"- Seed: `{run_result.run_config.rollout.seed}`",
            f"- Scenarios: `{scenario_names}`",
            f"- Traces: `{len(run_result.traces)}`",
            f"- Service kind: `{service_kind}`",
            "",
            "## Executive Summary",
            "",
        ]
        lines.extend(f"- {line}" for line in summary_lines)

        lines.extend(["", "## Launch Risks", ""])
        if not run_result.risk_flags:
            lines.append("- No medium or high risk cohorts were detected in this run.")
        else:
            for flag in run_result.risk_flags:
                lines.append(
                    f"- `{flag.severity}` {flag.scenario_name} / {flag.archetype_label}: "
                    f"{flag.message} Evidence: {flag.evidence_summary}"
                )

        lines.extend(["", "## Scenario Coverage", ""])
        for scenario in run_result.run_config.scenarios:
            lines.append(
                f"- `{scenario.name}`: {scenario.description} "
                f"(history depth `{scenario.history_depth}`, max steps `{scenario.max_steps}`)"
            )

        lines.extend(
            [
                "",
                "## Cohort Summary",
                "",
                "| Scenario | Archetype | Risk | Failure Mode | Utility | Trust Δ | Skip Rate |",
                "| --- | --- | --- | --- | --- | --- | --- |",
            ]
        )
        for cohort in run_result.cohort_summaries:
            lines.append(
                f"| {cohort.scenario_name} | {cohort.archetype_label} | "
                f"{cohort.risk_level} | {cohort.dominant_failure_mode} | "
                f"{cohort.mean_session_utility:.3f} | {cohort.mean_trust_delta:.3f} | "
                f"{cohort.mean_skip_rate:.3f} |"
            )

        lines.extend(["", "## Representative Traces To Inspect", ""])
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

        lines.extend(
            [
                "## Reproducibility And Metadata",
                "",
                "- Runs are deterministic for a fixed seed and scenario selection.",
                "- The judge consumes completed traces only and does not call the system under test.",
                f"- Service artifact dir: `{run_result.metadata.get('service_artifact_dir', '') or 'n/a'}`",
                f"- Artifact ID: `{run_result.metadata.get('artifact_id', 'unknown')}`",
                "",
                "## Trace Scores",
                "",
                "| Trace | Scenario | Archetype | Utility | Failure Mode | Trust Δ | Skip Rate | Abandoned |",
                "| --- | --- | --- | --- | --- | --- | --- | --- |",
            ]
        )
        for score in run_result.trace_scores:
            lines.append(
                f"| {score.trace_id} | {score.scenario_name} | {score.archetype_label} | "
                f"{score.session_utility:.3f} | {score.dominant_failure_mode} | "
                f"{score.trust_delta:.3f} | {score.skip_rate:.3f} | "
                f"{score.abandoned} |"
            )

        report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return {"report_path": str(report_path)}

    def _executive_summary(self, run_result: RunResult) -> list[str]:
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
