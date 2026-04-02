from __future__ import annotations

import io
import urllib.request
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

from .paths import DEFAULT_DATA_DIR

MOVIELENS_URL = "https://files.grouplens.org/datasets/movielens/ml-100k.zip"
MOVIELENS_DIRNAME = "ml-100k"
GENRE_COLUMNS = [
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


def load_movielens_100k(
    data_dir: str | Path = DEFAULT_DATA_DIR,
) -> tuple[pd.DataFrame, pd.DataFrame]:
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
        *GENRE_COLUMNS,
    ]
    items = pd.read_csv(
        dataset_dir / "u.item",
        sep="|",
        names=item_columns,
        usecols=range(len(item_columns)),
        encoding="latin-1",
    )
    return ratings, items


def _normalize_rows(matrix: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    safe_norms = np.where(norms == 0, 1.0, norms)
    return matrix / safe_norms


def _build_user_profile(
    item_lookup: dict[int, np.ndarray], item_ids: list[int]
) -> np.ndarray:
    vectors = [item_lookup[item_id] for item_id in item_ids if item_id in item_lookup]
    if not vectors:
        return np.zeros(len(GENRE_COLUMNS), dtype=float)
    profile = np.mean(np.vstack(vectors), axis=0)
    norm = np.linalg.norm(profile)
    if norm == 0:
        return profile
    return profile / norm


def build_dataset(data_dir: str | Path = DEFAULT_DATA_DIR) -> dict:
    ratings, items = load_movielens_100k(data_dir)
    ratings = ratings.sort_values(["user_id", "timestamp"]).copy()

    total_counts = ratings.groupby("user_id").size()
    positive_counts = ratings.loc[ratings["rating"] >= 4].groupby("user_id").size()
    eligible_users = sorted(
        set(total_counts[total_counts >= 10].index).intersection(
            positive_counts[positive_counts >= 5].index
        )
    )

    ratings = ratings[ratings["user_id"].isin(eligible_users)].copy()
    positive = ratings[ratings["rating"] >= 4].copy()
    positive = positive.sort_values(["user_id", "timestamp"])
    test_positive = positive.groupby("user_id").tail(2).copy()
    train_ratings = ratings.drop(index=test_positive.index).copy()
    train_positive = train_ratings[train_ratings["rating"] >= 4].copy()

    items = items.copy()
    items["genre_vector"] = list(items[GENRE_COLUMNS].astype(float).to_numpy())
    popularity_counts = (
        train_positive.groupby("item_id").size().reindex(items["item_id"], fill_value=0)
    )
    max_popularity = float(popularity_counts.max()) if len(popularity_counts) else 1.0
    items["popularity_count"] = popularity_counts.to_numpy(dtype=float)
    items["popularity_norm"] = (
        items["popularity_count"] / max(max_popularity, 1.0)
    ).astype(float)
    pop_threshold = float(items["popularity_count"].quantile(0.9))
    items["top_popularity_decile"] = items["popularity_count"] >= pop_threshold

    items["genre_vector_normed"] = list(
        _normalize_rows(np.vstack(items["genre_vector"].to_list()))
    )
    normed_lookup = {
        int(row.item_id): np.asarray(row.genre_vector_normed, dtype=float)
        for row in items.itertuples()
    }

    user_seen_items = train_ratings.groupby("user_id")["item_id"].apply(list).to_dict()
    user_positive_train_items = (
        train_positive.groupby("user_id")["item_id"].apply(list).to_dict()
    )
    user_recent_positive_history = {
        int(user_id): item_ids[-2:]
        for user_id, item_ids in user_positive_train_items.items()
    }
    user_profiles = {
        int(user_id): _build_user_profile(normed_lookup, item_ids)
        for user_id, item_ids in user_positive_train_items.items()
    }

    test_positive_by_user = (
        test_positive.groupby("user_id")["item_id"].apply(list).to_dict()
    )

    dataset_summary = {
        "ratings": int(len(ratings)),
        "train_ratings": int(len(train_ratings)),
        "test_positive_rows": int(len(test_positive)),
        "users": int(len(eligible_users)),
        "items": int(items["item_id"].nunique()),
    }

    return {
        "summary": dataset_summary,
        "items": items[
            [
                "item_id",
                "title",
                *GENRE_COLUMNS,
                "popularity_count",
                "popularity_norm",
                "top_popularity_decile",
            ]
        ].copy(),
        "all_item_ids": items["item_id"].astype(int).tolist(),
        "item_vector_lookup": normed_lookup,
        "item_title_lookup": dict(zip(items["item_id"], items["title"])),
        "item_popularity_lookup": dict(zip(items["item_id"], items["popularity_norm"])),
        "item_top_decile_lookup": dict(
            zip(items["item_id"], items["top_popularity_decile"])
        ),
        "train_ratings": train_ratings.reset_index(drop=True),
        "train_positive": train_positive.reset_index(drop=True),
        "test_positive": test_positive.reset_index(drop=True),
        "test_positive_by_user": {
            int(k): [int(v) for v in vals] for k, vals in test_positive_by_user.items()
        },
        "eligible_users": [int(user_id) for user_id in eligible_users],
        "user_profiles": user_profiles,
        "user_seen_items": {
            int(k): [int(v) for v in vals] for k, vals in user_seen_items.items()
        },
        "user_recent_positive_history": user_recent_positive_history,
    }
