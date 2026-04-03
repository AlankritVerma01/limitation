from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np

from .canonical import CANONICAL_RUN_CONFIG
from .data import build_dataset
from .evaluator import evaluate_models
from .paths import (
    DEFAULT_CANONICAL_ARTIFACTS_DIR,
    DEFAULT_DATA_DIR,
    DEFAULT_OUTPUT_DIR,
)
from .recommenders import GenreProfileRecommender, PopularityRecommender
from .report import generate_report


def run_demo(
    data_dir: str | Path = DEFAULT_DATA_DIR,
    output_dir: str | Path = DEFAULT_OUTPUT_DIR,
    config=CANONICAL_RUN_CONFIG,
) -> dict:
    np.random.seed(config.seed)
    dataset = build_dataset(data_dir=data_dir)

    model_a = PopularityRecommender().fit(
        train_ratings=dataset["train_ratings"],
        items=dataset["items"],
        user_profiles=dataset["user_profiles"],
    )
    model_b = GenreProfileRecommender(
        popularity_weight=config.popularity_weight,
        diversity_weight=config.diversity_weight,
        shortlist_size=config.shortlist_size,
    ).fit(
        train_ratings=dataset["train_ratings"],
        items=dataset["items"],
        user_profiles=dataset["user_profiles"],
    )

    models = {
        model_a.name: model_a,
        model_b.name: model_b,
    }
    metrics = evaluate_models(
        models=models,
        dataset=dataset,
        k=config.top_k,
        session_steps=config.session_steps,
        slate_size=config.slate_size,
        choice_pool=config.choice_pool,
    )
    report_artifacts = generate_report(
        metrics=metrics,
        output_dir=output_dir,
        config=config,
    )

    return {
        "dataset": dataset,
        "metrics": metrics,
        "config": config.as_dict(),
        **report_artifacts,
    }


def run_canonical_demo(
    output_dir: str | Path = DEFAULT_OUTPUT_DIR,
    data_dir: str | Path = DEFAULT_DATA_DIR,
) -> dict:
    return run_demo(data_dir=data_dir, output_dir=output_dir, config=CANONICAL_RUN_CONFIG)


def refresh_canonical_artifacts(
    output_dir: str | Path = DEFAULT_CANONICAL_ARTIFACTS_DIR,
    data_dir: str | Path = DEFAULT_DATA_DIR,
) -> dict:
    return run_canonical_demo(output_dir=output_dir, data_dir=data_dir)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the official MovieLens recommender behavior evaluation demo."
    )
    parser.add_argument(
        "--data-dir",
        default=str(DEFAULT_DATA_DIR),
        help="Directory that contains or will download MovieLens 100K data.",
    )
    parser.add_argument(
        "--output-dir",
        default=str(DEFAULT_OUTPUT_DIR),
        help="Directory for generated report, JSON, and chart artifacts.",
    )
    parser.add_argument(
        "--refresh-canonical",
        action="store_true",
        help="Write the committed canonical artifact bundle instead of the local output directory.",
    )
    return parser


def main() -> None:
    args = _build_parser().parse_args()
    if args.refresh_canonical:
        result = refresh_canonical_artifacts(
            output_dir=DEFAULT_CANONICAL_ARTIFACTS_DIR,
            data_dir=args.data_dir,
        )
    else:
        result = run_canonical_demo(output_dir=args.output_dir, data_dir=args.data_dir)
    print(f"Report: {result['report_path']}")
    print(f"Metrics: {result['metrics_path']}")
    print(f"Chart: {result['chart_path']}")


if __name__ == "__main__":
    main()
