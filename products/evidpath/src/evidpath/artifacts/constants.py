"""Stable constants for durable artifact contracts."""

RUN_PLAN_CONTRACT_VERSION = "v1"

ALLOWED_WORKFLOW_TYPES = frozenset({"run-swarm", "compare", "audit"})
ALLOWED_AI_PROFILES = frozenset({"fast", "balanced", "deep"})
ALLOWED_GENERATION_MODES = frozenset({"fixture", "provider"})
ALLOWED_SEMANTIC_MODES = frozenset({"off", "fixture", "provider"})
ALLOWED_SCENARIO_ACTIONS = frozenset(
    {
        "generate_new",
        "planner_reuse_existing",
        "explicit_reuse",
        "use_built_in_scenarios",
    }
)
ALLOWED_SWARM_ACTIONS = frozenset(
    {
        "generate_new",
        "planner_reuse_existing",
        "explicit_reuse",
        "use_built_in_population",
    }
)
