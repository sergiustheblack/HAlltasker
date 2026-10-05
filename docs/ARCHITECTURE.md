# HAlltasker — architecture (v1.0, 2026-10-05)

> Language: English only (agent-facing, binding). A Russian reading copy is in [docs/ru/ARCHITECTURE.md](ru/ARCHITECTURE.md); if they differ, this file wins.

This document describes **how** `docs/SPEC.md` is implemented. The signatures and data structures here are binding: tasks in `docs/TASKS.md` refer to them by name.

## 1. Overview

```
Home Assistant
│
├── todo.icloud_reminders   (stock CalDAV)         ─┐
├── todo.google_tasks_my    (stock Google Tasks)   ─┤  nodes = todo.* entities
├── todo.yandex_dela        (stock CalDAV)         ─┤
└── todo.home_list          (local_todo)           ─┘
            ▲  │  services todo.get_items / add_item / update_item / remove_item
            │  ▼
custom_components/halltasker
├── __init__.py        load YAML → ConfigEntry, register services
├── coordinator.py     schedule: one timer per pair + state_changed events → engine.run_pair
├── core/
│   ├── model.py       CanonicalTask, Snapshot, Link, SyncPair, DirectionRule, Capabilities
│   ├── link_store.py  LinkStore on top of homeassistant.helpers.storage.Store
│   ├── diff.py        changed fields, echo detection
│   ├── downgrade.py   downgrade to capabilities, comparison that accounts for the downgrade
│   ├── router.py      direction rules: operations, filter, transforms
│   ├── conflict.py    field merge and the prefer_a / prefer_b policy
│   ├── matching.py    linking heuristic for the initial sync
│   ├── engine.py      SyncEngine.run_pair — the only place where everything is joined
│   └── actions.py     Action (create/update/delete/complete/link/tombstone), action plan
├── plugins/
│   ├── base.py        Plugin (ABC), PluginSchema
│   ├── registry.py    choose a plugin by the node string
│   └── ha_todo.py     HaTodoPlugin: todo.* ↔ CanonicalTask
├── sensor.py          status sensor per pair
├── diagnostics.py
├── schema.py          CONFIG_SCHEMA (voluptuous) and parsing of YAML into dataclasses
├── const.py
├── config_flow.py     import from YAML only
├── services.yaml, strings.json, translations/{en,ru}.json, manifest.json
```

Topology is a "star": a plugin knows only the canonical model. There are no direct plugin↔plugin conversions.

## 2. Canonical model (`core/model.py`)

All structures are `dataclasses`, immutable (`frozen=True`), with explicit serialization to JSON-compatible dicts.

```python
from __future__ import annotations
import datetime as dt
from dataclasses import dataclass, field
from typing import Any, Literal

Status = Literal["open", "done"]
Due = dt.date | dt.datetime | None          # datetime always has tzinfo

@dataclass(frozen=True)
class CanonicalTask:
    title: str
    description: str | None = None
    status: Status = "open"
    due: Due = None
    extensions: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]: ...
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CanonicalTask": ...

FIELDS: tuple[str, ...] = ("title", "description", "status", "due")
```

Serialization of `due`: `None` → `null`; `date` → `"YYYY-MM-DD"`; `datetime` → ISO 8601 with offset. Parsing: a string of length 10 without `T` is a `date`; otherwise a `datetime`; a naive datetime is forbidden when parsing (error). The invariant is checked in `__post_init__`: a `datetime` without `tzinfo` → `ValueError`.

```python
@dataclass(frozen=True)
class Snapshot:
    data: dict[str, Any]       # CanonicalTask.to_dict()
    hash: str                  # sha256 of the canonical JSON (sort_keys=True, separators=(",", ":"))

    @classmethod
    def of(cls, task: CanonicalTask) -> "Snapshot": ...
    def task(self) -> CanonicalTask: ...
```

```python
@dataclass
class Link:                    # mutable: updated by the engine
    canonical_id: str          # uuid4 hex
    node: str                  # node string, e.g. "todo.icloud_reminders"
    external_id: str           # uid of the item in the node
    last_observed: Snapshot | None = None
    last_written: Snapshot | None = None
    last_synced: Snapshot | None = None
    last_seen_at: str = ""     # ISO UTC
    tombstone: bool = False
    tombstone_at: str | None = None
```

One canonical task has one `Link` per node. The store is indexed by two in-memory dicts: `by_canonical[canonical_id][node] -> Link` and `by_external[(node, external_id)] -> Link`.

```python
@dataclass(frozen=True)
class Capabilities:
    create: bool
    update: bool
    delete: bool
    due: Literal["datetime", "date", "none"]
    description: bool
```

```python
DeletePolicy = Literal["true", "false", "soft"]   # in YAML: true | false | soft

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
    a: str                                   # node
    b: str                                   # node
    interval: int = 60                       # seconds, >= 15
    conflict: Literal["prefer_a", "prefer_b"] = "prefer_a"
    initial_sync: Literal["merge", "dry_run"] = "merge"
    a_to_b: DirectionRule = DirectionRule()
    b_to_a: DirectionRule = DirectionRule()
    enabled: bool = True
```

## 3. Plugin contract (`plugins/base.py`)

```python
class PluginSchema:                 # frozen dataclass
    plugin_id: str                  # "ha_todo"
    fields: frozenset[str]          # subset of FIELDS that the plugin can read/write
    extensions: frozenset[str]      # names of extension fields declared by the plugin (MVP: empty)

class Plugin(ABC):
    schema: PluginSchema

    @abstractmethod
    def matches(self, node: str) -> bool:
        """Whether the plugin serves the node string (ha_todo: node.startswith('todo.'))."""

    @abstractmethod
    async def capabilities(self, node: str) -> Capabilities:
        """Capabilities of the given node. Raises NodeUnavailable."""

    @abstractmethod
    async def list(self, node: str) -> dict[str, CanonicalTask]:
        """Full list: external_id -> task. Raises NodeUnavailable on any error.
        Returning a partial result is forbidden."""

    @abstractmethod
    async def create(self, node: str, task: CanonicalTask,
                     known_ids: frozenset[str]) -> str:
        """Creates an item, returns external_id. known_ids — ids already known to the core in the node."""

    @abstractmethod
    async def update(self, node: str, external_id: str, task: CanonicalTask,
                     changed: frozenset[str]) -> None:
        """Writes only the fields from changed."""

    @abstractmethod
    async def delete(self, node: str, external_id: str) -> None: ...

class NodeUnavailable(Exception): ...
```

Rule: the plugin receives a task that is already **downgraded** (see §5). The plugin makes no sync decisions.

## 4. Plugin `ha_todo` (`plugins/ha_todo.py`)

Facts about the HA API (checked against the sources of `homeassistant/components/todo`, version 2026.9):

| What | How |
|---|---|
| Read | `await hass.services.async_call("todo", "get_items", {"entity_id": node}, blocking=True, return_response=True)` → `{node: {"items": [ {uid, summary, status, due?, description?} ]}}`. Fields with `None` are omitted. `due` is an ISO string: a date `YYYY-MM-DD` or a datetime with offset. `status`: `needs_action` or `completed` |
| Create | `todo.add_item` with `{"entity_id": node, "item": title, "due_date": date}` or `"due_datetime": datetime`, `"description": str}`. No response |
| Update | `todo.update_item` with `{"entity_id": node, "item": uid, "rename": str, "status": "needs_action"\|"completed", "due_date"\|"due_datetime": ..., "description": ...}`. The `item` field is looked up by uid or by summary; always pass the uid. To clear `due`, pass `"due_date": None` |
| Delete | `todo.remove_item` with `{"entity_id": node, "item": [uid]}` |
| Capabilities | `hass.states.get(node).attributes.get("supported_features", 0)`; bits: CREATE=1, DELETE=2, UPDATE=4, MOVE=8, SET_DUE_DATE=16, SET_DUE_DATETIME=32, SET_DESCRIPTION=64 |
| Unavailability | `hass.states.get(node)` returned `None`, or `state in ("unavailable", "unknown")` → `NodeUnavailable` |
| The service rejects a field the entity does not support | `ServiceValidationError`; therefore fields are filtered by capabilities before the call |

Known capabilities of the stock integrations (from the sources): CalDAV — everything except MOVE (datetime is supported); Google Tasks — no SET_DUE_DATETIME (date only); Local To-do — everything; Shopping List — no due and no description.

Mapping:

| `todo` | Canon |
|---|---|
| `summary` | `title` |
| `description` | `description` |
| `status == "completed"` | `status = "done"`, otherwise `"open"` |
| `due` string | `date` if 10 characters without `T`; otherwise `dt_util.parse_datetime`; if the result is naive — `replace(tzinfo=dt_util.get_default_time_zone())` |

Create (SPEC FR-1, item 4): after `add_item` the plugin calls `get_items`, takes the items whose `uid` is not in the passed set `known_ids`, and picks the one whose canonical form equals the downgraded task being created. If there are several, take the first one. If there are none, retry the read after 1 s, at most 3 attempts, then raise `NodeUnavailable("created item not found")`. For this, the base contract `Plugin.create` (§3) takes `known_ids: frozenset[str]` — the identifiers already known to the core at the time of the call.

## 5. Downgrade (`core/downgrade.py`)

```python
def downgrade(task: CanonicalTask, caps: Capabilities) -> CanonicalTask:
    # due: datetime and caps.due == "date"  -> dt_util.as_local(due).date()
    # due: any and caps.due == "none"       -> None
    # description and not caps.description  -> None
    # extensions -> {} (ha_todo declares no extensions)

def equivalent(observed: CanonicalTask, expected: CanonicalTask, caps: Capabilities) -> bool:
    return Snapshot.of(observed).hash == Snapshot.of(downgrade(expected, caps)).hash
```

The `due: date_only` transform from the direction rule is applied before the downgrade, with the same conversion as for `caps.due == "date"`.

## 6. Engine (`core/engine.py`)

One cycle for one pair. The whole algorithm is a sequence of pure functions plus write operations. No parallelism inside a pair.

```python
class SyncEngine:
    def __init__(self, store: LinkStore, registry: PluginRegistry, clock: Callable[[], dt.datetime]): ...

    async def run_pair(self, pair: SyncPair, *, dry_run: bool) -> RunResult:
        ...
```

### 6.1 Steps

1. **Plugins and capabilities.** `pa = registry.for_node(pair.a)`, `pb = ...`. `caps_a = await pa.capabilities(pair.a)`, `caps_b`. `NodeUnavailable` → `RunResult(error=...)`, exit.
2. **Full read.** `snap_a = await pa.list(pair.a)`, `snap_b`. An exception → exit with an error. From here on, both lists are considered complete (FR-6.1).
3. **Link state.** `links = store.links_for_pair(pair.a, pair.b)` — all canonical tasks that have a link to at least one of the two nodes. Tombstone links go into `tombstoned_ext_ids` per node and are skipped from here on.
4. **Classification for each canonical task** (`core/diff.py`):

   ```python
   @dataclass(frozen=True)
   class SideState:
       kind: Literal["unchanged", "changed", "deleted", "echo", "missing_link"]
       current: CanonicalTask | None
       changed_fields: frozenset[str]     # relative to link.last_synced
   def classify(link: Link | None, current: CanonicalTask | None, caps: Capabilities) -> SideState
   ```

   Rules of `classify`:
   - `link is None` → `missing_link` (the task is not yet created on this side).
   - `current is None` → `deleted`.
   - `hash(current) == link.last_observed.hash` → `unchanged`.
   - `link.last_written` and `equivalent(current, link.last_written.task(), caps)` → `echo`.
   - otherwise `changed`, `changed_fields = {f for f in FIELDS if current[f] != last_synced[f]}`, with the downgrade taken into account for `due`.

5. **Decision** (`core/conflict.py` + `core/router.py`) → list of `Action`:

   | A | B | Action |
   |---|---|---|
   | unchanged/echo | unchanged/echo | update `last_observed` on echo |
   | changed | unchanged/echo | `router.plan_update(pair.a_to_b, task_a, changed_a)` → `UpdateAction(B)`, or nothing if the operation is forbidden |
   | unchanged/echo | changed | symmetric, via `b_to_a` |
   | changed | changed | `conflict.merge(task_a, changed_a, task_b, changed_b, pair.conflict)` → resulting task; `UpdateAction` on both sides for the fields where a side differs from the result |
   | deleted | unchanged/echo/changed | see §6.2 |
   | unchanged/echo/changed | deleted | symmetric |
   | deleted | deleted | `TombstoneAction` |
   | missing_link | changed/unchanged | `router.plan_create(pair.b_to_a, task_b)` → `CreateAction(A)`, or a `TombstoneAction`-like "do not sync" mark (`LinkOnlyAction` with `tombstone=True` on side A) |
   | changed/unchanged | missing_link | symmetric |

   `complete`: a change of the `status` field alone counts as the `complete` operation and is checked against the `complete` rule, not `update`.

6. **New items.** `new_a = {eid for eid in snap_a if (pair.a, eid) not in store.by_external}`; likewise `new_b`. First `matching.pair_up(new_a, new_b, caps_a, caps_b)` (FR-8.3): a match of `title` and downgraded `due` → `LinkAction` on both sides with no write. The rest become a `CreateAction` on the opposite side via `router.plan_create`, if allowed and the filter passes; otherwise a `LinkOnlyAction` (a link to one side only, so the item is not reprocessed).
7. **Initial cycle.** If `store.pair_initialized(pair.id)` is false: all `DeleteAction` and `SoftDeleteAction` are dropped (FR-8.1); after a successful cycle call `store.mark_pair_initialized(pair.id)`.
8. **Execution.** If `dry_run or pair.initial_sync == "dry_run"` — return the plan without writing. Otherwise, for each action in order: execute it, update the `Link` (`last_written = Snapshot.of(downgrade(task, caps))`, `last_synced = Snapshot.of(task)`, `last_observed` is updated on the next read), `await store.save()`. An action error → record it in the result, continue with the rest.
9. **Result.** `RunResult(ok: bool, error: str | None, actions_planned: list[Action], actions_applied: list[Action], actions_failed: list[tuple[Action, str]], links: int)`.

### 6.2 Delete (FR-5.4, FR-6)

Side X is deleted, side Y is in state S, `rule = direction X→Y`:

| S | rule.delete | Action |
|---|---|---|
| unchanged/echo | `true` | `DeleteAction(Y)` + tombstone |
| unchanged/echo | `soft` | `SoftDeleteAction(Y)` (update status=done) + tombstone |
| unchanged/echo | `false` | tombstone only |
| changed | the policy prefers X | same as for unchanged |
| changed | the policy prefers Y and the reverse `create` rule is allowed | `CreateAction(X)` with the task of Y, the link is updated to the new external_id |
| changed | otherwise | tombstone only |

### 6.3 Actions (`core/actions.py`)

```python
@dataclass(frozen=True)
class Action:
    kind: Literal["create", "update", "complete", "delete", "soft_delete", "link", "tombstone"]
    node: str
    canonical_id: str
    task: CanonicalTask | None = None
    external_id: str | None = None
    changed: frozenset[str] = frozenset()
    reason: str = ""
```

The plan is serialized to a list of dicts for the sensor and for the `dry_run` service response.

## 7. YAML configuration (`schema.py`)

```yaml
halltasker:
  pairs:
    - id: yandex_to_icloud          # required, unique, [a-z0-9_]+
      a: todo.yandex_dela           # required, entity_id of the todo domain
      b: todo.icloud_reminders      # required
      interval: 60                  # >= 15, default 60
      conflict: prefer_a            # prefer_a | prefer_b
      initial_sync: merge           # merge | dry_run
      enabled: true
      a_to_b:                       # all keys are optional
        create: true
        update: true
        complete: true
        delete: true                # true | false | soft
        filter:
          title_regex: "^(?!#).*"   # valid regex, checked on load
          require_due: false
        transform:
          due: keep                 # keep | date_only | drop
          title_prefix: ""
      b_to_a: {}
```

The schema is built on `voluptuous` (HA 2026.9). `schema.py` exports `CONFIG_SCHEMA` and `def parse_pairs(conf: dict) -> list[SyncPair]`. When HA moves to `probatio`, only this file changes.

`__init__.py`: `async_setup(hass, config)` saves `config[DOMAIN]` to `hass.data[DOMAIN]["yaml"]` and starts the import flow (`hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_IMPORT}, data={})`) if there is no ConfigEntry yet. `async_setup_entry` builds `SyncCoordinator` from the YAML (not from `entry.data`), registers the services and the `sensor` platform. `async_unload_entry` stops the coordinator.

## 8. Coordinator (`coordinator.py`)

```python
class SyncCoordinator:
    def __init__(self, hass, pairs: list[SyncPair], engine: SyncEngine): ...
    async def async_start(self) -> None:
        # for each pair: async_track_time_interval(hass, cb, timedelta(seconds=pair.interval))
        # for all nodes: async_track_state_change_event(hass, entity_ids, on_state) → debounce 2 s → run the pairs with this node
        # first run of all pairs 10 s after start
    async def async_stop(self) -> None: ...
    async def async_run_pair(self, pair_id: str, *, dry_run: bool = False) -> RunResult:
        # asyncio.Lock per pair: concurrent runs are serialized
    @property
    def results(self) -> dict[str, RunResult]:   # last result per pair, read by the sensor
    def subscribe(self, cb: Callable[[str], None]) -> Callable[[], None]:   # notifies sensors
```

## 9. Store (`core/link_store.py`)

`Store(hass, version=1, key="halltasker")`. Format:

```json
{
  "links": [ {Link as dict} ],
  "initialized_pairs": ["yandex_to_icloud"]
}
```

```python
class LinkStore:
    async def load(self) -> None
    async def save(self) -> None            # Store.async_save, no delay
    def get(self, node: str, external_id: str) -> Link | None
    def links_of(self, canonical_id: str) -> dict[str, Link]
    def links_for_pair(self, a: str, b: str) -> dict[str, dict[str, Link]]   # canonical_id -> {node: Link}
    def upsert(self, link: Link) -> None
    def new_canonical_id(self) -> str
    def pair_initialized(self, pair_id: str) -> bool
    def mark_pair_initialized(self, pair_id: str) -> None
    def purge_tombstones(self, older_than_days: int = 30, now: dt.datetime) -> int
```

The core does not import HA: `LinkStore` accepts an object with the methods `async_load() -> dict | None` and `async_save(dict)` (duck typing); tests replace it with an in-memory one.

## 10. Sensor and services

- `sensor.py`: one `SensorEntity` per pair, `unique_id = f"halltasker_{pair.id}"`, `name = f"HAlltasker {pair.id}"`, state from `RunResult`: `error` if `not ok`, `dry_run` if the mode is dry_run, `disabled` if `not pair.enabled`, otherwise `ok`. Attributes per FR-10.3. Updated through `coordinator.subscribe`.
- Services in `__init__.py`: `sync_now` (`pair_id` optional) and `dry_run` (`pair_id` optional, `SupportsResponse.ONLY`, returns `{"pairs": {pair_id: [actions]}}`). Descriptions are in `services.yaml`.

## 11. Logging

`_LOGGER = logging.getLogger(__package__)`. One `INFO` line per cycle: `pair=%s ok=%s planned=%d applied=%d failed=%d links=%d duration=%.2fs`. Actions with task content — `DEBUG`. `NodeUnavailable` — `WARNING`, at most once per 10 minutes per node (a simple rate limit in the coordinator).

## 12. Testing

- `tests/core/`: pure Python, no HA. `FakeStorage` with in-memory `async_load/async_save`. `FakePlugin` with controllable lists and capabilities, recording calls. All acceptance scenarios of group A from SPEC §7 are checked through it at the engine level.
- `tests/plugins/test_ha_todo.py`: the `hass` fixture from `pytest-homeassistant-custom-component`; services of the `todo` domain are registered manually through `hass.services.async_register` with call recording; entity state through `hass.states.async_set("todo.x", "0", {"supported_features": 127})`.
- `tests/test_init.py`: loading the integration from YAML, creation of the ConfigEntry, appearance of the sensor.
- `tests/conftest.py`: `pytest_plugins = "pytest_homeassistant_custom_component"`, autouse fixture `auto_enable_custom_integrations`.

Commands: see `CLAUDE.md`.

## 13. Future extension

- New plugin: a module in `plugins/`, the class inherits `Plugin`, registered in `registry.py`; a node string with a prefix such as `jira:PROJ-123` is resolved through `matches`. The core does not change.
- Groups of N nodes: the engine already works with a canonical task and a set of links; it will need `SyncPair` extended to `SyncGroup` and the decision table in §6.1 generalized.
- UI: config/options flow on top of the same `parse_pairs`; YAML stays the source of truth until a separate decision.
