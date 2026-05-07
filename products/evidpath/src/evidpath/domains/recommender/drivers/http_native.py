"""Native HTTP driver for the recommender domain."""

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
    SlateItem,
)
from ._config import HttpNativeDriverConfig


class HttpNativeRecommenderDriver:
    """Calls a recommender endpoint and normalizes its response."""

    def __init__(self, config: HttpNativeDriverConfig) -> None:
        self.base_url = config.base_url.rstrip("/")
        self.timeout_seconds = config.timeout_seconds

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
        payload = json.dumps(asdict(adapter_request)).encode("utf-8")
        req = request.Request(
            f"{self.base_url}/recommendations",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        body = self._request_json(req, purpose="recommendation request")
        adapter_response = self._normalize_response(body)
        return Slate(
            slate_id=f"{scenario_config.scenario_id or scenario_config.name}-{agent_state.agent_id}-{observation.step_index}",
            step_index=observation.step_index,
            items=adapter_response.items,
        )

    def get_service_metadata(self) -> dict[str, str | int | float]:
        return self._get_service_metadata(strict=False)

    def get_service_metadata_strict(self) -> dict[str, str | int | float]:
        """Fetch and validate the metadata endpoint strictly for target checks."""
        return self._get_service_metadata(strict=True)

    def check_health(self) -> dict[str, str | int | float]:
        """Validate the health endpoint for target onboarding and preflight checks."""
        req = request.Request(
            f"{self.base_url}/health",
            headers={"Content-Type": "application/json"},
            method="GET",
        )
        body = self._request_json(req, purpose="health check")
        if not isinstance(body, dict):
            raise RuntimeError(
                f"Recommender target returned an invalid health payload: {self.base_url}."
            )
        status = body.get("status")
        if not isinstance(status, str) or status.lower() != "ok":
            raise RuntimeError(
                f"Recommender target health check failed: expected `status=ok` from {self.base_url}."
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
                f"Recommender target returned an invalid metadata payload: {self.base_url}."
            )
        return {
            key: value
            for key, value in body.items()
            if isinstance(value, (str, int, float))
        }

    def _normalize_response(self, payload: dict) -> AdapterResponse:
        try:
            request_id = payload["request_id"]
            raw_items = payload["items"]
            items = tuple(
                SlateItem(
                    item_id=item["item_id"],
                    title=item["title"],
                    genre=item["genre"],
                    score=float(item["score"]),
                    rank=int(item["rank"]),
                    popularity=float(item["popularity"]),
                    novelty=float(item["novelty"]),
                )
                for item in raw_items
            )
        except KeyError as exc:
            raise RuntimeError(
                f"Recommender target returned an invalid response payload: missing `{exc.args[0]}`."
            ) from exc
        except (TypeError, ValueError) as exc:
            raise RuntimeError(
                "Recommender target returned an invalid response payload: item fields could not be normalized."
            ) from exc
        return AdapterResponse(request_id=request_id, items=items)

    def _request_json(self, req: request.Request, *, purpose: str) -> dict:
        from ._http import request_json

        body = request_json(req, timeout=self.timeout_seconds, purpose=purpose)
        if not isinstance(body, dict):
            raise RuntimeError(
                f"Recommender target returned an invalid JSON payload: {self.base_url}."
            )
        return body
