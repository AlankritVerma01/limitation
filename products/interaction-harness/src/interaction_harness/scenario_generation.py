"""Scenario-pack generation, validation, storage, and runtime projection."""

from __future__ import annotations

import json
import re
from dataclasses import asdict
from datetime import datetime, timezone
from hashlib import sha1
from pathlib import Path
from typing import Protocol

from .cli_progress import ProgressCallback, emit_progress
from .domains.recommender.scenarios import BUILT_IN_RECOMMENDER_SCENARIO_NAMES
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
    GeneratedScenario,
    ScenarioGeneratorMode,
    ScenarioPack,
    ScenarioPackMetadata,
)

DEFAULT_SCENARIO_COUNT = 3
_SUPPORTED_RUNTIME_PROFILES = set(BUILT_IN_RECOMMENDER_SCENARIO_NAMES)


class ScenarioGenerator(Protocol):
    """Returns raw generated scenarios for a user brief."""

    def generate(
        self,
        brief: str,
        *,
        scenario_count: int,
        domain_label: str,
    ) -> list[dict[str, object]]: ...


class FixtureScenarioGenerator:
    """Deterministic scenario generator used for tests, CI, and offline demos."""

    def generate(
        self,
        brief: str,
        *,
        scenario_count: int,
        domain_label: str,
    ) -> list[dict[str, object]]:
        focus_tokens = extract_focus_tokens(brief)
        focus_label = " ".join(focus_tokens[:3]) or "general recommendation quality"
        base_slug = "-".join(focus_tokens[:3]) or "generated"
        templates = (
            {
                "slug": "context-rich",
                "runtime_profile": "returning-user-home-feed",
                "history_depth": 4,
                "max_steps": 5,
                "risk_focus_tags": ["staleness", "over-specialization"],
                "description": (
                    f"Returning-user session for `{focus_label}` with meaningful prior history."
                ),
                "test_goal": (
                    f"Check whether the system keeps recommendations relevant without becoming stale around {focus_label}."
                ),
            },
            {
                "slug": "thin-context",
                "runtime_profile": "sparse-history-home-feed",
                "history_depth": 1,
                "max_steps": 5,
                "risk_focus_tags": ["cold-start", "popularity-bias"],
                "description": (
                    f"Thin-context session for `{focus_label}` where the system has very little prior evidence."
                ),
                "test_goal": (
                    f"Check whether the system falls back too hard to generic popularity when the brief is {focus_label}."
                ),
            },
            {
                "slug": "taste-elicitation",
                "runtime_profile": "taste-elicitation-home-feed",
                "history_depth": 0,
                "max_steps": 4,
                "risk_focus_tags": ["cold-start", "weak-first-impression", "novelty-mismatch"],
                "description": (
                    f"Onboarding-style session for `{focus_label}` where the system needs to infer taste with almost no prior evidence."
                ),
                "test_goal": (
                    f"Check whether the system can earn an early click for {focus_label} while still learning fresh taste signals."
                ),
            },
            {
                "slug": "exploration-pressure",
                "runtime_profile": "returning-user-home-feed",
                "history_depth": 2,
                "max_steps": 6,
                "risk_focus_tags": ["novelty-mismatch", "trust-drop"],
                "description": (
                    f"Mixed-history session for `{focus_label}` with stronger pressure to balance novelty against familiarity."
                ),
                "test_goal": (
                    f"Check whether the system explores enough for {focus_label} without causing trust collapse."
                ),
            },
            {
                "slug": "low-patience",
                "runtime_profile": "sparse-history-home-feed",
                "history_depth": 1,
                "max_steps": 4,
                "risk_focus_tags": ["early-abandonment", "weak-first-impression"],
                "description": (
                    f"Short low-patience session for `{focus_label}` where the first few slates matter heavily."
                ),
                "test_goal": (
                    f"Check whether the system earns early engagement for {focus_label} before patience runs out."
                ),
            },
            {
                "slug": "re-engagement",
                "runtime_profile": "re-engagement-home-feed",
                "history_depth": 2,
                "max_steps": 5,
                "risk_focus_tags": ["staleness", "trust-drop", "weak-first-impression"],
                "description": (
                    f"Drifted-user return session for `{focus_label}` where stale or off-target recommendations can quickly collapse trust."
                ),
                "test_goal": (
                    f"Check whether the system can rebuild trust for {focus_label} after a period of low engagement."
                ),
            },
        )
        scenarios: list[dict[str, object]] = []
        for index, template in enumerate(templates[:scenario_count], start=1):
            scenarios.append(
                {
                    "scenario_id": f"{base_slug}-{template['slug']}-{index}",
                    "name": f"{focus_label.title()} / {template['slug'].replace('-', ' ')}",
                    "description": template["description"],
                    "test_goal": template["test_goal"],
                    "risk_focus_tags": template["risk_focus_tags"],
                    "max_steps": template["max_steps"],
                    "allowed_actions": ["click", "skip", "abandon"],
                    "adapter_hints": {
                        "recommender": {
                            "runtime_profile": template["runtime_profile"],
                            "history_depth": template["history_depth"],
                            "context_hint": focus_label,
                        }
                    },
                }
            )
        return scenarios


class ProviderScenarioGenerator:
    """Live provider-backed generator that returns structured scenario entries."""

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
        scenario_count: int,
        domain_label: str,
    ) -> list[dict[str, object]]:
        import os

        load_dotenv_if_present()
        api_key = os.getenv(self.api_key_env)
        if not api_key:
            raise RuntimeError(
                f"{self.api_key_env} is required for provider-backed scenario generation."
            )
        endpoint = build_responses_endpoint(os.getenv(self.base_url_env))
        timeout_seconds = read_timeout_seconds(self.timeout_seconds_env)
        retry_count = read_retry_count(self.retry_count_env)
        prompt = self._build_prompt(
            brief=brief,
            scenario_count=scenario_count,
            domain_label=domain_label,
        )
        payload = request_provider_payload(
            endpoint=endpoint,
            api_key=api_key,
            model_name=self.model_name,
            prompt=prompt,
            timeout_seconds=timeout_seconds,
            retry_count=retry_count,
            purpose="scenario generation",
        )
        raw_text = extract_response_text(payload)
        try:
            parsed = json.loads(raw_text)
        except json.JSONDecodeError as exc:
            raise ValueError(
                "Provider returned malformed JSON for scenario generation. "
                "Try fixture mode or a simpler/faster generation model."
            ) from exc
        scenarios = parsed.get("scenarios")
        if not isinstance(scenarios, list):
            raise ValueError("Provider output must contain a top-level `scenarios` list.")
        return scenarios

    def _build_prompt(self, *, brief: str, scenario_count: int, domain_label: str) -> str:
        """Build a narrow JSON-only prompt for scenario generation."""
        return (
            "You generate portable scenario packs for testing non-deterministic software.\n"
            "Return JSON only. No markdown, no prose outside the JSON object.\n"
            f"Generate exactly {scenario_count} scenarios for the domain `{domain_label}`.\n"
            "Return this exact top-level shape:\n"
            "{\n"
            '  "scenarios": [\n'
            "    {\n"
            '      "scenario_id": "string",\n'
            '      "name": "string",\n'
            '      "description": "string",\n'
            '      "test_goal": "string",\n'
            '      "risk_focus_tags": ["string"],\n'
            '      "max_steps": 5,\n'
            '      "allowed_actions": ["click", "skip", "abandon"],\n'
            '      "adapter_hints": {\n'
            '        "recommender": {\n'
            '          "runtime_profile": "returning-user-home-feed, sparse-history-home-feed, taste-elicitation-home-feed, or re-engagement-home-feed",\n'
            '          "history_depth": 1,\n'
            '          "context_hint": "string"\n'
            "        }\n"
            "      }\n"
            "    }\n"
            "  ]\n"
            "}\n"
            "Make the scenarios related but meaningfully different. Vary prior context, exploration pressure, "
            "and risk focus. Keep them clear, concise, and runtime-friendly.\n"
            f"Brief: {brief}"
        )


def generate_scenario_pack(
    brief: str,
    *,
    generator_mode: ScenarioGeneratorMode,
    scenario_count: int = DEFAULT_SCENARIO_COUNT,
    domain_label: str = "recommender",
    model_name: str = DEFAULT_PROVIDER_MODEL,
    progress_callback: ProgressCallback | None = None,
) -> ScenarioPack:
    """Generate, validate, and return a structured scenario pack."""
    if not brief.strip():
        raise ValueError("scenario brief must not be empty")
    if scenario_count < 1:
        raise ValueError("scenario_count must be at least 1")

    emit_progress(
        progress_callback,
        phase="build_generation_input",
        message="Building scenario-generation input",
        stage="start",
    )
    emit_progress(
        progress_callback,
        phase="build_generation_input",
        message="Built scenario-generation input",
        stage="finish",
    )
    emit_progress(
        progress_callback,
        phase="generate_candidates",
        message="Generating scenario candidates",
        stage="start",
    )
    if generator_mode == "fixture":
        raw_scenarios = FixtureScenarioGenerator().generate(
            brief,
            scenario_count=scenario_count,
            domain_label=domain_label,
        )
        provider_name = ""
        resolved_model_name = ""
    else:
        generator = ProviderScenarioGenerator(model_name=model_name)
        raw_scenarios = generator.generate(
            brief,
            scenario_count=scenario_count,
            domain_label=domain_label,
        )
        provider_name = generator.provider_name
        resolved_model_name = generator.model_name
    emit_progress(
        progress_callback,
        phase="generate_candidates",
        message="Generated scenario candidates",
        stage="finish",
    )
    generated_at_utc = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    emit_progress(
        progress_callback,
        phase="validate_generation_output",
        message="Validating generated scenarios",
        stage="start",
    )
    pack = build_scenario_pack(
        raw_scenarios,
        brief=brief,
        generator_mode=generator_mode,
        generated_at_utc=generated_at_utc,
        domain_label=domain_label,
        provider_name=provider_name,
        model_name=resolved_model_name,
    )
    emit_progress(
        progress_callback,
        phase="validate_generation_output",
        message="Validated generated scenarios",
        stage="finish",
    )
    return pack


def build_scenario_pack(
    raw_scenarios: list[dict[str, object]],
    *,
    brief: str,
    generator_mode: ScenarioGeneratorMode,
    generated_at_utc: str,
    domain_label: str,
    provider_name: str = "",
    model_name: str = "",
) -> ScenarioPack:
    """Validate raw scenario payloads and build the durable pack contract."""
    scenarios = tuple(_parse_generated_scenario(raw_scenario) for raw_scenario in raw_scenarios)
    if not scenarios:
        raise ValueError("scenario pack must contain at least one scenario")
    _validate_unique_scenario_keys(scenarios)
    digest = sha1(
        json.dumps(
            {
                "brief": brief,
                "generator_mode": generator_mode,
                "domain_label": domain_label,
                "scenarios": [asdict(scenario) for scenario in scenarios],
            },
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()[:12]
    metadata = ScenarioPackMetadata(
        pack_id=f"pack-{digest}",
        brief=brief,
        generator_mode=generator_mode,
        generated_at_utc=generated_at_utc,
        domain_label=domain_label,
        provider_name=provider_name,
        model_name=model_name,
    )
    return ScenarioPack(metadata=metadata, scenarios=scenarios)


def write_scenario_pack(pack: ScenarioPack, path: str | Path) -> str:
    """Write a scenario pack JSON artifact and return the resolved path."""
    resolved = _resolve_scenario_pack_path(pack, path)
    resolved.parent.mkdir(parents=True, exist_ok=True)
    resolved.write_text(
        json.dumps(asdict(pack), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return str(resolved)


def load_scenario_pack(path: str | Path) -> ScenarioPack:
    """Load and validate a saved scenario pack artifact."""
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    metadata = payload.get("metadata")
    scenarios = payload.get("scenarios")
    if not isinstance(metadata, dict) or not isinstance(scenarios, list):
        raise ValueError("scenario pack must contain `metadata` and `scenarios` fields")
    return build_scenario_pack(
        scenarios,
        brief=str(metadata.get("brief", "")),
        generator_mode=str(metadata.get("generator_mode", "fixture")),  # type: ignore[arg-type]
        generated_at_utc=str(metadata.get("generated_at_utc", "")),
        domain_label=str(metadata.get("domain_label", "recommender")),
        provider_name=str(metadata.get("provider_name", "")),
        model_name=str(metadata.get("model_name", "")),
    )


def build_default_scenario_pack_path(
    output_root: str | Path,
    *,
    brief: str,
    generator_mode: ScenarioGeneratorMode,
) -> str:
    """Build the default artifact path for a generated scenario pack."""
    slug = re.sub(r"[^a-z0-9]+", "-", brief.lower()).strip("-") or "scenario-pack"
    return str(Path(output_root) / "scenario-packs" / f"{slug}-{generator_mode}.json")

def _parse_generated_scenario(payload: dict[str, object]) -> GeneratedScenario:
    """Validate one raw generated scenario entry."""
    scenario_id = _require_non_empty_string(payload, "scenario_id")
    name = _require_non_empty_string(payload, "name")
    description = _require_non_empty_string(payload, "description")
    test_goal = _require_non_empty_string(payload, "test_goal")
    max_steps = _require_positive_int(payload, "max_steps")
    risk_focus_tags = _require_string_list(payload, "risk_focus_tags")
    allowed_actions = _require_string_list(payload, "allowed_actions")
    raw_adapter_hints = payload.get("adapter_hints")
    if not isinstance(raw_adapter_hints, dict):
        raise ValueError(f"Scenario `{scenario_id}` must include an `adapter_hints` object.")
    adapter_hints: dict[str, dict[str, str | int | float | bool | list[str]]] = {}
    for adapter_name, adapter_payload in raw_adapter_hints.items():
        if not isinstance(adapter_name, str) or not isinstance(adapter_payload, dict):
            raise ValueError(f"Scenario `{scenario_id}` has malformed adapter hints.")
        normalized: dict[str, str | int | float | bool | list[str]] = {}
        for key, value in adapter_payload.items():
            if not isinstance(key, str):
                raise ValueError(f"Scenario `{scenario_id}` has malformed adapter hint keys.")
            if isinstance(value, str | int | float | bool):
                normalized[key] = value
            elif isinstance(value, list) and all(isinstance(item, str) for item in value):
                normalized[key] = value
            else:
                raise ValueError(
                    f"Scenario `{scenario_id}` has unsupported adapter hint value for `{key}`."
                )
        adapter_hints[adapter_name] = normalized
    return GeneratedScenario(
        scenario_id=scenario_id,
        name=name,
        description=description,
        test_goal=test_goal,
        risk_focus_tags=tuple(risk_focus_tags),
        max_steps=max_steps,
        allowed_actions=tuple(allowed_actions),
        adapter_hints=adapter_hints,
    )


def _require_non_empty_string(payload: dict[str, object], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Scenario entry is missing a non-empty `{key}` field.")
    return value.strip()


def _require_positive_int(payload: dict[str, object], key: str) -> int:
    value = payload.get(key)
    if not isinstance(value, int) or value < 1:
        raise ValueError(f"Scenario entry has invalid `{key}` value.")
    return value


def _require_string_list(payload: dict[str, object], key: str) -> list[str]:
    value = payload.get(key)
    if not isinstance(value, list) or not value or not all(isinstance(item, str) for item in value):
        raise ValueError(f"Scenario entry has invalid `{key}` value.")
    return [item.strip() for item in value if item.strip()]


def _validate_unique_scenario_keys(scenarios: tuple[GeneratedScenario, ...]) -> None:
    """Reject packs that would collide in runtime identity or reporting."""
    seen_ids: set[str] = set()
    seen_names: set[str] = set()
    for scenario in scenarios:
        if scenario.scenario_id in seen_ids:
            raise ValueError(
                f"scenario pack contains duplicate scenario_id `{scenario.scenario_id}`."
            )
        if scenario.name in seen_names:
            raise ValueError(
                f"scenario pack contains duplicate scenario name `{scenario.name}`."
            )
        seen_ids.add(scenario.scenario_id)
        seen_names.add(scenario.name)


def _resolve_scenario_pack_path(pack: ScenarioPack, path: str | Path) -> Path:
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
