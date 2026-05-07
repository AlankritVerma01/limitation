"""Type-preserving template substitution for schema-mapped driver configs."""

from __future__ import annotations

import os
import re
from collections.abc import Mapping

_PURE_MARKER = re.compile(r"^\$\{([^}]+)\}$")
_ANY_MARKER = re.compile(r"\$\{([^}]+)\}")


class TemplateValidationError(RuntimeError):
    """Raised when a template references unknown fields."""


class EnvVarMissingError(RuntimeError):
    """Raised when an environment template marker has no value."""


def substitute(template: object, context: Mapping[str, object]) -> object:
    """Walk a JSON-like template and substitute field markers."""
    if isinstance(template, Mapping):
        return {key: substitute(value, context) for key, value in template.items()}
    if isinstance(template, list):
        return [substitute(item, context) for item in template]
    if isinstance(template, tuple):
        return tuple(substitute(item, context) for item in template)
    if isinstance(template, str):
        return _resolve_string(template, context)
    return template


def discover_field_references(template: object) -> set[str]:
    """Return non-env field names referenced by a template."""
    found: set[str] = set()
    _collect_references(template, found)
    return found


def _resolve_string(value: str, context: Mapping[str, object]) -> object:
    pure = _PURE_MARKER.match(value)
    if pure:
        marker = pure.group(1)
        if marker.startswith("env:"):
            return _resolve_env(marker[len("env:") :])
        return _resolve_field(marker, context)

    def replace(match: re.Match[str]) -> str:
        marker = match.group(1)
        if marker.startswith("env:"):
            return _resolve_env(marker[len("env:") :])
        return str(_resolve_field(marker, context))

    return _ANY_MARKER.sub(replace, value)


def _resolve_env(var_name: str) -> str:
    if var_name not in os.environ:
        raise EnvVarMissingError(
            f"Template references `${{env:{var_name}}}` but the env var is not set."
        )
    return os.environ[var_name]


def _resolve_field(field_name: str, context: Mapping[str, object]) -> object:
    if field_name not in context:
        raise TemplateValidationError(
            f"Template references unknown field `${{{field_name}}}`."
        )
    return context[field_name]


def _collect_references(template: object, found: set[str]) -> None:
    if isinstance(template, Mapping):
        for value in template.values():
            _collect_references(value, found)
    elif isinstance(template, (list, tuple)):
        for item in template:
            _collect_references(item, found)
    elif isinstance(template, str):
        for match in _ANY_MARKER.finditer(template):
            marker = match.group(1)
            if not marker.startswith("env:"):
                found.add(marker)
