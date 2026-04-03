# Study 01: Recommender Behavior QA

This study is the public v1 of the repository: a small, reproducible recommender evaluation tool that compares a baseline model against a candidate model and highlights what aggregate offline metrics miss.

It is designed to help recommender, ranking, and ML engineers answer a pre-launch question:

> Should I trust this new recommender before I ship it?

The study keeps the scope intentionally narrow:

- MovieLens as the first public dataset
- exactly 2 models: baseline vs candidate
- fixed user buckets
- short trajectory diagnostics
- one clean comparison report

The canonical Phase 1 result is committed under `artifacts/canonical/` so the public proof can be read without rerunning the pipeline.

This study can now also run config-driven comparisons on external CSV datasets while keeping the same report, bucket, and metric structure.

## Code Map

- `src/recommender_offline_eval/config.py`: JSON config loading and validation
- `src/recommender_offline_eval/data.py`: MovieLens and CSV dataset loading, filtering, and split prep
- `src/recommender_offline_eval/model_registry.py`: built-in model lookup from config
- `src/recommender_offline_eval/evaluator.py`: offline metrics, bucket metrics, and trace selection
- `src/recommender_offline_eval/report.py`: markdown, JSON, and chart artifact generation
- `src/recommender_offline_eval/run_demo.py`: thin orchestration entrypoints and CLI

## Contents

- [artifacts/canonical](artifacts/canonical): official report, JSON, and chart bundle
- [examples/canonical_run.json](examples/canonical_run.json): JSON config for the official MovieLens run
- [examples/custom_csv_run.json](examples/custom_csv_run.json): JSON config for a custom CSV dataset run
- [docs/v1-product-spec.md](docs/v1-product-spec.md): locked product spec for the public tool
- [docs/dataset-schema.md](docs/dataset-schema.md): CSV dataset contract for custom runs
- [docs/article-draft.md](docs/article-draft.md): article draft
- [docs/article-outline.md](docs/article-outline.md): article structure and notes
- [docs/project-brief.md](docs/project-brief.md): original brief
- [docs/README.md](docs/README.md): writing guide
- [notebooks/offline_eval_demo.ipynb](notebooks/offline_eval_demo.ipynb): notebook walkthrough
- [src/recommender_offline_eval](src/recommender_offline_eval): Python package for the demo

Local-only directories:

- `data/`: MovieLens dataset download/extract location
- `output/`: local generated report, metrics, and chart scratch space

## What The Run Should Show

Each run should make it easy to see:

- who wins on Recall@10 and NDCG@10
- which user buckets improve or regress
- whether the candidate is more novel, repetitive, or head-heavy
- where aggregate metrics hide important tradeoffs
- what a few short example trajectories look like

## Run

From the repository root:

```bash
make run
```

With a config file:

```bash
make run CONFIG=studies/01-recommender-offline-eval/examples/custom_csv_run.json
```

Or directly:

```bash
PYTHONPATH=studies/01-recommender-offline-eval/src .venv/bin/python -m recommender_offline_eval
```

Refresh the committed canonical bundle:

```bash
make canonical
```

Custom dataset contract:

- `interactions.csv`: `user_id`, `item_id`, `rating`, `timestamp`
- `items.csv`: `item_id`, `title`, and optional numeric or boolean feature columns

`genre_profile` requires item feature columns. Popularity-only runs do not.

## Notebook

From the repository root:

```bash
make notebook
```
