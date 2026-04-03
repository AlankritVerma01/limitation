from __future__ import annotations

from pathlib import Path

import pytest
from recommender_offline_eval.config import (
    EvaluationConfig,
    evaluation_config_from_dict,
    load_evaluation_config,
)
from recommender_offline_eval.data import build_dataset
from recommender_offline_eval.model_registry import build_model
from recommender_offline_eval.report import (
    DEFAULT_JSON_FILENAME,
    DEFAULT_REPORT_FILENAME,
)
from recommender_offline_eval.run_demo import run_evaluation

FIXTURES_ROOT = Path(__file__).resolve().parent / "fixtures"
EXAMPLES_ROOT = Path(__file__).resolve().parents[1] / "examples"


def _write_dataset(
    dataset_root: Path,
    *,
    with_numeric_features: bool,
    include_timestamp: bool = True,
    include_title: bool = True,
) -> None:
    interactions_header = ["user_id", "item_id", "rating"]
    if include_timestamp:
        interactions_header.append("timestamp")

    interaction_rows = [
        [1, 1, 5, 1],
        [1, 2, 4, 2],
        [1, 3, 5, 3],
        [1, 4, 4, 4],
        [1, 5, 5, 5],
        [2, 2, 5, 6],
        [2, 3, 4, 7],
        [2, 4, 5, 8],
        [2, 5, 4, 9],
        [2, 6, 5, 10],
    ]
    if not include_timestamp:
        interaction_rows = [row[:-1] for row in interaction_rows]

    items_header = ["item_id"]
    if include_title:
        items_header.append("title")
    items_header.append("category")
    if with_numeric_features:
        items_header.extend(["feature_action", "feature_drama"])

    item_rows = []
    for item_id in range(1, 7):
        row = [item_id]
        if include_title:
            row.append(f"Item {item_id}")
        row.append("mixed")
        if with_numeric_features:
            row.extend([1 if item_id % 2 else 0, 0 if item_id % 2 else 1])
        item_rows.append(row)

    dataset_root.mkdir(parents=True, exist_ok=True)
    (dataset_root / "interactions.csv").write_text(
        "\n".join(
            [",".join(map(str, interactions_header))]
            + [",".join(map(str, row)) for row in interaction_rows]
        )
        + "\n"
    )
    (dataset_root / "items.csv").write_text(
        "\n".join(
            [",".join(map(str, items_header))]
            + [",".join(map(str, row)) for row in item_rows]
        )
        + "\n"
    )


def _config_for_dataset(
    dataset_root: Path,
    *,
    baseline_type: str = "popularity",
    candidate_type: str = "genre_profile",
) -> EvaluationConfig:
    return evaluation_config_from_dict(
        {
            "dataset": {
                "type": "csv",
                "name": "Temp CSV dataset",
                "dataset_id": "temp-csv-dataset",
                "path": str(dataset_root),
            },
            "baseline_model": {
                "type": baseline_type,
                "label": "Baseline",
                "params": {},
            },
            "candidate_model": {
                "type": candidate_type,
                "label": "Candidate",
                "params": {},
            },
            "top_k": 5,
            "session_steps": 2,
            "slate_size": 5,
            "choice_pool": 3,
            "min_user_ratings": 5,
            "min_user_positive_ratings": 4,
            "test_holdout_positive_count": 1,
        }
    )


def test_canonical_config_round_trips() -> None:
    config = load_evaluation_config(EXAMPLES_ROOT / "canonical_run.json")
    assert config.artifact_mode == "canonical"
    assert config.as_dict() == evaluation_config_from_dict(
        config.as_dict(),
        base_dir=EXAMPLES_ROOT,
    ).as_dict()


def test_custom_config_loads_and_resolves_dataset_path() -> None:
    config = load_evaluation_config(EXAMPLES_ROOT / "custom_csv_run.json")
    assert config.dataset.type == "csv"
    assert config.dataset.path == str(
        (EXAMPLES_ROOT / "../tests/fixtures/sample_csv_dataset").resolve()
    )
    assert config.candidate_model.label == "Feature-aware candidate"
    assert config.candidate_model.params == {
        "popularity_weight": 0.15,
        "diversity_weight": 0.25,
        "shortlist_size": 20,
    }


def test_invalid_model_type_fails_clearly() -> None:
    config = EvaluationConfig(
        dataset=load_evaluation_config(EXAMPLES_ROOT / "custom_csv_run.json").dataset,
        baseline_model=load_evaluation_config(
            EXAMPLES_ROOT / "custom_csv_run.json"
        ).baseline_model,
        candidate_model=evaluation_config_from_dict(
            {
                "dataset": {
                    "type": "csv",
                    "name": "tmp",
                    "dataset_id": "tmp",
                    "path": str(FIXTURES_ROOT / "sample_csv_dataset"),
                },
                "baseline_model": {
                    "type": "popularity",
                    "label": "A",
                    "params": {},
                },
                "candidate_model": {
                    "type": "not_real",
                    "label": "B",
                    "params": {},
                },
            }
        ).candidate_model,
    )
    with pytest.raises(ValueError, match="Unsupported model type"):
        build_model(config.candidate_model)


def test_csv_dataset_ignores_non_numeric_features() -> None:
    config = load_evaluation_config(EXAMPLES_ROOT / "custom_csv_run.json")
    dataset = build_dataset(dataset_spec=config.dataset, config=config)
    assert dataset["item_feature_columns"] == [
        "feature_action",
        "feature_romance",
        "feature_documentary",
    ]


def test_featureless_csv_dataset_supports_popularity_only_runs(tmp_path: Path) -> None:
    dataset_root = tmp_path / "featureless_dataset"
    _write_dataset(dataset_root, with_numeric_features=False)
    config = _config_for_dataset(
        dataset_root,
        baseline_type="popularity",
        candidate_type="popularity",
    )

    result = run_evaluation(config, output_dir=tmp_path / "out")

    assert result["dataset"]["item_feature_columns"] == []
    assert (tmp_path / "out" / DEFAULT_REPORT_FILENAME).exists()
    assert (tmp_path / "out" / DEFAULT_JSON_FILENAME).exists()


def test_genre_profile_fails_clearly_without_item_features(tmp_path: Path) -> None:
    dataset_root = tmp_path / "featureless_dataset"
    _write_dataset(dataset_root, with_numeric_features=False)
    config = _config_for_dataset(dataset_root)

    with pytest.raises(
        ValueError,
        match="genre_profile requires at least one numeric or boolean item feature column",
    ):
        run_evaluation(config, output_dir=tmp_path / "out")


def test_missing_interactions_timestamp_fails(tmp_path: Path) -> None:
    dataset_root = tmp_path / "bad_dataset"
    _write_dataset(
        dataset_root,
        with_numeric_features=True,
        include_timestamp=False,
    )
    config = _config_for_dataset(dataset_root)

    with pytest.raises(ValueError, match="interactions.csv is missing required columns"):
        build_dataset(dataset_spec=config.dataset, config=config)


def test_missing_item_title_fails(tmp_path: Path) -> None:
    dataset_root = tmp_path / "bad_dataset"
    _write_dataset(
        dataset_root,
        with_numeric_features=True,
        include_title=False,
    )
    config = _config_for_dataset(dataset_root)

    with pytest.raises(ValueError, match="items.csv is missing required columns"):
        build_dataset(dataset_spec=config.dataset, config=config)
