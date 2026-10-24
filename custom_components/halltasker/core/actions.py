"""Actions and the result of one pair cycle."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from .model import CanonicalTask

ActionKind = Literal["create", "update", "complete", "delete", "soft_delete", "link", "tombstone"]


@dataclass(frozen=True)
class Action:
    """A planned change to one node; the plan is serializable for sensors and services."""

    kind: ActionKind
    node: str
    canonical_id: str
    task: CanonicalTask | None = None
    external_id: str | None = None
    changed: frozenset[str] = frozenset()
    reason: str = ""


@dataclass(frozen=True)
class RunResult:
    """The outcome of one run of a pair."""

    ok: bool
    error: str | None
    actions_planned: list[Action] = field(default_factory=list)
    actions_applied: list[Action] = field(default_factory=list)
    actions_failed: list[tuple[Action, str]] = field(default_factory=list)
    links: int = 0


def action_to_dict(action: Action) -> dict[str, Any]:
    """Serialize an action to a JSON-compatible dict without None fields."""
    data: dict[str, Any] = {
        "kind": action.kind,
        "node": action.node,
        "canonical_id": action.canonical_id,
    }
    if action.task is not None:
        data["task"] = action.task.to_dict()
    if action.external_id is not None:
        data["external_id"] = action.external_id
    if action.changed:
        data["changed"] = sorted(action.changed)
    if action.reason:
        data["reason"] = action.reason
    return data
