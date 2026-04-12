"""Independent example recommender artifacts for external HTTP proof."""

from __future__ import annotations

import json
import math
import zipfile
from collections import Counter, defaultdict
from dataclasses import dataclass
from functools import lru_cache
from hashlib import sha1
from io import BytesIO
from itertools import combinations
from pathlib import Path
from urllib import request

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

PACKAGE_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_DATA_DIR = (
    PACKAGE_ROOT / "studies" / "01-recommender-offline-eval" / "data" / "ml-100k"
)
DEFAULT_ARTIFACT_DIR = Path(__file__).resolve().parent / "artifacts"
ARTIFACT_FILENAME = "example_recommender_artifacts.json"
MOVIELENS_100K_ZIP_URL = "https://files.grouplens.org/datasets/movielens/ml-100k.zip"


@dataclass(frozen=True)
class ExampleItem:
    item_id: str
    title: str
    genre: str
    genres: tuple[str, ...]
    popularity: float
    novelty: float
    quality: float
    neighbor_scores: tuple[tuple[str, float], ...]


def ensure_example_artifacts(
    output_dir: str | Path | None = None,
    *,
    data_dir: str | Path | None = None,
) -> Path:
    """Build the example service artifacts if they do not already exist."""
    resolved_dir = Path(output_dir or DEFAULT_ARTIFACT_DIR)
    artifact_path = resolved_dir / ARTIFACT_FILENAME
    if artifact_path.exists():
        return artifact_path
    return build_example_artifacts(resolved_dir, data_dir=data_dir)


def build_example_artifacts(
    output_dir: str | Path,
    *,
    data_dir: str | Path | None = None,
) -> Path:
    """Build shared item metadata and item-item CF artifacts from MovieLens 100K."""
    resolved_output_dir = Path(output_dir)
    resolved_data_dir, data_source = _resolve_source_data_dir(
        resolved_output_dir, data_dir=data_dir
    )
    items_path = resolved_data_dir / "u.item"
    ratings_path = resolved_data_dir / "u.data"
    if not items_path.exists() or not ratings_path.exists():
        missing = [str(path) for path in (items_path, ratings_path) if not path.exists()]
        raise FileNotFoundError(f"Example source data missing: {', '.join(missing)}")

    raw_items = _load_items(items_path)
    stats = _load_rating_stats(ratings_path)
    items_payload = _build_item_payloads(raw_items, stats)
    fingerprint = sha1(
        json.dumps(
            {
                "dataset": "MovieLens 100K",
                "item_count": len(items_payload),
                "sample": items_payload[:50],
            },
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()[:12]
    payload = {
        "artifact_id": f"movielens-100k-example-{fingerprint}",
        "dataset": "MovieLens 100K",
        "data_source": data_source,
        "version": "v1",
        "item_count": len(items_payload),
        "items": items_payload,
        "global_popularity_order": [
            item["item_id"]
            for item in sorted(
                items_payload,
                key=lambda item: (item["popularity"], item["quality"], item["novelty"]),
                reverse=True,
            )
        ],
    }
    resolved_output_dir.mkdir(parents=True, exist_ok=True)
    artifact_path = resolved_output_dir / ARTIFACT_FILENAME
    artifact_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    load_example_artifacts.cache_clear()
    return artifact_path


@lru_cache(maxsize=8)
def load_example_artifacts(artifact_dir: str | Path) -> dict:
    """Load the example recommender artifacts from disk."""
    resolved_dir = Path(artifact_dir)
    artifact_path = resolved_dir / ARTIFACT_FILENAME
    return json.loads(artifact_path.read_text(encoding="utf-8"))


def load_items(artifact_dir: str | Path) -> dict[str, ExampleItem]:
    """Load typed items from a built artifact bundle."""
    payload = load_example_artifacts(artifact_dir)
    return {
        item["item_id"]: ExampleItem(
            item_id=item["item_id"],
            title=item["title"],
            genre=item["genre"],
            genres=tuple(item["genres"]),
            popularity=float(item["popularity"]),
            novelty=float(item["novelty"]),
            quality=float(item["quality"]),
            neighbor_scores=tuple(
                (neighbor["item_id"], float(neighbor["score"]))
                for neighbor in item["neighbor_scores"]
            ),
        )
        for item in payload["items"]
    }


def _load_items(items_path: Path) -> dict[str, dict]:
    items: dict[str, dict] = {}
    with items_path.open("r", encoding="latin-1") as handle:
        for line in handle:
            parts = line.rstrip("\n").split("|")
            if len(parts) < 24:
                continue
            item_id = parts[0]
            title = parts[1]
            genre_flags = tuple(int(flag) for flag in parts[-19:])
            genres = tuple(
                _normalize_genre_name(name)
                for name, flag in zip(GENRE_COLUMNS, genre_flags, strict=True)
                if flag
            )
            filtered = tuple(dict.fromkeys(genre for genre in genres if genre != "unknown"))
            normalized = filtered or ("drama",)
            items[item_id] = {
                "item_id": item_id,
                "title": title,
                "genres": normalized,
                "primary_genre": normalized[0],
            }
    return items


def _load_rating_stats(ratings_path: Path) -> dict:
    rating_counts: Counter[str] = Counter()
    rating_sums: Counter[str] = Counter()
    positive_counts: Counter[str] = Counter()
    user_positive_items: dict[str, list[str]] = defaultdict(list)

    with ratings_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            _user_id, item_id, rating, _timestamp = line.rstrip("\n").split("\t")
            rating_value = int(rating)
            rating_counts[item_id] += 1
            rating_sums[item_id] += rating_value
            if rating_value >= 4:
                positive_counts[item_id] += 1
                user_positive_items[_user_id].append(item_id)

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
    }


def _build_item_payloads(raw_items: dict[str, dict], stats: dict) -> list[dict]:
    rating_counts: Counter[str] = stats["rating_counts"]
    rating_sums: Counter[str] = stats["rating_sums"]
    positive_counts: Counter[str] = stats["positive_counts"]
    pair_counts: dict[str, Counter[str]] = stats["pair_counts"]
    max_count = max(rating_counts.values()) if rating_counts else 1
    payloads: list[dict] = []
    for item_id, item in raw_items.items():
        count = rating_counts[item_id]
        popularity = count / max_count if max_count else 0.0
        novelty = 1.0 - popularity
        avg_rating = rating_sums[item_id] / count if count else 3.0
        quality = (avg_rating - 1.0) / 4.0
        payloads.append(
            {
                "item_id": item_id,
                "title": item["title"],
                "genre": item["primary_genre"],
                "genres": list(item["genres"]),
                "popularity": round(popularity, 6),
                "novelty": round(novelty, 6),
                "quality": round(quality, 6),
                "neighbor_scores": _top_neighbors(item_id, positive_counts, pair_counts),
            }
        )
    payloads.sort(key=lambda item: item["item_id"])
    return payloads


def _top_neighbors(
    item_id: str,
    positive_counts: Counter[str],
    pair_counts: dict[str, Counter[str]],
) -> list[dict[str, float | str]]:
    neighbors = []
    item_positive = max(positive_counts[item_id], 1)
    for neighbor_id, pair_count in pair_counts[item_id].items():
        neighbor_positive = max(positive_counts[neighbor_id], 1)
        score = pair_count / math.sqrt(item_positive * neighbor_positive)
        neighbors.append(
            {
                "item_id": neighbor_id,
                "score": round(score, 6),
            }
        )
    neighbors.sort(key=lambda entry: float(entry["score"]), reverse=True)
    return neighbors[:40]


def _normalize_genre_name(name: str) -> str:
    lowered = name.lower()
    return GENRE_NORMALIZATION.get(lowered, lowered)


def _resolve_source_data_dir(
    output_dir: Path,
    data_dir: str | Path | None,
) -> tuple[Path, str]:
    if data_dir is not None:
        explicit_dir = Path(data_dir)
        if not explicit_dir.exists():
            raise FileNotFoundError(f"Explicit example data dir does not exist: {explicit_dir}")
        return explicit_dir, "explicit_dir"
    if DEFAULT_DATA_DIR.exists():
        return DEFAULT_DATA_DIR, "repo_copy"
    return _download_movielens_100k(output_dir / "source-data"), "downloaded"


def _download_movielens_100k(download_root: Path) -> Path:
    target_dir = download_root / "ml-100k"
    items_path = target_dir / "u.item"
    ratings_path = target_dir / "u.data"
    if items_path.exists() and ratings_path.exists():
        return target_dir

    download_root.mkdir(parents=True, exist_ok=True)
    with request.urlopen(MOVIELENS_100K_ZIP_URL, timeout=20.0) as response:
        archive = BytesIO(response.read())
    with zipfile.ZipFile(archive) as zipped:
        zipped.extractall(download_root)
    if not items_path.exists() or not ratings_path.exists():
        raise FileNotFoundError(
            "Downloaded MovieLens 100K archive did not contain the expected ml-100k files."
        )
    return target_dir
