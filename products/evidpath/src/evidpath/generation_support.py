"""Shared helpers for provider-backed and fixture-backed AI workflows."""

from __future__ import annotations

import json
import os
import re
import socket
import time
from pathlib import Path
from typing import Literal
from urllib import request
from urllib.error import HTTPError, URLError

DEFAULT_PROVIDER_NAME = "openai"
DEFAULT_PROVIDER_BASE_URL = "https://api.openai.com/v1"
DEFAULT_PROVIDER_TIMEOUT_SECONDS = 45.0
DEFAULT_PROVIDER_RETRY_COUNT = 1
DEFAULT_PROVIDER_PROFILE = "fast"

ProviderPurpose = Literal[
    "scenario_generation",
    "population_generation",
    "semantic_interpretation",
    "run_planning",
]

PROVIDER_MODEL_PROFILES: dict[str, dict[ProviderPurpose, str]] = {
    "fast": {
        "scenario_generation": "gpt-5-mini",
        "population_generation": "gpt-5-mini",
        "semantic_interpretation": "gpt-5-mini",
        "run_planning": "gpt-5-mini",
    },
    "balanced": {
        "scenario_generation": "gpt-5.4-mini",
        "population_generation": "gpt-5.4-mini",
        "semantic_interpretation": "gpt-5.4-mini",
        "run_planning": "gpt-5.4-mini",
    },
    "deep": {
        "scenario_generation": "gpt-5.4",
        "population_generation": "gpt-5.4",
        "semantic_interpretation": "gpt-5.4",
        "run_planning": "gpt-5.4",
    },
}

DEFAULT_SCENARIO_PROVIDER_MODEL = PROVIDER_MODEL_PROFILES[DEFAULT_PROVIDER_PROFILE][
    "scenario_generation"
]
DEFAULT_POPULATION_PROVIDER_MODEL = PROVIDER_MODEL_PROFILES[DEFAULT_PROVIDER_PROFILE][
    "population_generation"
]
DEFAULT_SEMANTIC_PROVIDER_MODEL = PROVIDER_MODEL_PROFILES[DEFAULT_PROVIDER_PROFILE][
    "semantic_interpretation"
]
DEFAULT_PLANNER_PROVIDER_MODEL = PROVIDER_MODEL_PROFILES[DEFAULT_PROVIDER_PROFILE][
    "run_planning"
]

# Backward-compatible alias for existing imports. Scenario generation was the
# original shared default, so keep this pointing at the scenario default.
DEFAULT_PROVIDER_MODEL = DEFAULT_SCENARIO_PROVIDER_MODEL


def extract_focus_tokens(brief: str) -> list[str]:
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


def list_provider_profiles() -> tuple[str, ...]:
    """Return the supported provider model profiles in stable display order."""
    return tuple(PROVIDER_MODEL_PROFILES.keys())


def resolve_provider_model(
    *,
    purpose: ProviderPurpose,
    explicit_model_name: str | None = None,
    profile_name: str | None = None,
) -> tuple[str, str]:
    """Resolve the provider model for one workflow.

    Explicit model overrides always win. Otherwise the named profile selects the
    model for the given purpose. The returned profile is `custom` when an
    explicit model override is used.
    """
    if explicit_model_name is not None and explicit_model_name.strip():
        return explicit_model_name.strip(), "custom"
    resolved_profile = (profile_name or DEFAULT_PROVIDER_PROFILE).strip() or DEFAULT_PROVIDER_PROFILE
    if resolved_profile not in PROVIDER_MODEL_PROFILES:
        supported = ", ".join(list_provider_profiles())
        raise ValueError(
            f"Unsupported AI profile `{resolved_profile}`. Expected one of: {supported}."
        )
    return PROVIDER_MODEL_PROFILES[resolved_profile][purpose], resolved_profile


def provider_credentials_available(api_key_env: str = "OPENAI_API_KEY") -> bool:
    """Return whether provider-backed generation can run in the current env."""
    load_dotenv_if_present()
    api_key = os.getenv(api_key_env, "").strip()
    return bool(api_key)


def load_dotenv_if_present() -> None:
    """Load a simple root-level `.env` file without overriding env vars."""
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


def build_responses_endpoint(base_url: str | None) -> str:
    """Normalize a provider base URL into a Responses API endpoint."""
    resolved_base = (base_url or DEFAULT_PROVIDER_BASE_URL).rstrip("/")
    if resolved_base.endswith("/responses"):
        return resolved_base
    if resolved_base.endswith("/v1"):
        return f"{resolved_base}/responses"
    return f"{resolved_base}/v1/responses"


def read_timeout_seconds(env_name: str) -> float:
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


def read_timeout_seconds_with_fallback(*env_names: str) -> float:
    """Read the first configured timeout from a list of env names."""
    for env_name in env_names:
        raw = os.getenv(env_name)
        if raw is None or not raw.strip():
            continue
        return read_timeout_seconds(env_name)
    return DEFAULT_PROVIDER_TIMEOUT_SECONDS


def read_retry_count(env_name: str) -> int:
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


def read_retry_count_with_fallback(*env_names: str) -> int:
    """Read the first configured retry count from a list of env names."""
    for env_name in env_names:
        raw = os.getenv(env_name)
        if raw is None or not raw.strip():
            continue
        return read_retry_count(env_name)
    return DEFAULT_PROVIDER_RETRY_COUNT


def request_provider_payload(
    *,
    endpoint: str,
    api_key: str,
    model_name: str,
    prompt: str,
    timeout_seconds: float,
    retry_count: int,
    purpose: str,
) -> dict[str, object]:
    """Call the provider endpoint with light retry and clearer failures."""
    last_error: Exception | None = None
    for attempt in range(retry_count + 1):
        req = request.Request(
            endpoint,
            data=json.dumps({"model": model_name, "input": prompt}).encode("utf-8"),
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
                f"Provider-backed {purpose} failed with status {exc.code} "
                f"for model `{model_name}` at `{endpoint}`: {detail or exc.reason}"
            ) from exc
        except (TimeoutError, socket.timeout, URLError) as exc:
            last_error = exc
            if attempt >= retry_count:
                break
            time.sleep(0.5 * (attempt + 1))
    reason = format_provider_error_reason(last_error)
    raise RuntimeError(
        f"Provider-backed {purpose} failed after retrying. "
        f"Model `{model_name}` at `{endpoint}` timed out or could not be reached: {reason}. "
        "Try fixture mode, a faster generation model, or increasing the purpose-specific "
        "timeout env vars such as OPENAI_SCENARIO_TIMEOUT_SECONDS, "
        "OPENAI_POPULATION_TIMEOUT_SECONDS, OPENAI_SEMANTIC_TIMEOUT_SECONDS, "
        "or the shared OPENAI_TIMEOUT_SECONDS."
    )


def extract_response_text(payload: dict[str, object]) -> str:
    """Extract text from a Responses API payload without SDK helpers."""
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


def format_provider_error_reason(error: Exception | None) -> str:
    """Extract a short readable reason from the last provider error."""
    if error is None:
        return "unknown error"
    if isinstance(error, URLError):
        return str(error.reason)
    return str(error)


def _candidate_dotenv_paths() -> tuple[Path, ...]:
    """Return the likely `.env` locations for local development and CLI usage."""
    cwd_path = Path.cwd() / ".env"
    home_path = Path.home() / ".evidpath.env"
    repo_root_path = Path(__file__).resolve().parents[4] / ".env"
    candidates: list[Path] = [cwd_path, home_path]
    if repo_root_path not in candidates:
        candidates.append(repo_root_path)
    return tuple(candidates)


def _normalize_env_value(value: str) -> str:
    """Strip matching quotes around simple `.env` values."""
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value
