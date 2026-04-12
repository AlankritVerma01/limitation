"""Small shared helpers for planner payload and display state."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def coverage_display_mode(
    *,
    explicit_path: str | None,
    planner_action: str,
    generation_mode: str,
) -> str:
    if explicit_path is not None:
        return "reused"
    if planner_action == "planner_reuse_existing":
        return "planner-reused"
    if planner_action.startswith("use_built_in"):
        return "built_in"
    return generation_mode


def coverage_source(*, scenario_mode: str, swarm_mode: str) -> str:
    modes = {scenario_mode, swarm_mode}
    if modes == {"reused"}:
        return "reused"
    if modes == {"built_in"}:
        return "built_in"
    if "planner-reused" in modes and len(modes) == 1:
        return "planner_reused"
    if modes <= {"fixture", "provider"} and len(modes) == 1:
        return "generated"
    if "planner-reused" in modes and modes <= {"planner-reused", "fixture", "provider"}:
        return "mixed"
    if "reused" in modes or "built_in" in modes:
        return "mixed"
    return "generated"


def now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def optional_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    return int(value)


def optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
