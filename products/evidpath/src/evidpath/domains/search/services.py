"""Service and target wiring owned by the search domain."""

from __future__ import annotations

from contextlib import nullcontext
from urllib.parse import urlparse

from ...config import build_run_config, slugify_name
from ...schema import RegressionTarget, RunConfig
from .drivers import (
    HttpNativeSearchDriver,
    HttpNativeSearchDriverConfig,
    InProcessSearchDriver,
)
from .policy import SearchAgentPolicy, build_seeded_search_archetypes
from .reference_backend import ReferenceSearchBackend
from .scenarios import build_scenarios, resolve_built_in_search_scenarios


def open_search_service_context(run_config: RunConfig):
    """Open the search service context for one run config."""
    if run_config.rollout.driver_kind == "in_process":
        return nullcontext(
            (None, {"service_kind": "in_process", "service_metadata_status": "in_process"})
        )
    if run_config.rollout.driver_kind == "http_schema_mapped":
        base_url = str((run_config.rollout.driver_config or {}).get("base_url", ""))
        return nullcontext(
            (
                base_url.rstrip("/") or None,
                {
                    "service_kind": "http_schema_mapped",
                    "service_metadata_status": "not_provided",
                },
            )
        )
    if run_config.rollout.driver_kind == "http_native_external":
        base_url = str((run_config.rollout.driver_config or {}).get("base_url", ""))
        return _external_context(base_url)
    if run_config.rollout.adapter_base_url is not None:
        return _external_context(run_config.rollout.adapter_base_url)
    return nullcontext(
        (
            None,
            {"service_kind": "reference_search", "service_metadata_status": "fixture"},
        )
    )


def build_search_target_identity(target: RegressionTarget) -> str:
    """Build a short stable identity for search compare and audit targets."""
    if target.driver_kind == "http_native_external":
        base_url = str(target.driver_config.get("base_url", ""))
        normalized_url = base_url.rstrip("/")
        parsed = urlparse(normalized_url)
        label = slugify_name(parsed.netloc or parsed.path or "external")
        raw_identity = normalized_url
        prefix = "url"
    elif target.driver_kind == "http_native_reference":
        label = "reference-search"
        raw_identity = "reference_search"
        prefix = "reference"
    elif target.driver_kind == "in_process":
        import_path = str(target.driver_config.get("import_path", "in_process"))
        label = slugify_name(import_path)
        raw_identity = import_path
        prefix = "in-proc"
    elif target.driver_kind == "http_schema_mapped":
        base_url = str(target.driver_config.get("base_url", "")).rstrip("/")
        parsed = urlparse(base_url)
        label = slugify_name(parsed.netloc or parsed.path or "schema-mapped")
        raw_identity = base_url
        prefix = "schema"
    else:
        raise NotImplementedError(f"Unsupported search driver kind: {target.driver_kind}")
    return f"{prefix}-{label}-{_short_hash(raw_identity)}"


def build_search_target_audit_kwargs(target: RegressionTarget) -> dict[str, object]:
    """Translate a regression target into audit-time service overrides."""
    if target.driver_kind == "http_native_reference":
        return {"service_mode": "reference"}
    if target.driver_kind == "http_native_external":
        base_url = target.driver_config.get("base_url")
        if not isinstance(base_url, str) or not base_url:
            raise ValueError("http_native_external targets require driver_config.base_url.")
        return {"adapter_base_url": base_url}
    if target.driver_kind in {"in_process", "http_schema_mapped"}:
        return {
            "driver_kind": target.driver_kind,
            "driver_config": dict(target.driver_config),
        }
    raise NotImplementedError(f"Unsupported search driver kind: {target.driver_kind}")


def check_search_target(
    base_url: str,
    timeout_seconds: float,
) -> dict[str, str | int | float]:
    """Probe a native search endpoint through the public contract before a real run."""
    driver = HttpNativeSearchDriver(
        HttpNativeSearchDriverConfig(base_url=base_url, timeout_seconds=timeout_seconds)
    )
    health = driver.check_health()
    metadata = driver.get_service_metadata_strict()
    scenario_config = resolve_built_in_search_scenarios(("navigational-query",))[0]
    run_config = build_run_config(
        seed=7,
        scenarios=(scenario_config,),
        agent_seeds=(build_seeded_search_archetypes()[0],),
        service_mode="external",
        adapter_base_url=base_url,
        run_name="evidpath-search-target-check",
    )
    scenario = build_scenarios((scenario_config,))[0]
    agent_seed = run_config.agent_seeds[0]
    observation = scenario.initialize(agent_seed, run_config)
    state = SearchAgentPolicy().initialize_state(agent_seed, observation.scenario_context)
    ranked_list = driver.get_ranked_list(state, observation, scenario_config)
    if not ranked_list.items:
        raise RuntimeError(
            f"Search target returned an empty result list during contract validation: {base_url}."
        )
    top_item = ranked_list.items[0]
    return {
        "target_url": base_url.rstrip("/"),
        "health_status": str(health.get("status", "ok")),
        "probe_status": "ok",
        "probe_scenario": scenario_config.name,
        "probe_agent": agent_seed.agent_id,
        "result_count": len(ranked_list.items),
        "top_result_id": top_item.item_id,
        "top_result_title": top_item.title,
        **metadata,
    }


def build_reference_search_driver() -> InProcessSearchDriver:
    """Return the deterministic in-process reference search driver."""
    return InProcessSearchDriver.from_callable(
        ReferenceSearchBackend.from_artifacts(),
        backend_name="reference-search",
    )


def _short_hash(value: str) -> str:
    from hashlib import sha1

    return sha1(value.encode("utf-8")).hexdigest()[:8]


def _external_context(base_url: str):
    normalized_url = base_url.rstrip("/")
    parsed = urlparse(normalized_url)
    return nullcontext(
        (
            normalized_url or None,
            {
                "service_kind": "external",
                "target_endpoint_host": parsed.netloc or parsed.path,
                "target_endpoint_scheme": parsed.scheme or "http",
                "service_metadata_status": "not_provided",
            },
        )
    )
