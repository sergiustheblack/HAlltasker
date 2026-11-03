"""Pure data types shared by the core and plugins."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
import datetime as dt
import hashlib
import json
from types import MappingProxyType
from typing import Any, Literal, cast

Status = Literal["open", "done"]
Due = dt.date | dt.datetime | None
DeletePolicy = Literal["true", "false", "soft"]
FieldType = Literal["str", "text", "enum", "due", "datetime", "int", "str_list"]
FieldCap = Literal["none", "partial", "full"]


def _frozen_mapping(values: Mapping[str, Any]) -> Mapping[str, Any]:
    return MappingProxyType(dict(values))


def due_to_str(due: Due) -> str | None:
    """Serialize a due value."""
    if due is None:
        return None
    if isinstance(due, dt.datetime) and due.tzinfo is None:
        raise ValueError("datetime due must carry tzinfo")
    return due.isoformat()


def due_from_str(value: str | None) -> Due:
    """Parse a due value without allowing naive datetimes."""
    if value is None:
        return None
    if len(value) == 10 and "T" not in value:
        return dt.date.fromisoformat(value)
    parsed = dt.datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError(f"naive datetime in due is forbidden: {value!r}")
    return parsed


@dataclass(frozen=True)
class FieldSpec:
    """The shape and static access rules of one native or slot field."""

    name: str
    type: FieldType
    role: str | None = None
    read: bool = True
    write: bool = True
    values: tuple[str, ...] = ()
    required_create: bool = False
    minimum: int | None = None
    maximum: int | None = None

    def __post_init__(self) -> None:
        if (self.minimum is not None or self.maximum is not None) and self.type != "int":
            raise ValueError("numeric bounds are valid only for int fields")
        if self.minimum is not None and self.maximum is not None and self.minimum > self.maximum:
            raise ValueError("minimum must not exceed maximum")

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "type": self.type,
            "role": self.role,
            "read": self.read,
            "write": self.write,
            "values": list(self.values),
            "required_create": self.required_create,
            "minimum": self.minimum,
            "maximum": self.maximum,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> FieldSpec:
        return cls(
            name=cast(str, data["name"]),
            type=cast(FieldType, data["type"]),
            role=cast(str | None, data.get("role")),
            read=bool(data.get("read", True)),
            write=bool(data.get("write", True)),
            values=tuple(cast(list[str], data.get("values", []))),
            required_create=bool(data.get("required_create", False)),
            minimum=cast(int | None, data.get("minimum")),
            maximum=cast(int | None, data.get("maximum")),
        )


def normalize_value(spec: FieldSpec, value: Any) -> Any:
    """Validate a value and return its canonical in-memory form."""
    if value is None:
        return None
    if spec.type in ("str", "text"):
        if not isinstance(value, str):
            raise ValueError(f"{spec.name}: expected string")
        return value
    if spec.type == "enum":
        if not isinstance(value, str):
            raise ValueError(f"{spec.name}: expected enum string")
        if spec.values and value not in spec.values:
            raise ValueError(f"{spec.name}: unsupported enum value")
        return value
    if spec.type == "due":
        if isinstance(value, dt.datetime):
            if value.tzinfo is None:
                raise ValueError(f"{spec.name}: datetime must carry tzinfo")
            return value
        if isinstance(value, dt.date):
            return value
        raise ValueError(f"{spec.name}: expected date or datetime")
    if spec.type == "datetime":
        if not isinstance(value, dt.datetime) or value.tzinfo is None:
            raise ValueError(f"{spec.name}: expected timezone-aware datetime")
        return value
    if spec.type == "int":
        if not isinstance(value, int) or isinstance(value, bool):
            raise ValueError(f"{spec.name}: expected integer")
        if spec.minimum is not None and value < spec.minimum:
            raise ValueError(f"{spec.name}: value is below minimum")
        if spec.maximum is not None and value > spec.maximum:
            raise ValueError(f"{spec.name}: value is above maximum")
        return value
    if spec.type == "str_list":
        if not isinstance(value, (list, tuple)) or not all(isinstance(item, str) for item in value):
            raise ValueError(f"{spec.name}: expected a sequence of strings")
        return tuple(sorted(set(value)))
    raise ValueError(f"{spec.name}: unsupported field type")


def serialize_value(field_type: FieldType, value: Any) -> Any:
    """Turn a normalized value into a JSON-safe value."""
    if value is None:
        return None
    if field_type in ("str", "text", "enum", "int"):
        return value
    if field_type in ("due", "datetime"):
        return due_to_str(value)
    if field_type == "str_list":
        return list(value)
    raise ValueError(f"unsupported field type: {field_type}")


def parse_value(field_type: FieldType, raw: Any) -> Any:
    """Parse a JSON-safe value into its canonical in-memory form."""
    if field_type == "due":
        value = due_from_str(raw)
    elif field_type == "datetime" and raw is not None:
        value = dt.datetime.fromisoformat(raw)
    else:
        value = raw
    return normalize_value(FieldSpec("value", field_type), value)


@dataclass(frozen=True)
class ItemSchema:
    """A pair-specific canonical schema."""

    kind: str
    fields: tuple[FieldSpec, ...]
    match_key: tuple[str, ...] = ("title", "due")

    def __post_init__(self) -> None:
        fields = tuple(self.fields)
        if len({spec.name for spec in fields}) != len(fields):
            raise ValueError("item schema field names must be unique")
        names = {spec.name for spec in fields}
        object.__setattr__(self, "fields", fields)
        object.__setattr__(
            self,
            "match_key",
            tuple(name for name in ("title", "due") if name in names),
        )

    def field(self, name: str) -> FieldSpec:
        for spec in self.fields:
            if spec.name == name:
                return spec
        raise KeyError(name)

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "fields": [spec.to_dict() for spec in self.fields],
            "match_key": list(self.match_key),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> ItemSchema:
        return cls(
            kind=cast(str, data["kind"]),
            fields=tuple(
                FieldSpec.from_dict(item) for item in cast(list[Mapping[str, Any]], data["fields"])
            ),
            match_key=tuple(cast(list[str], data.get("match_key", ("title", "due")))),
        )


@dataclass(frozen=True)
class CanonicalItem:
    """A canonical item at a core or plugin boundary."""

    kind: str
    fields: Mapping[str, Any]

    def __post_init__(self) -> None:
        object.__setattr__(self, "fields", _frozen_mapping(self.fields))

    def to_dict(self, schema: ItemSchema) -> dict[str, Any]:
        if self.kind != schema.kind:
            raise ValueError(f"item kind {self.kind!r} does not match schema {schema.kind!r}")
        return {
            "kind": self.kind,
            "fields": {
                spec.name: serialize_value(
                    spec.type, normalize_value(spec, self.fields.get(spec.name))
                )
                for spec in schema.fields
            },
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any], schema: ItemSchema) -> CanonicalItem:
        kind = cast(str, data["kind"])
        if kind != schema.kind:
            raise ValueError(f"item kind {kind!r} does not match schema {schema.kind!r}")
        raw_fields = cast(Mapping[str, Any], data.get("fields", {}))
        return cls(
            kind=kind,
            fields={
                spec.name: parse_value(spec.type, raw_fields.get(spec.name))
                for spec in schema.fields
            },
        )


@dataclass(frozen=True)
class NodeListing:
    """A complete node response with explicitly filtered external ids."""

    items: Mapping[str, CanonicalItem]
    filtered_ids: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        object.__setattr__(self, "items", _frozen_mapping(self.items))
        object.__setattr__(self, "filtered_ids", frozenset(self.filtered_ids))


@dataclass(frozen=True)
class Capabilities:
    """Dynamic operation and independently readable/writable field shapes."""

    create: bool
    update: bool
    delete: bool
    fields: Mapping[str, FieldCap] = field(default_factory=dict)
    read_fields: Mapping[str, FieldCap] = field(default_factory=dict)
    due: Literal["datetime", "date", "none"] | None = None
    description: bool | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "fields", _frozen_mapping(self.fields))
        object.__setattr__(self, "read_fields", _frozen_mapping(self.read_fields))


@dataclass(frozen=True)
class Filter:
    title_regex: str | None = None
    require_due: bool | Literal["datetime"] = False

    def to_dict(self) -> dict[str, Any]:
        return {"title_regex": self.title_regex, "require_due": self.require_due}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Filter:
        return cls(
            title_regex=cast(str | None, data.get("title_regex")),
            require_due=cast(bool | Literal["datetime"], data.get("require_due", False)),
        )


@dataclass(frozen=True)
class Transform:
    due: Literal["keep", "date_only", "drop"] = "keep"
    title_prefix: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"due": self.due, "title_prefix": self.title_prefix}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Transform:
        return cls(
            due=cast(Literal["keep", "date_only", "drop"], data.get("due", "keep")),
            title_prefix=cast(str, data.get("title_prefix", "")),
        )


@dataclass(frozen=True)
class DirectionRule:
    create: bool = True
    update: bool = True
    complete: bool = True
    delete: DeletePolicy = "true"
    delete_past_due: bool = True
    filter: Filter = Filter()
    transform: Transform = Transform()

    def to_dict(self) -> dict[str, Any]:
        return {
            "create": self.create,
            "update": self.update,
            "complete": self.complete,
            "delete": self.delete,
            "delete_past_due": self.delete_past_due,
            "filter": self.filter.to_dict(),
            "transform": self.transform.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> DirectionRule:
        return cls(
            create=bool(data.get("create", True)),
            update=bool(data.get("update", True)),
            complete=bool(data.get("complete", True)),
            delete=cast(DeletePolicy, data.get("delete", "true")),
            delete_past_due=bool(data.get("delete_past_due", True)),
            filter=Filter.from_dict(cast(Mapping[str, Any], data.get("filter", {}))),
            transform=Transform.from_dict(cast(Mapping[str, Any], data.get("transform", {}))),
        )


@dataclass(frozen=True)
class Connection:
    id: str
    name: str
    plugin_id: str
    settings: Mapping[str, Any] = field(default_factory=dict)
    interval: int = 300

    def __post_init__(self) -> None:
        object.__setattr__(self, "settings", _frozen_mapping(self.settings))

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "plugin_id": self.plugin_id,
            "settings": dict(self.settings),
            "interval": self.interval,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Connection:
        return cls(
            cast(str, data["id"]),
            cast(str, data["name"]),
            cast(str, data["plugin_id"]),
            cast(Mapping[str, Any], data.get("settings", {})),
            cast(int, data.get("interval", 300)),
        )


@dataclass(frozen=True)
class Container:
    id: str
    name: str
    path: str | None = None
    query: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "name": self.name, "path": self.path, "query": self.query}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Container:
        return cls(
            cast(str, data["id"]),
            cast(str, data["name"]),
            cast(str | None, data.get("path")),
            cast(str | None, data.get("query")),
        )


@dataclass(frozen=True)
class Node:
    id: str
    name: str
    connection_id: str
    container: Container
    kind: str = "task"

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "connection_id": self.connection_id,
            "container": self.container.to_dict(),
            "kind": self.kind,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Node:
        return cls(
            cast(str, data["id"]),
            cast(str, data["name"]),
            cast(str, data["connection_id"]),
            Container.from_dict(cast(Mapping[str, Any], data["container"])),
            cast(str, data.get("kind", "task")),
        )


@dataclass(frozen=True)
class ValueMap:
    read: Mapping[str, str]
    write: Mapping[str, str]
    default: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "read", _frozen_mapping(self.read))
        object.__setattr__(self, "write", _frozen_mapping(self.write))

    def to_dict(self) -> dict[str, Any]:
        return {"read": dict(self.read), "write": dict(self.write), "default": self.default}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> ValueMap:
        return cls(
            cast(Mapping[str, str], data["read"]),
            cast(Mapping[str, str], data["write"]),
            cast(str | None, data.get("default")),
        )


@dataclass(frozen=True)
class FieldMap:
    slot: str
    a: str | None
    b: str | None
    prefer: Literal["pair", "a", "b"] = "pair"
    value_map_a: ValueMap | None = None
    value_map_b: ValueMap | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "slot": self.slot,
            "a": self.a,
            "b": self.b,
            "prefer": self.prefer,
            "value_map_a": None if self.value_map_a is None else self.value_map_a.to_dict(),
            "value_map_b": None if self.value_map_b is None else self.value_map_b.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> FieldMap:
        raw_a = data.get("value_map_a")
        raw_b = data.get("value_map_b")
        return cls(
            slot=cast(str, data["slot"]),
            a=cast(str | None, data.get("a")),
            b=cast(str | None, data.get("b")),
            prefer=cast(Literal["pair", "a", "b"], data.get("prefer", "pair")),
            value_map_a=(
                None if raw_a is None else ValueMap.from_dict(cast(Mapping[str, Any], raw_a))
            ),
            value_map_b=(
                None if raw_b is None else ValueMap.from_dict(cast(Mapping[str, Any], raw_b))
            ),
        )


@dataclass(frozen=True)
class Pair:
    id: str
    name: str
    a: str
    b: str
    mapping: tuple[FieldMap, ...]
    direction: Literal["both", "a_to_b", "b_to_a"] = "both"
    interval: int = 60
    conflict: Literal["prefer_a", "prefer_b"] = "prefer_a"
    initial_sync: Literal["merge", "dry_run"] = "merge"
    enabled: bool = True
    a_to_b: DirectionRule = DirectionRule()
    b_to_a: DirectionRule = DirectionRule()

    def __post_init__(self) -> None:
        object.__setattr__(self, "mapping", tuple(self.mapping))

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "a": self.a,
            "b": self.b,
            "mapping": [row.to_dict() for row in self.mapping],
            "direction": self.direction,
            "interval": self.interval,
            "conflict": self.conflict,
            "initial_sync": self.initial_sync,
            "enabled": self.enabled,
            "a_to_b": self.a_to_b.to_dict(),
            "b_to_a": self.b_to_a.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Pair:
        return cls(
            id=cast(str, data["id"]),
            name=cast(str, data["name"]),
            a=cast(str, data["a"]),
            b=cast(str, data["b"]),
            mapping=tuple(
                FieldMap.from_dict(item) for item in cast(list[Mapping[str, Any]], data["mapping"])
            ),
            direction=cast(Literal["both", "a_to_b", "b_to_a"], data.get("direction", "both")),
            interval=cast(int, data.get("interval", 60)),
            conflict=cast(Literal["prefer_a", "prefer_b"], data.get("conflict", "prefer_a")),
            initial_sync=cast(Literal["merge", "dry_run"], data.get("initial_sync", "merge")),
            enabled=bool(data.get("enabled", True)),
            a_to_b=DirectionRule.from_dict(cast(Mapping[str, Any], data.get("a_to_b", {}))),
            b_to_a=DirectionRule.from_dict(cast(Mapping[str, Any], data.get("b_to_a", {}))),
        )


@dataclass(frozen=True)
class SyncPair:
    """The v1 pair facade retained until the v2 configuration migration."""

    id: str
    a: str
    b: str
    interval: int = 60
    conflict: Literal["prefer_a", "prefer_b"] = "prefer_a"
    initial_sync: Literal["merge", "dry_run"] = "merge"
    a_to_b: DirectionRule = DirectionRule()
    b_to_a: DirectionRule = DirectionRule()
    enabled: bool = True


TASK_SCHEMA = ItemSchema(
    kind="task",
    fields=(
        FieldSpec("title", "str", role="title"),
        FieldSpec("description", "text", role="description"),
        FieldSpec("status", "enum", role="status", values=("open", "done")),
        FieldSpec("due", "due", role="due"),
    ),
)
FIELDS: tuple[str, ...] = ("title", "description", "status", "due")


@dataclass(frozen=True)
class CanonicalTask:
    """The v1 task facade retained for the existing todo plugin."""

    title: str
    description: str | None = None
    status: Status = "open"
    due: Due = None
    extensions: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if isinstance(self.due, dt.datetime) and self.due.tzinfo is None:
            raise ValueError("datetime due must carry tzinfo")
        object.__setattr__(self, "extensions", dict(self.extensions))

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "description": self.description,
            "status": self.status,
            "due": due_to_str(self.due),
            "extensions": self.extensions,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> CanonicalTask:
        return cls(
            title=cast(str, data["title"]),
            description=cast(str | None, data.get("description")),
            status=cast(Status, data.get("status", "open")),
            due=due_from_str(cast(str | None, data.get("due"))),
            extensions=dict(cast(Mapping[str, Any], data.get("extensions") or {})),
        )

    def to_item(self) -> CanonicalItem:
        return CanonicalItem(
            "task",
            {
                "title": self.title,
                "description": self.description,
                "status": self.status,
                "due": self.due,
            },
        )

    @classmethod
    def from_item(cls, item: CanonicalItem) -> CanonicalTask:
        if item.kind != "task":
            raise ValueError(f"cannot convert {item.kind!r} to CanonicalTask")
        return cls(
            title=cast(str, item.fields["title"]),
            description=cast(str | None, item.fields.get("description")),
            status=cast(Status, item.fields.get("status", "open")),
            due=cast(Due, item.fields.get("due")),
        )


@dataclass(frozen=True)
class Snapshot:
    """A serialized item and its canonical hash."""

    data: dict[str, Any]
    hash: str

    @classmethod
    def of(cls, item: CanonicalItem | CanonicalTask, schema: ItemSchema | None = None) -> Snapshot:
        if isinstance(item, CanonicalTask):
            data = item.to_dict()
        else:
            if schema is None:
                raise ValueError("an ItemSchema is required for CanonicalItem snapshots")
            data = item.to_dict(schema)
        payload = json.dumps(data, sort_keys=True, separators=(",", ":"))
        return cls(data=data, hash=hashlib.sha256(payload.encode()).hexdigest())

    def item(self, schema: ItemSchema | None = None) -> CanonicalItem | CanonicalTask:
        if schema is None:
            return CanonicalTask.from_dict(self.data)
        return CanonicalItem.from_dict(self.data, schema)

    def task(self) -> CanonicalTask:
        """Return the retained v1 task facade."""
        return CanonicalTask.from_dict(self.data)


def _snapshot_to_dict(snapshot: Snapshot | None) -> dict[str, Any] | None:
    if snapshot is None:
        return None
    return {"data": snapshot.data, "hash": snapshot.hash}


def _snapshot_from_dict(data: Mapping[str, Any] | None) -> Snapshot | None:
    if data is None:
        return None
    return Snapshot(data=dict(cast(Mapping[str, Any], data["data"])), hash=cast(str, data["hash"]))


@dataclass
class Link:
    """A mutable link updated by the engine."""

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
    def from_dict(cls, data: Mapping[str, Any]) -> Link:
        return cls(
            canonical_id=cast(str, data["canonical_id"]),
            node=cast(str, data["node"]),
            external_id=cast(str, data["external_id"]),
            last_observed=_snapshot_from_dict(
                cast(Mapping[str, Any] | None, data.get("last_observed"))
            ),
            last_written=_snapshot_from_dict(
                cast(Mapping[str, Any] | None, data.get("last_written"))
            ),
            last_synced=_snapshot_from_dict(
                cast(Mapping[str, Any] | None, data.get("last_synced"))
            ),
            last_seen_at=cast(str, data.get("last_seen_at", "")),
            tombstone=bool(data.get("tombstone", False)),
            tombstone_at=cast(str | None, data.get("tombstone_at")),
        )
