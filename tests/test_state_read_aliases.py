from __future__ import annotations

from pathlib import Path

import pytest

from coded_tools.state_read import StateRead


@pytest.mark.parametrize(
    ("requested", "canonical"),
    [
        ("economics", "economics_all"),
        ("map_layout", "status_layout"),
        ("status_staffing", "status_staff"),
    ],
)
def test_observed_safe_aliases_resolve(tmp_path: Path, requested: str, canonical: str) -> None:
    target = tmp_path / f"{canonical}.txt"
    target.write_text("verified\n", encoding="utf-8")

    result = StateRead().invoke({"name": requested, "name_map": {canonical: str(target)}}, {})

    assert isinstance(result, dict)
    assert result["name"] == canonical
    assert result["requested_name"] == requested
    assert result["alias_resolved"] is True
    assert result["content"] == "verified\n"


def test_alias_does_not_expand_operator_map(tmp_path: Path) -> None:
    target = tmp_path / "other.txt"
    target.write_text("nope\n", encoding="utf-8")

    result = StateRead().invoke({"name": "economics", "name_map": {"status_layout": str(target)}}, {})

    assert isinstance(result, str)
    assert result.startswith("ERROR: unknown_name: 'economics'")


@pytest.mark.parametrize("logical_name", ["status_full", "status_champion"])
def test_complete_status_reads_are_not_silently_truncated(tmp_path: Path, logical_name: str) -> None:
    target = tmp_path / f"{logical_name}.json"
    content = "x" * (StateRead.DEFAULT_MAX_CHARS + 5000)
    target.write_text(content, encoding="utf-8")

    result = StateRead().invoke({"name": logical_name, "name_map": {logical_name: str(target)}}, {})

    assert isinstance(result, dict)
    assert result["content"] == content
    assert result["truncated"] is False
