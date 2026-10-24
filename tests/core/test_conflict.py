"""Tests for conflict merging (SPEC §7 scenarios A5 and A6)."""

from __future__ import annotations

import datetime as dt

from custom_components.halltasker.core.conflict import merge
from custom_components.halltasker.core.model import CanonicalTask

BASE_DUE = dt.date(2026, 10, 5)
NEW_DUE = dt.date(2026, 10, 6)


def test_non_overlapping_fields_are_merged_on_both_sides() -> None:
    task_a = CanonicalTask(title="title from a", due=BASE_DUE)
    task_b = CanonicalTask(title="original", due=NEW_DUE)
    result, write_a, write_b = merge(
        task_a, frozenset({"title"}), task_b, frozenset({"due"}), "prefer_a"
    )
    assert result == CanonicalTask(title="title from a", due=NEW_DUE)
    assert write_a == frozenset({"due"})
    assert write_b == frozenset({"title"})


def test_overlapping_title_prefers_side_a() -> None:
    task_a = CanonicalTask(title="title from a")
    task_b = CanonicalTask(title="title from b")
    result, write_a, write_b = merge(
        task_a, frozenset({"title"}), task_b, frozenset({"title"}), "prefer_a"
    )
    assert result.title == "title from a"
    assert write_a == frozenset()
    assert write_b == frozenset({"title"})


def test_overlapping_title_prefers_side_b() -> None:
    task_a = CanonicalTask(title="title from a")
    task_b = CanonicalTask(title="title from b")
    result, write_a, write_b = merge(
        task_a, frozenset({"title"}), task_b, frozenset({"title"}), "prefer_b"
    )
    assert result.title == "title from b"
    assert write_a == frozenset({"title"})
    assert write_b == frozenset()


def test_overlap_and_non_overlap_in_one_merge() -> None:
    task_a = CanonicalTask(title="a title", description="a desc", due=BASE_DUE, status="done")
    task_b = CanonicalTask(title="b title", description="b desc", due=BASE_DUE, status="open")
    result, write_a, write_b = merge(
        task_a,
        frozenset({"title", "status"}),
        task_b,
        frozenset({"title", "description"}),
        "prefer_b",
    )
    assert result.title == "b title"
    assert result.description == "b desc"
    assert result.status == "done"
    assert write_a == frozenset({"title", "description"})
    assert write_b == frozenset({"status"})
