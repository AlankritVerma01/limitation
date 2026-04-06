"""HTTP adapter for recommender systems exposed through a simple JSON API."""

from __future__ import annotations

import json
from dataclasses import asdict
from urllib import request
from urllib.error import HTTPError, URLError

from ..schema import (
    AdapterRequest,
    AdapterResponse,
    AgentState,
    Observation,
    ScenarioConfig,
    Slate,
    SlateItem,
)


class HttpRecommenderAdapter:
    """Calls a recommender endpoint and normalizes its response."""

    def __init__(self, base_url: str, timeout_seconds: float = 2.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

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
        body = self._request_json(req)
        adapter_response = self._normalize_response(body)
        return Slate(
            slate_id=f"{scenario_config.scenario_id or scenario_config.name}-{agent_state.agent_id}-{observation.step_index}",
            step_index=observation.step_index,
            items=adapter_response.items,
        )

    def get_service_metadata(self) -> dict[str, str | int | float]:
        req = request.Request(
            f"{self.base_url}/metadata",
            headers={"Content-Type": "application/json"},
            method="GET",
        )
        try:
            body = self._request_json(req)
        except (HTTPError, URLError, TimeoutError, ValueError):
            return {}
        return {
            key: value
            for key, value in body.items()
            if isinstance(value, str | int | float)
        }

    def _normalize_response(self, payload: dict) -> AdapterResponse:
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
            for item in payload["items"]
        )
        return AdapterResponse(request_id=payload["request_id"], items=items)

    def _request_json(self, req: request.Request) -> dict:
        with request.urlopen(req, timeout=self.timeout_seconds) as response:
            return json.loads(response.read().decode("utf-8"))
