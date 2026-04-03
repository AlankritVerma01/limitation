"""Configuration models and JSON loading for recommender evaluation runs."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class DatasetSpec:
    type: str
    name: str
    dataset_id: str
    path: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ModelSpec:
    type: str
    label: str
    params: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "label": self.label,
            "params": dict(self.params),
        }


@dataclass(frozen=True)
class EvaluationConfig:
    dataset: DatasetSpec
    baseline_model: ModelSpec
    candidate_model: ModelSpec
    output_dir: str | None = None
    artifact_mode: str = "default"
    seed: int = 0
    top_k: int = 10
    session_steps: int = 4
    slate_size: int = 10
    choice_pool: int = 5
    positive_rating_threshold: int = 4
    min_user_ratings: int = 10
    min_user_positive_ratings: int = 5
    test_holdout_positive_count: int = 2

    def as_dict(self) -> dict[str, Any]:
        return {
            "dataset": self.dataset.as_dict(),
            "baseline_model": self.baseline_model.as_dict(),
            "candidate_model": self.candidate_model.as_dict(),
            "output_dir": self.output_dir,
            "artifact_mode": self.artifact_mode,
            "seed": self.seed,
            "top_k": self.top_k,
            "session_steps": self.session_steps,
            "slate_size": self.slate_size,
            "choice_pool": self.choice_pool,
            "positive_rating_threshold": self.positive_rating_threshold,
            "min_user_ratings": self.min_user_ratings,
            "min_user_positive_ratings": self.min_user_positive_ratings,
            "test_holdout_positive_count": self.test_holdout_positive_count,
        }


@dataclass(frozen=True)
class CanonicalRunConfig(EvaluationConfig):
    pass


def _require_mapping(payload: Any, context: str) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError(f"{context} must be a JSON object.")
    return payload


def _require_string(payload: dict[str, Any], key: str, context: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{context}.{key} must be a non-empty string.")
    return value


def _optional_string(payload: dict[str, Any], key: str) -> str | None:
    value = payload.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} must be a non-empty string when provided.")
    return value


def _optional_int(payload: dict[str, Any], key: str, default: int) -> int:
    value = payload.get(key, default)
    if not isinstance(value, int):
        raise ValueError(f"{key} must be an integer.")
    return value


def _optional_mapping(
    payload: dict[str, Any],
    key: str,
    *,
    context: str | None = None,
) -> dict[str, Any]:
    value = payload.get(key, {})
    if not isinstance(value, dict):
        label = context or key
        raise ValueError(f"{label} must be a JSON object when provided.")
    return dict(value)


def _optional_artifact_mode(payload: dict[str, Any]) -> str:
    value = payload.get("artifact_mode", "default")
    if value not in {"default", "canonical"}:
        raise ValueError("artifact_mode must be either 'default' or 'canonical'.")
    return value


def _resolve_optional_path(path_value: str | None, base_dir: Path) -> str | None:
    if path_value is None:
        return None
    path = Path(path_value)
    if not path.is_absolute():
        path = (base_dir / path).resolve()
    return str(path)


def evaluation_config_from_dict(
    payload: dict[str, Any],
    *,
    base_dir: str | Path | None = None,
) -> EvaluationConfig:
    base_path = Path(base_dir).resolve() if base_dir is not None else Path.cwd()
    root = _require_mapping(payload, "config")
    dataset_payload = _require_mapping(root.get("dataset"), "dataset")
    baseline_payload = _require_mapping(root.get("baseline_model"), "baseline_model")
    candidate_payload = _require_mapping(root.get("candidate_model"), "candidate_model")

    dataset = DatasetSpec(
        type=_require_string(dataset_payload, "type", "dataset"),
        name=_require_string(dataset_payload, "name", "dataset"),
        dataset_id=_require_string(dataset_payload, "dataset_id", "dataset"),
        path=_resolve_optional_path(
            _optional_string(dataset_payload, "path"),
            base_path,
        ),
    )
    baseline_model = ModelSpec(
        type=_require_string(baseline_payload, "type", "baseline_model"),
        label=_require_string(baseline_payload, "label", "baseline_model"),
        params=_optional_mapping(
            baseline_payload,
            "params",
            context="baseline_model.params",
        ),
    )
    candidate_model = ModelSpec(
        type=_require_string(candidate_payload, "type", "candidate_model"),
        label=_require_string(candidate_payload, "label", "candidate_model"),
        params=_optional_mapping(
            candidate_payload,
            "params",
            context="candidate_model.params",
        ),
    )

    output_dir = _resolve_optional_path(_optional_string(root, "output_dir"), base_path)

    return EvaluationConfig(
        dataset=dataset,
        baseline_model=baseline_model,
        candidate_model=candidate_model,
        output_dir=output_dir,
        artifact_mode=_optional_artifact_mode(root),
        seed=_optional_int(root, "seed", 0),
        top_k=_optional_int(root, "top_k", 10),
        session_steps=_optional_int(root, "session_steps", 4),
        slate_size=_optional_int(root, "slate_size", 10),
        choice_pool=_optional_int(root, "choice_pool", 5),
        positive_rating_threshold=_optional_int(
            root, "positive_rating_threshold", 4
        ),
        min_user_ratings=_optional_int(root, "min_user_ratings", 10),
        min_user_positive_ratings=_optional_int(
            root, "min_user_positive_ratings", 5
        ),
        test_holdout_positive_count=_optional_int(
            root, "test_holdout_positive_count", 2
        ),
    )


def load_evaluation_config(path: str | Path) -> EvaluationConfig:
    config_path = Path(path).resolve()
    payload = json.loads(config_path.read_text())
    return evaluation_config_from_dict(payload, base_dir=config_path.parent)
