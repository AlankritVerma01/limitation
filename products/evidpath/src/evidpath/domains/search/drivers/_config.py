"""Driver configuration dataclasses for the search domain."""

from __future__ import annotations

import dataclasses
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from ..contracts import SearchRequest
from ._templating import discover_field_references

_IMPORT_PATH_PATTERN = re.compile(r"^[a-zA-Z_][\w.]*:[a-zA-Z_]\w*$")
_ALLOWED_METHODS = frozenset({"GET", "POST", "PUT", "PATCH"})


@dataclass(frozen=True)
class HttpNativeSearchDriverConfig:
    """Configuration for the native HTTP search driver."""

    base_url: str
    timeout_seconds: float


@dataclass(frozen=True)
class InProcessSearchDriverConfig:
    """Configuration for the in-process search driver."""

    import_path: str
    init_kwargs: Mapping[str, object] = field(default_factory=dict)
    backend_name: str = ""

    def __post_init__(self) -> None:
        if not _IMPORT_PATH_PATTERN.match(self.import_path):
            raise ValueError(
                f"Invalid import_path `{self.import_path}`. Expected `module:attribute`."
            )

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> "InProcessSearchDriverConfig":
        return cls(
            import_path=str(payload.get("import_path", "")),
            init_kwargs=dict(payload.get("init_kwargs") or {}),
            backend_name=str(payload.get("backend_name", "")),
        )


@dataclass(frozen=True)
class SearchResponseMapping:
    """Dot-path extraction config for a JSON search response payload."""

    results_path: str | None = None
    result_id_field: str = "result_id"
    title_field: str = "title"
    snippet_field: str = "snippet"
    url_field: str = "url"
    type_field: str = "result_type"
    relevance_score_field: str = "relevance_score"
    freshness_timestamp_field: str | None = None
    freshness_score_field: str | None = None
    flat_field_map: Mapping[str, str] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> "SearchResponseMapping":
        return cls(
            results_path=_optional_str(payload.get("results_path")),
            result_id_field=str(payload.get("result_id_field", "result_id")),
            title_field=str(payload.get("title_field", "title")),
            snippet_field=str(payload.get("snippet_field", "snippet")),
            url_field=str(payload.get("url_field", "url")),
            type_field=str(payload.get("type_field", "result_type")),
            relevance_score_field=str(
                payload.get("relevance_score_field", "relevance_score")
            ),
            freshness_timestamp_field=_optional_str(
                payload.get("freshness_timestamp_field")
            ),
            freshness_score_field=_optional_str(payload.get("freshness_score_field")),
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
    response: SearchResponseMapping | None = None

    def __post_init__(self) -> None:
        if self.method.upper() not in _ALLOWED_METHODS:
            raise ValueError(
                f"Endpoint method `{self.method}` is not supported. "
                f"Allowed: {sorted(_ALLOWED_METHODS)}."
            )

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> "EndpointMapping":
        response_payload = payload.get("response")
        return cls(
            method=str(payload.get("method", "")).upper(),
            path=str(payload.get("path", "")),
            headers={
                str(key): str(value)
                for key, value in dict(payload.get("headers") or {}).items()
            },
            body=dict(payload["body"]) if payload.get("body") is not None else None,
            response=SearchResponseMapping.from_dict(response_payload)
            if isinstance(response_payload, Mapping)
            else None,
        )


@dataclass(frozen=True)
class HttpSchemaMappedSearchDriverConfig:
    """Configuration for the schema-mapped HTTP search driver."""

    base_url: str
    timeout_seconds: float
    search: EndpointMapping
    health: EndpointMapping | None = None
    metadata: EndpointMapping | None = None

    def __post_init__(self) -> None:
        known_fields = frozenset(f.name for f in dataclasses.fields(SearchRequest))
        used_fields: set[str] = set()
        if self.search.body is not None:
            used_fields.update(discover_field_references(self.search.body))
        for endpoint in (self.search, self.health, self.metadata):
            if endpoint is not None:
                used_fields.update(discover_field_references(dict(endpoint.headers)))
                used_fields.update(discover_field_references(endpoint.path))
        unknown = used_fields - known_fields
        if unknown:
            raise ValueError(
                f"Unknown SearchRequest fields referenced: {sorted(unknown)}."
            )

    @classmethod
    def from_dict(
        cls,
        payload: Mapping[str, object],
        *,
        timeout_seconds: float | None = None,
    ) -> "HttpSchemaMappedSearchDriverConfig":
        search_payload = payload.get("search")
        if not isinstance(search_payload, Mapping):
            raise ValueError("HttpSchemaMappedSearchDriverConfig requires a `search` endpoint.")
        return cls(
            base_url=str(payload.get("base_url", "")),
            timeout_seconds=float(
                payload.get("timeout_seconds")
                if "timeout_seconds" in payload
                else (timeout_seconds if timeout_seconds is not None else 2.0)
            ),
            search=EndpointMapping.from_dict(search_payload),
            health=EndpointMapping.from_dict(payload["health"])
            if isinstance(payload.get("health"), Mapping)
            else None,
            metadata=EndpointMapping.from_dict(payload["metadata"])
            if isinstance(payload.get("metadata"), Mapping)
            else None,
        )


def _optional_str(value: object) -> str | None:
    return str(value) if isinstance(value, str) and value else None
