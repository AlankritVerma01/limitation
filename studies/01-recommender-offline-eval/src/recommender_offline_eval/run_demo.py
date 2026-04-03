"""Thin orchestration layer for config -> evaluation -> artifacts."""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np

from .canonical import CANONICAL_RUN_CONFIG
from .config import EvaluationConfig, load_evaluation_config
from .data import build_dataset
from .evaluator import evaluate_models
from .model_registry import build_model
from .paths import (
    DEFAULT_CANONICAL_ARTIFACTS_DIR,
    DEFAULT_DATA_DIR,
    DEFAULT_OUTPUT_DIR,
)
from .report import generate_report


def _fit_model(model, dataset: dict) -> object:
    return model.fit(
        train_ratings=dataset["train_ratings"],
        items=dataset["items"],
        user_profiles=dataset["user_profiles"],
        item_feature_columns=dataset["item_feature_columns"],
    )


def _resolved_output_dir(
    config: EvaluationConfig,
    output_dir: str | Path | None,
) -> str | Path:
    return output_dir or config.output_dir or DEFAULT_OUTPUT_DIR


def run_evaluation(
    config: EvaluationConfig,
    *,
    data_dir: str | Path = DEFAULT_DATA_DIR,
    output_dir: str | Path | None = None,
) -> dict:
    np.random.seed(config.seed)
    dataset = build_dataset(
        dataset_spec=config.dataset,
        config=config,
        data_dir=data_dir,
    )

    baseline_model = _fit_model(build_model(config.baseline_model), dataset)
    candidate_model = _fit_model(build_model(config.candidate_model), dataset)
    models = {
        "Model A": baseline_model,
        "Model B": candidate_model,
    }
    model_specs = {
        "Model A": config.baseline_model.as_dict(),
        "Model B": config.candidate_model.as_dict(),
    }

    metrics = evaluate_models(
        models=models,
        dataset=dataset,
        model_specs=model_specs,
        k=config.top_k,
        session_steps=config.session_steps,
        slate_size=config.slate_size,
        choice_pool=config.choice_pool,
    )

    report_artifacts = generate_report(
        metrics=metrics,
        output_dir=_resolved_output_dir(config, output_dir),
        config=config,
    )

    return {
        "dataset": dataset,
        "metrics": metrics,
        "config": config.as_dict(),
        **report_artifacts,
    }


def run_demo(
    data_dir: str | Path = DEFAULT_DATA_DIR,
    output_dir: str | Path = DEFAULT_OUTPUT_DIR,
    config: EvaluationConfig = CANONICAL_RUN_CONFIG,
) -> dict:
    """Backward-compatible alias for the original demo entrypoint."""
    return run_evaluation(config, data_dir=data_dir, output_dir=output_dir)


def run_canonical_demo(
    output_dir: str | Path = DEFAULT_OUTPUT_DIR,
    data_dir: str | Path = DEFAULT_DATA_DIR,
) -> dict:
    return run_evaluation(
        CANONICAL_RUN_CONFIG,
        output_dir=output_dir,
        data_dir=data_dir,
    )


def refresh_canonical_artifacts(
    output_dir: str | Path = DEFAULT_CANONICAL_ARTIFACTS_DIR,
    data_dir: str | Path = DEFAULT_DATA_DIR,
) -> dict:
    return run_canonical_demo(output_dir=output_dir, data_dir=data_dir)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the recommender behavior evaluation tool."
    )
    parser.add_argument(
        "--config",
        help="Path to a JSON evaluation config. If omitted, the canonical MovieLens demo is used.",
    )
    parser.add_argument(
        "--data-dir",
        default=str(DEFAULT_DATA_DIR),
        help="Directory that contains or will download MovieLens 100K data.",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Optional override for the output artifact directory.",
    )
    parser.add_argument(
        "--refresh-canonical",
        action="store_true",
        help="Write the committed canonical artifact bundle instead of a local output directory.",
    )
    return parser


def main() -> None:
    args = _build_parser().parse_args()
    if args.refresh_canonical:
        result = refresh_canonical_artifacts(
            output_dir=DEFAULT_CANONICAL_ARTIFACTS_DIR,
            data_dir=args.data_dir,
        )
    elif args.config:
        config = load_evaluation_config(args.config)
        result = run_evaluation(
            config,
            data_dir=args.data_dir,
            output_dir=args.output_dir,
        )
    else:
        resolved_output_dir = args.output_dir or DEFAULT_OUTPUT_DIR
        result = run_canonical_demo(
            output_dir=resolved_output_dir,
            data_dir=args.data_dir,
        )
    print(f"Report: {result['report_path']}")
    print(f"Metrics: {result['metrics_path']}")
    print(f"Chart: {result['chart_path']}")


if __name__ == "__main__":
    main()
