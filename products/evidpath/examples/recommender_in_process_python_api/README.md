# recommender_in_process_python_api

Demonstrates the Python-API onboarding path. No HTTP, no JSON config:
pass your `predict` function to `audit()` and get a `RunResult` back.

```bash
PYTHONPATH=products/evidpath uv run --locked python -m examples.recommender_in_process_python_api.run \
    --seed 0 --output-dir ./run-output
```

To use this with your own recommender, replace `predict` with any callable
that takes an `AdapterRequest` and returns an `AdapterResponse`. Or pass a
class instance with a `.predict()` method directly.
