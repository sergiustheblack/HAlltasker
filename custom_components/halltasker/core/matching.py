"""Linking heuristic for the initial sync."""

from __future__ import annotations

import datetime as dt

from .downgrade import downgrade
from .model import CanonicalTask, Capabilities

_DUE_RANK = {"none": 0, "date": 1, "datetime": 2}


def pair_up(
    new_a: dict[str, CanonicalTask],
    new_b: dict[str, CanonicalTask],
    caps_a: Capabilities,
    caps_b: Capabilities,
    tz: dt.tzinfo,
) -> list[tuple[str, str]]:
    """Pair unlinked items with equal title and equal due downgraded to the weaker caps."""
    weak = _weaker_due(caps_a, caps_b)
    result: list[tuple[str, str]] = []
    used_b: set[str] = set()
    for ext_a, task_a in new_a.items():
        for ext_b, task_b in new_b.items():
            if ext_b in used_b:
                continue
            if _same_key(task_a, task_b, weak, tz):
                result.append((ext_a, ext_b))
                used_b.add(ext_b)
                break
    return result


def _weaker_due(caps_a: Capabilities, caps_b: Capabilities) -> Capabilities:
    due = caps_a.due if _DUE_RANK[caps_a.due] <= _DUE_RANK[caps_b.due] else caps_b.due
    return Capabilities(create=True, update=True, delete=True, due=due, description=True)


def _same_key(
    task_a: CanonicalTask, task_b: CanonicalTask, weak: Capabilities, tz: dt.tzinfo
) -> bool:
    if task_a.title != task_b.title:
        return False
    return downgrade(task_a, weak, tz).due == downgrade(task_b, weak, tz).due
