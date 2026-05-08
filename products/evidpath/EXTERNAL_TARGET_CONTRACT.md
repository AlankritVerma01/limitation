# External Target Contract

This document describes the native HTTP integration contract for recommender
systems.

## What The Customer Provides

The simplest service integration is an external HTTP target that already speaks
Evidpath's native request and response contract.

A customer typically provides:

- a reachable recommender base URL
- the three supported endpoints listed below
- returned item metadata in the expected shape
- any deployment details needed to keep that service reachable

This path does **not** require:

- dataset handoff into the harness
- raw model files
- direct model loading inside the harness
- auth support

If your service uses a different HTTP shape, use the schema-mapped driver
instead of changing your service. It supports dot-path extraction, a small
JSONPath subset for `items_path`, and optional Python request/response
transforms. If your recommender is local Python code, use
`evidpath.audit(callable=...)` or the in-process driver.

The repo includes examples for the native HTTP contract, schema-mapped HTTP
targets, in-process Python callables, and framework adapters under
`examples/`.

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
- schema-mapped target = existing customer HTTP shape
- in-process target = local Python callable/class path
- reference target = product-owned local/demo path
- mock target = internal-only fixture/debug path

The native external target is the smallest service integration when your API
can speak this contract. Schema-mapped and in-process targets cover teams that
already have a different HTTP shape or local Python model code. The reference
target exists to make demos, onboarding, CI, and local proof runs easy. The
mock target exists only for narrow internal tests and debug loops.
