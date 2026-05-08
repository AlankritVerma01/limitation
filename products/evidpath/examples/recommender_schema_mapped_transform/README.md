# recommender_schema_mapped_transform

Demonstrates the escape hatch: the user's API expects an event-derived
request shape that flat `${field}` substitution can't produce. The
`transform_request` function in `evidpath_transform.py` builds the body in
Python; the response stays declarative.

```bash
# Terminal 1: example server
PYTHONPATH=products/evidpath uv run --locked python -m examples.recommender_schema_mapped_transform.server --port 8074

# Terminal 2: audit
PYTHONPATH=products/evidpath uv run --locked evidpath audit \
    --driver-config-path products/evidpath/examples/recommender_schema_mapped_transform/driver_config.json \
    --seed 0
```
