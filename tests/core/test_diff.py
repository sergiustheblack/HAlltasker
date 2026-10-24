"""Tests for change classification."""

from __future__ import annotations

import datetime as dt

from custom_components.halltasker.core.diff import classify
from custom_components.halltasker.core.model import CanonicalTask, Capabilities, Link, Snapshot

MSK = dt.timezone(dt.timedelta(hours=3))

CAPS = Capabilities(create=True, update=True, delete=True, due="datetime", description=True)
DATE_CAPS = Capabilities(create=True, update=True, delete=True, due="date", description=True)

TASK = CanonicalTask(title="x", description="d", due=dt.date(2026, 10, 5))


def _link(**kwargs: object) -> Link:
    return Link(canonical_id="c1", node="todo.a", external_id="uid-1", **kwargs)  # type: ignore[arg-type]


def test_absent_link_reports_missing_link() -> None:
    state = classify(None, TASK, CAPS, MSK)
    assert state.kind == "missing_link"
    assert state.current == TASK
    assert state.changed_fields == frozenset()


def test_absent_item_reports_deleted() -> None:
    state = classify(_link(), None, CAPS, MSK)
    assert state.kind == "deleted"
    assert state.current is None


def test_same_hash_as_last_observed_reports_unchanged() -> None:
    link = _link(last_observed=Snapshot.of(TASK))
    state = classify(link, TASK, CAPS, MSK)
    assert state.kind == "unchanged"


def test_matching_last_written_reports_echo() -> None:
    link = _link(
        last_written=Snapshot.of(CanonicalTask(title="x", due=dt.date(2026, 10, 5))),
        last_synced=Snapshot.of(TASK),
    )
    state = classify(link, CanonicalTask(title="x", due=dt.date(2026, 10, 5)), CAPS, MSK)
    assert state.kind == "echo"


def test_date_read_back_from_written_datetime_is_echo() -> None:
    written = CanonicalTask(title="x", due=dt.datetime(2026, 10, 5, 23, 30, tzinfo=MSK))
    link = _link(
        last_written=Snapshot.of(written),
        last_synced=Snapshot.of(written),
    )
    state = classify(link, CanonicalTask(title="x", due=dt.date(2026, 10, 5)), DATE_CAPS, MSK)
    assert state.kind == "echo"


def test_different_value_reports_changed_with_fields() -> None:
    link = _link(
        last_observed=Snapshot.of(TASK),
        last_synced=Snapshot.of(TASK),
    )
    current = CanonicalTask(title="y", description="d", status="done", due=dt.date(2026, 10, 5))
    state = classify(link, current, CAPS, MSK)
    assert state.kind == "changed"
    assert state.changed_fields == frozenset({"title", "status"})


def test_changed_falls_back_to_last_observed_without_last_synced() -> None:
    link = _link(last_observed=Snapshot.of(TASK))
    current = CanonicalTask(title="x", description="new", due=dt.date(2026, 10, 5))
    state = classify(link, current, CAPS, MSK)
    assert state.kind == "changed"
    assert state.changed_fields == frozenset({"description"})


def test_changed_without_snapshots_lists_non_empty_fields() -> None:
    state = classify(_link(), CanonicalTask(title="x", due=dt.date(2026, 10, 5)), CAPS, MSK)
    assert state.kind == "changed"
    assert state.changed_fields == frozenset({"title", "status", "due"})


def test_due_downgraded_from_last_synced_is_not_a_change() -> None:
    link = _link(
        last_observed=Snapshot.of(TASK),
        last_synced=Snapshot.of(
            CanonicalTask(title="x", due=dt.datetime(2026, 10, 5, 12, 0, tzinfo=MSK))
        ),
    )
    current = CanonicalTask(title="x", due=dt.date(2026, 10, 5))
    state = classify(link, current, DATE_CAPS, MSK)
    assert state.kind == "changed"
    assert state.changed_fields == frozenset()
