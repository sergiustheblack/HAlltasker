"""Change classification for one side of a link."""

from __future__ import annotations

from dataclasses import dataclass
import datetime as dt
from typing import Literal

from .downgrade import downgrade, equivalent
from .model import FIELDS, CanonicalTask, Capabilities, Link, Snapshot

SideKind = Literal["unchanged", "changed", "deleted", "echo", "missing_link"]


@dataclass(frozen=True)
class SideState:
    kind: SideKind
    current: CanonicalTask | None
    changed_fields: frozenset[str]


def classify(
    link: Link | None,
    current: CanonicalTask | None,
    caps: Capabilities,
    tz: dt.tzinfo,
) -> SideState:
    """Classify one side of a canonical task: unchanged, echo, changed, or deleted."""
    if link is None:
        return SideState("missing_link", current, frozenset())
    if current is None:
        return SideState("deleted", None, frozenset())
    if link.last_observed is not None and Snapshot.of(current).hash == link.last_observed.hash:
        return SideState("unchanged", current, frozenset())
    if link.last_written is not None and equivalent(current, link.last_written.task(), caps, tz):
        return SideState("echo", current, frozenset())
    return SideState("changed", current, _changed_fields(link, current, caps, tz))


def _changed_fields(
    link: Link, current: CanonicalTask, caps: Capabilities, tz: dt.tzinfo
) -> frozenset[str]:
    reference = link.last_synced if link.last_synced is not None else link.last_observed
    if reference is None:
        return frozenset(f for f in FIELDS if getattr(current, f) not in (None, ""))
    ref_task = reference.task()
    changed: set[str] = set()
    for field_name in FIELDS:
        ref_value = getattr(ref_task, field_name)
        if field_name == "due":
            ref_value = downgrade(CanonicalTask(title="", due=ref_value), caps, tz).due
        if getattr(current, field_name) != ref_value:
            changed.add(field_name)
    return frozenset(changed)
