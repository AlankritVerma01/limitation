"""Tests for the in-process recommender driver."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from types import ModuleType

import pytest
from evidpath.artifacts.run_manifest import write_run_manifest
from evidpath.audit import execute_domain_audit, write_run_artifacts
from evidpath.domains.recommender import CATALOG
from evidpath.domains.recommender.drivers import (
    InProcessDriverConfig,
    InProcessRecommenderDriver,
)
from evidpath.schema import (
    AdapterResponse,
    AgentState,
    Observation,
    ScenarioConfig,
    ScenarioContext,
    SlateItem,
)


def test_in_process_driver_config_from_dict() -> None:
    config = InProcessDriverConfig.from_dict(
        {
            "import_path": "myproject.recsys:Model",
            "init_kwargs": {"top_k": 5},
            "backend_name": "local-model",
        }
    )

    assert config.import_path == "myproject.recsys:Model"
    assert config.init_kwargs == {"top_k": 5}
    assert config.backend_name == "local-model"


def test_in_process_driver_config_rejects_invalid_import_path() -> None:
    with pytest.raises(ValueError, match="import_path"):
        InProcessDriverConfig(import_path="missing_colon")


def test_in_process_driver_calls_function() -> None:
    def predict(request):
        return AdapterResponse(
            request_id=request.request_id,
            items=(
                SlateItem(
                    item_id="x1",
                    title="Item",
                    genre="action",
                    score=0.9,
                    rank=1,
                    popularity=0.5,
                    novelty=0.3,
                ),
            ),
        )

    _register_module("evidpath_test_in_process_function", {"predict": predict})
    driver = InProcessRecommenderDriver(
        InProcessDriverConfig(import_path="evidpath_test_in_process_function:predict")
    )

    slate = driver.get_slate(_dummy_state(), _dummy_observation(), _dummy_scenario())

    assert slate.items[0].item_id == "x1"
    assert driver.check_health() == {"status": "ok"}


def test_in_process_driver_calls_class_predict() -> None:
    class FakeRecsys:
        service_metadata = {"model_id": "class-v1"}

        def __init__(self, base_score: float) -> None:
            self.base_score = base_score

        def predict(self, request):
            return AdapterResponse(
                request_id=request.request_id,
                items=(
                    SlateItem(
                        item_id="class-x1",
                        title="ClassItem",
                        genre="action",
                        score=self.base_score,
                        rank=1,
                        popularity=0.5,
                        novelty=0.3,
                    ),
                ),
            )

    _register_module("evidpath_test_in_process_class", {"FakeRecsys": FakeRecsys})
    driver = InProcessRecommenderDriver(
        InProcessDriverConfig(
            import_path="evidpath_test_in_process_class:FakeRecsys",
            init_kwargs={"base_score": 0.77},
            backend_name="custom",
        )
    )

    slate = driver.get_slate(_dummy_state(), _dummy_observation(), _dummy_scenario())
    metadata = driver.get_service_metadata()

    assert slate.items[0].score == 0.77
    assert metadata["service_kind"] == "in_process"
    assert metadata["backend_name"] == "custom"
    assert metadata["model_id"] == "class-v1"


def test_in_process_driver_runs_through_audit(tmp_path: Path) -> None:
    def predict(request):
        items = tuple(
            SlateItem(
                item_id=item.item_id,
                title=item.title,
                genre=item.genre,
                score=0.9 - 0.1 * index,
                rank=index + 1,
                popularity=item.popularity,
                novelty=item.novelty,
            )
            for index, item in enumerate(CATALOG[:5])
        )
        return AdapterResponse(request_id=request.request_id, items=items)

    _register_module("evidpath_test_in_process_smoke", {"predict": predict})
    run_result = execute_domain_audit(
        domain_name="recommender",
        seed=11,
        output_dir=str(tmp_path / "audit"),
        scenario_names=("returning-user-home-feed",),
        driver_kind="in_process",
        driver_config={"import_path": "evidpath_test_in_process_smoke:predict"},
    )
    paths = write_run_artifacts(run_result)
    manifest_path = write_run_manifest(
        run_result,
        artifact_paths=paths,
        workflow_type="audit",
    )
    manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))

    assert manifest["service"]["target_driver_kind"] == "in_process"
    assert manifest["service"]["target_driver_config"]["import_path"].endswith(":predict")
    assert run_result.trace_scores


def _register_module(name: str, attrs: dict[str, object]) -> None:
    module = ModuleType(name)
    for key, value in attrs.items():
        setattr(module, key, value)
    sys.modules[name] = module


def _dummy_state() -> AgentState:
    return AgentState(
        agent_id="agent-1",
        archetype_label="archetype",
        step_index=0,
        click_threshold=0.5,
        preferred_genres=("action",),
        popularity_preference=0.5,
        novelty_preference=0.4,
        repetition_tolerance=0.6,
        sparse_history_confidence=0.5,
        abandonment_sensitivity=0.2,
        engagement_baseline=0.5,
        quality_sensitivity=0.6,
        repeat_exposure_penalty=0.1,
        novelty_fatigue=0.1,
        frustration_recovery=0.3,
        history_reliance=0.4,
        skip_tolerance=1,
        abandonment_threshold=0.85,
        patience_remaining=2,
        last_action="start",
        history_item_ids=(),
    )


def _dummy_observation() -> Observation:
    return Observation(
        session_id="s",
        step_index=0,
        max_steps=2,
        available_actions=("click", "skip"),
        scenario_context=ScenarioContext(
            scenario_name="scenario-1",
            history_depth=0,
            history_item_ids=(),
            description="",
            scenario_id="scenario-1",
            runtime_profile="",
            context_hint="",
        ),
    )


def _dummy_scenario() -> ScenarioConfig:
    return ScenarioConfig(
        name="scenario-1",
        max_steps=2,
        allowed_actions=("click", "skip"),
        history_depth=0,
        description="",
        scenario_id="scenario-1",
        test_goal="",
        runtime_profile="",
        context_hint="",
    )
