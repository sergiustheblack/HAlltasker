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
