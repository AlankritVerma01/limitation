# recommender_schema_mapped_jsonpath

Demonstrates onboarding a recsys whose `/v1/predict` endpoint returns a
multi-bucket response shape. JSONPath selects the `main` bucket only.

```bash
# Terminal 1: example server
PYTHONPATH=products/evidpath uv run --locked python -m examples.recommender_schema_mapped_jsonpath.server --port 8073

# Terminal 2: audit
PYTHONPATH=products/evidpath uv run --locked evidpath audit \
    --driver-config-path products/evidpath/examples/recommender_schema_mapped_jsonpath/driver_config.json \
    --seed 0
```

The audit calls the example server, picks items only from the `main` bucket
via `$.buckets[?(@.name=='main')].items[*]`, and ignores the fallback bucket.
