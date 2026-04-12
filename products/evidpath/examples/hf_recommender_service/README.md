# Hugging Face External Recommender Service

This example shows the same external-target flow using a Hugging Face-backed
model instead of only the in-repo handcrafted recommender examples.

Use it when:

- you want a more realistic third-party model example
- you want to prove that Evidpath works with an external-style service boundary
- you want a local example that behaves differently from the simpler demo service

It is not:

- the built-in reference target
- a production deployment template
- a replacement for your own service

## Start The Service

Install the extra dependencies first:

```bash
.venv/bin/python -m pip install -e 'products/evidpath[dev,hf-example]'
```

Start the semantic mode:

```bash
.venv/bin/python products/evidpath/examples/hf_recommender_service/run.py \
  --model-kind hf-semantic \
  --port 8061
```

Start the popularity-blend mode:

```bash
.venv/bin/python products/evidpath/examples/hf_recommender_service/run.py \
  --model-kind hf-semantic-popularity-blend \
  --port 8062
```

The first run reuses the shared MovieLens-based artifact builder and downloads
the Hugging Face model weights if needed.

## Test It With Evidpath

Check the first service:

```bash
.venv/bin/python -m evidpath check-target --domain recommender \
  --target-url http://127.0.0.1:8061
```

Run a brief-driven swarm:

```bash
.venv/bin/python -m evidpath run-swarm --domain recommender \
  --target-url http://127.0.0.1:8061 \
  --brief "test trust collapse and novelty balance for impatient exploratory users" \
  --generation-mode fixture \
  --output-dir products/evidpath/output/hf-run-swarm-demo
```

Compare the two service modes:

```bash
.venv/bin/python -m evidpath compare --domain recommender \
  --baseline-url http://127.0.0.1:8061 \
  --candidate-url http://127.0.0.1:8062 \
  --baseline-label hf-semantic \
  --candidate-label hf-semantic-popularity-blend \
  --rerun-count 2 \
  --output-dir products/evidpath/output/hf-compare-demo
```

## What To Do Next

Once the service is up:

1. run `check-target`
2. run a single `audit` or a broader `run-swarm`
3. use `compare` when you want to inspect change between two versions

If you want the simpler local external-target proof path first, start with
[../recommender_http_service/README.md](../recommender_http_service/README.md).
