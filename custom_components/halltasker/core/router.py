"""Direction rules: allowed operations, filter, transforms."""

from __future__ import annotations

import datetime as dt
import re
from typing import Literal

from .model import CanonicalTask, DirectionRule

Operation = Literal["create", "update", "complete"]


def passes_filter(rule: DirectionRule, task: CanonicalTask) -> bool:
    """Whether the source task may be propagated in this direction."""
    if rule.filter.require_due and task.due is None:
        return False
    if rule.filter.title_regex is None:
        return True
    return re.fullmatch(rule.filter.title_regex, task.title) is not None


def apply_transform(rule: DirectionRule, task: CanonicalTask, tz: dt.tzinfo) -> CanonicalTask:
    """Apply the direction transform; runs after the filter and before the downgrade."""
    due = task.due
    if rule.transform.due == "drop":
        due = None
    elif rule.transform.due == "date_only" and isinstance(due, dt.datetime):
        due = due.astimezone(tz).date()
    title = task.title
    prefix = rule.transform.title_prefix
    if prefix and not title.startswith(prefix):
        title = prefix + title
    return CanonicalTask(
        title=title,
        description=task.description,
        status=task.status,
        due=due,
        extensions=task.extensions,
    )


def allows(rule: DirectionRule, op: Operation) -> bool:
    return getattr(rule, op)


def op_for_change(changed: frozenset[str]) -> Literal["update", "complete"]:
    """A change of the status field alone is the complete operation."""
    if changed == frozenset({"status"}):
        return "complete"
    return "update"
