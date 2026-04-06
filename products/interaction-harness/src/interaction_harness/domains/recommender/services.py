"""Service and target wiring owned by the recommender domain."""

from __future__ import annotations

from contextlib import contextmanager, nullcontext
from pathlib import Path
from urllib.parse import urlparse

from ...config import slugify_name
from ...schema import RegressionTarget, RunConfig
from ...services.mock_recommender import run_mock_recommender_service
from ...services.reference_artifacts import ensure_reference_artifacts
from ...services.reference_recommender import run_reference_recommender_service


def open_recommender_service_context(run_config: RunConfig):
    """Open the correct recommender service context for one run config."""
    if run_config.rollout.adapter_base_url is not None:
        return nullcontext((run_config.rollout.adapter_base_url, {}))
    if run_config.rollout.service_mode == "mock":
        return _mock_service_context()
    artifact_path = ensure_reference_artifacts(run_config.rollout.service_artifact_dir)
    return run_reference_recommender_service(str(artifact_path.parent))


def build_recommender_target_identity(target: RegressionTarget) -> str:
    """Build a short stable identity for recommender compare and audit targets."""
    if target.mode == "external_url":
        normalized_url = (target.adapter_base_url or "").rstrip("/")
        parsed = urlparse(normalized_url)
        label = slugify_name(parsed.netloc or parsed.path or "external")
        raw_identity = normalized_url
        prefix = "url"
    else:
        artifact_dir = str(Path(target.service_artifact_dir or "")).rstrip("/")
        label = slugify_name(Path(artifact_dir).name or "artifact")
        raw_identity = artifact_dir
        prefix = "artifact"
    return f"{prefix}-{label}-{_short_hash(raw_identity)}"


def build_recommender_target_audit_kwargs(target: RegressionTarget) -> dict[str, object]:
    """Translate a regression target into audit-time service overrides."""
    if target.mode == "reference_artifact":
        if not target.service_artifact_dir:
            raise ValueError("reference_artifact targets require service_artifact_dir.")
        return {
            "service_mode": "reference",
            "service_artifact_dir": target.service_artifact_dir,
        }
    if target.mode == "external_url":
        if not target.adapter_base_url:
            raise ValueError("external_url targets require adapter_base_url.")
        return {"adapter_base_url": target.adapter_base_url}
    raise NotImplementedError(f"Unsupported regression target mode: {target.mode}")


@contextmanager
def _mock_service_context():
    """Normalize the mock service into the shared `(base_url, metadata)` shape."""
    with run_mock_recommender_service() as base_url:
        yield base_url, {}


def _short_hash(value: str) -> str:
    from hashlib import sha1

    return sha1(value.encode("utf-8")).hexdigest()[:8]
