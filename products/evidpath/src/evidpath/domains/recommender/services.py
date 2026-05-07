"""Service and target wiring owned by the recommender domain."""

from __future__ import annotations

from contextlib import contextmanager, nullcontext
from pathlib import Path
from urllib.parse import urlparse

from ...config import build_run_config, slugify_name
from ...schema import RegressionTarget, RunConfig
from .drivers import HttpNativeDriverConfig, HttpNativeRecommenderDriver
from .mock_recommender import run_mock_recommender_service
from .policy import build_seeded_archetypes, initial_state_from_seed
from .reference_artifacts import ensure_reference_artifacts
from .reference_recommender import run_reference_recommender_service
from .scenarios import build_scenarios, resolve_built_in_recommender_scenarios


def open_recommender_service_context(run_config: RunConfig):
    """Open the correct recommender service context for one run config."""
    if run_config.rollout.adapter_base_url is not None:
        normalized_url = run_config.rollout.adapter_base_url.rstrip("/")
        parsed = urlparse(normalized_url)
        return nullcontext(
            (
                normalized_url,
                {
                    "service_kind": "external",
                    "target_endpoint_host": parsed.netloc or parsed.path,
                    "target_endpoint_scheme": parsed.scheme or "http",
                    "service_metadata_status": "not_provided",
                },
            )
        )
    if run_config.rollout.service_mode == "mock":
        return _mock_service_context()
    artifact_path = ensure_reference_artifacts(run_config.rollout.service_artifact_dir)
    return run_reference_recommender_service(str(artifact_path.parent))


def build_recommender_target_identity(target: RegressionTarget) -> str:
    """Build a short stable identity for recommender compare and audit targets."""
    if target.driver_kind == "http_native_external":
        base_url = str(target.driver_config.get("base_url", ""))
        normalized_url = base_url.rstrip("/")
        parsed = urlparse(normalized_url)
        label = slugify_name(parsed.netloc or parsed.path or "external")
        raw_identity = normalized_url
        prefix = "url"
    elif target.driver_kind == "http_native_reference":
        artifact_dir = str(target.driver_config.get("artifact_dir", "")).rstrip("/")
        label = slugify_name(Path(artifact_dir).name or "artifact")
        raw_identity = artifact_dir
        prefix = "artifact"
    elif target.driver_kind == "http_native_mock":
        label = "mock"
        raw_identity = "mock"
        prefix = "mock"
    else:
        raise NotImplementedError(
            f"Unsupported recommender driver kind: {target.driver_kind}"
        )
    return f"{prefix}-{label}-{_short_hash(raw_identity)}"


def build_recommender_target_audit_kwargs(target: RegressionTarget) -> dict[str, object]:
    """Translate a regression target into audit-time service overrides."""
    if target.driver_kind == "http_native_reference":
        artifact_dir = target.driver_config.get("artifact_dir")
        if not isinstance(artifact_dir, str) or not artifact_dir:
            raise ValueError(
                "http_native_reference targets require driver_config.artifact_dir."
            )
        return {
            "service_mode": "reference",
            "service_artifact_dir": artifact_dir,
        }
    if target.driver_kind == "http_native_external":
        base_url = target.driver_config.get("base_url")
        if not isinstance(base_url, str) or not base_url:
            raise ValueError(
                "http_native_external targets require driver_config.base_url."
            )
        return {"adapter_base_url": base_url}
    if target.driver_kind == "http_native_mock":
        return {"service_mode": "mock"}
    raise NotImplementedError(
        f"Unsupported recommender driver kind: {target.driver_kind}"
    )


def check_recommender_target(
    base_url: str,
    timeout_seconds: float,
) -> dict[str, str | int | float]:
    """Probe a recommender endpoint through the public contract before a real run."""
    driver = HttpNativeRecommenderDriver(
        HttpNativeDriverConfig(base_url=base_url, timeout_seconds=timeout_seconds)
    )
    health = driver.check_health()
    metadata = driver.get_service_metadata_strict()
    scenario_config = resolve_built_in_recommender_scenarios(
        ("returning-user-home-feed",)
    )[0]
    run_config = build_run_config(
        seed=7,
        scenarios=(scenario_config,),
        agent_seeds=(build_seeded_archetypes()[0],),
        service_mode="external",
        adapter_base_url=base_url,
        run_name="evidpath-target-check",
    )
    scenario = build_scenarios((scenario_config,))[0]
    agent_seed = run_config.agent_seeds[0]
    observation = scenario.initialize(agent_seed, run_config)
    state = initial_state_from_seed(agent_seed, observation.scenario_context)
    slate = driver.get_slate(state, observation, scenario_config)
    if not slate.items:
        raise RuntimeError(
            f"Recommender target returned an empty slate during contract validation: {base_url}."
        )
    top_item = slate.items[0]
    return {
        "target_url": base_url.rstrip("/"),
        "health_status": str(health.get("status", "ok")),
        "probe_status": "ok",
        "probe_scenario": scenario_config.name,
        "probe_agent": agent_seed.agent_id,
        "slate_item_count": len(slate.items),
        "top_item_id": top_item.item_id,
        "top_item_title": top_item.title,
        **metadata,
    }


@contextmanager
def _mock_service_context():
    """Normalize the mock service into the shared `(base_url, metadata)` shape."""
    with run_mock_recommender_service() as base_url:
        yield base_url, {
            "service_kind": "mock",
            "service_metadata_status": "fixture",
        }


def _short_hash(value: str) -> str:
    from hashlib import sha1

    return sha1(value.encode("utf-8")).hexdigest()[:8]
