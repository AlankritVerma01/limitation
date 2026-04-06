"""Population-pack generation, validation, selection, storage, and projection."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from hashlib import sha1
from pathlib import Path
from typing import Protocol

from .generation_support import (
    DEFAULT_PROVIDER_MODEL,
    DEFAULT_PROVIDER_NAME,
    build_responses_endpoint,
    extract_focus_tokens,
    extract_response_text,
    load_dotenv_if_present,
    read_retry_count,
    read_timeout_seconds,
    request_provider_payload,
)
from .schema import (
    AgentSeed,
    GeneratedPersona,
    PopulationGeneratorMode,
    PopulationPack,
    PopulationPackMetadata,
)

DEFAULT_POPULATION_SIZE = 12
DEFAULT_CANDIDATE_COUNT = 24


@dataclass(frozen=True)
class GeneratedPopulationCandidates:
    """Normalized generator output before validation and diversity filtering."""

    personas: tuple[dict[str, object], ...]
    suggested_population_size: int | None = None


class PopulationGenerator(Protocol):
    """Returns generated persona candidates for a population brief."""

    def generate(
        self,
        brief: str,
        *,
        candidate_count: int,
        domain_label: str,
    ) -> GeneratedPopulationCandidates: ...


class FixturePopulationGenerator:
    """Deterministic population generator used for tests, CI, and offline demos."""

    def generate(
        self,
        brief: str,
        *,
        candidate_count: int,
        domain_label: str,
    ) -> GeneratedPopulationCandidates:
        focus_tokens = extract_focus_tokens(brief)
        focus_label = " ".join(focus_tokens[:3]) or "general recommendation quality"
        base_slug = "-".join(focus_tokens[:3]) or "population"
        templates = _fixture_persona_templates(focus_label)
        personas: list[dict[str, object]] = []
        for index in range(candidate_count):
            template = templates[index % len(templates)]
            personas.append(
                {
                    "persona_id": f"{base_slug}-{template['slug']}-{index + 1}",
                    "display_label": f"{template['label']} #{index + 1}",
                    "persona_summary": template["persona_summary"],
                    "behavior_goal": template["behavior_goal"],
                    "diversity_tags": template["diversity_tags"],
                    "adapter_hints": {"recommender": template["recommender_hints"]},
                }
            )
        return GeneratedPopulationCandidates(personas=tuple(personas))


class ProviderPopulationGenerator:
    """Live provider-backed generator that returns structured persona entries."""

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

    def generate(
        self,
        brief: str,
        *,
        candidate_count: int,
        domain_label: str,
    ) -> GeneratedPopulationCandidates:
        import os

        payload = request_provider_payload(
            endpoint=build_responses_endpoint(os.getenv(self.base_url_env)),
            api_key=self._require_api_key(),
            model_name=self.model_name,
            prompt=self._build_prompt(
                brief=brief,
                candidate_count=candidate_count,
                domain_label=domain_label,
            ),
            timeout_seconds=read_timeout_seconds(self.timeout_seconds_env),
            retry_count=read_retry_count(self.retry_count_env),
            purpose="population generation",
        )
        raw_text = extract_response_text(payload)
        try:
            parsed = json.loads(raw_text)
        except json.JSONDecodeError as exc:
            raise ValueError(
                "Provider returned malformed JSON for population generation. "
                "Try fixture mode or a simpler/faster generation model."
            ) from exc
        personas = parsed.get("personas")
        if not isinstance(personas, list):
            raise ValueError("Provider output must contain a top-level `personas` list.")
        suggested_population_size = parsed.get("target_population_size")
        if suggested_population_size is not None and (
            not isinstance(suggested_population_size, int) or suggested_population_size < 1
        ):
            raise ValueError(
                "Provider output must use a positive integer for `target_population_size`."
            )
        return GeneratedPopulationCandidates(
            personas=tuple(personas),
            suggested_population_size=suggested_population_size,
        )

    def _require_api_key(self) -> str:
        """Read the provider API key through the existing scenario-generation loader."""
        import os

        load_dotenv_if_present()
        api_key = os.getenv(self.api_key_env)
        if not api_key:
            raise RuntimeError(
                f"{self.api_key_env} is required for provider-backed population generation."
            )
        return api_key

    def _build_prompt(self, *, brief: str, candidate_count: int, domain_label: str) -> str:
        """Build a narrow JSON-only prompt for recommender population generation."""
        return (
            "You generate structured recommender population packs for testing recommendation systems.\n"
            "Return JSON only. No markdown, no prose outside the JSON object.\n"
            f"Generate exactly {candidate_count} candidate personas for the domain `{domain_label}`.\n"
            "Return this exact top-level shape:\n"
            "{\n"
            '  "target_population_size": 12,\n'
            '  "personas": [\n'
            "    {\n"
            '      "persona_id": "string",\n'
            '      "display_label": "string",\n'
            '      "persona_summary": "string",\n'
            '      "behavior_goal": "string",\n'
            '      "diversity_tags": ["string"],\n'
            '      "adapter_hints": {\n'
            '        "recommender": {\n'
            '          "preferred_genres": ["string"],\n'
            '          "popularity_preference": 0.5,\n'
            '          "novelty_preference": 0.5,\n'
            '          "repetition_tolerance": 0.5,\n'
            '          "sparse_history_confidence": 0.5,\n'
            '          "abandonment_sensitivity": 0.5,\n'
            '          "patience": 3,\n'
            '          "engagement_baseline": 0.5,\n'
            '          "quality_sensitivity": 0.5,\n'
            '          "repeat_exposure_penalty": 0.2,\n'
            '          "novelty_fatigue": 0.2,\n'
            '          "frustration_recovery": 0.2,\n'
            '          "history_reliance": 0.5,\n'
            '          "skip_tolerance": 2,\n'
            '          "abandonment_threshold": 0.6\n'
            "        }\n"
            "      }\n"
            "    }\n"
            "  ]\n"
            "}\n"
            "Choose `target_population_size` as the number of personas that should be kept "
            "for the final explicit swarm. Use a value between 6 and 18 based on the brief.\n"
            "Keep the personas meaningfully distinct across preference profile, novelty appetite, "
            "patience, abandonment behavior, and history reliance. Keep values between 0 and 1 where applicable.\n"
            f"Brief: {brief}"
        )



def generate_population_pack(
    brief: str,
    *,
    generator_mode: PopulationGeneratorMode,
    population_size: int | None = None,
    candidate_count: int | None = None,
    domain_label: str = "recommender",
    model_name: str = DEFAULT_PROVIDER_MODEL,
) -> PopulationPack:
    """Generate, select, and return a structured recommender population pack."""
    if not brief.strip():
        raise ValueError("population brief must not be empty")
    if population_size is not None and population_size < 1:
        raise ValueError("population_size must be at least 1")
    resolved_candidate_count = _resolve_candidate_count(candidate_count, population_size)

    if generator_mode == "fixture":
        generated = FixturePopulationGenerator().generate(
            brief,
            candidate_count=resolved_candidate_count,
            domain_label=domain_label,
        )
        provider_name = ""
        resolved_model_name = ""
    else:
        generator = ProviderPopulationGenerator(model_name=model_name)
        generated = generator.generate(
            brief,
            candidate_count=resolved_candidate_count,
            domain_label=domain_label,
        )
        provider_name = generator.provider_name
        resolved_model_name = generator.model_name
    resolved_population_size, size_source = _resolve_population_size(
        explicit_population_size=population_size,
        suggested_population_size=generated.suggested_population_size,
        candidate_count=len(generated.personas),
    )
    generated_at_utc = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    return build_population_pack(
        list(generated.personas),
        brief=brief,
        generator_mode=generator_mode,
        generated_at_utc=generated_at_utc,
        domain_label=domain_label,
        target_population_size=resolved_population_size,
        candidate_count=len(generated.personas),
        population_size_source=size_source,
        provider_name=provider_name,
        model_name=resolved_model_name,
    )


def build_population_pack(
    raw_personas: list[dict[str, object]],
    *,
    brief: str,
    generator_mode: PopulationGeneratorMode,
    generated_at_utc: str,
    domain_label: str,
    target_population_size: int,
    candidate_count: int,
    population_size_source: str = "explicit",
    provider_name: str = "",
    model_name: str = "",
) -> PopulationPack:
    """Validate raw persona payloads, select a diverse swarm, and build the pack."""
    personas = tuple(_parse_generated_persona(raw_persona) for raw_persona in raw_personas)
    if not personas:
        raise ValueError("population pack must contain at least one persona")
    _validate_unique_persona_keys(personas)
    selected_personas = _select_diverse_personas(personas, target_population_size)
    if len(selected_personas) != target_population_size:
        raise ValueError(
            "population pack could not satisfy the requested target_population_size."
        )
    digest = sha1(
        json.dumps(
            {
                "brief": brief,
                "generator_mode": generator_mode,
                "domain_label": domain_label,
                "target_population_size": target_population_size,
                "personas": [asdict(persona) for persona in selected_personas],
            },
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()[:12]
    metadata = PopulationPackMetadata(
        pack_id=f"population-{digest}",
        brief=brief,
        generator_mode=generator_mode,
        generated_at_utc=generated_at_utc,
        domain_label=domain_label,
        target_population_size=target_population_size,
        candidate_count=candidate_count,
        selected_count=len(selected_personas),
        population_size_source=population_size_source,
        provider_name=provider_name,
        model_name=model_name,
    )
    return PopulationPack(metadata=metadata, personas=selected_personas)


def write_population_pack(pack: PopulationPack, path: str | Path) -> str:
    """Write a population pack JSON artifact and return the resolved path."""
    resolved = _resolve_population_pack_path(pack, path)
    resolved.parent.mkdir(parents=True, exist_ok=True)
    resolved.write_text(
        json.dumps(asdict(pack), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return str(resolved)


def load_population_pack(path: str | Path) -> PopulationPack:
    """Load and validate a saved population-pack artifact."""
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    metadata = payload.get("metadata")
    personas = payload.get("personas")
    if not isinstance(metadata, dict) or not isinstance(personas, list):
        raise ValueError("population pack must contain `metadata` and `personas` fields")
    return build_population_pack(
        personas,
        brief=str(metadata.get("brief", "")),
        generator_mode=str(metadata.get("generator_mode", "fixture")),  # type: ignore[arg-type]
        generated_at_utc=str(metadata.get("generated_at_utc", "")),
        domain_label=str(metadata.get("domain_label", "recommender")),
        target_population_size=int(metadata.get("target_population_size", len(personas))),
        candidate_count=int(metadata.get("candidate_count", len(personas))),
        population_size_source=str(metadata.get("population_size_source", "explicit")),
        provider_name=str(metadata.get("provider_name", "")),
        model_name=str(metadata.get("model_name", "")),
    )


def build_default_population_pack_path(
    output_root: str | Path,
    *,
    brief: str,
    generator_mode: PopulationGeneratorMode,
) -> str:
    """Build the default artifact path for a generated population pack."""
    slug = re.sub(r"[^a-z0-9]+", "-", brief.lower()).strip("-") or "population-pack"
    return str(Path(output_root) / "population-packs" / f"{slug}-{generator_mode}.json")


def project_recommender_population(pack: PopulationPack) -> tuple[AgentSeed, ...]:
    """Project a saved recommender population pack into concrete runtime agent seeds."""
    return tuple(_project_persona_to_agent_seed(persona) for persona in pack.personas)


def _parse_generated_persona(payload: dict[str, object]) -> GeneratedPersona:
    """Validate one raw generated persona entry."""
    persona_id = _require_non_empty_string(payload, "persona_id")
    display_label = _require_non_empty_string(payload, "display_label")
    persona_summary = _require_non_empty_string(payload, "persona_summary")
    behavior_goal = _require_non_empty_string(payload, "behavior_goal")
    diversity_tags = _require_string_list(payload, "diversity_tags")
    raw_adapter_hints = payload.get("adapter_hints")
    if not isinstance(raw_adapter_hints, dict):
        raise ValueError(f"Persona `{persona_id}` must include an `adapter_hints` object.")
    adapter_hints: dict[str, dict[str, str | int | float | bool | list[str]]] = {}
    for adapter_name, adapter_payload in raw_adapter_hints.items():
        if not isinstance(adapter_name, str) or not isinstance(adapter_payload, dict):
            raise ValueError(f"Persona `{persona_id}` has malformed adapter hints.")
        normalized: dict[str, str | int | float | bool | list[str]] = {}
        for key, value in adapter_payload.items():
            if not isinstance(key, str):
                raise ValueError(f"Persona `{persona_id}` has malformed adapter hint keys.")
            if isinstance(value, str | int | float | bool):
                normalized[key] = value
            elif isinstance(value, list) and all(isinstance(item, str) for item in value):
                normalized[key] = [item.strip() for item in value if item.strip()]
            else:
                raise ValueError(
                    f"Persona `{persona_id}` has unsupported adapter hint value for `{key}`."
                )
        adapter_hints[adapter_name] = normalized
    return GeneratedPersona(
        persona_id=persona_id,
        display_label=display_label,
        persona_summary=persona_summary,
        behavior_goal=behavior_goal,
        diversity_tags=tuple(diversity_tags),
        adapter_hints=adapter_hints,
    )


def _project_persona_to_agent_seed(persona: GeneratedPersona) -> AgentSeed:
    """Turn one saved generated persona into the current deterministic runtime seed."""
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


def _resolve_candidate_count(
    candidate_count: int | None,
    population_size: int | None,
) -> int:
    """Choose a candidate-pool size that leaves room for deterministic filtering."""
    if candidate_count is not None:
        if candidate_count < 1:
            raise ValueError("candidate_count must be at least 1")
        return candidate_count
    baseline_target = population_size or DEFAULT_POPULATION_SIZE
    return max(DEFAULT_CANDIDATE_COUNT, baseline_target * 2)


def _resolve_population_size(
    *,
    explicit_population_size: int | None,
    suggested_population_size: int | None,
    candidate_count: int,
) -> tuple[int, str]:
    """Resolve the final swarm size from explicit input, provider advice, or default."""
    if explicit_population_size is not None:
        resolved = explicit_population_size
        source = "explicit"
    elif suggested_population_size is not None:
        resolved = suggested_population_size
        source = "provider"
    else:
        resolved = DEFAULT_POPULATION_SIZE
        source = "default"
    if resolved > candidate_count:
        raise ValueError(
            "population generation could not satisfy the resolved target size from the available candidates."
        )
    return resolved, source


def _select_diverse_personas(
    personas: tuple[GeneratedPersona, ...],
    target_population_size: int,
) -> tuple[GeneratedPersona, ...]:
    """Keep an explicit swarm with simple deterministic diversity coverage."""
    if len(personas) <= target_population_size:
        return personas
    ordered_candidates = sorted(personas, key=lambda persona: persona.persona_id)
    selected: list[GeneratedPersona] = []
    while ordered_candidates and len(selected) < target_population_size:
        best = max(
            ordered_candidates,
            key=lambda persona: (
                _marginal_diversity_score(persona, tuple(selected)),
                -ordered_candidates.index(persona),
            ),
        )
        selected.append(best)
        ordered_candidates.remove(best)
    return tuple(selected)


def _marginal_diversity_score(
    persona: GeneratedPersona,
    selected: tuple[GeneratedPersona, ...],
) -> int:
    """Score how much new behavioral coverage a candidate adds to the current swarm."""
    signature = _persona_signature(persona)
    if not selected:
        return len(signature)
    covered = set().union(*(_persona_signature(existing) for existing in selected))
    new_signal_count = len(signature.difference(covered))
    tag_bonus = len(set(persona.diversity_tags).difference(*(set(p.diversity_tags) for p in selected)))
    genre_bonus = len(
        set(_require_hint_string_list(_require_recommender_hints(persona), persona.persona_id, "preferred_genres"))
        .difference(
            *(
                set(_require_hint_string_list(_require_recommender_hints(existing), existing.persona_id, "preferred_genres"))
                for existing in selected
            )
        )
    )
    return new_signal_count + tag_bonus + genre_bonus


def _persona_signature(persona: GeneratedPersona) -> set[str]:
    """Map a persona onto a small set of diversity dimensions."""
    hints = _require_recommender_hints(persona)
    preferred_genres = _require_hint_string_list(hints, persona.persona_id, "preferred_genres")
    signature = {
        f"genre:{genre}" for genre in preferred_genres[:2]
    }
    signature.update(
        {
            f"popularity:{_bucket(_require_hint_float(hints, persona.persona_id, 'popularity_preference'))}",
            f"novelty:{_bucket(_require_hint_float(hints, persona.persona_id, 'novelty_preference'))}",
            f"patience:{_require_hint_int(hints, persona.persona_id, 'patience', minimum=1)}",
            f"abandonment:{_bucket(_require_hint_float(hints, persona.persona_id, 'abandonment_sensitivity'))}",
            f"history:{_bucket(_require_hint_float(hints, persona.persona_id, 'history_reliance'))}",
            f"quality:{_bucket(_require_hint_float(hints, persona.persona_id, 'quality_sensitivity'))}",
        }
    )
    signature.update(f"tag:{tag}" for tag in persona.diversity_tags)
    return signature


def _bucket(value: float) -> str:
    """Bucket a normalized float into a small deterministic label."""
    if value < 0.34:
        return "low"
    if value < 0.67:
        return "mid"
    return "high"


def _validate_unique_persona_keys(personas: tuple[GeneratedPersona, ...]) -> None:
    """Reject packs that would collide in runtime identity or reporting."""
    seen_ids: set[str] = set()
    seen_labels: set[str] = set()
    for persona in personas:
        if persona.persona_id in seen_ids:
            raise ValueError(
                f"population pack contains duplicate persona_id `{persona.persona_id}`."
            )
        if persona.display_label in seen_labels:
            raise ValueError(
                f"population pack contains duplicate display label `{persona.display_label}`."
            )
        seen_ids.add(persona.persona_id)
        seen_labels.add(persona.display_label)


def _resolve_population_pack_path(pack: PopulationPack, path: str | Path) -> Path:
    """Avoid overwriting a different generated pack at the default path."""
    resolved = Path(path)
    if not resolved.exists():
        return resolved
    try:
        existing = json.loads(resolved.read_text(encoding="utf-8"))
        existing_pack_id = existing.get("metadata", {}).get("pack_id")
    except (OSError, json.JSONDecodeError, AttributeError):
        existing_pack_id = None
    if existing_pack_id == pack.metadata.pack_id:
        return resolved
    return resolved.with_name(f"{resolved.stem}-{pack.metadata.pack_id}{resolved.suffix}")


def _require_non_empty_string(payload: dict[str, object], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Persona entry is missing a non-empty `{key}` field.")
    return value.strip()


def _require_string_list(payload: dict[str, object], key: str) -> list[str]:
    value = payload.get(key)
    if not isinstance(value, list) or not value or not all(isinstance(item, str) for item in value):
        raise ValueError(f"Persona entry has invalid `{key}` value.")
    return [item.strip() for item in value if item.strip()]


def _require_hint_string_list(
    hints: dict[str, str | int | float | bool | list[str]],
    persona_id: str,
    key: str,
) -> list[str]:
    value = hints.get(key)
    if not isinstance(value, list) or not value or not all(isinstance(item, str) for item in value):
        raise ValueError(f"Persona `{persona_id}` has invalid recommender hint `{key}`.")
    return [item.strip() for item in value if item.strip()]


def _require_recommender_hints(
    persona: GeneratedPersona,
) -> dict[str, str | int | float | bool | list[str]]:
    """Return recommender adapter hints or fail clearly before runtime."""
    hints = persona.adapter_hints.get("recommender")
    if hints is None:
        raise ValueError(f"Persona `{persona.persona_id}` is missing recommender adapter hints.")
    return hints


def _require_hint_float(
    hints: dict[str, str | int | float | bool | list[str]],
    persona_id: str,
    key: str,
) -> float:
    value = hints.get(key)
    if not isinstance(value, int | float):
        raise ValueError(f"Persona `{persona_id}` has invalid recommender hint `{key}`.")
    value = float(value)
    if not 0.0 <= value <= 1.0:
        raise ValueError(f"Persona `{persona_id}` has out-of-range recommender hint `{key}`.")
    return round(value, 4)


def _require_hint_int(
    hints: dict[str, str | int | float | bool | list[str]],
    persona_id: str,
    key: str,
    *,
    minimum: int,
) -> int:
    value = hints.get(key)
    if not isinstance(value, int) or value < minimum:
        raise ValueError(f"Persona `{persona_id}` has invalid recommender hint `{key}`.")
    return value


def _fixture_persona_templates(focus_label: str) -> tuple[dict[str, object], ...]:
    """Return stable recommender persona templates for fixture generation."""
    return (
        _template(
            slug="mainstream",
            label="Conservative mainstream",
            summary=f"Popular familiar viewer around {focus_label}.",
            goal=f"Stress whether the system stays reliable and not overly stale for {focus_label}.",
            tags=("mainstream", "familiarity", "high-popularity"),
            genres=("action", "comedy", "family"),
            popularity=0.92,
            novelty=0.18,
            repetition=0.82,
            sparse_confidence=0.55,
            abandonment=0.45,
            patience=3,
            engagement=0.66,
            quality=0.52,
            repeat_penalty=0.18,
            novelty_fatigue=0.22,
            frustration_recovery=0.14,
            history_reliance=0.82,
            skip_tolerance=2,
            abandonment_threshold=0.68,
        ),
        _template(
            slug="explorer",
            label="Explorer / novelty-seeking",
            summary=f"Novelty-hungry viewer around {focus_label}.",
            goal=f"Stress whether the system explores enough for {focus_label} without breaking trust.",
            tags=("exploration", "novelty", "indie"),
            genres=("sci-fi", "thriller", "indie"),
            popularity=0.32,
            novelty=0.92,
            repetition=0.24,
            sparse_confidence=0.62,
            abandonment=0.38,
            patience=3,
            engagement=0.58,
            quality=0.61,
            repeat_penalty=0.08,
            novelty_fatigue=0.44,
            frustration_recovery=0.12,
            history_reliance=0.36,
            skip_tolerance=3,
            abandonment_threshold=0.76,
        ),
        _template(
            slug="niche",
            label="Niche-interest",
            summary=f"Genre-loyal specialist around {focus_label}.",
            goal=f"Stress whether the system respects niche intent for {focus_label}.",
            tags=("niche", "genre-loyal", "high-quality"),
            genres=("horror", "documentary", "indie"),
            popularity=0.28,
            novelty=0.78,
            repetition=0.45,
            sparse_confidence=0.41,
            abandonment=0.52,
            patience=3,
            engagement=0.54,
            quality=0.72,
            repeat_penalty=0.15,
            novelty_fatigue=0.30,
            frustration_recovery=0.11,
            history_reliance=0.74,
            skip_tolerance=2,
            abandonment_threshold=0.71,
        ),
        _template(
            slug="low-patience",
            label="Low-patience",
            summary=f"Quick-bounce viewer around {focus_label}.",
            goal=f"Stress whether early slates hook users focused on {focus_label}.",
            tags=("low-patience", "first-impression", "bounce-risk"),
            genres=("action", "drama", "comedy"),
            popularity=0.81,
            novelty=0.33,
            repetition=0.31,
            sparse_confidence=0.48,
            abandonment=0.92,
            patience=2,
            engagement=0.63,
            quality=0.48,
            repeat_penalty=0.24,
            novelty_fatigue=0.18,
            frustration_recovery=0.08,
            history_reliance=0.58,
            skip_tolerance=1,
            abandonment_threshold=0.52,
        ),
        _template(
            slug="quality-first",
            label="Quality-first skeptic",
            summary=f"Quality-sensitive viewer around {focus_label}.",
            goal=f"Stress whether the system avoids low-quality filler for {focus_label}.",
            tags=("quality", "skeptical", "trust"),
            genres=("drama", "documentary", "thriller"),
            popularity=0.39,
            novelty=0.58,
            repetition=0.34,
            sparse_confidence=0.44,
            abandonment=0.61,
            patience=3,
            engagement=0.49,
            quality=0.92,
            repeat_penalty=0.18,
            novelty_fatigue=0.20,
            frustration_recovery=0.16,
            history_reliance=0.66,
            skip_tolerance=2,
            abandonment_threshold=0.61,
        ),
        _template(
            slug="headline-chaser",
            label="Headline chaser",
            summary=f"Popularity-anchored viewer around {focus_label}.",
            goal=f"Stress whether the system over-indexes on obvious hits for {focus_label}.",
            tags=("head-items", "popularity", "mainstream"),
            genres=("action", "thriller", "family"),
            popularity=0.96,
            novelty=0.14,
            repetition=0.74,
            sparse_confidence=0.72,
            abandonment=0.36,
            patience=4,
            engagement=0.71,
            quality=0.41,
            repeat_penalty=0.14,
            novelty_fatigue=0.12,
            frustration_recovery=0.20,
            history_reliance=0.48,
            skip_tolerance=3,
            abandonment_threshold=0.73,
        ),
        _template(
            slug="cold-start-fragile",
            label="Cold-start fragile",
            summary=f"User with weak history confidence around {focus_label}.",
            goal=f"Stress cold-start behavior for {focus_label} without over-falling back to generic popularity.",
            tags=("cold-start", "fragile", "trust"),
            genres=("comedy", "sci-fi", "documentary"),
            popularity=0.57,
            novelty=0.51,
            repetition=0.29,
            sparse_confidence=0.16,
            abandonment=0.74,
            patience=2,
            engagement=0.42,
            quality=0.56,
            repeat_penalty=0.21,
            novelty_fatigue=0.26,
            frustration_recovery=0.09,
            history_reliance=0.22,
            skip_tolerance=1,
            abandonment_threshold=0.49,
        ),
        _template(
            slug="slow-burn-curious",
            label="Slow-burn curious",
            summary=f"Patient mixed-intent viewer around {focus_label}.",
            goal=f"Stress long-session balance of exploration and coherence for {focus_label}.",
            tags=("patient", "curious", "mixed-intent"),
            genres=("drama", "sci-fi", "indie"),
            popularity=0.46,
            novelty=0.68,
            repetition=0.42,
            sparse_confidence=0.52,
            abandonment=0.27,
            patience=5,
            engagement=0.57,
            quality=0.69,
            repeat_penalty=0.11,
            novelty_fatigue=0.31,
            frustration_recovery=0.28,
            history_reliance=0.59,
            skip_tolerance=4,
            abandonment_threshold=0.82,
        ),
        _template(
            slug="comfort-loop",
            label="Comfort-loop loyalist",
            summary=f"Familiarity-seeking repeat viewer around {focus_label}.",
            goal=f"Stress over-repetition risk while preserving comfort for {focus_label}.",
            tags=("comfort", "repeat", "loyalist"),
            genres=("family", "comedy", "romance"),
            popularity=0.74,
            novelty=0.19,
            repetition=0.94,
            sparse_confidence=0.63,
            abandonment=0.25,
            patience=4,
            engagement=0.69,
            quality=0.44,
            repeat_penalty=0.05,
            novelty_fatigue=0.14,
            frustration_recovery=0.24,
            history_reliance=0.88,
            skip_tolerance=4,
            abandonment_threshold=0.85,
        ),
        _template(
            slug="novelty-fragile",
            label="Novelty-fragile experimenter",
            summary=f"Exploration-friendly but trust-sensitive viewer around {focus_label}.",
            goal=f"Stress whether the system can explore for {focus_label} without abrupt trust collapse.",
            tags=("exploration", "fragile", "trust"),
            genres=("thriller", "indie", "documentary"),
            popularity=0.33,
            novelty=0.83,
            repetition=0.26,
            sparse_confidence=0.57,
            abandonment=0.68,
            patience=3,
            engagement=0.53,
            quality=0.67,
            repeat_penalty=0.12,
            novelty_fatigue=0.52,
            frustration_recovery=0.10,
            history_reliance=0.31,
            skip_tolerance=2,
            abandonment_threshold=0.58,
        ),
        _template(
            slug="head-to-tail-bridge",
            label="Head-to-tail bridge",
            summary=f"User who likes a mix of hits and long-tail items around {focus_label}.",
            goal=f"Stress balance between relevance and discovery for {focus_label}.",
            tags=("balanced", "head-tail", "bridge"),
            genres=("action", "indie", "documentary"),
            popularity=0.61,
            novelty=0.61,
            repetition=0.36,
            sparse_confidence=0.49,
            abandonment=0.43,
            patience=4,
            engagement=0.60,
            quality=0.66,
            repeat_penalty=0.17,
            novelty_fatigue=0.24,
            frustration_recovery=0.17,
            history_reliance=0.53,
            skip_tolerance=3,
            abandonment_threshold=0.69,
        ),
        _template(
            slug="precision-seeker",
            label="Precision seeker",
            summary=f"High-alignment viewer around {focus_label}.",
            goal=f"Stress whether the system stays tightly relevant for {focus_label} without collapsing diversity.",
            tags=("precision", "alignment", "relevance"),
            genres=("documentary", "drama", "sci-fi"),
            popularity=0.42,
            novelty=0.47,
            repetition=0.28,
            sparse_confidence=0.37,
            abandonment=0.55,
            patience=3,
            engagement=0.50,
            quality=0.84,
            repeat_penalty=0.20,
            novelty_fatigue=0.17,
            frustration_recovery=0.13,
            history_reliance=0.79,
            skip_tolerance=2,
            abandonment_threshold=0.64,
        ),
        _template(
            slug="casual-wanderer",
            label="Casual wanderer",
            summary=f"Light-intent browsing viewer around {focus_label}.",
            goal=f"Stress whether the system can keep casual sessions alive for {focus_label}.",
            tags=("casual", "browsing", "low-commitment"),
            genres=("comedy", "family", "sci-fi"),
            popularity=0.63,
            novelty=0.44,
            repetition=0.47,
            sparse_confidence=0.68,
            abandonment=0.34,
            patience=4,
            engagement=0.56,
            quality=0.38,
            repeat_penalty=0.14,
            novelty_fatigue=0.22,
            frustration_recovery=0.21,
            history_reliance=0.35,
            skip_tolerance=3,
            abandonment_threshold=0.74,
        ),
        _template(
            slug="strict-filter",
            label="Strict filterer",
            summary=f"Low-noise viewer around {focus_label}.",
            goal=f"Stress whether noisy or generic items break confidence for {focus_label}.",
            tags=("strict", "low-noise", "quality"),
            genres=("thriller", "documentary", "drama"),
            popularity=0.27,
            novelty=0.55,
            repetition=0.19,
            sparse_confidence=0.33,
            abandonment=0.77,
            patience=2,
            engagement=0.43,
            quality=0.89,
            repeat_penalty=0.28,
            novelty_fatigue=0.25,
            frustration_recovery=0.07,
            history_reliance=0.71,
            skip_tolerance=1,
            abandonment_threshold=0.47,
        ),
    )


def _template(
    *,
    slug: str,
    label: str,
    summary: str,
    goal: str,
    tags: tuple[str, ...],
    genres: tuple[str, ...],
    popularity: float,
    novelty: float,
    repetition: float,
    sparse_confidence: float,
    abandonment: float,
    patience: int,
    engagement: float,
    quality: float,
    repeat_penalty: float,
    novelty_fatigue: float,
    frustration_recovery: float,
    history_reliance: float,
    skip_tolerance: int,
    abandonment_threshold: float,
) -> dict[str, object]:
    """Build one fixture persona template."""
    return {
        "slug": slug,
        "label": label,
        "persona_summary": summary,
        "behavior_goal": goal,
        "diversity_tags": list(tags),
        "recommender_hints": {
            "preferred_genres": list(genres),
            "popularity_preference": popularity,
            "novelty_preference": novelty,
            "repetition_tolerance": repetition,
            "sparse_history_confidence": sparse_confidence,
            "abandonment_sensitivity": abandonment,
            "patience": patience,
            "engagement_baseline": engagement,
            "quality_sensitivity": quality,
            "repeat_exposure_penalty": repeat_penalty,
            "novelty_fatigue": novelty_fatigue,
            "frustration_recovery": frustration_recovery,
            "history_reliance": history_reliance,
            "skip_tolerance": skip_tolerance,
            "abandonment_threshold": abandonment_threshold,
        },
    }
