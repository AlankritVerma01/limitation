"""Driver configuration dataclasses for the recommender domain."""

from __future__ import annotations

import dataclasses
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from ....schema import AdapterRequest


@dataclass(frozen=True)
class HttpNativeDriverConfig:
    """Configuration for the native HTTP recommender driver."""

    base_url: str
    timeout_seconds: float


_IMPORT_PATH_PATTERN = re.compile(r"^[a-zA-Z_][\w.]*:[a-zA-Z_]\w*$")
_ALLOWED_METHODS = frozenset({"GET", "POST", "PUT", "PATCH"})


@dataclass(frozen=True)
class InProcessDriverConfig:
    """Configuration for the in-process recommender driver."""

    import_path: str
    init_kwargs: Mapping[str, object] = field(default_factory=dict)
    backend_name: str = ""

    def __post_init__(self) -> None:
        if not _IMPORT_PATH_PATTERN.match(self.import_path):
            raise ValueError(
                f"Invalid import_path `{self.import_path}`. Expected `module:attribute`."
            )

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> "InProcessDriverConfig":
        """Construct an in-process driver config from a JSON object."""
        return cls(
            import_path=str(payload.get("import_path", "")),
            init_kwargs=dict(payload.get("init_kwargs") or {}),
            backend_name=str(payload.get("backend_name", "")),
        )


@dataclass(frozen=True)
class ResponseMapping:
    """Dot-path extraction config for a JSON response payload."""

    items_path: str | None = None
    item_id_field: str = "item_id"
    score_field: str = "score"
    title_field: str | None = None
    flat_field_map: Mapping[str, str] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> "ResponseMapping":
        """Construct response mapping config from a JSON object."""
        return cls(
            items_path=_optional_str(payload.get("items_path")),
            item_id_field=str(payload.get("item_id_field", "item_id")),
            score_field=str(payload.get("score_field", "score")),
            title_field=_optional_str(payload.get("title_field")),
            flat_field_map={
                str(key): str(value)
                for key, value in dict(payload.get("flat_field_map") or {}).items()
            },
        )


@dataclass(frozen=True)
class EndpointMapping:
    """Templated HTTP mapping for one endpoint."""

    method: str
    path: str
    headers: Mapping[str, str] = field(default_factory=dict)
    body: Mapping[str, Any] | None = None
    response: ResponseMapping | None = None

    def __post_init__(self) -> None:
        if self.method.upper() not in _ALLOWED_METHODS:
            raise ValueError(
                f"Endpoint method `{self.method}` is not supported. "
                f"Allowed: {sorted(_ALLOWED_METHODS)}."
            )

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> "EndpointMapping":
        """Construct endpoint mapping config from a JSON object."""
        response_payload = payload.get("response")
        return cls(
            method=str(payload.get("method", "")).upper(),
            path=str(payload.get("path", "")),
            headers={str(key): str(value) for key, value in dict(payload.get("headers") or {}).items()},
            body=dict(payload["body"]) if payload.get("body") is not None else None,
            response=ResponseMapping.from_dict(response_payload)
            if isinstance(response_payload, Mapping)
            else None,
        )


@dataclass(frozen=True)
class HttpSchemaMappedDriverConfig:
    """Configuration for the schema-mapped HTTP recommender driver."""

    base_url: str
    timeout_seconds: float
    predict: EndpointMapping
    health: EndpointMapping | None = None
    metadata: EndpointMapping | None = None

    def __post_init__(self) -> None:
        from ._templating import discover_field_references

        known_fields = frozenset(f.name for f in dataclasses.fields(AdapterRequest))
        used_fields: set[str] = set()
        if self.predict.body is not None:
            used_fields.update(discover_field_references(self.predict.body))
        for endpoint in (self.predict, self.health, self.metadata):
            if endpoint is not None:
                used_fields.update(discover_field_references(dict(endpoint.headers)))
        unknown = used_fields - known_fields
        if unknown:
            raise ValueError(
                f"Unknown AdapterRequest fields referenced: {sorted(unknown)}."
            )

    @classmethod
    def from_dict(
        cls,
        payload: Mapping[str, object],
        *,
        timeout_seconds: float | None = None,
    ) -> "HttpSchemaMappedDriverConfig":
        """Construct schema-mapped driver config from a JSON object."""
        predict_payload = payload.get("predict")
        if not isinstance(predict_payload, Mapping):
            raise ValueError("HttpSchemaMappedDriverConfig requires a `predict` endpoint.")
        return cls(
            base_url=str(payload.get("base_url", "")),
            timeout_seconds=float(
                payload.get("timeout_seconds")
                if "timeout_seconds" in payload
                else (timeout_seconds if timeout_seconds is not None else 2.0)
            ),
            predict=EndpointMapping.from_dict(predict_payload),
            health=EndpointMapping.from_dict(payload["health"])
            if isinstance(payload.get("health"), Mapping)
            else None,
            metadata=EndpointMapping.from_dict(payload["metadata"])
            if isinstance(payload.get("metadata"), Mapping)
            else None,
        )


def _optional_str(value: object) -> str | None:
    return str(value) if isinstance(value, str) and value else None
