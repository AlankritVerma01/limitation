"""In-process driver for the recommender domain."""

from __future__ import annotations

import importlib
from collections.abc import Mapping

from ....contracts.recommender import (
    RecommenderRequest,
    RecommenderResponse,
)
from ....schema import (
    AgentState,
    Observation,
    ScenarioConfig,
    Slate,
)
from ._config import InProcessDriverConfig


class InProcessRecommenderDriver:
    """Calls a Python recommender imported by entry-point path."""

    def __init__(self, config: InProcessDriverConfig) -> None:
        target = self._resolve_import(config.import_path)
        if isinstance(target, type):
            self._impl = target(**dict(config.init_kwargs))
            self._call_predict = self._impl.predict
        elif callable(target):
            if config.init_kwargs:
                raise ValueError(
                    f"`init_kwargs` provided but `{config.import_path}` resolved to a function."
                )
            self._impl = target
            self._call_predict = target
        else:
            raise TypeError(
                f"`{config.import_path}` resolved to {type(target).__name__}; expected a callable or class."
            )
        self._backend_name = config.backend_name or config.import_path

    def get_ranked_list(
        self,
        agent_state: AgentState,
        observation: Observation,
        scenario_config: ScenarioConfig,
    ) -> Slate:
        adapter_request = RecommenderRequest(
            request_id=f"{agent_state.agent_id}-{observation.scenario_context.scenario_id or observation.scenario_context.scenario_name}-{observation.step_index}",
            agent_id=agent_state.agent_id,
            scenario_name=observation.scenario_context.scenario_name,
            scenario_profile=observation.scenario_context.runtime_profile,
            step_index=observation.step_index,
            history_depth=observation.scenario_context.history_depth,
            history_item_ids=agent_state.history_item_ids,
            recent_exposure_ids=agent_state.recent_exposure_ids,
            preferred_genres=agent_state.preferred_genres,
        )
        adapter_response = self._call_predict(adapter_request)
        if not isinstance(adapter_response, RecommenderResponse):
            raise TypeError(
                f"In-process recsys returned {type(adapter_response).__name__}; expected RecommenderResponse."
            )
        return Slate(
            slate_id=f"{scenario_config.scenario_id or scenario_config.name}-{agent_state.agent_id}-{observation.step_index}",
            step_index=observation.step_index,
            items=adapter_response.items,
        )

    def get_slate(
        self,
        agent_state: AgentState,
        observation: Observation,
        scenario_config: ScenarioConfig,
    ) -> Slate:
        """Return a recommender slate for compatibility with existing callers."""
        return self.get_ranked_list(agent_state, observation, scenario_config)

    def get_service_metadata(self) -> dict[str, str | int | float]:
        base: dict[str, str | int | float] = {
            "service_kind": "in_process",
            "backend_name": self._backend_name,
        }
        for key, value in self._collect_user_metadata().items():
            if isinstance(value, (str, int, float)):
                base[key] = value
        return base

    def get_service_metadata_strict(self) -> dict[str, str | int | float]:
        """Return metadata with the strict HTTP-driver-compatible method name."""
        return self.get_service_metadata()

    def check_health(self) -> dict[str, str | int | float]:
        """Return the in-process health payload."""
        return {"status": "ok"}

    def _collect_user_metadata(self) -> Mapping[str, object]:
        impl = self._impl
        metadata_fn = getattr(impl, "get_service_metadata", None)
        if callable(metadata_fn):
            payload = metadata_fn()
            if isinstance(payload, Mapping):
                return payload
        service_metadata = getattr(impl, "service_metadata", None)
        if isinstance(service_metadata, Mapping):
            return service_metadata
        return {}

    @staticmethod
    def _resolve_import(import_path: str):
        module_path, _, attr = import_path.partition(":")
        try:
            module = importlib.import_module(module_path)
        except ImportError as exc:
            raise ImportError(f"Module `{module_path}` could not be imported: {exc}") from exc
        try:
            return getattr(module, attr)
        except AttributeError:
            public_names = sorted(name for name in dir(module) if not name.startswith("_"))
            raise ImportError(
                f"Module `{module_path}` has no attribute `{attr}`. Public names: {public_names!r}."
            ) from None

    @classmethod
    def from_callable(
        cls,
        target: object,
        *,
        backend_name: str | None = None,
    ) -> "InProcessRecommenderDriver":
        """Construct an in-process driver from a callable, class, or instance."""
        instance = cls.__new__(cls)
        if isinstance(target, type):
            impl = target()
            call_predict = impl.predict
            resolved_backend = backend_name or target.__name__
        elif callable(target) and not hasattr(target, "predict"):
            impl = target
            call_predict = target
            resolved_backend = backend_name or getattr(target, "__name__", "<inline>")
        elif hasattr(target, "predict") and callable(target.predict):
            impl = target
            call_predict = target.predict
            resolved_backend = backend_name or type(target).__name__
        else:
            raise TypeError(
                f"`{type(target).__name__}` is not a callable, class, or class instance with .predict."
            )
        instance._impl = impl
        instance._call_predict = call_predict
        instance._backend_name = resolved_backend
        return instance
