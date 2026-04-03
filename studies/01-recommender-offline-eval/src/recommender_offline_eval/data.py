"""Dataset loading and preparation for recommender evaluation runs.

This module turns either built-in MovieLens data or a CSV dataset directory into the
normalized in-memory structure used by recommenders, the evaluator, and reporting.
"""

from __future__ import annotations

import io
import urllib.request
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

from .canonical import CANONICAL_RUN_CONFIG
from .config import DatasetSpec, EvaluationConfig
from .paths import DEFAULT_DATA_DIR

MOVIELENS_URL = "https://files.grouplens.org/datasets/movielens/ml-100k.zip"
MOVIELENS_DIRNAME = "ml-100k"
MOVIELENS_FEATURE_COLUMNS = [
    "unknown",
    "Action",
    "Adventure",
    "Animation",
    "Children",
    "Comedy",
    "Crime",
    "Documentary",
    "Drama",
    "Fantasy",
    "Film-Noir",
    "Horror",
    "Musical",
    "Mystery",
    "Romance",
    "Sci-Fi",
    "Thriller",
    "War",
    "Western",
]


def ensure_movielens_100k(data_dir: str | Path = DEFAULT_DATA_DIR) -> Path:
    data_path = Path(data_dir)
    data_path.mkdir(parents=True, exist_ok=True)
    dataset_dir = data_path / MOVIELENS_DIRNAME
    if dataset_dir.exists():
        return dataset_dir

    response = urllib.request.urlopen(MOVIELENS_URL, timeout=30)
    payload = response.read()
    with zipfile.ZipFile(io.BytesIO(payload)) as zf:
        zf.extractall(data_path)
    return dataset_dir


def _normalize_rows(matrix: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    safe_norms = np.where(norms == 0, 1.0, norms)
    return matrix / safe_norms


def _coerce_interactions_frame(ratings: pd.DataFrame) -> pd.DataFrame:
    required_columns = ["user_id", "item_id", "rating", "timestamp"]
    missing = [column for column in required_columns if column not in ratings.columns]
    if missing:
        raise ValueError(
            "interactions.csv is missing required columns: "
            + ", ".join(sorted(missing))
        )

    coerced = ratings.copy()
    for column in required_columns:
        try:
            coerced[column] = pd.to_numeric(coerced[column], errors="raise")
        except Exception as exc:  # noqa: BLE001
            raise ValueError(
                f"interactions.csv column {column!r} must contain numeric values."
            ) from exc
    coerced["user_id"] = coerced["user_id"].astype(int)
    coerced["item_id"] = coerced["item_id"].astype(int)
    coerced["timestamp"] = coerced["timestamp"].astype(int)
    return coerced


def _item_feature_columns(items: pd.DataFrame) -> list[str]:
    feature_columns = []
    for column in items.columns:
        if column in {"item_id", "title"}:
            continue
        series = items[column]
        if pd.api.types.is_bool_dtype(series) or pd.api.types.is_numeric_dtype(series):
            feature_columns.append(column)
    return feature_columns


def _coerce_items_frame(items: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    required_columns = ["item_id", "title"]
    missing = [column for column in required_columns if column not in items.columns]
    if missing:
        raise ValueError(
            "items.csv is missing required columns: " + ", ".join(sorted(missing))
        )

    coerced = items.copy()
    try:
        coerced["item_id"] = pd.to_numeric(coerced["item_id"], errors="raise").astype(
            int
        )
    except Exception as exc:  # noqa: BLE001
        raise ValueError("items.csv column 'item_id' must contain numeric values.") from exc

    feature_columns = _item_feature_columns(coerced)
    for column in feature_columns:
        coerced[column] = coerced[column].astype(float)

    return coerced, feature_columns


def load_movielens_100k(
    data_dir: str | Path = DEFAULT_DATA_DIR,
) -> tuple[pd.DataFrame, pd.DataFrame, list[str]]:
    dataset_dir = ensure_movielens_100k(data_dir)

    ratings = pd.read_csv(
        dataset_dir / "u.data",
        sep="\t",
        names=["user_id", "item_id", "rating", "timestamp"],
        encoding="latin-1",
    )
    item_columns = [
        "item_id",
        "title",
        "release_date",
        "video_release_date",
        "imdb_url",
        *MOVIELENS_FEATURE_COLUMNS,
    ]
    items = pd.read_csv(
        dataset_dir / "u.item",
        sep="|",
        names=item_columns,
        usecols=range(len(item_columns)),
        encoding="latin-1",
    )
    items = items[["item_id", "title", *MOVIELENS_FEATURE_COLUMNS]].copy()
    items["item_id"] = items["item_id"].astype(int)
    for column in MOVIELENS_FEATURE_COLUMNS:
        items[column] = items[column].astype(float)

    return _coerce_interactions_frame(ratings), items, list(MOVIELENS_FEATURE_COLUMNS)


def load_csv_dataset(
    dataset_path: str | Path,
) -> tuple[pd.DataFrame, pd.DataFrame, list[str]]:
    dataset_root = Path(dataset_path)
    interactions_path = dataset_root / "interactions.csv"
    items_path = dataset_root / "items.csv"

    if not interactions_path.exists():
        raise ValueError(f"Expected interactions file at {interactions_path}.")
    if not items_path.exists():
        raise ValueError(f"Expected items file at {items_path}.")

    ratings = _coerce_interactions_frame(pd.read_csv(interactions_path))
    items, feature_columns = _coerce_items_frame(pd.read_csv(items_path))
    return ratings, items, feature_columns


def _load_source_dataset(
    dataset_spec: DatasetSpec,
    *,
    data_dir: str | Path = DEFAULT_DATA_DIR,
) -> tuple[pd.DataFrame, pd.DataFrame, list[str], dict[str, str | None]]:
    if dataset_spec.type == "movielens_100k":
        source_dir = dataset_spec.path or str(data_dir)
        ratings, items, feature_columns = load_movielens_100k(source_dir)
        return ratings, items, feature_columns, {
            "dataset_type": "movielens_100k",
            "dataset_id": dataset_spec.dataset_id,
            "dataset_path": dataset_spec.path,
        }

    if dataset_spec.type == "csv":
        if dataset_spec.path is None:
            raise ValueError("CSV dataset configs must provide dataset.path.")
        ratings, items, feature_columns = load_csv_dataset(dataset_spec.path)
        return ratings, items, feature_columns, {
            "dataset_type": "csv",
            "dataset_id": dataset_spec.dataset_id,
            "dataset_path": str(Path(dataset_spec.path).resolve()),
        }

    raise ValueError(
        f"Unsupported dataset type {dataset_spec.type!r}. Expected 'movielens_100k' or 'csv'."
    )


def _eligible_users(ratings: pd.DataFrame, config: EvaluationConfig) -> list[int]:
    total_counts = ratings.groupby("user_id").size()
    positive_counts = (
        ratings.loc[ratings["rating"] >= config.positive_rating_threshold]
        .groupby("user_id")
        .size()
    )
    return sorted(
        set(total_counts[total_counts >= config.min_user_ratings].index).intersection(
            positive_counts[
                positive_counts >= config.min_user_positive_ratings
            ].index
        )
    )


def _split_ratings(
    ratings: pd.DataFrame,
    config: EvaluationConfig,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    # Hold out each eligible user's last few positive interactions chronologically.
    positive = ratings[
        ratings["rating"] >= config.positive_rating_threshold
    ].sort_values(["user_id", "timestamp"])
    test_positive = positive.groupby("user_id").tail(
        config.test_holdout_positive_count
    ).copy()
    train_ratings = ratings.drop(index=test_positive.index).copy()
    train_positive = train_ratings[
        train_ratings["rating"] >= config.positive_rating_threshold
    ].copy()
    return train_ratings, train_positive, test_positive


def _prepared_item_vectors(
    items: pd.DataFrame,
    feature_columns: list[str],
) -> tuple[pd.DataFrame, dict[int, np.ndarray]]:
    prepared_items = items.copy()
    if feature_columns:
        feature_matrix = prepared_items[feature_columns].astype(float).to_numpy()
    else:
        feature_matrix = np.zeros((len(prepared_items), 0), dtype=float)

    prepared_items["feature_vector_normed"] = list(_normalize_rows(feature_matrix))
    vector_lookup = {
        int(row.item_id): np.asarray(row.feature_vector_normed, dtype=float)
        for row in prepared_items.itertuples()
    }
    return prepared_items, vector_lookup


def _prepare_items(
    items: pd.DataFrame,
    feature_columns: list[str],
    train_positive: pd.DataFrame,
) -> tuple[pd.DataFrame, dict[int, np.ndarray]]:
    prepared_items, vector_lookup = _prepared_item_vectors(items, feature_columns)
    popularity_counts = (
        train_positive.groupby("item_id")
        .size()
        .reindex(prepared_items["item_id"], fill_value=0)
    )
    max_popularity = float(popularity_counts.max()) if len(popularity_counts) else 1.0
    prepared_items["popularity_count"] = popularity_counts.to_numpy(dtype=float)
    prepared_items["popularity_norm"] = (
        prepared_items["popularity_count"] / max(max_popularity, 1.0)
    ).astype(float)
    pop_threshold = float(prepared_items["popularity_count"].quantile(0.9))
    prepared_items["top_popularity_decile"] = (
        prepared_items["popularity_count"] >= pop_threshold
    )
    return prepared_items, vector_lookup


def _build_user_profile(
    item_lookup: dict[int, np.ndarray],
    item_ids: list[int],
) -> np.ndarray:
    vectors = [item_lookup[item_id] for item_id in item_ids if item_id in item_lookup]
    if not vectors:
        first_vector = next(iter(item_lookup.values()), np.array([], dtype=float))
        return np.zeros(len(first_vector), dtype=float)
    profile = np.mean(np.vstack(vectors), axis=0)
    norm = np.linalg.norm(profile)
    if norm == 0:
        return profile
    return profile / norm


def _build_user_state(
    train_ratings: pd.DataFrame,
    train_positive: pd.DataFrame,
    item_vector_lookup: dict[int, np.ndarray],
) -> tuple[dict[int, list[int]], dict[int, np.ndarray], dict[int, list[int]]]:
    user_seen_items = train_ratings.groupby("user_id")["item_id"].apply(list).to_dict()
    user_positive_train_items = (
        train_positive.groupby("user_id")["item_id"].apply(list).to_dict()
    )
    user_profiles = {
        int(user_id): _build_user_profile(item_vector_lookup, item_ids)
        for user_id, item_ids in user_positive_train_items.items()
    }
    user_recent_positive_history = {
        int(user_id): item_ids[-2:]
        for user_id, item_ids in user_positive_train_items.items()
    }
    return (
        {int(k): [int(v) for v in vals] for k, vals in user_seen_items.items()},
        user_profiles,
        user_recent_positive_history,
    )


def build_dataset(
    *,
    dataset_spec: DatasetSpec | None = None,
    config: EvaluationConfig | None = None,
    data_dir: str | Path = DEFAULT_DATA_DIR,
) -> dict:
    effective_config = config or CANONICAL_RUN_CONFIG
    effective_dataset_spec = dataset_spec or effective_config.dataset
    ratings, items, feature_columns, source = _load_source_dataset(
        effective_dataset_spec,
        data_dir=data_dir,
    )

    ratings = ratings.sort_values(["user_id", "timestamp"]).copy()
    eligible_users = _eligible_users(ratings, effective_config)
    ratings = ratings[ratings["user_id"].isin(eligible_users)].copy()
    train_ratings, train_positive, test_positive = _split_ratings(ratings, effective_config)

    prepared_items, item_vector_lookup = _prepare_items(
        items,
        feature_columns,
        train_positive,
    )
    user_seen_items, user_profiles, user_recent_positive_history = _build_user_state(
        train_ratings,
        train_positive,
        item_vector_lookup,
    )
    test_positive_by_user = (
        test_positive.groupby("user_id")["item_id"].apply(list).to_dict()
    )

    summary = {
        "ratings": int(len(ratings)),
        "train_ratings": int(len(train_ratings)),
        "test_positive_rows": int(len(test_positive)),
        "users": int(len(eligible_users)),
        "items": int(prepared_items["item_id"].nunique()),
    }

    return {
        "summary": summary,
        "source": source,
        "items": prepared_items[
            [
                "item_id",
                "title",
                *feature_columns,
                "popularity_count",
                "popularity_norm",
                "top_popularity_decile",
            ]
        ].copy(),
        "item_feature_columns": list(feature_columns),
        "all_item_ids": prepared_items["item_id"].astype(int).tolist(),
        "item_vector_lookup": item_vector_lookup,
        "item_title_lookup": dict(zip(prepared_items["item_id"], prepared_items["title"])),
        "item_popularity_lookup": dict(
            zip(prepared_items["item_id"], prepared_items["popularity_norm"])
        ),
        "item_top_decile_lookup": dict(
            zip(prepared_items["item_id"], prepared_items["top_popularity_decile"])
        ),
        "train_ratings": train_ratings.reset_index(drop=True),
        "train_positive": train_positive.reset_index(drop=True),
        "test_positive": test_positive.reset_index(drop=True),
        "test_positive_by_user": {
            int(k): [int(v) for v in vals] for k, vals in test_positive_by_user.items()
        },
        "eligible_users": [int(user_id) for user_id in eligible_users],
        "user_profiles": user_profiles,
        "user_seen_items": user_seen_items,
        "user_recent_positive_history": user_recent_positive_history,
    }
