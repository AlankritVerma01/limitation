# Study 01: Recommender Offline Eval

This project is a small, reproducible case study for a larger point: aggregate offline ranking metrics are useful, but they do not fully capture recommender quality when behavior unfolds over interaction trajectories.

## Contents

- [docs/article-draft.md](docs/article-draft.md): article draft
- [docs/article-outline.md](docs/article-outline.md): article structure and notes
- [docs/project-brief.md](docs/project-brief.md): original brief
- [docs/README.md](docs/README.md): writing guide
- [notebooks/offline_eval_demo.ipynb](notebooks/offline_eval_demo.ipynb): notebook walkthrough
- [src/recommender_offline_eval](src/recommender_offline_eval): Python package for the demo

Local-only directories:

- `data/`: MovieLens dataset download/extract location
- `output/`: generated report, metrics, and chart

## Run

From the repository root:

```bash
make run
```

Or directly:

```bash
PYTHONPATH=studies/01-recommender-offline-eval/src .venv/bin/python -m recommender_offline_eval
```

## Notebook

From the repository root:

```bash
make notebook
```
