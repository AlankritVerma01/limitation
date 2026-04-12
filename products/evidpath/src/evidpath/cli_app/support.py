"""Shared CLI-only helpers."""

from __future__ import annotations

import json
import time
from pathlib import Path

from ..schema import RegressionTarget


def planner_model_summary(
    provider_name: str,
    model_name: str,
    model_profile: str,
) -> str:
    if not model_name:
        return "n/a"
    profile = model_profile or "custom"
    if provider_name:
        return f"{provider_name}/{model_name} ({profile})"
    return f"{model_name} ({profile})"


def ensure_reused_artifact(path: str | None, *, label: str) -> None:
    resolved = optional_text(path)
    if not resolved:
        raise SystemExit(f"Saved plan requires a {label}, but no path was provided.")
    if not Path(resolved).exists():
        raise SystemExit(
            f"Saved plan requires {label} at `{resolved}`, but that path does not exist."
        )


def regression_target_from_plan(payload: dict[str, object]) -> RegressionTarget:
    mode = str(payload.get("mode", ""))
    if mode not in {"reference_artifact", "external_url"}:
        raise SystemExit(f"Saved plan has unsupported compare target mode `{mode}`.")
    return RegressionTarget(
        label=str(payload.get("label", "")),
        mode=mode,
        service_artifact_dir=optional_text(payload.get("service_artifact_dir")),
        adapter_base_url=optional_text(payload.get("adapter_base_url")),
    )


def optional_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def wait_for_interrupt() -> None:
    """Keep a foreground service command alive until interrupted."""
    while True:
        time.sleep(1.0)


def count_high_risk_cohorts(run_result) -> int:
    return sum(1 for cohort in run_result.cohort_summaries if cohort.risk_level == "high")


def audit_launch_status(run_result) -> str:
    high_risk_count = count_high_risk_cohorts(run_result)
    medium_risk_count = sum(
        1 for cohort in run_result.cohort_summaries if cohort.risk_level == "medium"
    )
    if high_risk_count > 0:
        return "needs review"
    if medium_risk_count > 0 or run_result.risk_flags:
        return "watch"
    return "clear"


def load_json_summary(path: str) -> dict[str, object]:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def print_summary(title: str, rows: tuple[tuple[str, str], ...]) -> None:
    print(f"{title}:")
    for label, value in rows:
        if value:
            print(f"  {label}: {value}")
