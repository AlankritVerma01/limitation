# External Target Contract: Search

This document describes the native HTTP integration contract for search
rankers.

## Supported Endpoints

- `GET /health`
- `GET /metadata`
- `POST /search`

## Request Shape

`POST /search`

```json
{
  "request_id": "agent-1-time-sensitive-query-0",
  "query": "current weather alerts toronto",
  "user_id": "agent-1",
  "session_id": "time-sensitive-query-agent-1",
  "user_context": {
    "archetype_label": "Current-info searcher",
    "preferred_genres": ["news", "article"],
    "history_item_ids": [],
    "clicked_item_ids": []
  },
  "locale": "",
  "freshness_window_days": null,
  "max_results": 10
}
```

## Response Shape

```json
{
  "request_id": "agent-1-time-sensitive-query-0",
  "results": [
    {
      "result_id": "doc-weather-alerts",
      "title": "Live Weather Alerts for Toronto",
      "snippet": "Current weather warnings, short-term radar, and emergency updates for Toronto.",
      "url": "https://example.com/weather/toronto/alerts",
      "result_type": "news",
      "relevance_score": 0.97,
      "rank": 1,
      "freshness_timestamp": "2026-05-06T16:30:00Z",
      "freshness_score": 0.97
    }
  ]
}
```

Required result fields:

- `result_id`
- `title`
- `snippet`
- `url`
- `result_type`
- `relevance_score`
- `rank`

Optional but recommended:

- `freshness_timestamp`
- `freshness_score`

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
- `document_count`

## Preflight Validation

```bash
uv run python -m evidpath check-target --domain search \
  --target-url http://127.0.0.1:8051
```

## Existing HTTP Shapes

If your service does not speak the native `/search` contract, use the
schema-mapped HTTP driver with `driver_kind: "http_schema_mapped"`. The search
schema-mapped driver supports templated request bodies and URL paths, dot-path
response extraction, and safe percent-encoding for templated URL values.

If your ranker is local Python code, use the `in_process` driver and return a
`SearchResponse`.
