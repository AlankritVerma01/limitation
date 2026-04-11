# Hugging Face External Recommender Service

This example proves the external-target path against a real third-party model
source instead of only the in-repo handcrafted recommender service.

It is:

- out of process
- HTTP served
- backed by a Hugging Face embedding model
- compatible with the same `--target-url` flow a customer would use

It is not:

- harness-core model loading
- a production deployment stack
- the local reference target

## Startup

Install the HF example dependencies first:

```bash
.venv/bin/python -m pip install -e 'products/interaction-harness[dev,hf-example]'
```

Start the semantic mode:

```bash
.venv/bin/python products/interaction-harness/examples/hf_recommender_service/run.py \
  --model-kind hf-semantic \
  --port 8061
```

Start the popularity-blend mode:

```bash
.venv/bin/python products/interaction-harness/examples/hf_recommender_service/run.py \
  --model-kind hf-semantic-popularity-blend \
  --port 8062
```

The first run reuses the shared MovieLens 100K artifact builder used by the
other example recommender service and downloads the HF model weights through the
normal Hugging Face cache if needed.

## Example Harness Usage

```bash
.venv/bin/python -m interaction_harness check-target --domain recommender \
  --target-url http://127.0.0.1:8061
```

```bash
.venv/bin/python -m interaction_harness run-swarm --domain recommender \
  --target-url http://127.0.0.1:8061 \
  --brief "test trust collapse and novelty balance for impatient exploratory users" \
  --generation-mode fixture \
  --output-dir products/interaction-harness/output/hf-run-swarm-demo
```

```bash
.venv/bin/python -m interaction_harness compare --domain recommender \
  --baseline-url http://127.0.0.1:8061 \
  --candidate-url http://127.0.0.1:8062 \
  --baseline-label hf-semantic \
  --candidate-label hf-semantic-popularity-blend \
  --rerun-count 2 \
  --output-dir products/interaction-harness/output/hf-compare-demo
```
