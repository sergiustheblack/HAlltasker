"""Tests for direction rules."""

from __future__ import annotations

import datetime as dt

from custom_components.halltasker.core.model import (
    CanonicalTask,
    Capabilities,
    DirectionRule,
    Filter,
    Transform,
)
from custom_components.halltasker.core.router import (
    allowed,
    apply_transform,
    op_for_change,
    passes_filter,
)

MSK = dt.timezone(dt.timedelta(hours=3))


def _rule(**kwargs: object) -> DirectionRule:
    return DirectionRule(**kwargs)  # type: ignore[arg-type]


def test_title_regex_filter_matches_and_rejects() -> None:
    rule = _rule(filter=Filter(title_regex="^(?!#).*"))
    assert passes_filter(rule, CanonicalTask(title="buy milk")) is True
    assert passes_filter(rule, CanonicalTask(title="# hidden")) is False


def test_require_due_rejects_tasks_without_due() -> None:
    rule = _rule(filter=Filter(require_due=True))
    assert passes_filter(rule, CanonicalTask(title="x", due=dt.date(2026, 10, 5))) is True
    assert passes_filter(rule, CanonicalTask(title="x")) is False


def test_default_rule_passes_everything() -> None:
    assert passes_filter(DirectionRule(), CanonicalTask(title="x")) is True


def test_date_only_transform_converts_datetime_to_date() -> None:
    rule = _rule(transform=Transform(due="date_only"))
    task = CanonicalTask(title="x", due=dt.datetime(2026, 10, 5, 23, 30, tzinfo=MSK))
    assert apply_transform(rule, task, MSK).due == dt.date(2026, 10, 5)


def test_drop_transform_removes_due() -> None:
    rule = _rule(transform=Transform(due="drop"))
    task = CanonicalTask(title="x", due=dt.date(2026, 10, 5))
    assert apply_transform(rule, task, MSK).due is None


def test_keep_transform_changes_nothing() -> None:
    task = CanonicalTask(title="x", description="d", due=dt.date(2026, 10, 5))
    assert apply_transform(DirectionRule(), task, MSK) == task


def test_title_prefix_added_once() -> None:
    rule = _rule(transform=Transform(title_prefix="sync: "))
    plain = CanonicalTask(title="buy milk")
    prefixed = CanonicalTask(title="sync: buy milk")
    assert apply_transform(rule, plain, MSK).title == "sync: buy milk"
    assert apply_transform(rule, prefixed, MSK).title == "sync: buy milk"


def test_allowed_combines_rule_flags_and_capabilities() -> None:
    rule = _rule(create=False, complete=False, delete="soft")
    caps = Capabilities(create=True, update=False, delete=True, due="datetime", description=True)
    assert allowed(rule, caps, "create") is False
    assert allowed(rule, caps, "update") is False
    assert allowed(rule, caps, "complete") is False
    assert allowed(rule, caps, "delete") is False
    assert allowed(rule, caps, "soft_delete") is False


def test_allowed_uses_update_capability_for_complete_and_soft_delete() -> None:
    rule = _rule(delete="soft")
    caps = Capabilities(create=False, update=True, delete=False, due="datetime", description=False)
    assert allowed(rule, caps, "complete") is True
    assert allowed(rule, caps, "soft_delete") is True
    assert allowed(rule, caps, "delete") is False


def test_op_for_change_status_only_is_complete() -> None:
    assert op_for_change(frozenset({"status"})) == "complete"
    assert op_for_change(frozenset({"status", "title"})) == "update"
    assert op_for_change(frozenset({"title"})) == "update"
