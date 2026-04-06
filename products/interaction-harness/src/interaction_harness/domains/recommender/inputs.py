"""Runtime input resolution and generated-pack projection for the recommender domain."""

from __future__ import annotations

from ...domains.base import ResolvedRuntimeInputs
from ...schema import (
    AgentSeed,
    GeneratedPersona,
    PopulationPack,
    ScenarioConfig,
    ScenarioPack,
)
from .policy import build_seeded_archetypes
from .scenarios import (
    BUILT_IN_RECOMMENDER_SCENARIO_NAMES,
    resolve_built_in_recommender_scenarios,
)

_SUPPORTED_RUNTIME_PROFILES = set(BUILT_IN_RECOMMENDER_SCENARIO_NAMES)


def resolve_recommender_inputs(
    *,
    scenario_names: tuple[str, ...] | None = None,
    scenario_pack_path: str | None = None,
    population_pack_path: str | None = None,
) -> ResolvedRuntimeInputs:
    """Resolve recommender runtime inputs from built-ins and saved packs."""
    scenarios, scenario_metadata = _resolve_scenarios(
        scenario_names=scenario_names,
        scenario_pack_path=scenario_pack_path,
    )
    agent_seeds, population_metadata = _resolve_population(
        population_pack_path=population_pack_path,
    )
    return ResolvedRuntimeInputs(
        scenarios=scenarios,
        agent_seeds=agent_seeds,
        metadata={**scenario_metadata, **population_metadata},
    )


def project_recommender_scenarios(pack: ScenarioPack) -> tuple[ScenarioConfig, ...]:
    """Project a portable scenario pack into recommender runtime configs."""
    scenario_configs: list[ScenarioConfig] = []
    for scenario in pack.scenarios:
        hints = scenario.adapter_hints.get("recommender")
        if hints is None:
            raise ValueError(
                f"Scenario `{scenario.scenario_id}` is missing recommender adapter hints."
            )
        runtime_profile = hints.get("runtime_profile")
        history_depth = hints.get("history_depth")
        if not isinstance(runtime_profile, str) or runtime_profile not in _SUPPORTED_RUNTIME_PROFILES:
            raise ValueError(
                f"Scenario `{scenario.scenario_id}` has unsupported recommender runtime profile."
            )
        if not isinstance(history_depth, int) or history_depth < 0:
            raise ValueError(
                f"Scenario `{scenario.scenario_id}` has invalid recommender history depth."
            )
        allowed_actions = tuple(str(action) for action in scenario.allowed_actions)
        unsupported_actions = sorted(
            set(allowed_actions).difference({"click", "skip", "abandon"})
        )
        if unsupported_actions:
            raise ValueError(
                f"Scenario `{scenario.scenario_id}` uses unsupported recommender actions: "
                f"{', '.join(unsupported_actions)}."
            )
        scenario_configs.append(
            ScenarioConfig(
                name=scenario.name,
                max_steps=scenario.max_steps,
                allowed_actions=allowed_actions,  # type: ignore[arg-type]
                history_depth=history_depth,
                description=scenario.description,
                scenario_id=scenario.scenario_id,
                test_goal=scenario.test_goal,
                risk_focus_tags=scenario.risk_focus_tags,
                runtime_profile=runtime_profile,
                context_hint=str(hints.get("context_hint", "")),
            )
        )
    return tuple(scenario_configs)


def project_recommender_population(pack: PopulationPack) -> tuple[AgentSeed, ...]:
    """Project a saved recommender population pack into deterministic agent seeds."""
    return tuple(_project_persona_to_agent_seed(persona) for persona in pack.personas)


def _resolve_scenarios(
    *,
    scenario_names: tuple[str, ...] | None,
    scenario_pack_path: str | None,
) -> tuple[tuple[ScenarioConfig, ...], dict[str, str]]:
    """Resolve recommender scenarios from built-ins or a saved scenario pack."""
    if scenario_pack_path is not None:
        if scenario_names is not None:
            raise ValueError(
                "scenario_names cannot be combined with scenario_pack_path in a single recommender run."
            )
        from ...scenario_generation import load_scenario_pack

        pack = load_scenario_pack(scenario_pack_path)
        return (
            project_recommender_scenarios(pack),
            {
                "scenario_source": "generated_pack",
                "scenario_pack_id": pack.metadata.pack_id,
                "scenario_pack_mode": pack.metadata.generator_mode,
                "scenario_pack_domain": pack.metadata.domain_label,
                "scenario_count": len(pack.scenarios),
                "scenario_pack_path": scenario_pack_path,
            },
        )
    scenarios = resolve_built_in_recommender_scenarios(scenario_names)
    return scenarios, {
        "scenario_source": "built_in",
        "scenario_count": len(scenarios),
    }


def _resolve_population(
    *,
    population_pack_path: str | None,
) -> tuple[tuple[AgentSeed, ...], dict[str, str | int]]:
    """Resolve recommender runtime personas from built-ins or a saved population pack."""
    if population_pack_path is None:
        built_in = build_seeded_archetypes()
        return built_in, {
            "population_source": "built_in_seeds",
            "population_pack_size": len(built_in),
            "population_target_size": len(built_in),
            "population_size_source": "built_in",
        }
    from ...population_generation import load_population_pack

    pack = load_population_pack(population_pack_path)
    return (
        project_recommender_population(pack),
        {
            "population_source": "generated_pack",
            "population_pack_id": pack.metadata.pack_id,
            "population_pack_mode": pack.metadata.generator_mode,
            "population_pack_domain": pack.metadata.domain_label,
            "population_pack_size": pack.metadata.selected_count,
            "population_target_size": pack.metadata.target_population_size,
            "population_pack_candidate_count": pack.metadata.candidate_count,
            "population_size_source": pack.metadata.population_size_source,
            "population_pack_path": population_pack_path,
        },
    )


def _project_persona_to_agent_seed(persona: GeneratedPersona) -> AgentSeed:
    """Turn one saved generated persona into the deterministic recommender runtime seed."""
    hints = _require_recommender_hints(persona)
    preferred_genres = _require_hint_string_list(hints, persona.persona_id, "preferred_genres")
    patience = _require_hint_int(hints, persona.persona_id, "patience", minimum=1)
    skip_tolerance = _require_hint_int(hints, persona.persona_id, "skip_tolerance", minimum=0)
    return AgentSeed(
        agent_id=persona.persona_id,
        archetype_label=persona.display_label,
        preferred_genres=tuple(preferred_genres),
        popularity_preference=_require_hint_float(hints, persona.persona_id, "popularity_preference"),
        novelty_preference=_require_hint_float(hints, persona.persona_id, "novelty_preference"),
        repetition_tolerance=_require_hint_float(hints, persona.persona_id, "repetition_tolerance"),
        sparse_history_confidence=_require_hint_float(hints, persona.persona_id, "sparse_history_confidence"),
        abandonment_sensitivity=_require_hint_float(hints, persona.persona_id, "abandonment_sensitivity"),
        patience=patience,
        engagement_baseline=_require_hint_float(hints, persona.persona_id, "engagement_baseline"),
        quality_sensitivity=_require_hint_float(hints, persona.persona_id, "quality_sensitivity"),
        repeat_exposure_penalty=_require_hint_float(hints, persona.persona_id, "repeat_exposure_penalty"),
        novelty_fatigue=_require_hint_float(hints, persona.persona_id, "novelty_fatigue"),
        frustration_recovery=_require_hint_float(hints, persona.persona_id, "frustration_recovery"),
        history_reliance=_require_hint_float(hints, persona.persona_id, "history_reliance"),
        skip_tolerance=skip_tolerance,
        abandonment_threshold=_require_hint_float(hints, persona.persona_id, "abandonment_threshold"),
    )


def _require_hint_string_list(
    hints: dict[str, str | int | float | bool | list[str]],
    persona_id: str,
    key: str,
) -> list[str]:
    value = hints.get(key)
    if not isinstance(value, list) or not value or not all(isinstance(item, str) for item in value):
        raise ValueError(f"Persona `{persona_id}` has invalid recommender hint `{key}`.")
    normalized = [item.strip() for item in value if item.strip()]
    if not normalized:
        raise ValueError(f"Persona `{persona_id}` has invalid recommender hint `{key}`.")
    return normalized


def _require_recommender_hints(
    persona: GeneratedPersona,
) -> dict[str, str | int | float | bool | list[str]]:
    """Return recommender adapter hints or fail clearly before runtime."""
    hints = persona.adapter_hints.get("recommender")
    if not isinstance(hints, dict):
        raise ValueError(f"Persona `{persona.persona_id}` is missing recommender adapter hints.")
    return hints


def _require_hint_float(
    hints: dict[str, str | int | float | bool | list[str]],
    persona_id: str,
    key: str,
) -> float:
    value = hints.get(key)
    if not isinstance(value, int | float) or isinstance(value, bool):
        raise ValueError(f"Persona `{persona_id}` has invalid recommender hint `{key}`.")
    value = float(value)
    if not 0.0 <= value <= 1.0:
        raise ValueError(f"Persona `{persona_id}` has out-of-range recommender hint `{key}`.")
    return value


def _require_hint_int(
    hints: dict[str, str | int | float | bool | list[str]],
    persona_id: str,
    key: str,
    *,
    minimum: int = 0,
) -> int:
    value = hints.get(key)
    if not isinstance(value, int) or isinstance(value, bool) or value < minimum:
        raise ValueError(f"Persona `{persona_id}` has invalid recommender hint `{key}`.")
    return value
