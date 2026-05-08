# Evidpath

[Source](https://github.com/NDETERMINA/limitation) |
[Full docs](https://github.com/NDETERMINA/limitation/tree/main/products/evidpath) |
[Releases](https://github.com/NDETERMINA/limitation/releases) |
[Issues](https://github.com/NDETERMINA/limitation/issues)

Evidpath helps teams check recommender and search rankers before launch. Point
it at an endpoint, run an audit, and open a report that shows what happened.

## Install

```bash
python -m pip install evidpath
```

Requirements:

- Python `3.11+`

## First Run

Check that your recommender endpoint responds in the expected shape:

```bash
evidpath check-target --domain recommender --target-url http://127.0.0.1:8051
```

Run one audit:

```bash
evidpath audit --domain recommender --target-url http://127.0.0.1:8051 --scenario returning-user-home-feed --seed 7
```

For search rankers, use `--domain search`:

```bash
evidpath audit --domain search --scenario navigational-query --seed 7
```

By default, Evidpath writes an `evidpath-output/` folder in your current
directory. The most useful files are:

- `report.md`
- `results.json`
- `traces.jsonl`

Compare two versions before launch:

```bash
evidpath compare --domain recommender --baseline-url http://127.0.0.1:8051 --candidate-url http://127.0.0.1:8052 --rerun-count 2
```

## What You Need

- a recommender or search HTTP endpoint, or a Python callable/class
- for native HTTP targets, the request and response shape described in the
  recommender or search external target contract

If your HTTP service has a different shape, use a schema-mapped driver config
with dot paths, JSONPath `items_path`, or small Python transforms. If your
ranker is local Python code, use `evidpath.audit(callable=predict, ...)`.

Optional extras provide adapters for common in-process objects:

- `evidpath[huggingface]`
- `evidpath[mlflow]`
- `evidpath[sklearn]`

The reference target remains available in the repo for demos and local
onboarding.

Provider credentials are only needed for AI-backed generation and advisory
semantic features. A normal `check-target`, `audit`, or `compare` run does not
need an API key.

## Links

- Full product docs: https://github.com/NDETERMINA/limitation/tree/main/products/evidpath
- Demo guide: https://github.com/NDETERMINA/limitation/blob/main/products/evidpath/DEMO.md
- Releases: https://github.com/NDETERMINA/limitation/releases
- Issues: https://github.com/NDETERMINA/limitation/issues
