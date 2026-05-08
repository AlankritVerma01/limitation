"""Schema-mapped HTTP driver for the recommender domain."""

from __future__ import annotations

import json
from dataclasses import asdict
from urllib import request

from ....schema import (
    AdapterRequest,
    AdapterResponse,
    AgentState,
    Observation,
    ScenarioConfig,
    Slate,
)
from ._config import EndpointMapping, HttpSchemaMappedDriverConfig
from ._extraction import extract_items, resolve_dot_path
from ._http import request_json
from ._templating import substitute
from ._transform import load_request_transform, load_response_transform


class HttpSchemaMappedRecommenderDriver:
    """Calls a user-shaped HTTP endpoint and adapts the response."""

    def __init__(self, config: HttpSchemaMappedDriverConfig) -> None:
        self._config = config
        self._base_url = config.base_url.rstrip("/")
        self._timeout = config.timeout_seconds
        self._request_transform = (
            load_request_transform(config.transform_request_module)
            if config.transform_request_module
            else None
        )
        self._response_transform = (
            load_response_transform(config.transform_response_module)
            if config.transform_response_module
            else None
        )

    def get_slate(
        self,
        agent_state: AgentState,
        observation: Observation,
        scenario_config: ScenarioConfig,
    ) -> Slate:
        adapter_request = AdapterRequest(
            request_id=f"{agent_state.agent_id}-{observation.scenario_context.scenario_id or observation.scenario_context.scenario_name}-{observation.step_index}",
            agent_id=agent_state.agent_id,
            scenario_name=observation.scenario_context.scenario_name,
            scenario_profile=observation.scenario_context.runtime_profile,
            step_index=observation.step_index,
            history_depth=observation.scenario_context.history_depth,
            history_item_ids=agent_state.history_item_ids,
            recent_exposure_ids=agent_state.recent_exposure_ids,
            preferred_genres=agent_state.preferred_genres,
        )
        body = self._invoke_predict(adapter_request)
        if self._response_transform is not None:
            response = self._response_transform(body, adapter_request)
            if not isinstance(response, AdapterResponse):
                raise RuntimeError(
                    "transform_response must return an AdapterResponse instance."
                )
            return Slate(
                slate_id=f"{scenario_config.scenario_id or scenario_config.name}-{agent_state.agent_id}-{observation.step_index}",
                step_index=observation.step_index,
                items=response.items,
            )
        if self._config.predict.response is None:
            raise RuntimeError("Schema-mapped predict endpoint missing `response` mapping.")
        return Slate(
            slate_id=f"{scenario_config.scenario_id or scenario_config.name}-{agent_state.agent_id}-{observation.step_index}",
            step_index=observation.step_index,
            items=extract_items(body, self._config.predict.response),
        )

    def _invoke_predict(self, source: AdapterRequest):
        endpoint = self._config.predict
        if self._request_transform is None:
            return self._invoke_endpoint(
                endpoint,
                source,
                purpose="recommendation request",
            )
        source_payload = asdict(source)
        rendered_path = substitute(endpoint.path, source_payload)
        rendered_headers = {
            key: str(substitute(value, source_payload))
            for key, value in endpoint.headers.items()
        }
        rendered_headers.setdefault("Content-Type", "application/json")
        body_obj = self._request_transform(source)
        if not isinstance(body_obj, dict):
            raise RuntimeError("transform_request must return a dict.")
        req = request.Request(
            f"{self._base_url}{rendered_path}",
            data=json.dumps(body_obj).encode("utf-8"),
            headers=rendered_headers,
            method=endpoint.method,
        )
        return request_json(req, timeout=self._timeout, purpose="recommendation request")

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
        flat = self._config.metadata.response.flat_field_map if self._config.metadata.response else {}
        return self._extract_flat_metadata(body, flat)

    def get_service_metadata_strict(self) -> dict[str, str | int | float]:
        """Fetch metadata strictly for preflight-compatible callers."""
        if self._config.metadata is None:
            return {"service_kind": "http_schema_mapped"}
        body = self._invoke_endpoint(
            self._config.metadata,
            _empty_request(),
            purpose="metadata request",
        )
        flat = self._config.metadata.response.flat_field_map if self._config.metadata.response else {}
        return self._extract_flat_metadata(body, flat)

    def check_health(self) -> dict[str, str | int | float]:
        """Validate the optional schema-mapped health endpoint."""
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
                    f"Schema-mapped target health check failed: status `{status}`."
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
        source: AdapterRequest,
        *,
        purpose: str,
    ):
        source_payload = asdict(source)
        rendered_path = substitute(endpoint.path, source_payload)
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


def _empty_request() -> AdapterRequest:
    return AdapterRequest(
        request_id="metadata-or-health",
        agent_id="",
        scenario_name="",
        scenario_profile="",
        step_index=0,
        history_depth=0,
        history_item_ids=(),
        recent_exposure_ids=(),
        preferred_genres=(),
    )
