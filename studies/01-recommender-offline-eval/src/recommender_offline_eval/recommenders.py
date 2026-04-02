from __future__ import annotations

from abc import ABC, abstractmethod

import numpy as np
import pandas as pd


class Recommender(ABC):
    def __init__(self, name: str) -> None:
        self.name = name
        self.items = None
        self.user_seen_items = {}

    def fit(
        self,
        train_ratings: pd.DataFrame,
        items: pd.DataFrame,
        user_profiles: dict[int, np.ndarray],
    ) -> "Recommender":
        self.items = items.set_index("item_id").copy()
        self.user_seen_items = (
            train_ratings.groupby("user_id")["item_id"].apply(set).to_dict()
        )
        return self

    @abstractmethod
    def score_user(self, user_id: int, candidate_item_ids: list[int]) -> np.ndarray:
        raise NotImplementedError

    def recommend(
        self,
        user_id: int,
        k: int,
        exclude_seen: bool = True,
        extra_exclude: set[int] | None = None,
    ) -> pd.DataFrame:
        extra_exclude = extra_exclude or set()
        seen_items = (
            set(self.user_seen_items.get(user_id, set())) if exclude_seen else set()
        )
        seen_items.update(extra_exclude)
        candidate_item_ids = [
            int(item_id)
            for item_id in self.items.index.tolist()
            if int(item_id) not in seen_items
        ]
        scores = self.score_user(user_id, candidate_item_ids)
        ranked = (
            pd.DataFrame(
                {
                    "item_id": candidate_item_ids,
                    "score": scores,
                    "title": self.items.loc[candidate_item_ids, "title"].to_numpy(),
                }
            )
            .sort_values(["score", "item_id"], ascending=[False, True])
            .head(k)
            .reset_index(drop=True)
        )
        return ranked


class PopularityRecommender(Recommender):
    def __init__(self) -> None:
        super().__init__(name="Model A")
        self.popularity_lookup = {}

    def fit(
        self,
        train_ratings: pd.DataFrame,
        items: pd.DataFrame,
        user_profiles: dict[int, np.ndarray],
    ) -> "PopularityRecommender":
        super().fit(train_ratings, items, user_profiles)
        self.popularity_lookup = self.items["popularity_norm"].to_dict()
        return self

    def score_user(self, user_id: int, candidate_item_ids: list[int]) -> np.ndarray:
        return np.array(
            [
                float(self.popularity_lookup.get(item_id, 0.0))
                for item_id in candidate_item_ids
            ],
            dtype=float,
        )


class GenreProfileRecommender(Recommender):
    def __init__(
        self,
        popularity_weight: float = 0.25,
        diversity_weight: float = 0.35,
        shortlist_size: int = 75,
    ) -> None:
        super().__init__(name="Model B")
        self.popularity_weight = popularity_weight
        self.diversity_weight = diversity_weight
        self.shortlist_size = shortlist_size
        self.user_profiles = {}
        self.item_positions = {}
        self.genre_matrix = None
        self.popularity_vector = None

    def fit(
        self,
        train_ratings: pd.DataFrame,
        items: pd.DataFrame,
        user_profiles: dict[int, np.ndarray],
    ) -> "GenreProfileRecommender":
        super().fit(train_ratings, items, user_profiles)
        self.user_profiles = user_profiles
        item_ids = [int(item_id) for item_id in self.items.index.tolist()]
        self.item_positions = {item_id: idx for idx, item_id in enumerate(item_ids)}
        genre_cols = [
            column
            for column in self.items.columns
            if column
            not in {
                "title",
                "popularity_count",
                "popularity_norm",
                "top_popularity_decile",
            }
        ]
        genre_cols = [column for column in genre_cols if column != "item_id"]
        genre_cols = [
            column for column in genre_cols if self.items[column].dtype != object
        ]
        self.genre_matrix = self.items.loc[item_ids, genre_cols].to_numpy(dtype=float)
        norms = np.linalg.norm(self.genre_matrix, axis=1, keepdims=True)
        safe_norms = np.where(norms == 0, 1.0, norms)
        self.genre_matrix = self.genre_matrix / safe_norms
        self.popularity_vector = self.items.loc[item_ids, "popularity_norm"].to_numpy(
            dtype=float
        )
        return self

    def score_user(self, user_id: int, candidate_item_ids: list[int]) -> np.ndarray:
        profile = self.user_profiles.get(user_id)
        if profile is None:
            profile = np.zeros(self.genre_matrix.shape[1], dtype=float)
        candidate_positions = [
            self.item_positions[item_id] for item_id in candidate_item_ids
        ]
        candidate_matrix = self.genre_matrix[candidate_positions]
        popularity = self.popularity_vector[candidate_positions]
        affinity = candidate_matrix @ profile
        return affinity + self.popularity_weight * popularity

    def recommend(
        self,
        user_id: int,
        k: int,
        exclude_seen: bool = True,
        extra_exclude: set[int] | None = None,
    ) -> pd.DataFrame:
        extra_exclude = extra_exclude or set()
        seen_items = (
            set(self.user_seen_items.get(user_id, set())) if exclude_seen else set()
        )
        seen_items.update(extra_exclude)
        candidate_item_ids = [
            int(item_id)
            for item_id in self.items.index.tolist()
            if int(item_id) not in seen_items
        ]
        base_scores = self.score_user(user_id, candidate_item_ids)
        ranking = pd.DataFrame(
            {
                "item_id": candidate_item_ids,
                "base_score": base_scores,
                "title": self.items.loc[candidate_item_ids, "title"].to_numpy(),
            }
        ).sort_values(["base_score", "item_id"], ascending=[False, True])

        shortlist = ranking.head(max(k, self.shortlist_size)).reset_index(drop=True)
        selected_rows: list[dict] = []
        selected_vectors = []
        remaining = shortlist.to_dict(orient="records")

        while remaining and len(selected_rows) < k:
            best_index = 0
            best_score = None
            for index, row in enumerate(remaining):
                item_vector = self.genre_matrix[
                    self.item_positions[int(row["item_id"])]
                ]
                diversity_penalty = 0.0
                if selected_vectors:
                    diversity_penalty = float(
                        max(
                            np.dot(item_vector, selected_vector)
                            for selected_vector in selected_vectors
                        )
                    )
                reranked_score = (
                    float(row["base_score"]) - self.diversity_weight * diversity_penalty
                )
                if best_score is None or reranked_score > best_score:
                    best_score = reranked_score
                    best_index = index

            chosen = remaining.pop(best_index)
            chosen["score"] = best_score
            selected_rows.append(chosen)
            selected_vectors.append(
                self.genre_matrix[self.item_positions[int(chosen["item_id"])]]
            )

        return pd.DataFrame(selected_rows)[["item_id", "score", "title"]]
