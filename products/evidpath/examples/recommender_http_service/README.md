# Example External Recommender Service

This example gives you a local recommender service that behaves like a real
external target for Evidpath.

Use it when:

- you want to try Evidpath without wiring your own service yet
- you want to prove the external-target flow end to end
- you have model logic but not a production service yet

It is not:

- the built-in reference target
- a production deployment template
- a replacement for your own service layer

## Start The Service

Install the example dependencies first:

```bash
.venv/bin/python -m pip install -e products/evidpath[dev]
```

Start a popularity-based service:

```bash
.venv/bin/python products/evidpath/examples/recommender_http_service/run.py \
  --model-kind popularity \
  --port 8051
```

Start an item-item CF service:

```bash
.venv/bin/python products/evidpath/examples/recommender_http_service/run.py \
  --model-kind item-item-cf \
  --port 8052
```

Start a genre-history blend service:

```bash
.venv/bin/python products/evidpath/examples/recommender_http_service/run.py \
  --model-kind genre-history-blend \
  --port 8053
```

The first run builds lightweight example artifacts from MovieLens 100K. If the
repo copy is not present, the service downloads it automatically.

If you want to point at your own checked-out MovieLens data:

```bash
.venv/bin/python products/evidpath/examples/recommender_http_service/run.py \
  --model-kind popularity \
  --data-dir /path/to/ml-100k \
  --port 8051
```

## What The Service Exposes

- `GET /health`
- `GET /metadata`
- `POST /recommendations`

## Test It With Evidpath

Check the service first:

```bash
.venv/bin/python -m evidpath check-target --domain recommender \
  --target-url http://127.0.0.1:8051
```

Run one audit:

```bash
.venv/bin/python -m evidpath audit --domain recommender \
  --target-url http://127.0.0.1:8051 \
  --scenario returning-user-home-feed \
  --seed 7 \
  --output-dir products/evidpath/output/external-audit-demo
```

Compare two service versions:

```bash
.venv/bin/python -m evidpath compare --domain recommender \
  --baseline-url http://127.0.0.1:8051 \
  --candidate-url http://127.0.0.1:8052 \
  --baseline-label popularity \
  --candidate-label item-item-cf \
  --rerun-count 2 \
  --output-dir products/evidpath/output/external-compare-demo
```

## What To Do Next

After the service is running and `check-target` passes, the normal next steps
are:

1. run `audit`
2. open `report.md` and `results.json`
3. run `compare` when you want a baseline-vs-candidate decision workflow

If your team already has recommender logic but not an HTTP service yet, start
from [wrapper_template.py](./wrapper_template.py). It shows the smallest
service shape Evidpath expects while keeping model loading and scoring in your
own code.
