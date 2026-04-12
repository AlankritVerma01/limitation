"""Offline artifact build and loading for the reference recommender service."""

from __future__ import annotations

import json
import math
from collections import Counter, defaultdict
from functools import lru_cache
from hashlib import sha1
from itertools import combinations
from pathlib import Path

GENRE_COLUMNS = (
    "unknown",
    "action",
    "adventure",
    "animation",
    "children's",
    "comedy",
    "crime",
    "documentary",
    "drama",
    "fantasy",
    "film-noir",
    "horror",
    "musical",
    "mystery",
    "romance",
    "sci-fi",
    "thriller",
    "war",
    "western",
)

GENRE_NORMALIZATION = {
    "children's": "family",
    "animation": "family",
    "film-noir": "thriller",
}

PREFERRED_GENRE_ALIASES = {
    "family": ("family", "comedy"),
    "indie": ("documentary", "drama", "romance"),
}

PACKAGE_ROOT = Path(__file__).resolve().parents[6]
REFERENCE_DATA_DIR = (
    PACKAGE_ROOT / "studies" / "01-recommender-offline-eval" / "data" / "ml-100k"
)
DEFAULT_REFERENCE_ARTIFACT_DIR = (
    PACKAGE_ROOT
    / "products"
    / "evidpath"
    / "output"
    / "reference-service-artifacts"
)
DEFAULT_ITEMS_PATH = REFERENCE_DATA_DIR / "u.item"
DEFAULT_RATINGS_PATH = REFERENCE_DATA_DIR / "u.data"
ARTIFACT_FILENAME = "reference_backend_artifacts.json"
PACKAGED_REFERENCE_ARTIFACT_PATH = Path(__file__).with_name(ARTIFACT_FILENAME)


def build_reference_artifacts(
    output_dir: str | Path,
    *,
    items_path: str | Path | None = None,
    ratings_path: str | Path | None = None,
) -> Path:
    """Build a lightweight reference backend artifact bundle from MovieLens 100K."""
    items_source = Path(items_path or DEFAULT_ITEMS_PATH)
    ratings_source = Path(ratings_path or DEFAULT_RATINGS_PATH)
    if not items_source.exists() or not ratings_source.exists():
        if items_path is None and ratings_path is None and PACKAGED_REFERENCE_ARTIFACT_PATH.exists():
            return _write_packaged_reference_artifacts(output_dir)
        missing = [str(path) for path in (items_source, ratings_source) if not path.exists()]
        raise FileNotFoundError(f"Reference source data missing: {', '.join(missing)}")

    raw_items = _load_items(items_source)
    stats = _load_rating_stats(ratings_source)
    items_payload = _build_item_payloads(raw_items, stats)
    global_top_item_ids = [
        item["item_id"]
        for item in sorted(
            items_payload,
            key=lambda item: (item["quality"], item["popularity"]),
            reverse=True,
        )[:50]
    ]
    fingerprint = sha1(
        json.dumps(
            {
                "items": items_payload[:50],
                "item_count": len(items_payload),
                "ratings_count": stats["rating_count"],
            },
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()[:12]
    artifact_payload = {
        "artifact_id": f"movielens-100k-reference-{fingerprint}",
        "dataset": "MovieLens 100K",
        "version": "v1",
        "item_count": len(items_payload),
        "rating_count": stats["rating_count"],
        "positive_threshold": 4,
        "items": items_payload,
        "global_top_item_ids": global_top_item_ids,
    }
    resolved_dir = Path(output_dir)
    resolved_dir.mkdir(parents=True, exist_ok=True)
    artifact_path = resolved_dir / ARTIFACT_FILENAME
    artifact_path.write_text(
        json.dumps(artifact_payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    load_reference_artifacts.cache_clear()
    return artifact_path


def _write_packaged_reference_artifacts(output_dir: str | Path) -> Path:
    """Write the packaged reference artifact bundle to the requested directory."""
    resolved_dir = Path(output_dir)
    resolved_dir.mkdir(parents=True, exist_ok=True)
    artifact_path = resolved_dir / ARTIFACT_FILENAME
    artifact_path.write_text(
        PACKAGED_REFERENCE_ARTIFACT_PATH.read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    load_reference_artifacts.cache_clear()
    return artifact_path


def ensure_reference_artifacts(output_dir: str | Path | None = None) -> Path:
    """Build the default reference artifacts if they do not already exist."""
    resolved_dir = Path(output_dir or DEFAULT_REFERENCE_ARTIFACT_DIR)
    artifact_path = resolved_dir / ARTIFACT_FILENAME
    if artifact_path.exists():
        return artifact_path
    return build_reference_artifacts(resolved_dir)


@lru_cache(maxsize=4)
def load_reference_artifacts(artifact_dir: str | Path) -> dict:
    """Load a reference artifact bundle from disk."""
    resolved_dir = Path(artifact_dir)
    artifact_path = resolved_dir / ARTIFACT_FILENAME
    return json.loads(artifact_path.read_text(encoding="utf-8"))


def history_for_reference_genres(
    preferred_genres: tuple[str, ...],
    depth: int,
    artifact_dir: str | Path,
) -> tuple[str, ...]:
    """Build deterministic history ids for a seed from reference artifacts."""
    artifacts = load_reference_artifacts(artifact_dir)
    preferred_targets = _expand_preferred_genres(preferred_genres)
    ranked_items = [
        item
        for item in artifacts["items"]
        if set(item["genres"]).intersection(preferred_targets)
    ]
    if not ranked_items:
        ranked_items = artifacts["items"]
    ranked_items.sort(
        key=lambda item: (item["quality"], item["popularity"], item["novelty"]),
        reverse=True,
    )
    selected = [item["item_id"] for item in ranked_items[:depth]]
    if len(selected) < depth:
        for item_id in artifacts["global_top_item_ids"]:
            if item_id not in selected:
                selected.append(item_id)
            if len(selected) == depth:
                break
    return tuple(selected[:depth])


def _load_items(items_path: Path) -> dict[str, dict]:
    items: dict[str, dict] = {}
    with items_path.open("r", encoding="latin-1") as handle:
        for line in handle:
            parts = line.rstrip("\n").split("|")
            if len(parts) < 24:
                continue
            item_id, title = parts[0], parts[1]
            genre_flags = tuple(int(flag) for flag in parts[-19:])
            genres = tuple(
                _normalize_genre_name(name)
                for name, flag in zip(GENRE_COLUMNS, genre_flags, strict=True)
                if flag
            )
            filtered_genres = tuple(dict.fromkeys(genre for genre in genres if genre != "unknown"))
            items[item_id] = {
                "item_id": item_id,
                "title": title,
                "genres": filtered_genres or ("drama",),
                "primary_genre": (filtered_genres or ("drama",))[0],
            }
    return items


def _load_rating_stats(ratings_path: Path) -> dict:
    rating_counts: Counter[str] = Counter()
    rating_sums: Counter[str] = Counter()
    positive_counts: Counter[str] = Counter()
    user_positive_items: dict[str, list[str]] = defaultdict(list)
    rating_count = 0
    with ratings_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            user_id, item_id, rating, _timestamp = line.rstrip("\n").split("\t")
            rating_value = int(rating)
            rating_counts[item_id] += 1
            rating_sums[item_id] += rating_value
            rating_count += 1
            if rating_value >= 4:
                positive_counts[item_id] += 1
                user_positive_items[user_id].append(item_id)

    pair_counts: dict[str, Counter[str]] = defaultdict(Counter)
    for item_ids in user_positive_items.values():
        unique_item_ids = sorted(set(item_ids))
        for left, right in combinations(unique_item_ids, 2):
            pair_counts[left][right] += 1
            pair_counts[right][left] += 1
    return {
        "rating_counts": rating_counts,
        "rating_sums": rating_sums,
        "positive_counts": positive_counts,
        "pair_counts": pair_counts,
        "rating_count": rating_count,
    }


def _build_item_payloads(raw_items: dict[str, dict], stats: dict) -> list[dict]:
    rating_counts: Counter[str] = stats["rating_counts"]
    rating_sums: Counter[str] = stats["rating_sums"]
    positive_counts: Counter[str] = stats["positive_counts"]
    pair_counts: dict[str, Counter[str]] = stats["pair_counts"]
    max_count = max(rating_counts.values()) if rating_counts else 1
    items_payload: list[dict] = []
    for item_id, item in raw_items.items():
        count = rating_counts[item_id]
        popularity = count / max_count if max_count else 0.0
        novelty = 1.0 - popularity
        avg_rating = rating_sums[item_id] / count if count else 3.0
        quality = (avg_rating - 1.0) / 4.0
        neighbors = _top_neighbors(item_id, positive_counts, pair_counts)
        items_payload.append(
            {
                "item_id": item_id,
                "title": item["title"],
                "genre": item["primary_genre"],
                "genres": list(item["genres"]),
                "popularity": round(popularity, 6),
                "novelty": round(novelty, 6),
                "quality": round(quality, 6),
                "neighbor_scores": neighbors,
            }
        )
    items_payload.sort(
        key=lambda item: (item["quality"], item["popularity"], item["novelty"]),
        reverse=True,
    )
    return items_payload


def _top_neighbors(
    item_id: str,
    positive_counts: Counter[str],
    pair_counts: dict[str, Counter[str]],
) -> list[dict]:
    neighbors = pair_counts.get(item_id, Counter())
    scored = []
    item_positive_count = positive_counts[item_id]
    for neighbor_id, co_count in neighbors.items():
        denominator = math.sqrt(max(1, item_positive_count) * max(1, positive_counts[neighbor_id]))
        score = co_count / denominator if denominator else 0.0
        scored.append((score, neighbor_id))
    scored.sort(reverse=True)
    return [
        {"item_id": neighbor_id, "score": round(score, 6)}
        for score, neighbor_id in scored[:8]
    ]


def _normalize_genre_name(name: str) -> str:
    lowered = name.lower()
    return GENRE_NORMALIZATION.get(lowered, lowered)


def _expand_preferred_genres(preferred_genres: tuple[str, ...]) -> set[str]:
    expanded: set[str] = set()
    for genre in preferred_genres:
        expanded.update(PREFERRED_GENRE_ALIASES.get(genre, (genre,)))
    return expanded or {"drama"}
