"""Native HTTP driver for the search domain."""

from __future__ import annotations

import json
from urllib import request

from ....schema import AgentState, Observation, RankedList, ScenarioConfig
from ..contracts import (
    SearchResponse,
    SearchResult,
    build_search_request,
    ranked_list_id,
    request_to_payload,
    response_to_ranked_list,
)
from ._config import HttpNativeSearchDriverConfig
from ._http import request_json


class HttpNativeSearchDriver:
    """Calls a native search endpoint and normalizes its response."""

    def __init__(self, config: HttpNativeSearchDriverConfig) -> None:
        self.base_url = config.base_url.rstrip("/")
        self.timeout_seconds = config.timeout_seconds

    def get_ranked_list(
        self,
        agent_state: AgentState,
        observation: Observation,
        scenario_config: ScenarioConfig,
    ) -> RankedList:
        search_request = build_search_request(agent_state, observation, scenario_config)
        payload = json.dumps(request_to_payload(search_request)).encode("utf-8")
        req = request.Request(
            f"{self.base_url}/search",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        body = self._request_json(req, purpose="search request")
        search_response = self._normalize_response(body)
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
        return self._get_service_metadata(strict=False)

    def get_service_metadata_strict(self) -> dict[str, str | int | float]:
        return self._get_service_metadata(strict=True)

    def check_health(self) -> dict[str, str | int | float]:
        req = request.Request(
            f"{self.base_url}/health",
            headers={"Content-Type": "application/json"},
            method="GET",
        )
        body = self._request_json(req, purpose="health check")
        if not isinstance(body, dict):
            raise RuntimeError(
                f"Search target returned an invalid health payload: {self.base_url}."
            )
        status = body.get("status")
        if not isinstance(status, str) or status.lower() != "ok":
            raise RuntimeError(
                f"Search target health check failed: expected `status=ok` from {self.base_url}."
            )
        return {
            key: value
            for key, value in body.items()
            if isinstance(value, (str, int, float))
        }

    def _get_service_metadata(self, *, strict: bool) -> dict[str, str | int | float]:
        req = request.Request(
            f"{self.base_url}/metadata",
            headers={"Content-Type": "application/json"},
            method="GET",
        )
        try:
            body = self._request_json(req, purpose="metadata request")
        except RuntimeError:
            if strict:
                raise
            return {}
        if not isinstance(body, dict):
            raise RuntimeError(
                f"Search target returned an invalid metadata payload: {self.base_url}."
            )
        return {
            key: value
            for key, value in body.items()
            if isinstance(value, (str, int, float))
        }

    def _normalize_response(self, payload: dict) -> SearchResponse:
        try:
            request_id = payload["request_id"]
            raw_results = payload["results"]
            results = tuple(
                SearchResult(
                    result_id=result["result_id"],
                    title=result["title"],
                    snippet=result["snippet"],
                    url=result["url"],
                    result_type=result["result_type"],
                    relevance_score=float(result["relevance_score"]),
                    rank=int(result["rank"]),
                    freshness_timestamp=str(result.get("freshness_timestamp", "")),
                    freshness_score=float(result.get("freshness_score", 0.0)),
                )
                for result in raw_results
            )
        except KeyError as exc:
            raise RuntimeError(
                f"Search target returned an invalid response payload: missing `{exc.args[0]}`."
            ) from exc
        except (TypeError, ValueError) as exc:
            raise RuntimeError(
                "Search target returned an invalid response payload: result fields could not be normalized."
            ) from exc
        return SearchResponse(request_id=request_id, results=results)

    def _request_json(self, req: request.Request, *, purpose: str) -> dict:
        body = request_json(req, timeout=self.timeout_seconds, purpose=purpose)
        if not isinstance(body, dict):
            raise RuntimeError(
                f"Search target returned an invalid JSON payload: {self.base_url}."
            )
        return body
