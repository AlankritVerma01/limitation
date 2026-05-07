# External Target Contract

This document describes the v1 customer integration path for recommender
systems.

## What The Customer Provides

In v1, the real customer path is an external HTTP target.

A customer typically provides:

- a reachable recommender base URL
- the three supported endpoints listed below
- returned item metadata in the expected shape
- any deployment details needed to keep that service reachable

This first pass does **not** require:

- dataset handoff into the harness
- raw model files
- direct model loading inside the harness
- auth support

If a team already has a served recommender, the harness integrates at that
service boundary. If a team only has model code or artifacts, the recommended
path is to wrap them behind this HTTP contract rather than teaching the harness
to load them directly. The repo includes both a basic wrapper example and a
Hugging Face-backed wrapper example under `examples/`.

## Supported Endpoints

- `GET /health`
- `GET /metadata`
- `POST /recommendations`

## Request Shape

`POST /recommendations`

```json
{
  "request_id": "agent-7-returning-user-home-feed-0",
  "agent_id": "agent-7",
  "scenario_name": "returning-user-home-feed",
  "scenario_profile": "returning-user-home-feed",
  "step_index": 0,
  "history_depth": 4,
  "history_item_ids": ["50", "181", "172", "174"],
  "recent_exposure_ids": ["50"],
  "preferred_genres": ["action", "thriller"]
}
```

## Response Shape

```json
{
  "request_id": "agent-7-returning-user-home-feed-0",
  "items": [
    {
      "item_id": "181",
      "title": "Return of the Jedi (1983)",
      "genre": "action",
      "score": 0.982,
      "rank": 1,
      "popularity": 0.91,
      "novelty": 0.09
    }
  ]
}
```

The harness expects:

- `request_id`
- ordered `items`
- each item to include:
  - `item_id`
  - `title`
  - `genre`
  - `score`
  - `rank`
  - `popularity`
  - `novelty`

## Metadata Shape

`GET /metadata` should return stable string/int/float fields where available.

Recommended fields:

- `service_kind`
- `backend_name`
- `dataset`
- `data_source`
- `model_kind`
- `model_id`
- `artifact_id`
- `item_count`

## Preflight Validation

Before running a full audit, use the public CLI to validate reachability,
health, metadata, and one lightweight recommendation probe:

```bash
uv run python -m evidpath check-target --domain recommender \
  --target-url http://127.0.0.1:8051
```

## Mental Model

- external target = real customer path
- reference target = product-owned local/demo path
- mock target = internal-only fixture/debug path

The harness uses the same adapter flow for both, but the external target is the
main path for real usage. The reference target exists to make demos,
onboarding, CI, and local proof runs easy. The mock target exists only for
narrow internal tests and debug loops.
