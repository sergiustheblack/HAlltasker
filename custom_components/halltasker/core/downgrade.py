"""Downgrade of a canonical task to the capabilities of a node."""

from __future__ import annotations

import datetime as dt

from .model import CanonicalTask, Capabilities, Snapshot


def downgrade(task: CanonicalTask, caps: Capabilities, tz: dt.tzinfo) -> CanonicalTask:
    """Reduce a task to what the node can store; a downgrade is not a change."""
    due = task.due
    if caps.due == "none":
        due = None
    elif caps.due == "date" and isinstance(due, dt.datetime):
        due = due.astimezone(tz).date()
    description = task.description if caps.description else None
    return CanonicalTask(
        title=task.title,
        description=description,
        status=task.status,
        due=due,
        extensions={},
    )


def equivalent(
    observed: CanonicalTask, expected: CanonicalTask, caps: Capabilities, tz: dt.tzinfo
) -> bool:
    """Whether an observed value matches the expected one in downgraded form."""
    return Snapshot.of(observed).hash == Snapshot.of(downgrade(expected, caps, tz)).hash
