from __future__ import annotations

from pathlib import Path

from .data import build_dataset
from .evaluator import evaluate_models
from .paths import DEFAULT_DATA_DIR, DEFAULT_OUTPUT_DIR
from .recommenders import GenreProfileRecommender, PopularityRecommender
from .report import generate_report


def run_demo(
    data_dir: str | Path = DEFAULT_DATA_DIR,
    output_dir: str | Path = DEFAULT_OUTPUT_DIR,
    popularity_weight: float = 0.25,
    top_k: int = 10,
) -> dict:
    dataset = build_dataset(data_dir=data_dir)

    model_a = PopularityRecommender().fit(
        train_ratings=dataset["train_ratings"],
        items=dataset["items"],
        user_profiles=dataset["user_profiles"],
    )
    model_b = GenreProfileRecommender(popularity_weight=popularity_weight).fit(
        train_ratings=dataset["train_ratings"],
        items=dataset["items"],
        user_profiles=dataset["user_profiles"],
    )

    models = {
        model_a.name: model_a,
        model_b.name: model_b,
    }
    metrics = evaluate_models(models=models, dataset=dataset, k=top_k)
    report_artifacts = generate_report(metrics=metrics, output_dir=output_dir)

    return {
        "dataset": dataset,
        "metrics": metrics,
        **report_artifacts,
    }


def main() -> None:
    result = run_demo()
    print(f"Report: {result['report_path']}")
    print(f"Metrics: {result['metrics_path']}")
    print(f"Chart: {result['chart_path']}")


if __name__ == "__main__":
    main()
