# Example External Recommender Service

This example service exists to prove the real customer path for Interaction
Harness.

It is:

- out of process
- HTTP served
- backed by real model artifacts
- usable through the same `--target-url` flow a customer would use
- a template for teams that have model code but do not yet have a service

It is not:

- the harness reference target
- a harness-owned inference helper
- a production deployment stack

## Startup

Install the harness dev dependencies first:

```bash
.venv/bin/python -m pip install -e products/interaction-harness[dev]
```

Start the popularity model:

```bash
.venv/bin/python products/interaction-harness/examples/recommender_http_service/run.py \
  --model-kind popularity \
  --port 8051
```

Start the item-item CF model:

```bash
.venv/bin/python products/interaction-harness/examples/recommender_http_service/run.py \
  --model-kind item-item-cf \
  --port 8052
```

Start the genre-history blend model:

```bash
.venv/bin/python products/interaction-harness/examples/recommender_http_service/run.py \
  --model-kind genre-history-blend \
  --port 8053
```

The first run builds lightweight example artifacts from MovieLens 100K. If the
repo copy of MovieLens 100K is not present, the service downloads it
automatically from the official GroupLens dataset URL.

If you want to point at your own checked-out MovieLens data explicitly:

```bash
.venv/bin/python products/interaction-harness/examples/recommender_http_service/run.py \
  --model-kind popularity \
  --data-dir /path/to/ml-100k \
  --port 8051
```

If you prefer to manage the app server yourself, the package-style Uvicorn path
still works:

```bash
IH_EXAMPLE_MODEL_KIND=popularity \
.venv/bin/python -m uvicorn recommender_http_service.app:create_app --factory \
  --app-dir products/interaction-harness/examples \
  --host 127.0.0.1 --port 8051
```

## Endpoints

- `GET /health`
- `GET /metadata`
- `POST /recommendations`

## Example Harness Usage

Check one target before a full run:

```bash
.venv/bin/python -m interaction_harness check-target --domain recommender \
  --target-url http://127.0.0.1:8051
```

Audit one external target:

```bash
.venv/bin/python -m interaction_harness audit --domain recommender \
  --target-url http://127.0.0.1:8051 \
  --scenario returning-user-home-feed \
  --seed 7 \
  --output-dir products/interaction-harness/output/external-audit-demo
```

Compare two external targets:

```bash
.venv/bin/python -m interaction_harness compare --domain recommender \
  --baseline-url http://127.0.0.1:8051 \
  --candidate-url http://127.0.0.1:8052 \
  --baseline-label popularity \
  --candidate-label item-item-cf \
  --rerun-count 2 \
  --output-dir products/interaction-harness/output/external-compare-demo
```

## Wrapper Template

If your team already has recommender logic but not an HTTP service yet, start
from [wrapper_template.py](./wrapper_template.py). It shows the minimal service
shape the harness expects while keeping model loading and scoring in your own
service layer.
