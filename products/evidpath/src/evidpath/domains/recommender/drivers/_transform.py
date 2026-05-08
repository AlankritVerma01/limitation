"""Loader for the schema-mapped driver's transform escape hatch."""

from __future__ import annotations

import importlib
from collections.abc import Callable
from typing import Any

from ....schema import AdapterRequest, AdapterResponse


class TransformLoadError(RuntimeError):
    """Raised when a transform module or its required function is missing."""


def load_request_transform(
    import_path: str,
) -> Callable[[AdapterRequest], dict[str, Any]]:
    """Load `transform_request` from `import_path`."""
    return _load(import_path, "transform_request")


def load_response_transform(
    import_path: str,
) -> Callable[[dict[str, Any], AdapterRequest], AdapterResponse]:
    """Load `transform_response` from `import_path`."""
    return _load(import_path, "transform_response")


def _load(import_path: str, function_name: str) -> Callable[..., Any]:
    try:
        module = importlib.import_module(import_path)
    except ImportError as exc:
        raise TransformLoadError(
            f"Module `{import_path}` could not be imported: {exc}"
        ) from exc
    fn = getattr(module, function_name, None)
    if not callable(fn):
        raise TransformLoadError(
            f"Module `{import_path}` does not define `{function_name}`."
        )
    return fn
