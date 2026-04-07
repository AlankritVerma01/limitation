"""Regression artifact writers for rerun and comparison outputs."""

from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any

from ..contracts.core import RegressionDiff
from .base import ReportBulletSection, ReportTableSection

_RISK_ORDER = {"low": 0, "medium": 1, "high": 2}


def _serialize(value: Any) -> Any:
    """Convert nested dataclasses into plain JSON-friendly Python objects."""
    if is_dataclass(value):
        return _serialize(asdict(value))
    if isinstance(value, dict):
        return {key: _serialize(inner) for key, inner in value.items()}
    if isinstance(value, tuple | list):
        return [_serialize(inner) for inner in value]
    return value


def _normalize_regression_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Normalize volatile paths and timestamps inside regression payloads."""
    for summary_key in ("baseline_summary", "candidate_summary"):
        summary = payload[summary_key]
        target = summary["target"]
        if "service_artifact_dir" in target:
            target["service_artifact_dir"] = "<normalized>"
        if "adapter_base_url" in target:
            target["adapter_base_url"] = "<normalized>"
        for run_artifact in summary["run_artifacts"]:
            run_artifact["output_dir"] = "<normalized>"
            run_artifact["report_path"] = "<normalized>"
            run_artifact["results_path"] = "<normalized>"
            run_artifact["traces_path"] = "<normalized>"
            run_artifact["chart_path"] = "<normalized>"
        if "service_artifact_dir" in summary["metadata"]:
            summary["metadata"]["service_artifact_dir"] = "<normalized>"
        if "adapter_base_url" in summary["metadata"]:
            summary["metadata"]["adapter_base_url"] = "<normalized>"
    if "generated_at_utc" in payload.get("metadata", {}):
        payload["metadata"]["generated_at_utc"] = "<normalized>"
    if "population_pack_path" in payload.get("metadata", {}):
        payload["metadata"]["population_pack_path"] = "<normalized>"
    if "semantic_interpretation" in payload and payload["semantic_interpretation"] is None:
        payload.pop("semantic_interpretation", None)
    semantic = payload.get("semantic_interpretation")
    if isinstance(semantic, dict) and "generated_at_utc" in semantic:
        semantic["generated_at_utc"] = "<normalized>"
    if "generated_at_utc" in payload.get("summary", {}):
        payload["summary"]["generated_at_utc"] = "<normalized>"
    return payload


def _risk_rank(severity: str | None) -> int:
    if severity is None:
        return -1
    return _RISK_ORDER.get(severity, -1)


class RegressionMarkdownWriter:
    """Writes a clearer baseline-vs-candidate regression report."""

    def write(self, regression_diff: RegressionDiff, output_dir: Path) -> dict[str, str]:
        """Write the human-facing regression report."""
        output_dir.mkdir(parents=True, exist_ok=True)
        report_path = output_dir / "regression_report.md"
        report_title = str(
            regression_diff.metadata.get(
                "regression_report_title", "Interaction Harness Regression Audit"
            )
        )
        lines = [f"# {report_title}"]
        lines.extend(self._decision_lines(regression_diff))
        lines.extend(self._executive_summary_lines(regression_diff))
        lines.extend(self._metric_delta_lines(regression_diff))
        lines.extend(self._variance_lines(regression_diff))
        lines.extend(self._cohort_change_lines(regression_diff))
        lines.extend(self._slice_change_lines(regression_diff))
        lines.extend(self._risk_change_lines(regression_diff))
        lines.extend(self._trace_change_lines(regression_diff))
        lines.extend(self._semantic_advisory_lines(regression_diff))

        report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return {"regression_report_path": str(report_path)}

    def _decision_lines(self, regression_diff: RegressionDiff) -> list[str]:
        """Render the policy decision and the top triggered checks first."""
        decision = regression_diff.decision
        if decision is None:
            return []
        lines = [
            "",
            "## Decision",
            "",
            f"- Result: `{decision.status}`",
            f"- Exit code: `{decision.exit_code}`",
            f"- Policy mode: `{regression_diff.gating_mode}`",
        ]
        if not decision.reasons:
            lines.append("- No warn or fail checks were triggered.")
            return lines
        lines.append("- Triggered checks:")
        lines.extend(f"  - {reason}" for reason in decision.reasons[:5])
        return lines

    def _executive_summary_lines(self, regression_diff: RegressionDiff) -> list[str]:
        """Render the opening regression summary and high-signal changes."""
        summary = self.build_summary(regression_diff)
        important_changes = self.build_important_changes(regression_diff)
        lines = [
            "",
            "## Executive Summary",
            "",
            f"- Comparison: `{regression_diff.baseline_summary.target.label}` -> `{regression_diff.candidate_summary.target.label}`",
            f"- Reruns per target: `{regression_diff.baseline_summary.run_count}`",
            f"- Overall direction: `{summary['overall_direction']}`",
            f"- Cohorts improved: `{summary['improved_cohort_count']}`; regressed: `{summary['regressed_cohort_count']}`",
            f"- Risk flags added: `{summary['added_risk_flag_count']}`; removed: `{summary['removed_risk_flag_count']}`",
            f"- Slice changes: `{summary['changed_slice_count']}` changed, `{summary['appeared_slice_count']}` appeared, `{summary['disappeared_slice_count']}` disappeared",
            f"- Variance confidence: {summary['variance_note']}",
            f"- Regression mode: `{regression_diff.gating_mode}`.",
            "",
            "## Most Important Changes",
            "",
        ]
        if not important_changes:
            lines.append("- No material changes were detected across the current rerun summaries.")
            return lines
        lines.extend(f"- {change}" for change in important_changes)
        return lines

    def _metric_delta_lines(self, regression_diff: RegressionDiff) -> list[str]:
        """Render the overall metric delta table."""
        lines = [
            "",
            "## Overall Metric Deltas",
            "",
            "| Metric | Baseline Mean | Candidate Mean | Delta |",
            "| --- | --- | --- | --- |",
        ]
        for metric in regression_diff.metric_deltas:
            lines.append(
                f"| {metric.metric_name} | {metric.baseline_mean:.3f} | {metric.candidate_mean:.3f} | {metric.delta:+.3f} |"
            )
        return lines

    def _variance_lines(self, regression_diff: RegressionDiff) -> list[str]:
        """Render the baseline and candidate rerun spread tables."""
        lines = [
            "",
            "## Variance Summary",
            "",
            "### Baseline",
            "",
        ]
        lines.extend(self._metric_summary_table(regression_diff.baseline_summary.metric_summaries))
        lines.extend(["", "### Candidate", ""])
        lines.extend(self._metric_summary_table(regression_diff.candidate_summary.metric_summaries))
        return lines

    def _metric_summary_table(self, metric_summaries) -> list[str]:
        """Render one min/mean/max table for rerun summaries."""
        lines = [
            "| Metric | Mean | Min | Max | Range |",
            "| --- | --- | --- | --- | --- |",
        ]
        for metric in metric_summaries:
            lines.append(
                f"| {metric.metric_name} | {metric.mean:.3f} | {metric.minimum:.3f} | {metric.maximum:.3f} | {metric.spread:.3f} |"
            )
        return lines

    def _cohort_change_lines(self, regression_diff: RegressionDiff) -> list[str]:
        """Render the cohort-level diff table."""
        hook = self._reporting_hook(regression_diff, "build_regression_cohort_change_section")
        if hook is not None:
            return self._render_section(hook(regression_diff))
        lines = [
            "",
            "## Cohort Changes",
            "",
            "| Scenario | Archetype | Baseline Risk | Candidate Risk | Failure Mode | Utility Δ | Abandon Δ | Trust Δ | Skip Δ |",
            "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
        ]
        for cohort in regression_diff.cohort_deltas:
            failure_mode = (
                cohort.candidate_failure_mode
                if cohort.candidate_failure_mode != "no_major_failure"
                else cohort.baseline_failure_mode
            )
            lines.append(
                f"| {cohort.scenario_name} | {cohort.archetype_label} | {cohort.baseline_risk_level} | "
                f"{cohort.candidate_risk_level} | {failure_mode} | {cohort.session_utility_delta:+.3f} | "
                f"{cohort.abandonment_rate_delta:+.3f} | {cohort.trust_delta_delta:+.3f} | {cohort.skip_rate_delta:+.3f} |"
            )
        return lines

    def _risk_change_lines(self, regression_diff: RegressionDiff) -> list[str]:
        """Render human-readable risk flag changes."""
        hook = self._reporting_hook(regression_diff, "build_regression_risk_change_section")
        if hook is not None:
            return self._render_section(hook(regression_diff))
        lines = ["", "## Risk Changes", ""]
        visible_risks = [
            risk
            for risk in regression_diff.risk_flag_deltas
            if risk.baseline_count != 0 or risk.candidate_count != 0
        ]
        if not visible_risks:
            lines.append("- No risk flag changes were detected.")
            return lines
        for risk in visible_risks:
            lines.append(
                f"- {risk.scenario_name} / {risk.archetype_label}: "
                f"baseline `{risk.baseline_count}` ({risk.baseline_top_severity or 'none'}) -> "
                f"candidate `{risk.candidate_count}` ({risk.candidate_top_severity or 'none'})"
            )
        return lines

    def _slice_change_lines(self, regression_diff: RegressionDiff) -> list[str]:
        """Render the deterministic discovered-slice diff table."""
        hook = self._reporting_hook(regression_diff, "build_regression_slice_change_section")
        if hook is not None:
            return self._render_section(hook(regression_diff))
        lines = [
            "",
            "## Discovered Slice Changes",
            "",
        ]
        visible_slices = [
            slice_delta
            for slice_delta in regression_diff.slice_deltas
            if slice_delta.change_type != "stable"
            or abs(slice_delta.session_utility_delta) >= 0.01
            or abs(slice_delta.trust_delta_delta) >= 0.01
            or abs(slice_delta.skip_rate_delta) >= 0.01
        ]
        if not visible_slices:
            lines.append("- No material discovered-slice changes were detected.")
            return lines
        lines.extend(
            [
                "| Signature | Change | Baseline Count | Candidate Count | Risk | Failure Mode | Utility Δ | Trust Δ | Skip Δ |",
                "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
            ]
        )
        for slice_delta in visible_slices:
            signature = ", ".join(slice_delta.feature_signature)
            risk = (
                f"{slice_delta.baseline_risk_level or 'none'} -> "
                f"{slice_delta.candidate_risk_level or 'none'}"
            )
            failure_mode = (
                slice_delta.candidate_failure_mode
                if slice_delta.candidate_failure_mode != "no_major_failure"
                else slice_delta.baseline_failure_mode
            )
            lines.append(
                f"| {signature} | {slice_delta.change_type} | {slice_delta.baseline_trace_count} | "
                f"{slice_delta.candidate_trace_count} | {risk} | {failure_mode} | "
                f"{slice_delta.session_utility_delta:+.3f} | {slice_delta.trust_delta_delta:+.3f} | "
                f"{slice_delta.skip_rate_delta:+.3f} |"
            )
        return lines

    def _trace_change_lines(self, regression_diff: RegressionDiff) -> list[str]:
        """Render the trace-level diff table."""
        hook = self._reporting_hook(regression_diff, "build_regression_trace_change_section")
        if hook is not None:
            return self._render_section(hook(regression_diff))
        lines = [
            "",
            "## Notable Trace Changes",
            "",
            "| Trace | Scenario | Archetype | Utility Δ | Risk Δ | Baseline Failure | Candidate Failure |",
            "| --- | --- | --- | --- | --- | --- | --- |",
        ]
        for trace in regression_diff.notable_trace_deltas:
            lines.append(
                f"| {trace.trace_id} | {trace.scenario_name} | {trace.archetype_label} | "
                f"{trace.session_utility_delta:+.3f} | {trace.trace_risk_score_delta:+.3f} | "
                f"{trace.baseline_failure_mode} | {trace.candidate_failure_mode} |"
            )
        return lines

    def _reporting_hook(self, regression_diff: RegressionDiff, hook_name: str):
        domain_name = str(regression_diff.metadata.get("domain_name", ""))
        if not domain_name:
            return None
        from ..domain_registry import get_domain_definition

        definition = get_domain_definition(domain_name)
        hooks = definition.reporting_hooks
        if hooks is None:
            return None
        return getattr(hooks, hook_name, None)

    def _render_section(
        self,
        section: ReportBulletSection | ReportTableSection,
    ) -> list[str]:
        if isinstance(section, ReportBulletSection):
            return ["", f"## {section.title}", "", *(f"- {bullet}" for bullet in section.bullets)]
        lines = ["", f"## {section.title}", ""]
        header = "| " + " | ".join(section.columns) + " |"
        divider = "| " + " | ".join("---" for _ in section.columns) + " |"
        lines.extend([header, divider])
        for row in section.rows:
            lines.append("| " + " | ".join(row) + " |")
        return lines

    def _semantic_advisory_lines(self, regression_diff: RegressionDiff) -> list[str]:
        """Render optional advisory semantic interpretation for compare mode."""
        interpretation = regression_diff.semantic_interpretation
        lines = ["", "## Semantic Advisory", ""]
        if interpretation is None:
            lines.append("- Semantic interpretation was not enabled for this comparison.")
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

    def build_summary(self, regression_diff: RegressionDiff) -> dict[str, object]:
        """Build the compact regression status summary used by reports and JSON."""
        domain_name = str(regression_diff.metadata.get("domain_name", ""))
        if domain_name:
            from ..domain_registry import get_domain_definition

            definition = get_domain_definition(domain_name)
            if definition.build_regression_summary is not None:
                return definition.build_regression_summary(regression_diff)
        improved = 0
        regressed = 0
        for cohort in regression_diff.cohort_deltas:
            score = (
                cohort.session_utility_delta
                - (0.6 * cohort.abandonment_rate_delta)
                + (0.4 * cohort.trust_delta_delta)
                - (0.3 * cohort.skip_rate_delta)
                + (0.08 * (_risk_rank(cohort.baseline_risk_level) - _risk_rank(cohort.candidate_risk_level)))
            )
            if score > 0.05:
                improved += 1
            elif score < -0.05:
                regressed += 1
        added_risks = sum(
            1
            for risk in regression_diff.risk_flag_deltas
            if risk.baseline_count == 0 and risk.candidate_count > 0
        )
        removed_risks = sum(
            1
            for risk in regression_diff.risk_flag_deltas
            if risk.baseline_count > 0 and risk.candidate_count == 0
        )
        changed_slices = sum(
            1 for slice_delta in regression_diff.slice_deltas if slice_delta.change_type == "changed"
        )
        appeared_slices = sum(
            1 for slice_delta in regression_diff.slice_deltas if slice_delta.change_type == "appeared"
        )
        disappeared_slices = sum(
            1 for slice_delta in regression_diff.slice_deltas if slice_delta.change_type == "disappeared"
        )
        spreads = [
            metric.spread for metric in regression_diff.baseline_summary.metric_summaries
        ] + [
            metric.spread for metric in regression_diff.candidate_summary.metric_summaries
        ]
        max_spread = max(spreads, default=0.0)
        if regressed == 0 and improved > 0 and added_risks == 0:
            overall_direction = "candidate improved"
        elif improved == 0 and (regressed > 0 or added_risks > removed_risks):
            overall_direction = "candidate regressed"
        elif improved == 0 and regressed == 0 and added_risks == 0 and removed_risks == 0:
            overall_direction = "no material change"
        else:
            overall_direction = "mixed"
        return {
            "overall_direction": overall_direction,
            "improved_cohort_count": improved,
            "regressed_cohort_count": regressed,
            "added_risk_flag_count": added_risks,
            "removed_risk_flag_count": removed_risks,
            "changed_slice_count": changed_slices,
            "appeared_slice_count": appeared_slices,
            "disappeared_slice_count": disappeared_slices,
            "variance_note": (
                "low observed variance across reruns"
                if max_spread <= 0.01
                else "visible rerun variance; interpret small deltas carefully"
            ),
        }

    def build_important_changes(self, regression_diff: RegressionDiff) -> list[str]:
        """Select the small set of deltas worth highlighting first."""
        domain_name = str(regression_diff.metadata.get("domain_name", ""))
        if domain_name:
            from ..domain_registry import get_domain_definition

            definition = get_domain_definition(domain_name)
            if definition.build_regression_important_changes is not None:
                return definition.build_regression_important_changes(regression_diff)
        changes: list[str] = []
        for cohort in regression_diff.cohort_deltas[:3]:
            magnitude = (
                abs(cohort.session_utility_delta)
                + abs(cohort.abandonment_rate_delta)
                + abs(cohort.trust_delta_delta)
                + abs(cohort.skip_rate_delta)
            )
            if magnitude < 0.01:
                continue
            changes.append(
                f"{cohort.scenario_name} / {cohort.archetype_label}: utility {cohort.session_utility_delta:+.3f}, "
                f"abandonment {cohort.abandonment_rate_delta:+.3f}, trust {cohort.trust_delta_delta:+.3f}"
            )
        for risk in regression_diff.risk_flag_deltas:
            if risk.delta != 0:
                direction = "added" if risk.delta > 0 else "removed"
                changes.append(
                    f"{risk.scenario_name} / {risk.archetype_label}: {direction} {abs(risk.delta)} risk flag(s)"
                )
            if len(changes) >= 3:
                break
        for slice_delta in regression_diff.slice_deltas:
            if slice_delta.change_type != "stable":
                signature = ", ".join(slice_delta.feature_signature)
                changes.append(
                    f"{signature}: {slice_delta.change_type}, utility {slice_delta.session_utility_delta:+.3f}, trust {slice_delta.trust_delta_delta:+.3f}"
                )
            if len(changes) >= 3:
                break
        for trace in regression_diff.notable_trace_deltas:
            if abs(trace.session_utility_delta) >= 0.02 or abs(trace.trace_risk_score_delta) >= 0.02:
                changes.append(
                    f"{trace.trace_id}: utility {trace.session_utility_delta:+.3f}, risk {trace.trace_risk_score_delta:+.3f}"
                )
            if len(changes) >= 3:
                break
        return changes[:3]


class RegressionJsonWriter:
    """Writes machine-readable regression summaries and notable trace deltas."""

    def write(self, regression_diff: RegressionDiff, output_dir: Path) -> dict[str, str]:
        """Write machine-readable regression summaries and trace deltas."""
        output_dir.mkdir(parents=True, exist_ok=True)
        summary_path = output_dir / "regression_summary.json"
        traces_path = output_dir / "regression_traces.json"
        payload = self._normalized_payload(regression_diff)
        summary_path.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        traces_path.write_text(
            json.dumps(payload["notable_trace_deltas"], indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return {
            "regression_summary_path": str(summary_path),
            "regression_traces_path": str(traces_path),
        }

    def _normalized_payload(self, regression_diff: RegressionDiff) -> dict[str, Any]:
        """Build one normalized payload shared by both regression JSON artifacts."""
        payload = _normalize_regression_payload(_serialize(regression_diff))
        payload["summary"] = self._build_summary(regression_diff)
        decision = payload.get("decision") or {}
        payload["decision_status"] = decision.get("status", "pass")
        payload["decision_reasons"] = decision.get("reasons", [])
        payload["checks"] = decision.get("checks", [])
        if "generated_at_utc" in payload.get("summary", {}):
            payload["summary"]["generated_at_utc"] = "<normalized>"
        return payload

    def _build_summary(self, regression_diff: RegressionDiff) -> dict[str, object]:
        """Build the top-level summary block stored in regression_summary.json."""
        markdown_summary = RegressionMarkdownWriter().build_summary(regression_diff)
        decision = regression_diff.decision
        return {
            "display_name": str(
                regression_diff.metadata.get(
                    "display_name",
                    f"{regression_diff.baseline_summary.target.label} vs {regression_diff.candidate_summary.target.label}",
                )
            ),
            "regression_id": str(regression_diff.metadata.get("regression_id", "")),
            "generated_at_utc": str(regression_diff.metadata.get("generated_at_utc", "")),
            "baseline_label": regression_diff.baseline_summary.target.label,
            "candidate_label": regression_diff.candidate_summary.target.label,
            "decision": decision.status if decision is not None else "pass",
            "exit_code": decision.exit_code if decision is not None else 0,
            "decision_reasons": list(decision.reasons) if decision is not None else [],
            "semantic_mode": str(regression_diff.metadata.get("semantic_mode", "off")),
            "overall_direction": markdown_summary["overall_direction"],
            "improved_cohort_count": markdown_summary["improved_cohort_count"],
            "regressed_cohort_count": markdown_summary["regressed_cohort_count"],
            "added_risk_flag_count": markdown_summary["added_risk_flag_count"],
            "removed_risk_flag_count": markdown_summary["removed_risk_flag_count"],
            "changed_slice_count": markdown_summary["changed_slice_count"],
            "appeared_slice_count": markdown_summary["appeared_slice_count"],
            "disappeared_slice_count": markdown_summary["disappeared_slice_count"],
            "variance_note": markdown_summary["variance_note"],
        }
