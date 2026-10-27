# HAlltasker — architecture (v1.1.1, 2026-10-28)

> Language: English only (agent-facing, binding). A Russian reading copy is in [docs/ru/ARCHITECTURE.md](ru/ARCHITECTURE.md); if they differ, this file wins.

This document describes **how** `docs/SPEC.md` is implemented. The signatures and data structures here are binding: tasks in `docs/TASKS.md` refer to them by name. Changes against v1.0 are listed in §14.

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
├── __init__.py        load YAML → ConfigEntry, register services (incl. reload)
├── coordinator.py     schedule: one timer per pair + state_changed events → engine.run_pair; one global lock
├── core/
│   ├── model.py       CanonicalTask, Snapshot, Link, SyncPair, DirectionRule, Capabilities
│   ├── link_store.py  LinkStore (all pairs) and PairLinks (one pair's namespace) on top of Store
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

**Links are scoped to a pair.** Every pair has its own namespace of links and canonical ids (`PairLinks`, §9). Inside a namespace one canonical task has at most one `Link` per node, so at most two links. The same `todo.*` item has one independent link in each pair it takes part in. Pairs never read or write each other's links.

A namespace is indexed by two in-memory dicts: `by_canonical[canonical_id][node] -> Link` and `by_external[(node, external_id)] -> Link`.

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
| Field `completed` | Since HA 2026.9 `TodoItem` has `completed: datetime \| None` (completion time), and `get_items` returns it when set. The plugin ignores it; it is not part of the canonical model |
| The service rejects a field the entity does not support | `ServiceValidationError`; therefore fields are filtered by capabilities before the call |

Known capabilities of the stock integrations (from the sources): CalDAV — everything except MOVE (datetime is supported); Google Tasks — no SET_DUE_DATETIME (date only); Local To-do — everything; Shopping List — no due and no description.

Mapping:

| `todo` | Canon |
|---|---|
| `summary` | `title` |
| `description` | `description` |
| `status == "completed"` | `status = "done"`, otherwise `"open"` |
| `due` string | `date` if 10 characters without `T`; otherwise `dt_util.parse_datetime`; if the result is naive — `replace(tzinfo=dt_util.get_default_time_zone())` |

Create (SPEC FR-1, item 4): after `add_item` the plugin calls `get_items`, takes the items whose `uid` is not in the passed set `known_ids`, and picks the one whose canonical form equals the downgraded task being created **with `status` forced to `open`**, because stock `todo.add_item` has no status input and always creates an open item. If the task being created is `done`, then once the item is found the plugin calls `todo.update_item` with `status: "completed"` (the item id is the found uid) before returning the uid; a failure of that call raises `NodeUnavailable("created item not completed")`. The engine never sees the intermediate open state. If the process dies between the two calls, the next cycle finds an orphan (step 5 below), which the engine then brings to the expected state with an `update`. If there are several, take the first one. If there are none, retry the read after 1 s, at most 3 attempts, then raise `NodeUnavailable("created item not found")`. For this, the base contract `Plugin.create` (§3) takes `known_ids: frozenset[str]` — the identifiers already known to the core at the time of the call.

## 5. Downgrade (`core/downgrade.py`)

```python
def downgrade(task: CanonicalTask, caps: Capabilities, tz: dt.tzinfo) -> CanonicalTask:
    # due: datetime and caps.due == "date"  -> due.astimezone(tz).date()
    # due: any and caps.due == "none"       -> None
    # description and not caps.description  -> None
    # extensions -> {} (ha_todo declares no extensions)

def equivalent(observed: CanonicalTask, expected: CanonicalTask, caps: Capabilities,
               tz: dt.tzinfo) -> bool:
    return Snapshot.of(observed).hash == Snapshot.of(downgrade(expected, caps, tz)).hash
```

`tz` is the HA local time zone. The core does not import HA, so the engine derives it as `clock().tzinfo` (fallback `dt.UTC`); the integration passes `clock=dt_util.now`.

The `due: date_only` transform from the direction rule is applied before the downgrade, with the same conversion as for `caps.due == "date"`.

## 6. Engine (`core/engine.py`)

One cycle for one pair. The whole algorithm is a sequence of pure functions plus write operations. No parallelism inside a pair, and no parallelism between pairs: the coordinator runs one cycle at a time (§8).

```python
class SyncEngine:
    def __init__(self, store: PairLinks, registry: PluginRegistry, clock: Callable[[], dt.datetime]): ...

    async def run_pair(self, pair: SyncPair, *, dry_run: bool) -> RunResult:
        ...
```

An engine instance works on **one pair's namespace**: the coordinator builds it per cycle as `SyncEngine(link_store.for_pair(pair), registry, clock)`. Inside the engine `self._store` is a `PairLinks` (§9), which has the same link methods as the v1.0 `LinkStore`. Because a pair sees only its own links, a write made by pair P1 into node Y is a regular external change for every other pair that contains Y. This is how changes travel through a shared node (SPEC FR-12).

### 6.1 Steps

1. **Plugins and capabilities.** `pa = registry.for_node(pair.a)`, `pb = ...`. `caps_a = await pa.capabilities(pair.a)`, `caps_b`. `NodeUnavailable` → `RunResult(error=...)`, exit.
2. **Full read.** `snap_a = await pa.list(pair.a)`, `snap_b`. An exception → exit with an error. From here on, both lists are considered complete (FR-6.1).
3. **Link state.** `links = store.links_for_pair(pair.a, pair.b)` — all canonical tasks of this pair's namespace. If either link of a canonical task is a tombstone, both of its external ids go into the per-node `tombstoned` sets and the task is skipped from here on.
3a. **New items.** Before the loop over canonical tasks compute `new_a = {eid: task for eid, task in snap_a.items() if store.get(pair.a, eid) is None and eid not in tombstoned_a}` and `new_b` the same way. These dicts are mutable for the rest of the cycle: step 5 (orphan matching) may remove entries; step 6 plans the rest.
4. **Classification for each canonical task** (`core/diff.py`):

   ```python
   @dataclass(frozen=True)
   class SideState:
       kind: Literal["unchanged", "changed", "deleted", "echo", "missing_link"]
       current: CanonicalTask | None
       changed_fields: frozenset[str]     # relative to link.last_synced
   def classify(link: Link | None, current: CanonicalTask | None, caps: Capabilities,
                tz: dt.tzinfo) -> SideState
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
   | missing_link on X | changed/unchanged | **orphan matching first** (below); if no orphan matches: `create` on X when the rule toward X allows `create` and the filter passes, otherwise `tombstone` on X ("create not allowed") |
   | changed/unchanged | missing_link | symmetric |

   `complete`: a change of the `status` field alone counts as the `complete` operation and is checked against the `complete` rule, not `update`.

   **Capability gating** (SPEC FR-1.3). A write on target side X is planned only if the direction rule toward X allows the operation **and** `caps_X` supports it. One helper in `core/router.py` holds the whole rule and every planning path uses it; no path checks `rule.*` or `caps.*` inline:

   ```python
   Operation = Literal["create", "update", "complete", "delete", "soft_delete"]
   def allowed(rule: DirectionRule, caps: Capabilities, op: Operation) -> bool:
       # create       -> rule.create and caps.create
       # update       -> rule.update and caps.update
       # complete     -> rule.complete and caps.update
       # delete       -> rule.delete == "true" and caps.delete
       # soft_delete  -> rule.delete == "soft" and caps.update   (it is an update of status, not a deletion)
   ```

   Callers: `_plan_update` (table rows 2–3), `_plan_missing` and `_plan_new_items` (`create`), `_plan_delete` (`delete`/`soft_delete` toward Y and the resurrection `create` toward X of §6.2), `_plan_conflict` (the `update` of each side; v1.1 checked neither the rule nor the capabilities there, which is a defect; the filter is still not applied to a merge), and the orphan update below. A capability that is off behaves exactly as a rule that forbids the operation: `update`/`complete` → no action, the change is accepted locally (below); `create` of a new item → `link` only ("not propagated"); `create` on a missing link → `tombstone` ("create not allowed"); `delete`/`soft_delete` → tombstone only, as with `delete: false`. `delete: true` on a node without `caps.delete` does **not** fall back to `soft`. Reasons stay as today; a `link`/`tombstone` planned because of a capability appends " (not supported by node)" to its reason.

   **Orphan matching** (SPEC FR-8.4). A missing link on side X can mean that an earlier `create` on X succeeded but its uid was not found (§4), so an unlinked "orphan" item already sits in X. Before planning `create` on X, call `matching.find_match(expected, new_X, caps_present, caps_X, tz) -> str | None` (`core/matching.py`; same key as `pair_up`: equal `title` and equal `due` downgraded to the weaker capabilities, `status` and `description` are not part of the key; the first match in dict order wins) with `expected = apply_transform(rule_toward_X, present.current, tz)` — the task that `create` on X would write (step 6 and §6.2 build the create action from the same expression). `find_match` downgrades `due` itself; no extra downgrade is needed. Matching the untransformed task would miss an orphan created from the transformed one (`title_prefix`, `due: date_only`/`drop`) and produce a duplicate on both sides. If it returns an external id: plan `link` on X with that id and delete the id from `new_X`, so step 6 does not process it again. Then, if `equivalent(orphan_current, expected, caps_X, tz)` (§5) is false, plan after the `link` an `update`/`complete` on X: `task = expected`, `changed = {f for f in FIELDS if getattr(downgrade(expected, caps_X, tz), f) != getattr(orphan_current, f)}`, kind by `op_for_change(changed)`, `reason = "orphan differs"`, gated by `allowed` like any update; if gated, only the `link` remains. This brings an orphan left open by a failed completion (§4) to `done` and converges a stale orphan instead of leaving the pair divergent. If `find_match` returns `None`: plan as in the table.

   **Locally accepted change** (SPEC FR-3.5). When the decision for a canonical task plans no write action (`create`, `update`, `complete`, `delete`, `soft_delete`), every side in state `changed` whose link exists is accepted locally: append `(link, Snapshot.of(current))` to `context.accepted`. Step 8 sets `last_observed` and `last_synced` of that link to the snapshot. This covers one changed side with the operation forbidden by the rule or the capability or the task rejected by the filter (v1.1), both changed sides when both merge writes are gated, and a matched orphan whose update is gated. When a merge writes to one side only, the other side is refreshed by step 8 ("refresh the source") and needs no entry. Without this, the stale `changed_fields` would later leak the forbidden change into the other side through a conflict merge.

6. **New items.** Use the `new_a`/`new_b` left after step 5. First `matching.pair_up(new_a, new_b, caps_a, caps_b, tz)` (FR-8.3): a match of `title` and downgraded `due` → `link` on both sides with no write. For every other new item on X, with a fresh canonical id:
   - if the rule X→Y allows `create` and the filter passes: `link(X, eid)` **then** `create(Y)`. The source link comes first, so if the create fails, the next cycle sees `missing_link` on Y and retries (with orphan matching);
   - otherwise: `link(X, eid)` only (reason "not propagated"), so the item is not reprocessed.
7. **Initial cycle.** If `store.pair_initialized(pair.id)` is false: all `delete`, `soft_delete` and `tombstone` actions are dropped (FR-8.1; a kept tombstone would forbid a later re-creation). After a successful cycle call `store.mark_pair_initialized(pair.id)`.
8. **Execution.** If `dry_run or pair.initial_sync == "dry_run"` — return the plan without writing. Otherwise, for each action in order: execute it, update the `Link`, `await store.save()`. An action error → record it in the result, continue with the rest.
   - `create` on X: upsert the X link with `last_written = Snapshot.of(downgrade(task, caps_X, tz))`, `last_synced = Snapshot.of(task)`.
   - `update`/`complete` on X: set the same two snapshots on the X link.
   - After `create`/`update`/`complete` on X, **refresh the source**: for the other link of the same canonical task (side Y), if Y is not itself a write target of this cycle, set `last_observed = last_synced = Snapshot.of(current_Y)`. Otherwise the consumed change is re-detected on Y every cycle.
   - `last_observed` of a written link is updated on the next read (it is then an `echo`).
   - After the loop: apply the echo updates (`last_observed`) and the accepted changes (`last_observed` and `last_synced`) from step 5. If there was at least one, call `await store.save()` once. A cycle with no actions, no echoes and no accepted changes performs no store writes.
8a. **Tombstone purge** (SPEC FR-6.5). Not in dry run. `purged = store.purge_tombstones(now=clock(), present={pair.a: snap_a.keys(), pair.b: snap_b.keys()})`. A tombstone link is removed only if it is older than 30 days **and** its external id is absent from the current snapshot of its node. A tombstone whose item still exists (the `delete: false` case: the Y item stays live for the user) is never removed, otherwise the item would reappear as "new" after 30 days and be re-created on the other side. If `purged > 0`, `await store.save()` once more.
9. **Result.** `RunResult(ok: bool, error: str | None, actions_planned: list[Action], actions_applied: list[Action], actions_failed: list[tuple[Action, str]], links: int)`. `links` is the number of live (non-tombstone) link records in the pair's namespace after execution: one synced task counts as 2. `run_pair` catches `NodeUnavailable` and any other `Exception` into `RunResult(ok=False, error=...)`.

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

"Tombstone" in this table means: both links of the canonical task **in this pair** get `tombstone = True` (for `soft`, the Y link is tombstoned after the "done" write). From then on this pair ignores both items. Other pairs are not affected: a `delete` or `soft` write into Y is an ordinary change for them (the item disappears or becomes done) and is handled by their own rules. With `false` the Y item stays live for other pairs.

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

Validation rules beyond field types (all checked in `CONFIG_SCHEMA`, error = the integration does not start):

1. `id` values are unique.
2. `a != b` in every pair.
3. No two pairs connect the same two nodes (in either order).
4. **No cycles:** the undirected graph whose vertices are nodes and whose edges are pairs must be a forest. Check with union-find over the pairs in order: if both nodes of a pair already have the same root, raise `vol.Invalid(f"pairs form a cycle at pair '{id}'")`.

The schema is built on `voluptuous`. Facts for HA 2026.9.4 (checked in the installed package): HA already depends on `probatio==0.11.4` and has started migrating to it (`helpers/config_validation.py` imports both), but almost all of HA core still uses `voluptuous`, which is a real package installed through HA's own dependencies (`annotatedyaml`, `hass_nabucasa`). `schema.py` stays on `voluptuous`; re-check this when the pinned HA version is raised. Only `schema.py` changes when we move to `probatio`. `schema.py` exports `CONFIG_SCHEMA` and `def parse_pairs(conf: dict) -> list[SyncPair]`; HA reads `CONFIG_SCHEMA` from the integration module, so `__init__.py` re-exports it (listed in `__all__`).

`__init__.py`:

- `async_setup(hass, config)` saves `config[DOMAIN]` to `hass.data[DOMAIN]["yaml"]`, registers the `reload` service (below), and, if there is no ConfigEntry yet, starts the import flow with `hass.async_create_task(hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_IMPORT}, data={}))`. Awaiting `async_init` inside `async_setup` deadlocks the setup.
- `async_setup_entry` builds `LinkStore`, `PluginRegistry` and `SyncCoordinator` from `hass.data[DOMAIN]["yaml"]` (not from `entry.data`), registers `sync_now`/`dry_run` and forwards the `sensor` platform with `hass.config_entries.async_forward_entry_setups(entry, ["sensor"])`.
- `async_unload_entry` stops the coordinator, unloads the platform with `hass.config_entries.async_unload_platforms(entry, ["sensor"])` and removes `sync_now`/`dry_run`.

**Reload** (SPEC FR-10.5). `homeassistant.reload_config_entry` does **not** re-read `configuration.yaml`: the entry is rebuilt from the YAML loaded at startup. Therefore HAlltasker has its own service `halltasker.reload`:

```python
from homeassistant.helpers.reload import async_integration_yaml_config
from homeassistant.helpers.service import async_register_admin_service

async def _handle_reload(call: ServiceCall) -> None:
    config = await async_integration_yaml_config(hass, DOMAIN)   # validated by CONFIG_SCHEMA; None on error
    if config is None or DOMAIN not in config:
        _LOGGER.error("halltasker: reload skipped, configuration is missing or invalid")
        return
    hass.data[DOMAIN]["yaml"] = config[DOMAIN]
    for entry in hass.config_entries.async_entries(DOMAIN):
        await hass.config_entries.async_reload(entry.entry_id)

async_register_admin_service(hass, DOMAIN, "reload", _handle_reload)   # in async_setup
```

`async_integration_yaml_config` is imported into the `__init__.py` namespace by name, so tests can patch `custom_components.halltasker.async_integration_yaml_config`.

## 8. Coordinator (`coordinator.py`)

```python
class SyncCoordinator:
    def __init__(self, hass, pairs: list[SyncPair],
                 engine_factory: Callable[[SyncPair], SyncEngine]): ...
    async def async_start(self) -> None:
        # for each pair: async_track_time_interval(hass, cb, timedelta(seconds=pair.interval))
        # for all nodes: async_track_state_change_event(hass, entity_ids, on_state) → debounce 2 s → run the pairs with this node
        # first run of all pairs 10 s after start
    async def async_stop(self) -> None: ...
    async def async_run_pair(self, pair_id: str, *, dry_run: bool = False) -> RunResult:
        # ONE asyncio.Lock shared by all pairs: at most one cycle runs at any time
        # engine = self._engine_factory(pair)
        # async with asyncio.timeout(CYCLE_TIMEOUT_SECONDS): result = await engine.run_pair(pair, dry_run=dry_run)
        # TimeoutError -> RunResult(ok=False, error="cycle timeout"); the lock is released
        # after the cycle: chained run (below)
    @property
    def results(self) -> dict[str, RunResult]:   # last result per pair, read by the sensor
    def subscribe(self, cb: Callable[[str], None]) -> Callable[[], None]:   # notifies sensors
```

In `__init__.py`: `engine_factory = lambda pair: SyncEngine(link_store.for_pair(pair), registry, clock=dt_util.now)`.

Why one global lock: pairs that share a node read and write the same `todo.*` entity. Two concurrent cycles could interleave a `create` in one pair with the uid lookup of a `create` in another (§4), and the store is saved as a whole. Cycles are short (a few service calls), so serializing them costs nothing noticeable.

**Cycle timeout** (SPEC FR-9.4, Q-2). A hanging `todo.*` service call would hold the global lock forever, so the engine call is wrapped in `asyncio.timeout(CYCLE_TIMEOUT_SECONDS)` (`const.py`, 120). The timeout is caught in the coordinator and becomes `RunResult(ok=False, error="cycle timeout")` with empty action lists; it is logged like any other pair error. Interrupting a cycle is safe: the store is saved after every applied action (§6.1 step 8), and a `create` cancelled between the service call and the uid lookup leaves an orphan that step 5 links on the next cycle.

**Chained run** (SPEC FR-12.6). `state_changed` does not fire on a title or due edit (FR-9.2), so a change written by pair P1 into a shared node Y would otherwise reach the other pairs of Y only on their next interval (one `interval` per hop). Therefore, after a cycle with a non-empty `actions_applied`, the coordinator collects the nodes of the applied `create`/`update`/`complete`/`delete`/`soft_delete` actions and schedules every other enabled pair that contains one of those nodes through the same 2-second debounce as `state_changed`. The chain ends by itself: a pair whose nodes are unchanged applies nothing. Dry runs never chain.

HA facts (2026.9): a function passed to `async_call_later` or `async_track_time_interval` must itself be decorated with `@callback` (decorating a factory that returns it is not enough); otherwise it runs in the executor and `hass.async_create_task` raises a thread-safety `RuntimeError`.

## 9. Store (`core/link_store.py`)

`Store(hass, version=1, key="halltasker")`. The HA store version stays 1; our own data format is versioned by the `schema` key inside the data. Format (schema 2):

```json
{
  "schema": 2,
  "pairs": {
    "yandex_to_icloud": {
      "nodes": ["todo.yandex_dela", "todo.icloud_reminders"],
      "initialized": true,
      "links": [ {Link as dict} ]
    }
  }
}
```

```python
class PairLinks:
    """One pair's namespace. Same link methods as the v1.0 LinkStore."""
    pair_id: str
    nodes: tuple[str, str]
    def get(self, node: str, external_id: str) -> Link | None
    def links_of(self, canonical_id: str) -> dict[str, Link]
    def links_for_pair(self, a: str, b: str) -> dict[str, dict[str, Link]]   # canonical_id -> {node: Link}
    def upsert(self, link: Link) -> None
    def new_canonical_id(self) -> str
    def pair_initialized(self, pair_id: str) -> bool        # pair_id must equal self.pair_id, else ValueError
    def mark_pair_initialized(self, pair_id: str) -> None   # pair_id must equal self.pair_id, else ValueError
    def purge_tombstones(self, *, older_than_days: int = 30, now: dt.datetime,
                         present: Mapping[str, Collection[str]]) -> int
        # removes a tombstone link only if tombstone_at < now - older_than_days
        # AND link.external_id not in present.get(link.node, ()); returns the count
    async def save(self) -> None                            # delegates to the owning LinkStore.save()

class LinkStore:
    async def load(self) -> None
    async def save(self) -> None            # Store.async_save of to_dict(), no delay
    def to_dict(self) -> dict[str, Any]     # the schema 2 structure above; also used by diagnostics
    def for_pair(self, pair: SyncPair) -> PairLinks
    def pair_ids(self) -> list[str]         # sorted
```

`purge_tombstones` is called by the engine at the end of every successful non-dry cycle (§6.1 step 8a); there is no other purge.

Rules:

- `for_pair(pair)` returns the existing namespace for `pair.id`, or creates an empty one with `nodes = (pair.a, pair.b)` and `initialized = False`. It always returns the same object for the same pair id.
- If an existing namespace has `nodes` different from `{pair.a, pair.b}` (compare as sets, so swapping `a` and `b` is allowed), the user re-pointed an existing pair id to other nodes: replace the namespace with an empty one for the new nodes and log `WARNING "halltasker: pair %s now connects %s and %s; its links were reset"`. The next cycle is an initial `merge` (SPEC FR-12.5).
- Namespaces of pair ids that are no longer in the configuration are kept untouched (a temporarily removed pair keeps its links).
- `load()`: if the data is `None` → empty store. If `data.get("schema") != 2` (v1.0 data has a top-level `"links"` key) → log `WARNING "halltasker: link storage format is outdated and was discarded"` and start empty. The project is pre-release; the initial `merge` re-links existing tasks by the matching heuristic.

The core does not import HA: `LinkStore` accepts an object with the methods `async_load() -> dict | None` and `async_save(dict)` (duck typing); tests replace it with an in-memory one. The core may use the standard `logging` module.

## 10. Sensor and services

- `sensor.py`: one `SensorEntity` per pair, `unique_id = f"halltasker_{pair.id}"`, `name = f"HAlltasker {pair.id}"`, state from `RunResult`: `error` if `not ok`, `dry_run` if the mode is dry_run, `disabled` if `not pair.enabled`, otherwise `ok`. Attributes per FR-10.3. Updated through `coordinator.subscribe`.
- Services in `__init__.py`: `sync_now` (`pair_id` optional) and `dry_run` (`pair_id` optional, `SupportsResponse.ONLY`, returns `{"pairs": {pair_id: [actions]}}`), both registered in `async_setup_entry`; `reload` (no fields), registered in `async_setup` with `async_register_admin_service` (§7). Without `pair_id`, `sync_now` runs the pairs one after another in configuration order. Descriptions are in `services.yaml`.
- `diagnostics.py`: `{"pairs": [...], "store": async_redact_data(link_store.to_dict(), {"title", "description"}), "results": {...}}` with `async_redact_data` from `homeassistant.components.diagnostics` (SPEC FR-10.4, Q-3): the snapshots keep `hash`, `status` and `due`, the task texts are replaced by `**REDACTED**`. `results` contain actions with tasks; redact them with the same call.

## 11. Logging

`_LOGGER = logging.getLogger(__package__)`. One `INFO` line per cycle: `pair=%s ok=%s planned=%d applied=%d failed=%d links=%d duration=%.2fs`. Actions with task content — `DEBUG`. `NodeUnavailable` — `WARNING`, at most once per 10 minutes per node (a simple rate limit in the coordinator).

## 12. Testing

- `tests/core/`: pure Python, no HA. `FakeStorage` with in-memory `async_load/async_save`. `FakePlugin` with controllable lists and capabilities, recording calls. All acceptance scenarios of group A from SPEC §7 are checked through it at the engine level.
- `tests/plugins/test_ha_todo.py`: the `hass` fixture from `pytest-homeassistant-custom-component`; services of the `todo` domain are registered manually through `hass.services.async_register` with call recording; entity state through `hass.states.async_set("todo.x", "0", {"supported_features": 127})`.
- `tests/test_init.py`: loading the integration from YAML, creation of the ConfigEntry, appearance of the sensor.
- `tests/conftest.py`: `pytest_plugins = "pytest_homeassistant_custom_component"`, autouse fixture `auto_enable_custom_integrations`.
- `tests/todo_platform.py` + `tests/test_e2e.py`: end-to-end tests through the **real** `todo.*` services. `local_todo` cannot be used in tests (it needs the `ical` package, which is not in `requirements_dev.txt`), so the tests register an in-memory `TodoListEntity` platform under a test domain (`MemoryTodoEntity`, built the same way as HA's own `tests/components/todo` helpers). The helpers exist in the installed `pytest_homeassistant_custom_component.common`: `MockModule`, `MockPlatform`, `MockConfigEntry`, `mock_integration(hass, MockModule("test", ...))`, `mock_platform(hass, "test.todo", MockPlatform(async_setup_entry=...))`. The entity implements `todo_items`, `async_create_todo_item`, `async_update_todo_item`, `async_delete_todo_items` over a dict and sets `_attr_supported_features` from a constructor argument, so one test can build a full-featured node and a date-only node. This catches what fake services cannot: `ServiceValidationError` on unsupported fields, the real `get_items` serialization, uid lookup.
- In integration tests the manifest dependency `"todo"` loads the real todo services; tests that fake the services must register the fakes **after** the integration setup (the last registration wins).
- The `pytest-homeassistant-custom-component` clock starts at the real "now"; use `dt_util.utcnow()` plus deltas with `async_fire_time_changed`, not fixed synthetic datetimes.

Commands: see `CLAUDE.md`.

## 13. Future extension

- New plugin: a module in `plugins/`, the class inherits `Plugin`, registered in `registry.py`; a node string with a prefix such as `jira:PROJ-123` is resolved through `matches`. The core does not change.
- Groups of N nodes: in v1.1 a node may already be shared by several pairs (a forest of pairs). A true N-node group with one canonical task across all nodes would need a new namespace kind and a generalized decision table; not planned.
- UI: config/options flow on top of the same `parse_pairs`; YAML stays the source of truth until a separate decision.

## 14. Changes in v1.1 (2026-10-26)

Source: the implementation of T-01…T-21 on branch `zcode`, `docs/IMPLEMENTATION_NOTES.md`, `docs/LINK_CHECK.md`, Q-1.

Implementer decisions adopted as binding:

- `tz` parameter of `downgrade`/`equivalent`/`classify`; the engine derives it from `clock()` (§5).
- `purge_tombstones` takes `now` as keyword-only (§9).
- New item: `link(source)` before `create(target)` (§6.1 step 6).
- Source refresh after `create`/`update`/`complete` (§6.1 step 8).
- The first cycle drops `delete`, `soft_delete` and `tombstone` (§6.1 step 7).
- `RunResult.links` counts live link records, two per synced task (§6.1 step 9).
- Store saves: after every applied action; one extra save only for echo/accepted updates or the first cycle; a no-op cycle performs no writes.
- HA 2026.9 facts: `config_entries.async_forward_entry_setups`, `hass.async_create_task` for the import flow, `@callback` on timer closures, `CONFIG_SCHEMA` re-export, test-ordering of fake services, phacc clock (§7, §8, §12).

New in v1.1:

- Several pairs per node (SPEC FR-12): per-pair link namespaces (`PairLinks`, schema 2 storage), engine per cycle via `engine_factory`, one global lock, forest-only validation (§2, §6, §7, §8, §9).
- Orphan matching before `create` (§6.1 step 5, SPEC FR-8.4).
- Tombstone purge moved into the engine cycle and restricted to items that are gone from the node (§6.1 step 8a, §9, SPEC FR-6.5). In v1.0 the purge was never called.
- Locally accepted changes for operations forbidden by a rule (§6.1 step 5, SPEC FR-3.5).
- Service `halltasker.reload`, because `reload_config_entry` does not re-read YAML (§7, SPEC FR-10.5).
- End-to-end tests with an in-memory `todo` platform (§12).
- From the implementer's review of v1.1 (Q-2, Q-3): cycle timeout under the global lock and chained runs of the pairs of a written node (§8); task texts redacted in diagnostics (§10).
- Corrected facts: probatio/voluptuous status in HA 2026.9 (Q-1), `TodoItem.completed` (§4, §7).

New in v1.1.1 (2026-10-28), from review remarks on IT-21, IT-24, IT-34:

- `router.allowed(rule, caps, op)` gates every planned write by rule **and** target capabilities, including the conflict merge, which v1.1 did not gate at all; `soft_delete` needs `caps.update` (§6.1 step 5, "Capability gating").
- Locally accepted change generalized: no write action planned → every `changed` side accepted (§6.1 step 5).
- `ha_todo.create` of a done task = `add_item` + lookup with `status` forced open + `update_item(status)` by uid (§4).
- Orphan matching uses `apply_transform(rule, present.current, tz)` — what `create` would write — and converges a differing orphan with a gated `update`/`complete` (§6.1 step 5).
