"""Tests for the downgrade to node capabilities."""

from __future__ import annotations

import datetime as dt

from custom_components.halltasker.core.downgrade import downgrade, equivalent
from custom_components.halltasker.core.model import CanonicalTask, Capabilities

MSK = dt.timezone(dt.timedelta(hours=3))

DATETIME_CAPS = Capabilities(
    create=True, update=True, delete=True, due="datetime", description=True
)
DATE_CAPS = Capabilities(create=True, update=True, delete=True, due="date", description=True)
NONE_CAPS = Capabilities(create=True, update=True, delete=True, due="none", description=False)


def test_datetime_due_becomes_local_date() -> None:
    task = CanonicalTask(title="x", due=dt.datetime(2026, 10, 5, 23, 30, tzinfo=MSK))
    assert downgrade(task, DATE_CAPS, MSK).due == dt.date(2026, 10, 5)


def test_datetime_due_in_another_tz_converts_before_truncating() -> None:
    task = CanonicalTask(title="x", due=dt.datetime(2026, 10, 5, 23, 30, tzinfo=MSK))
    assert downgrade(task, DATE_CAPS, dt.UTC).due == dt.date(2026, 10, 5)


def test_date_due_is_kept_for_date_caps() -> None:
    task = CanonicalTask(title="x", due=dt.date(2026, 10, 5))
    assert downgrade(task, DATE_CAPS, MSK).due == dt.date(2026, 10, 5)


def test_none_caps_drop_due_and_description() -> None:
    task = CanonicalTask(title="x", description="d", due=dt.date(2026, 10, 5))
    downgraded = downgrade(task, NONE_CAPS, MSK)
    assert downgraded.due is None
    assert downgraded.description is None


def test_datetime_caps_change_nothing() -> None:
    task = CanonicalTask(
        title="x", description="d", due=dt.datetime(2026, 10, 5, 23, 30, tzinfo=MSK)
    )
    assert downgrade(task, DATETIME_CAPS, MSK) == CanonicalTask(
        title="x", description="d", due=dt.datetime(2026, 10, 5, 23, 30, tzinfo=MSK)
    )


def test_downgrade_clears_extensions() -> None:
    task = CanonicalTask(title="x", extensions={"k": 1})
    assert downgrade(task, DATETIME_CAPS, MSK).extensions == {}


def test_equivalent_date_against_datetime_with_date_caps_is_true() -> None:
    observed = CanonicalTask(title="x", due=dt.date(2026, 10, 5))
    expected = CanonicalTask(title="x", due=dt.datetime(2026, 10, 5, 23, 30, tzinfo=MSK))
    assert equivalent(observed, expected, DATE_CAPS, MSK) is True


def test_equivalent_different_title_is_false() -> None:
    observed = CanonicalTask(title="y")
    expected = CanonicalTask(title="x")
    assert equivalent(observed, expected, DATETIME_CAPS, MSK) is False
