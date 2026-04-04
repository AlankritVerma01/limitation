# Study 01: Recommender Behavior QA

This study is the public v1 of the repository: a narrow recommender evaluation tool that compares a baseline model against a candidate model and highlights what aggregate offline metrics miss.

The public-facing landing page is the repository root [README](../../README.md). This study README is the developer and contributor companion.

## What Lives Here

- the frozen canonical MovieLens proof
- the config-driven run path for custom comparisons
- the code that loads datasets, builds models, evaluates them, and renders artifacts
- the writing and planning materials for the public narrative

## Code Map

- `src/recommender_offline_eval/config.py`: JSON config loading and validation
- `src/recommender_offline_eval/data.py`: MovieLens and CSV dataset loading, filtering, and split prep
- `src/recommender_offline_eval/model_registry.py`: built-in model lookup from config
- `src/recommender_offline_eval/evaluator.py`: offline metrics, bucket metrics, and trace selection
- `src/recommender_offline_eval/report.py`: markdown, JSON, and chart artifact generation
- `src/recommender_offline_eval/supporting_artifacts.py`: robustness note and launch-ready canonical support assets
- `src/recommender_offline_eval/run_demo.py`: thin orchestration entrypoints and CLI

## Canonical Proof Bundle

The public proof is committed under `artifacts/canonical/` so it can be read without rerunning the pipeline.

- `official_demo_report.md`: frozen canonical report
- `official_demo_results.json`: frozen canonical metrics
- `bucket_utility_comparison.svg`: reusable chart
- `offline_vs_bucket_story.svg`: shareable “what offline metrics missed” visual
- `canonical_result_snapshot.svg`: compact result + trust snapshot
- `robustness_summary.md`: medium-depth credibility note
- `robustness_results.json`: machine-readable robustness outputs

## Trust And Interpretation

Use the root README for the short public framing. For study work, keep these distinctions in mind:

- `Recall@10` and `NDCG@10` are standard offline ranking metrics on held-out positives.
- `Bucket utility`, `Novelty`, `Repetition`, and `Catalog concentration` are diagnostic proxies that help make tradeoffs visible.
- The four buckets are fixed v1 evaluation lenses, not claims about true user ontology.
- The canonical result is frozen; the robustness note is supporting evidence, not a second official benchmark.

## Run

From the repository root:

```bash
make run
```

With a custom config:

```bash
make run CONFIG=studies/01-recommender-offline-eval/examples/custom_csv_run.json
```

Refresh the committed canonical proof bundle:

```bash
make canonical
```

Open the notebook:

```bash
make notebook
```

## Dataset Contract

Custom dataset contract:

- `interactions.csv`: `user_id`, `item_id`, `rating`, `timestamp`
- `items.csv`: `item_id`, `title`, and optional numeric or boolean feature columns

`genre_profile` requires item feature columns. Popularity-only runs do not.

## Writing And Planning Docs

- [docs/v1-product-spec.md](docs/v1-product-spec.md): locked product spec
- [docs/dataset-schema.md](docs/dataset-schema.md): custom dataset contract
- [docs/README.md](docs/README.md): writing guide

## Local-Only Directories

- `data/`: MovieLens download and extract location
- `output/`: local generated scratch artifacts
- `docs-private/`: ignored local workspace for drafts, outreach notes, and blog planning
- `docs-private/`: ignored local workspace for drafts, notes, feedback packets, and blog prep
