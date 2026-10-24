"""Tests for the initial sync matching heuristic."""

from __future__ import annotations

import datetime as dt

from custom_components.halltasker.core.matching import pair_up
from custom_components.halltasker.core.model import CanonicalTask, Capabilities

MSK = dt.timezone(dt.timedelta(hours=3))

DATETIME_CAPS = Capabilities(
    create=True, update=True, delete=True, due="datetime", description=True
)
DATE_CAPS = Capabilities(create=True, update=True, delete=True, due="date", description=True)


def test_equal_title_and_due_is_matched() -> None:
    a = {"a1": CanonicalTask(title="milk", due=dt.datetime(2026, 10, 5, 23, 30, tzinfo=MSK))}
    b = {"b1": CanonicalTask(title="milk", due=dt.date(2026, 10, 5))}
    assert pair_up(a, b, DATETIME_CAPS, DATE_CAPS, MSK) == [("a1", "b1")]


def test_different_title_is_not_matched() -> None:
    a = {"a1": CanonicalTask(title="milk")}
    b = {"b1": CanonicalTask(title="bread")}
    assert pair_up(a, b, DATETIME_CAPS, DATETIME_CAPS, MSK) == []


def test_same_title_different_due_is_not_matched() -> None:
    a = {"a1": CanonicalTask(title="milk", due=dt.date(2026, 10, 5))}
    b = {"b1": CanonicalTask(title="milk", due=dt.date(2026, 10, 6))}
    assert pair_up(a, b, DATE_CAPS, DATE_CAPS, MSK) == []


def test_duplicates_are_linked_one_by_one() -> None:
    a = {
        "a1": CanonicalTask(title="milk"),
        "a2": CanonicalTask(title="milk"),
    }
    b = {
        "b1": CanonicalTask(title="milk"),
        "b2": CanonicalTask(title="milk"),
    }
    assert pair_up(a, b, DATETIME_CAPS, DATETIME_CAPS, MSK) == [("a1", "b1"), ("a2", "b2")]


def test_each_item_takes_part_in_at_most_one_pair() -> None:
    a = {"a1": CanonicalTask(title="milk"), "a2": CanonicalTask(title="milk")}
    b = {"b1": CanonicalTask(title="milk")}
    pairs = pair_up(a, b, DATETIME_CAPS, DATETIME_CAPS, MSK)
    assert len(pairs) == 1
    assert pairs[0] == ("a1", "b1")
