"""In-process driver for the search domain."""

from __future__ import annotations

import importlib
from collections.abc import Mapping

from ....schema import AgentState, Observation, RankedList, ScenarioConfig
from ..contracts import (
    SearchResponse,
    build_search_request,
    ranked_list_id,
    response_to_ranked_list,
)
from ._config import InProcessSearchDriverConfig


class InProcessSearchDriver:
    """Calls a Python search backend imported by entry-point path."""

    def __init__(self, config: InProcessSearchDriverConfig) -> None:
        target = self._resolve_import(config.import_path)
        if isinstance(target, type):
            self._impl = target(**dict(config.init_kwargs))
            self._call_search = self._resolve_search_callable(self._impl)
        elif callable(target):
            if config.init_kwargs:
                raise ValueError(
                    f"`init_kwargs` provided but `{config.import_path}` resolved to a function."
                )
            self._impl = target
            self._call_search = target
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
    ) -> RankedList:
        search_request = build_search_request(agent_state, observation, scenario_config)
        search_response = self._call_search(search_request)
        if not isinstance(search_response, SearchResponse):
            raise TypeError(
                f"In-process search returned {type(search_response).__name__}; expected SearchResponse."
            )
        return response_to_ranked_list(
            search_response,
            ranked_list_id=ranked_list_id(agent_state, observation, scenario_config),
            step_index=observation.step_index,
        )

    def get_slate(
        self,
        agent_state: AgentState,
        observation: Observation,
        scenario_config: ScenarioConfig,
    ) -> RankedList:
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
        return self.get_service_metadata()

    def check_health(self) -> dict[str, str | int | float]:
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
    def _resolve_search_callable(target):
        search_fn = getattr(target, "search", None)
        if callable(search_fn):
            return search_fn
        predict_fn = getattr(target, "predict", None)
        if callable(predict_fn):
            return predict_fn
        raise TypeError(
            f"`{type(target).__name__}` is not a class instance with .search or .predict."
        )

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
    ) -> "InProcessSearchDriver":
        instance = cls.__new__(cls)
        if isinstance(target, type):
            impl = target()
            call_search = cls._resolve_search_callable(impl)
            resolved_backend = backend_name or target.__name__
        elif callable(target) and not (
            hasattr(target, "search") or hasattr(target, "predict")
        ):
            impl = target
            call_search = target
            resolved_backend = backend_name or getattr(target, "__name__", "<inline>")
        elif hasattr(target, "search") or hasattr(target, "predict"):
            impl = target
            call_search = cls._resolve_search_callable(target)
            resolved_backend = backend_name or type(target).__name__
        else:
            raise TypeError(
                f"`{type(target).__name__}` is not a callable, class, or class instance with .search/.predict."
            )
        instance._impl = impl
        instance._call_search = call_search
        instance._backend_name = resolved_backend
        return instance
