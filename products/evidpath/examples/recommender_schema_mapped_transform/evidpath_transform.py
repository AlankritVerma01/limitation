"""User-supplied request transform for the asymmetric example."""

from __future__ import annotations

from evidpath.schema import AdapterRequest


def transform_request(adapter_request: AdapterRequest) -> dict:
    """Map evidpath's flat history into an event array."""
    return {
        "user_id": adapter_request.agent_id,
        "events": [
            {"type": "view", "item": item, "step": index}
            for index, item in enumerate(adapter_request.history_item_ids)
        ],
        "n": 5,
    }
