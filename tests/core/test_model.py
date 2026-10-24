"""Tests for the canonical model."""

from __future__ import annotations

import datetime as dt

import pytest

from custom_components.halltasker.core.model import (
    CanonicalTask,
    DirectionRule,
    Link,
    Snapshot,
    SyncPair,
    due_from_str,
    due_to_str,
)

TZ = dt.timezone(dt.timedelta(hours=3))


def test_due_round_trip_preserves_none_date_and_datetime() -> None:
    due_values: list[object] = [
        None,
        dt.date(2026, 10, 5),
        dt.datetime(2026, 10, 5, 23, 30, tzinfo=TZ),
    ]
    for due in due_values:
        task = CanonicalTask(title="x", due=due)  # type: ignore[arg-type]
        restored = CanonicalTask.from_dict(task.to_dict())
        assert restored == task
        assert due_from_str(due_to_str(task.due)) == task.due


def test_round_trip_keeps_date_and_datetime_types_distinct() -> None:
    date_task = CanonicalTask(title="x", due=dt.date(2026, 10, 5))
    datetime_task = CanonicalTask(title="x", due=dt.datetime(2026, 10, 5, 23, 30, tzinfo=TZ))
    restored_date = CanonicalTask.from_dict(date_task.to_dict()).due
    restored_datetime = CanonicalTask.from_dict(datetime_task.to_dict()).due
    assert isinstance(restored_date, dt.date) and not isinstance(restored_date, dt.datetime)
    assert isinstance(restored_datetime, dt.datetime)


def test_naive_datetime_is_rejected() -> None:
    with pytest.raises(ValueError):
        CanonicalTask(title="x", due=dt.datetime(2026, 10, 5, 23, 30))
    with pytest.raises(ValueError):
        due_from_str("2026-10-05T23:30:00")


def test_snapshot_hash_is_stable_for_equal_tasks() -> None:
    base = CanonicalTask(title="x", description="d", status="open", due=dt.date(2026, 10, 5))
    equal = CanonicalTask(title="x", description="d", status="open", due=dt.date(2026, 10, 5))
    assert Snapshot.of(base).hash == Snapshot.of(equal).hash


def test_snapshot_hash_differs_when_any_field_changes() -> None:
    base = CanonicalTask(title="x", description="d", status="open", due=dt.date(2026, 10, 5))
    changed = [
        CanonicalTask(title="y", description="d", status="open", due=dt.date(2026, 10, 5)),
        CanonicalTask(title="x", description=None, status="open", due=dt.date(2026, 10, 5)),
        CanonicalTask(title="x", description="d", status="done", due=dt.date(2026, 10, 5)),
        CanonicalTask(title="x", description="d", status="open", due=None),
    ]
    base_hash = Snapshot.of(base).hash
    assert all(Snapshot.of(task).hash != base_hash for task in changed)


def test_snapshot_hash_ignores_extensions_key_order() -> None:
    a = CanonicalTask(title="x", extensions={"k1": 1, "k2": {"n1": True, "n2": []}})
    b = CanonicalTask(title="x", extensions={"k2": {"n2": [], "n1": True}, "k1": 1})
    assert Snapshot.of(a).hash == Snapshot.of(b).hash


def test_snapshot_task_returns_equal_task() -> None:
    task = CanonicalTask(title="x", due=dt.datetime(2026, 10, 5, 23, 30, tzinfo=TZ))
    assert Snapshot.of(task).task() == task


def test_link_round_trip_with_filled_snapshots() -> None:
    task = CanonicalTask(title="x", description="d", due=dt.date(2026, 10, 5))
    link = Link(
        canonical_id="ab12",
        node="todo.a",
        external_id="uid-1",
        last_observed=Snapshot.of(task),
        last_written=Snapshot.of(task),
        last_synced=Snapshot.of(task),
        last_seen_at="2026-10-05T12:00:00+00:00",
        tombstone=True,
        tombstone_at="2026-10-05T13:00:00+00:00",
    )
    restored = Link.from_dict(link.to_dict())
    assert restored == link
    assert restored.last_observed is not None and restored.last_observed.task() == task


def test_link_round_trip_with_empty_snapshots() -> None:
    link = Link(canonical_id="ab12", node="todo.a", external_id="uid-1")
    restored = Link.from_dict(link.to_dict())
    assert restored == link
    assert restored.last_observed is None
    assert restored.last_written is None
    assert restored.last_synced is None
    assert restored.tombstone is False
    assert restored.tombstone_at is None


def test_sync_pair_defaults_allow_everything() -> None:
    pair = SyncPair(id="p", a="todo.a", b="todo.b")
    for rule in (pair.a_to_b, pair.b_to_a):
        assert isinstance(rule, DirectionRule)
        assert rule.create and rule.update and rule.complete
        assert rule.delete == "true"
        assert rule.filter.title_regex is None and rule.filter.require_due is False
        assert rule.transform.due == "keep" and rule.transform.title_prefix == ""
    assert pair.interval == 60
    assert pair.conflict == "prefer_a"
    assert pair.initial_sync == "merge"
    assert pair.enabled is True
