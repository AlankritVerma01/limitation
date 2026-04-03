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

## Contents

- [artifacts/canonical](artifacts/canonical): official report, JSON, and chart bundle
- [docs/v1-product-spec.md](docs/v1-product-spec.md): locked product spec for the public tool
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

Or directly:

```bash
PYTHONPATH=studies/01-recommender-offline-eval/src .venv/bin/python -m recommender_offline_eval
```

Refresh the committed canonical bundle:

```bash
make canonical
```

## Notebook

From the repository root:

```bash
make notebook
```
