"""Scenario-pack generation, validation, storage, and runtime projection."""

from __future__ import annotations

import json
import os
import re
import socket
import time
from dataclasses import asdict
from datetime import datetime, timezone
from hashlib import sha1
from pathlib import Path
from typing import Protocol
from urllib import request
from urllib.error import HTTPError, URLError

from .schema import (
    GeneratedScenario,
    ScenarioConfig,
    ScenarioGeneratorMode,
    ScenarioPack,
    ScenarioPackMetadata,
)

DEFAULT_SCENARIO_COUNT = 3
DEFAULT_PROVIDER_NAME = "openai"
DEFAULT_PROVIDER_MODEL = "gpt-5"
DEFAULT_PROVIDER_BASE_URL = "https://api.openai.com/v1"
DEFAULT_PROVIDER_TIMEOUT_SECONDS = 45.0
DEFAULT_PROVIDER_RETRY_COUNT = 1
_SUPPORTED_RUNTIME_PROFILES = {
    "returning-user-home-feed",
    "sparse-history-home-feed",
}


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
        focus_tokens = _extract_focus_tokens(brief)
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
        _maybe_load_dotenv()
        api_key = os.getenv(self.api_key_env)
        if not api_key:
            raise RuntimeError(
                f"{self.api_key_env} is required for provider-backed scenario generation."
            )
        endpoint = _build_responses_endpoint(os.getenv(self.base_url_env))
        timeout_seconds = _read_timeout_seconds(self.timeout_seconds_env)
        retry_count = _read_retry_count(self.retry_count_env)
        prompt = self._build_prompt(
            brief=brief,
            scenario_count=scenario_count,
            domain_label=domain_label,
        )
        payload = self._request_payload(
            endpoint=endpoint,
            api_key=api_key,
            prompt=prompt,
            timeout_seconds=timeout_seconds,
            retry_count=retry_count,
        )
        raw_text = self._extract_text(payload)
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

    def _request_payload(
        self,
        *,
        endpoint: str,
        api_key: str,
        prompt: str,
        timeout_seconds: float,
        retry_count: int,
    ) -> dict[str, object]:
        """Call the provider endpoint with light retry and clearer failures."""
        last_error: Exception | None = None
        for attempt in range(retry_count + 1):
            req = request.Request(
                endpoint,
                data=json.dumps({"model": self.model_name, "input": prompt}).encode("utf-8"),
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                method="POST",
            )
            try:
                with request.urlopen(req, timeout=timeout_seconds) as response:
                    return json.loads(response.read().decode("utf-8"))
            except HTTPError as exc:
                detail = exc.read().decode("utf-8", errors="ignore")
                raise RuntimeError(
                    f"Provider-backed scenario generation failed with status {exc.code} "
                    f"for model `{self.model_name}` at `{endpoint}`: {detail or exc.reason}"
                ) from exc
            except (TimeoutError, socket.timeout) as exc:
                last_error = exc
                if attempt >= retry_count:
                    break
                time.sleep(0.5 * (attempt + 1))
            except URLError as exc:
                last_error = exc
                if attempt >= retry_count:
                    break
                time.sleep(0.5 * (attempt + 1))
        reason = _format_provider_error_reason(last_error)
        raise RuntimeError(
            "Provider-backed scenario generation failed after retrying. "
            f"Model `{self.model_name}` at `{endpoint}` timed out or could not be reached: {reason}. "
            "Try fixture mode, a faster generation model, or increasing OPENAI_TIMEOUT_SECONDS."
        )

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
            '          "runtime_profile": "returning-user-home-feed or sparse-history-home-feed",\n'
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

    def _extract_text(self, payload: dict[str, object]) -> str:
        """Extract text from the Responses API payload without SDK helpers."""
        output_text = payload.get("output_text")
        if isinstance(output_text, str) and output_text.strip():
            return output_text
        output = payload.get("output", [])
        if not isinstance(output, list):
            raise ValueError("Provider response did not include any text output.")
        for item in output:
            if not isinstance(item, dict):
                continue
            content = item.get("content", [])
            if not isinstance(content, list):
                continue
            for part in content:
                if not isinstance(part, dict):
                    continue
                text = part.get("text")
                if isinstance(text, str) and text.strip():
                    return text
        raise ValueError("Provider response did not include any text output.")


def generate_scenario_pack(
    brief: str,
    *,
    generator_mode: ScenarioGeneratorMode,
    scenario_count: int = DEFAULT_SCENARIO_COUNT,
    domain_label: str = "recommender",
    model_name: str = DEFAULT_PROVIDER_MODEL,
) -> ScenarioPack:
    """Generate, validate, and return a structured scenario pack."""
    if not brief.strip():
        raise ValueError("scenario brief must not be empty")
    if scenario_count < 1:
        raise ValueError("scenario_count must be at least 1")

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
    generated_at_utc = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    return build_scenario_pack(
        raw_scenarios,
        brief=brief,
        generator_mode=generator_mode,
        generated_at_utc=generated_at_utc,
        domain_label=domain_label,
        provider_name=provider_name,
        model_name=resolved_model_name,
    )


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


def project_recommender_scenarios(pack: ScenarioPack) -> tuple[ScenarioConfig, ...]:
    """Project a portable scenario pack into the current recommender runtime shape."""
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


def _extract_focus_tokens(brief: str) -> list[str]:
    """Extract a few stable content words for deterministic fixture naming."""
    common = {
        "about",
        "after",
        "before",
        "brief",
        "chatbot",
        "could",
        "focus",
        "from",
        "have",
        "later",
        "maybe",
        "should",
        "system",
        "testing",
        "users",
        "want",
        "with",
    }
    tokens = [token for token in re.findall(r"[a-z0-9]+", brief.lower()) if len(token) >= 4]
    filtered = [token for token in tokens if token not in common]
    return filtered[:4] or ["quality"]


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


def _maybe_load_dotenv() -> None:
    """Load a simple root-level .env file without overriding existing env vars."""
    for candidate in _candidate_dotenv_paths():
        if not candidate.exists():
            continue
        for raw_line in candidate.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            if not key or key in os.environ:
                continue
            os.environ[key] = _normalize_env_value(value.strip())
        return


def _candidate_dotenv_paths() -> tuple[Path, ...]:
    """Return the likely .env locations for local development."""
    cwd_path = Path.cwd() / ".env"
    repo_root_path = Path(__file__).resolve().parents[4] / ".env"
    if cwd_path == repo_root_path:
        return (cwd_path,)
    return (cwd_path, repo_root_path)


def _normalize_env_value(value: str) -> str:
    """Strip matching quotes around simple .env values."""
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def _build_responses_endpoint(base_url: str | None) -> str:
    """Normalize the provider base URL into a responses endpoint."""
    resolved_base = (base_url or DEFAULT_PROVIDER_BASE_URL).rstrip("/")
    if resolved_base.endswith("/responses"):
        return resolved_base
    if resolved_base.endswith("/v1"):
        return f"{resolved_base}/responses"
    return f"{resolved_base}/v1/responses"


def _read_timeout_seconds(env_name: str) -> float:
    """Read provider timeout from env with a safe default."""
    raw = os.getenv(env_name)
    if raw is None or not raw.strip():
        return DEFAULT_PROVIDER_TIMEOUT_SECONDS
    try:
        value = float(raw)
    except ValueError as exc:
        raise ValueError(f"{env_name} must be a number of seconds.") from exc
    if value <= 0:
        raise ValueError(f"{env_name} must be greater than 0.")
    return value


def _read_retry_count(env_name: str) -> int:
    """Read provider retry count from env with a safe default."""
    raw = os.getenv(env_name)
    if raw is None or not raw.strip():
        return DEFAULT_PROVIDER_RETRY_COUNT
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{env_name} must be an integer.") from exc
    if value < 0:
        raise ValueError(f"{env_name} must be 0 or greater.")
    return value


def _format_provider_error_reason(error: Exception | None) -> str:
    """Extract a short readable reason from the last provider error."""
    if error is None:
        return "unknown error"
    if isinstance(error, URLError):
        return str(error.reason)
    return str(error)


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
