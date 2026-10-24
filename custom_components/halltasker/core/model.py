"""Canonical task model shared by all plugins."""

from __future__ import annotations

from dataclasses import dataclass, field
import datetime as dt
import hashlib
import json
from typing import Any, Literal

Status = Literal["open", "done"]
Due = dt.date | dt.datetime | None

FIELDS: tuple[str, ...] = ("title", "description", "status", "due")


def due_to_str(due: Due) -> str | None:
    """Serialize a due value: None, YYYY-MM-DD, or ISO 8601 with offset."""
    if due is None:
        return None
    return due.isoformat()


def due_from_str(s: str | None) -> Due:
    """Parse a due value; a naive datetime string is an error."""
    if s is None:
        return None
    if len(s) == 10 and "T" not in s:
        return dt.date.fromisoformat(s)
    parsed = dt.datetime.fromisoformat(s)
    if parsed.tzinfo is None:
        raise ValueError(f"naive datetime in due is forbidden: {s!r}")
    return parsed


@dataclass(frozen=True)
class CanonicalTask:
    """System-independent representation of a task."""

    title: str
    description: str | None = None
    status: Status = "open"
    due: Due = None
    extensions: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if isinstance(self.due, dt.datetime) and self.due.tzinfo is None:
            raise ValueError("datetime due must carry tzinfo")

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "description": self.description,
            "status": self.status,
            "due": due_to_str(self.due),
            "extensions": self.extensions,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CanonicalTask:
        return cls(
            title=data["title"],
            description=data.get("description"),
            status=data.get("status", "open"),
            due=due_from_str(data.get("due")),
            extensions=dict(data.get("extensions") or {}),
        )


@dataclass(frozen=True)
class Snapshot:
    """A serialized canonical task plus its hash."""

    data: dict[str, Any]
    hash: str

    @classmethod
    def of(cls, task: CanonicalTask) -> Snapshot:
        data = task.to_dict()
        payload = json.dumps(data, sort_keys=True, separators=(",", ":"))
        return cls(data=data, hash=hashlib.sha256(payload.encode()).hexdigest())

    def task(self) -> CanonicalTask:
        return CanonicalTask.from_dict(self.data)


def _snapshot_to_dict(snapshot: Snapshot | None) -> dict[str, Any] | None:
    if snapshot is None:
        return None
    return {"data": snapshot.data, "hash": snapshot.hash}


def _snapshot_from_dict(data: dict[str, Any] | None) -> Snapshot | None:
    if data is None:
        return None
    return Snapshot(data=data["data"], hash=data["hash"])


@dataclass
class Link:
    """A canonical task bound to one external id in one node; updated by the engine."""

    canonical_id: str
    node: str
    external_id: str
    last_observed: Snapshot | None = None
    last_written: Snapshot | None = None
    last_synced: Snapshot | None = None
    last_seen_at: str = ""
    tombstone: bool = False
    tombstone_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "canonical_id": self.canonical_id,
            "node": self.node,
            "external_id": self.external_id,
            "last_observed": _snapshot_to_dict(self.last_observed),
            "last_written": _snapshot_to_dict(self.last_written),
            "last_synced": _snapshot_to_dict(self.last_synced),
            "last_seen_at": self.last_seen_at,
            "tombstone": self.tombstone,
            "tombstone_at": self.tombstone_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Link:
        return cls(
            canonical_id=data["canonical_id"],
            node=data["node"],
            external_id=data["external_id"],
            last_observed=_snapshot_from_dict(data.get("last_observed")),
            last_written=_snapshot_from_dict(data.get("last_written")),
            last_synced=_snapshot_from_dict(data.get("last_synced")),
            last_seen_at=data.get("last_seen_at", ""),
            tombstone=data.get("tombstone", False),
            tombstone_at=data.get("tombstone_at"),
        )


@dataclass(frozen=True)
class Capabilities:
    """The set of fields and operations a node supports."""

    create: bool
    update: bool
    delete: bool
    due: Literal["datetime", "date", "none"]
    description: bool


DeletePolicy = Literal["true", "false", "soft"]


@dataclass(frozen=True)
class Filter:
    title_regex: str | None = None
    require_due: bool = False


@dataclass(frozen=True)
class Transform:
    due: Literal["keep", "date_only", "drop"] = "keep"
    title_prefix: str = ""


@dataclass(frozen=True)
class DirectionRule:
    create: bool = True
    update: bool = True
    complete: bool = True
    delete: DeletePolicy = "true"
    filter: Filter = Filter()
    transform: Transform = Transform()


@dataclass(frozen=True)
class SyncPair:
    id: str
    a: str
    b: str
    interval: int = 60
    conflict: Literal["prefer_a", "prefer_b"] = "prefer_a"
    initial_sync: Literal["merge", "dry_run"] = "merge"
    a_to_b: DirectionRule = DirectionRule()
    b_to_a: DirectionRule = DirectionRule()
    enabled: bool = True
