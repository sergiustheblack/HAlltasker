"""Field merge and the prefer_a / prefer_b conflict policy."""

from __future__ import annotations

from typing import Literal

from .model import FIELDS, CanonicalTask

Policy = Literal["prefer_a", "prefer_b"]


def merge(
    task_a: CanonicalTask,
    changed_a: frozenset[str],
    task_b: CanonicalTask,
    changed_b: frozenset[str],
    policy: Policy,
) -> tuple[CanonicalTask, frozenset[str], frozenset[str]]:
    """Merge two changed sides into one task plus the write sets for A and B.

    Non-overlapping changed fields are taken from the side that changed them;
    overlapping fields follow the policy; unchanged fields come from the preferred side.
    """
    preferred = task_a if policy == "prefer_a" else task_b
    values = {f: getattr(preferred, f) for f in FIELDS}
    for field_name in changed_a | changed_b:
        if field_name in changed_a and field_name in changed_b:
            values[field_name] = getattr(preferred, field_name)
        elif field_name in changed_a:
            values[field_name] = getattr(task_a, field_name)
        else:
            values[field_name] = getattr(task_b, field_name)
    result = CanonicalTask(
        title=values["title"],
        description=values["description"],
        status=values["status"],
        due=values["due"],
        extensions=dict(preferred.extensions),
    )
    write_a = frozenset(f for f in FIELDS if getattr(task_a, f) != getattr(result, f))
    write_b = frozenset(f for f in FIELDS if getattr(task_b, f) != getattr(result, f))
    return result, write_a, write_b
