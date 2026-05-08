"""Architecture boundary tests for shared/domain separation."""

from __future__ import annotations

from pathlib import Path

from evidpath import RankedItem, RankedList

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
