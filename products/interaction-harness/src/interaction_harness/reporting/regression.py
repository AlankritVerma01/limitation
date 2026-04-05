"""Regression artifact writers for rerun and comparison outputs."""

from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any

from ..schema import RegressionDiff

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
        lines = ["# Interaction Harness Regression Audit"]
        lines.extend(self._executive_summary_lines(regression_diff))
        lines.extend(self._metric_delta_lines(regression_diff))
        lines.extend(self._variance_lines(regression_diff))
        lines.extend(self._cohort_change_lines(regression_diff))
        lines.extend(self._risk_change_lines(regression_diff))
        lines.extend(self._trace_change_lines(regression_diff))

        report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return {"regression_report_path": str(report_path)}

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
            f"- Variance confidence: {summary['variance_note']}",
            f"- Regression mode: `{regression_diff.gating_mode}`; severity is informational in this version and no hard failure thresholds are enforced.",
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

    def _trace_change_lines(self, regression_diff: RegressionDiff) -> list[str]:
        """Render the trace-level diff table."""
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

    def build_summary(self, regression_diff: RegressionDiff) -> dict[str, object]:
        """Build the compact regression status summary used by reports and JSON."""
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
            "variance_note": (
                "low observed variance across reruns"
                if max_spread <= 0.01
                else "visible rerun variance; interpret small deltas carefully"
            ),
        }

    def build_important_changes(self, regression_diff: RegressionDiff) -> list[str]:
        """Select the small set of deltas worth highlighting first."""
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
        return _normalize_regression_payload(payload)

    def _build_summary(self, regression_diff: RegressionDiff) -> dict[str, object]:
        """Build the top-level summary block stored in regression_summary.json."""
        markdown_summary = RegressionMarkdownWriter().build_summary(regression_diff)
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
            "overall_direction": markdown_summary["overall_direction"],
            "improved_cohort_count": markdown_summary["improved_cohort_count"],
            "regressed_cohort_count": markdown_summary["regressed_cohort_count"],
            "added_risk_flag_count": markdown_summary["added_risk_flag_count"],
            "removed_risk_flag_count": markdown_summary["removed_risk_flag_count"],
            "variance_note": markdown_summary["variance_note"],
        }
