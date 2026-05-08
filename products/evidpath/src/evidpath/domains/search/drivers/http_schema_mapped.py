"""Schema-mapped HTTP driver for the search domain."""

from __future__ import annotations

import json
import re
from urllib import request
from urllib.parse import quote

from ....schema import AgentState, Observation, RankedList, ScenarioConfig
from ..contracts import (
    SearchResponse,
    build_search_request,
    ranked_list_id,
    request_to_payload,
    response_to_ranked_list,
)
from ._config import EndpointMapping, HttpSchemaMappedSearchDriverConfig
from ._extraction import extract_results, resolve_dot_path
from ._http import request_json
from ._templating import substitute

_PATH_MARKER = re.compile(r"\$\{([^}]+)\}")


class HttpSchemaMappedSearchDriver:
    """Calls a user-shaped HTTP search endpoint and adapts the response."""

    def __init__(self, config: HttpSchemaMappedSearchDriverConfig) -> None:
        self._config = config
        self._base_url = config.base_url.rstrip("/")
        self._timeout = config.timeout_seconds

    def get_ranked_list(
        self,
        agent_state: AgentState,
        observation: Observation,
        scenario_config: ScenarioConfig,
    ) -> RankedList:
        search_request = build_search_request(agent_state, observation, scenario_config)
        body = self._invoke_endpoint(
            self._config.search,
            search_request,
            purpose="search request",
        )
        if self._config.search.response is None:
            raise RuntimeError("Schema-mapped search endpoint missing `response` mapping.")
        search_response = SearchResponse(
            request_id=search_request.request_id,
            results=extract_results(body, self._config.search.response),
        )
        return response_to_ranked_list(
            search_response,
            ranked_list_id=ranked_list_id(agent_state, observation, scenario_config),
            step_index=observation.step_index,
        )

    def get_slate(
        self,
        agent_state: AgentState,
        observation: Observation,
        scenario_config: ScenarioConfig,
    ) -> RankedList:
        return self.get_ranked_list(agent_state, observation, scenario_config)

    def get_service_metadata(self) -> dict[str, str | int | float]:
        if self._config.metadata is None:
            return {"service_kind": "http_schema_mapped"}
        try:
            body = self._invoke_endpoint(
                self._config.metadata,
                _empty_request(),
                purpose="metadata request",
            )
        except RuntimeError:
            return {"service_kind": "http_schema_mapped"}
        flat = (
            self._config.metadata.response.flat_field_map
            if self._config.metadata.response
            else {}
        )
        return self._extract_flat_metadata(body, flat)

    def get_service_metadata_strict(self) -> dict[str, str | int | float]:
        if self._config.metadata is None:
            return {"service_kind": "http_schema_mapped"}
        body = self._invoke_endpoint(
            self._config.metadata,
            _empty_request(),
            purpose="metadata request",
        )
        flat = (
            self._config.metadata.response.flat_field_map
            if self._config.metadata.response
            else {}
        )
        return self._extract_flat_metadata(body, flat)

    def check_health(self) -> dict[str, str | int | float]:
        if self._config.health is None:
            return {"status": "ok"}
        body = self._invoke_endpoint(
            self._config.health,
            _empty_request(),
            purpose="health check",
        )
        if isinstance(body, dict):
            status = body.get("status")
            if isinstance(status, str) and status.lower() != "ok":
                raise RuntimeError(
                    f"Schema-mapped search target health check failed: status `{status}`."
                )
            return {
                key: value
                for key, value in body.items()
                if isinstance(value, (str, int, float))
            }
        return {"status": "ok"}

    def _invoke_endpoint(
        self,
        endpoint: EndpointMapping,
        source,
        *,
        purpose: str,
    ):
        source_payload = request_to_payload(source)
        rendered_path = _substitute_url_path(endpoint.path, source_payload)
        rendered_headers = {
            key: str(substitute(value, source_payload))
            for key, value in endpoint.headers.items()
        }
        rendered_headers.setdefault("Content-Type", "application/json")
        body_bytes = None
        if endpoint.body is not None:
            body_bytes = json.dumps(substitute(endpoint.body, source_payload)).encode(
                "utf-8"
            )
        req = request.Request(
            f"{self._base_url}{rendered_path}",
            data=body_bytes,
            headers=rendered_headers,
            method=endpoint.method,
        )
        return request_json(req, timeout=self._timeout, purpose=purpose)

    @staticmethod
    def _extract_flat_metadata(payload, flat_field_map) -> dict[str, str | int | float]:
        result: dict[str, str | int | float] = {"service_kind": "http_schema_mapped"}
        for output_key, path in flat_field_map.items():
            try:
                value = resolve_dot_path(payload, path)
            except Exception:
                continue
            if isinstance(value, (str, int, float)):
                result[str(output_key)] = value
        return result


def _empty_request():
    from ..contracts import SearchRequest

    return SearchRequest(
        request_id="metadata-or-health",
        query="",
    )


def _substitute_url_path(path_template: str, source_payload: dict[str, object]) -> str:
    """Render a URL path while encoding substituted values, not delimiters."""
    rendered_parts: list[str] = []
    cursor = 0
    for match in _PATH_MARKER.finditer(path_template):
        rendered_parts.append(quote(path_template[cursor : match.start()], safe="/:?&=%"))
        rendered_value = substitute(match.group(0), source_payload)
        rendered_parts.append(quote(str(rendered_value), safe=""))
        cursor = match.end()
    rendered_parts.append(quote(path_template[cursor:], safe="/:?&=%"))
    return "".join(rendered_parts)
