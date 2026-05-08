# recommender_huggingface_inproc

Demonstrates wrapping a Hugging Face Pipeline with
`evidpath.adapters.huggingface.wrap_pipeline` and auditing it in-process via
`evidpath.audit()`: no HTTP, no JSON config.

```bash
# Install the optional extra:
pip install evidpath[huggingface]

# Run the example:
PYTHONPATH=products/evidpath uv run --locked --extra huggingface python -m examples.recommender_huggingface_inproc.run \
    --seed 0 --output-dir ./run-output
```

The example uses a stub pipeline so it does not require downloading a model.
For real usage, replace `build_pipeline()` with a Transformers pipeline.

The same pattern works for MLflow pyfunc (`evidpath.adapters.mlflow.wrap_pyfunc`)
and scikit-learn classifiers (`evidpath.adapters.sklearn.wrap_classifier`).
