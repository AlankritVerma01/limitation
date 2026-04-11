"""Population-pack generation, validation, selection, storage, and projection."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from hashlib import sha1
from pathlib import Path
from typing import Protocol

from .cli_progress import ProgressCallback, emit_progress
from .domain_registry import get_domain_definition
from .generation_support import (
    DEFAULT_PROVIDER_NAME,
    DEFAULT_PROVIDER_PROFILE,
    build_responses_endpoint,
    extract_response_text,
    load_dotenv_if_present,
    read_retry_count_with_fallback,
    read_timeout_seconds_with_fallback,
    request_provider_payload,
    resolve_provider_model,
)
from .schema import (
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
        hooks = _require_generation_hooks(domain_label)
        if hooks.build_fixture_population_candidates is None:
            raise ValueError(
                f"Domain `{domain_label}` does not support fixture population generation."
            )
        return GeneratedPopulationCandidates(
            personas=hooks.build_fixture_population_candidates(
                brief,
                candidate_count=candidate_count,
            )
        )


class ProviderPopulationGenerator:
    """Live provider-backed generator that returns structured persona entries."""

    def __init__(
        self,
        *,
        provider_name: str = DEFAULT_PROVIDER_NAME,
        model_name: str | None = None,
        profile_name: str = DEFAULT_PROVIDER_PROFILE,
        api_key_env: str = "OPENAI_API_KEY",
        base_url_env: str = "OPENAI_BASE_URL",
        timeout_seconds_env: str = "OPENAI_POPULATION_TIMEOUT_SECONDS",
        retry_count_env: str = "OPENAI_POPULATION_RETRY_COUNT",
    ) -> None:
        self.provider_name = provider_name
        self.model_name, self.model_profile = resolve_provider_model(
            purpose="population_generation",
            explicit_model_name=model_name,
            profile_name=profile_name,
        )
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
            timeout_seconds=read_timeout_seconds_with_fallback(
                self.timeout_seconds_env,
                "OPENAI_TIMEOUT_SECONDS",
            ),
            retry_count=read_retry_count_with_fallback(
                self.retry_count_env,
                "OPENAI_RETRY_COUNT",
            ),
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
        """Build a narrow JSON-only prompt for one domain's population generation."""
        hooks = _require_generation_hooks(domain_label)
        if hooks.build_population_prompt is None:
            raise ValueError(
                f"Domain `{domain_label}` does not support provider population generation."
            )
        return hooks.build_population_prompt(
            brief=brief,
            candidate_count=candidate_count,
            domain_label=domain_label,
        )



def generate_population_pack(
    brief: str,
    *,
    generator_mode: PopulationGeneratorMode,
    population_size: int | None = None,
    candidate_count: int | None = None,
    domain_label: str = "recommender",
    model_name: str | None = None,
    model_profile: str = DEFAULT_PROVIDER_PROFILE,
    progress_callback: ProgressCallback | None = None,
) -> PopulationPack:
    """Generate, select, and return a structured population pack."""
    if not brief.strip():
        raise ValueError("population brief must not be empty")
    if population_size is not None and population_size < 1:
        raise ValueError("population_size must be at least 1")
    clarification = _build_population_brief_clarification(domain_label, brief)
    if clarification is not None:
        raise ValueError(clarification)
    resolved_candidate_count = _resolve_candidate_count(candidate_count, population_size)
    emit_progress(
        progress_callback,
        phase="build_generation_input",
        message="Building population-generation input",
        stage="start",
    )
    emit_progress(
        progress_callback,
        phase="build_generation_input",
        message="Built population-generation input",
        stage="finish",
    )

    emit_progress(
        progress_callback,
        phase="generate_candidates",
        message="Generating population candidates",
        stage="start",
    )
    if generator_mode == "fixture":
        generated = FixturePopulationGenerator().generate(
            brief,
            candidate_count=resolved_candidate_count,
            domain_label=domain_label,
        )
        provider_name = ""
        resolved_model_name = ""
        resolved_model_profile = ""
    else:
        generator = ProviderPopulationGenerator(model_name=model_name, profile_name=model_profile)
        generated = generator.generate(
            brief,
            candidate_count=resolved_candidate_count,
            domain_label=domain_label,
        )
        provider_name = generator.provider_name
        resolved_model_name = generator.model_name
        resolved_model_profile = generator.model_profile
    emit_progress(
        progress_callback,
        phase="generate_candidates",
        message="Generated population candidates",
        stage="finish",
    )
    resolved_population_size, size_source = _resolve_population_size(
        explicit_population_size=population_size,
        suggested_population_size=generated.suggested_population_size,
        candidate_count=len(generated.personas),
    )
    generated_at_utc = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    emit_progress(
        progress_callback,
        phase="validate_generation_output",
        message="Validating population candidates",
        stage="start",
    )
    emit_progress(
        progress_callback,
        phase="select_generation_output",
        message="Selecting final population",
        stage="start",
    )
    pack = build_population_pack(
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
        model_profile=resolved_model_profile,
    )
    emit_progress(
        progress_callback,
        phase="select_generation_output",
        message="Selected final population",
        stage="finish",
    )
    emit_progress(
        progress_callback,
        phase="validate_generation_output",
        message="Validated population candidates",
        stage="finish",
    )
    return pack


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
    model_profile: str = "",
) -> PopulationPack:
    """Validate raw persona payloads, select a final swarm, and build the pack."""
    personas = tuple(_parse_generated_persona(raw_persona) for raw_persona in raw_personas)
    if not personas:
        raise ValueError("population pack must contain at least one persona")
    _validate_unique_persona_keys(personas)
    selected_personas = _select_personas_for_domain(
        personas,
        target_population_size=target_population_size,
        domain_label=domain_label,
    )
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
        model_profile=model_profile,
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
        model_profile=str(metadata.get("model_profile", "")),
    )


def build_default_population_pack_path(
    output_root: str | Path,
    *,
    brief: str,
    generator_mode: PopulationGeneratorMode,
) -> str:
    """Build the default artifact path for a generated population pack."""
    slug = re.sub(r"[^a-z0-9]+", "-", brief.lower()).strip("-") or "population-pack"
    return str(
        Path(output_root) / "population-packs" / f"{slug}-{generator_mode}.json"
    )

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


def _select_personas_for_domain(
    personas: tuple[GeneratedPersona, ...],
    *,
    target_population_size: int,
    domain_label: str,
) -> tuple[GeneratedPersona, ...]:
    """Select the final explicit swarm through domain-owned semantics when present."""
    hooks = _require_generation_hooks(domain_label)
    if hooks.select_population_personas is not None:
        return hooks.select_population_personas(personas, target_population_size)
    return tuple(
        sorted(personas, key=lambda persona: persona.persona_id)[:target_population_size]
    )


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


def _build_population_brief_clarification(domain_label: str, brief: str) -> str | None:
    hooks = _require_generation_hooks(domain_label)
    if hooks.build_population_brief_clarification is None:
        return None
    return hooks.build_population_brief_clarification(brief)


def _require_generation_hooks(domain_label: str):
    definition = get_domain_definition(domain_label)
    hooks = definition.generation_hooks
    if hooks is None:
        raise ValueError(f"Domain `{domain_label}` does not define generation hooks.")
    return hooks
