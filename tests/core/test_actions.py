"""Tests for actions and the run result."""

from __future__ import annotations

from custom_components.halltasker.core.actions import Action, RunResult, action_to_dict
from custom_components.halltasker.core.model import CanonicalTask


def test_minimal_action_serializes_without_none_fields() -> None:
    action = Action(kind="tombstone", node="todo.a", canonical_id="c1")
    assert action_to_dict(action) == {"kind": "tombstone", "node": "todo.a", "canonical_id": "c1"}


def test_full_action_serializes_every_set_field() -> None:
    action = Action(
        kind="update",
        node="todo.b",
        canonical_id="c1",
        task=CanonicalTask(title="x"),
        external_id="uid-1",
        changed=frozenset({"title", "status"}),
        reason="changed on A",
    )
    data = action_to_dict(action)
    assert data["task"] == CanonicalTask(title="x").to_dict()
    assert data["external_id"] == "uid-1"
    assert data["changed"] == ["status", "title"]
    assert data["reason"] == "changed on A"
    assert None not in data.values()


def test_run_result_defaults_are_empty() -> None:
    result = RunResult(ok=True, error=None)
    assert result.actions_planned == []
    assert result.actions_applied == []
    assert result.actions_failed == []
    assert result.links == 0
