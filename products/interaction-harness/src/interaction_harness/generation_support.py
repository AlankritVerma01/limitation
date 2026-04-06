"""Shared helpers for provider-backed and fixture-backed generation flows."""

from __future__ import annotations

import json
import os
import re
import socket
import time
from pathlib import Path
from urllib import request
from urllib.error import HTTPError, URLError

DEFAULT_PROVIDER_NAME = "openai"
DEFAULT_PROVIDER_MODEL = "gpt-5"
DEFAULT_PROVIDER_BASE_URL = "https://api.openai.com/v1"
DEFAULT_PROVIDER_TIMEOUT_SECONDS = 45.0
DEFAULT_PROVIDER_RETRY_COUNT = 1


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
        "Try fixture mode, a faster generation model, or increasing OPENAI_TIMEOUT_SECONDS."
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
    """Return the likely `.env` locations for local development."""
    cwd_path = Path.cwd() / ".env"
    repo_root_path = Path(__file__).resolve().parents[4] / ".env"
    if cwd_path == repo_root_path:
        return (cwd_path,)
    return (cwd_path, repo_root_path)


def _normalize_env_value(value: str) -> str:
    """Strip matching quotes around simple `.env` values."""
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value
