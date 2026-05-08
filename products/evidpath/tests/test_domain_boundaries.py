"""Architecture boundary tests for shared/domain separation."""

from __future__ import annotations

from pathlib import Path

from evidpath import RankedItem, RankedList, TraceScore, trace_metric

_ROOT = Path(__file__).resolve().parents[1] / "src" / "evidpath"
_SHARED_MODULES = (
    _ROOT / "adapters" / "base.py",
    _ROOT / "agents" / "base.py",
    _ROOT / "analysis" / "base.py",
    _ROOT / "judges" / "base.py",
    _ROOT / "rollout" / "engine.py",
    _ROOT / "scenarios" / "base.py",
)


def test_shared_runtime_modules_do_not_import_recommender_domain() -> None:
    for path in _SHARED_MODULES:
        source = path.read_text(encoding="utf-8")
        assert "evidpath.domains.recommender" not in source
        assert "domains.recommender" not in source


def test_shared_adapter_protocol_uses_ranked_list_vocabulary() -> None:
    source = (_ROOT / "adapters" / "base.py").read_text(encoding="utf-8")
    assert "get_ranked_list" in source
    assert "def get_slate" not in source
    assert "RankedList" in source


def test_shared_ranked_output_contracts_are_exported() -> None:
    assert RankedItem.__name__ == "RankedItem"
    assert RankedList.__name__ == "RankedList"


def test_trace_metric_reads_common_and_domain_metrics() -> None:
    score = TraceScore(
        trace_id="t1",
        scenario_name="s1",
        archetype_label="a1",
        steps_completed=1,
        abandoned=False,
        click_count=0,
        session_utility=0.5,
        repetition=0.0,
        concentration=0.0,
        engagement=0.0,
        frustration=0.0,
        domain_metrics={"freshness_percentile": 0.75},
    )
    assert trace_metric(score, "session_utility") == 0.5
    assert trace_metric(score, "freshness_percentile") == 0.75
