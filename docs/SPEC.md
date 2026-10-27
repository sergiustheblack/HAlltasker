# HAlltasker — technical specification (v1.1, 2026-10-26)

Status: approved for development. Changes only by editing this file. Changes against v1.0 are listed in §9.

> Language: English only (agent-facing, binding). A Russian reading copy is in [docs/ru/SPEC.md](ru/SPEC.md); if they differ, this file wins.

## 1. Goal

Two-way synchronization of tasks and reminders between ecosystems (Yandex Alice, Apple Reminders, Google Tasks, Home Assistant lists). A task created in one system appears in the other systems and is kept in a consistent state there. Implemented as a custom integration for Home Assistant (hereafter HA), installed through HACS.

## 2. Key decisions

| Question | Decision |
|---|---|
| Platform, language | HA custom integration, Python 3.14+, stable HA 2026.9.x |
| Responsibility boundary | The core contains no authorization and no private APIs of external systems. The only data source in the MVP is the HA `todo.*` entities created by other integrations |
| Apple Reminders | Through the stock HA CalDAV integration to iCloud (`caldav.icloud.com`) |
| Google Tasks | Through the stock HA Google Tasks integration |
| Yandex | Through the stock HA CalDAV to `caldav.yandex.ru` (Calendar to-do items (дело)). Status: **experimental**, confirmed by stage 0 (see `docs/RESEARCH.md`). Alice reminders with an exact time are a separate experimental scenario; if needed, the source is added by an external PR to YandexStation, not to this core |
| Configuration | **YAML only** (`configuration.yaml`). Config/options flow in the UI is out of the MVP. Technical detail: an import flow creates one ConfigEntry from YAML for reload and diagnostics |
| Conflicts | Policy per pair: `prefer_a` (default) or `prefer_b`. Fields changed on one side only are merged. True last-write-wins is impossible: HA does not expose task modification times |
| Routing | Node pairs A↔B; each pair has rules for the A→B and B→A directions. A node may take part in several pairs (FR-12); the pairs must not form a cycle |
| Sync scope | create, field update, complete/uncomplete, delete. Each can be switched on and off in the rules |
| Notifications | Duplicate notifications from different systems are accepted; the core does not interfere |
| Users | One. Multiple accounts are not blocked: node = any `todo.*` entity, and there can be any number of them |
| Recurring tasks | Fully out of scope |
| Yandex shopping list | Out of the first iteration. Later, through the existing YandexStation bridge |

## 3. MVP scope

Included:

- Canonical task: `title`, `description`, `status` (open/done), `due` (none, a date, or a date+time with time zone), `extensions`.
- One plugin `ha_todo`: any `todo.*` entity as a node. Covers CalDAV (iCloud, Yandex), Google Tasks, Local To-do, Shopping List, and future integrations with no new code.
- Node pairs with per-direction rules: allowed operations, filters, transforms.
- Internal storage of links and tombstones in `.storage/halltasker`.
- Initial sync in the modes `merge` (default) and `dry_run`.
- Polling with a per-pair interval; reaction to HA events as a speed-up.
- Services `halltasker.sync_now`, `halltasker.dry_run`; a status sensor per pair; diagnostics without secrets.

Not included:

- RRULE, subtasks, attachments, tags, priorities, geo-reminders, item ordering.
- Notes, calendar events, task trackers, shopping list. The architecture leaves room for them as future plugins.
- Configuration UI, suppression of duplicate notifications, own clients for external APIs.

## 4. Terms

- **Node** — a specific task list in a specific system. In the MVP a node is given by the string `todo.<entity_id>`.
- **Plugin** — an internal HAlltasker module with a single contract (§6.2): it describes its capabilities, reads and writes nodes, and converts its own model to the canonical one and back. A plugin is not a separate HA integration.
- **Canonical task (CanonicalTask)** — the internal representation of a task, shared by all plugins.
- **Snapshot** — a serialized canonical task plus its hash.
- **Link** — a record "canonical task ↔ external id in a node" with three snapshots (`last_observed`, `last_written`, `last_synced`) and the flag `tombstone`.
- **Pair (SyncPair)** — two nodes A and B, a polling interval, a conflict policy, an initial sync mode, and direction rules.
- **Direction rule (DirectionRule)** — for the direction X→Y: which operations are allowed (`create`, `update`, `complete`, `delete` with the values true/false/soft), the filter, and the transforms.
- **Capabilities** — the set of fields and operations that a specific node supports. For `todo.*` it is read from the `supported_features` attribute.
- **Downgrade** — reducing a canonical task to the capabilities of a node (for example, `datetime` → `date` for Google Tasks). A downgrade is not a change and does not create a conflict.
- **Echo** — reading from a node a value that HAlltasker itself wrote earlier. An echo is not a change.
- **Tombstone** — a mark that a link is deleted. It forbids re-creation and repeated processing.

## 5. Functional requirements

### FR-1 Plugin `ha_todo`

1. Node = an `entity_id` of the `todo` domain.
2. Reading through the service `todo.get_items` with `return_response=True`. Writing through `todo.add_item`, `todo.update_item`, `todo.remove_item` with `blocking=True`.
3. Capabilities are read from `supported_features` of the entity state: `CREATE_TODO_ITEM=1`, `DELETE_TODO_ITEM=2`, `UPDATE_TODO_ITEM=4`, `SET_DUE_DATE_ON_ITEM=16`, `SET_DUE_DATETIME_ON_ITEM=32`, `SET_DESCRIPTION_ON_ITEM=64`. An operation or field that the node does not support is not called.
4. After `add_item` the plugin re-reads the list and finds the created item by matching content among items that have no link. This is the only way to obtain the `uid`, because the service returns no response.
5. If the entity is missing or unavailable (`unavailable`, `unknown`), the node is considered unavailable, and the pair is skipped with an error in the sensor.

### FR-2 Canonical model and plugin schema

1. `CanonicalTask`: `title: str`, `description: str | None`, `status: "open" | "done"`, `due: None | date | datetime` (a datetime must have tzinfo), `extensions: dict[str, Any]`.
2. A date without time is stored as `date`. Representing it as a `datetime` at midnight is forbidden.
3. The plugin declares a schema: the supported canonical fields, constraints on fields (`due: datetime | date_only | none`), the supported operations, and its own extension fields.
4. The downgrade on write is performed by the core according to node capabilities: `datetime` → `date` in the HA local time zone if the node does not support time; `due` is dropped if the node does not support a date; `description` is dropped if it is not supported.
5. When comparing a read value with the expected one, the core compares the downgraded forms. A date read back when a datetime was expected is not a change.
6. Extensions (`extensions`) are passed only to nodes whose plugin declared the corresponding field. In the MVP the `ha_todo` plugin declares no extensions.

### FR-3 Router

1. For each pair and each direction the following are set: `create`, `update`, `complete` (true/false), `delete` (true/false/soft), `filter` (`title_regex`, `require_due`), `transform` (`due: keep | date_only | drop`, `title_prefix`).
2. Default: all operations are allowed, `delete: true`, no filter, no transforms.
3. The filter is applied to the source's canonical task before writing. A task that does not pass the filter at creation is not created on the other side and is not linked to it.
4. The transform is applied after the filter and before the downgrade.
5. A change on one side that the direction rule does not propagate (the operation is switched off, or the task fails the filter) is accepted on that side as the new synced state. It is not reported again in later cycles and does not leak into the other side through a later merge.

### FR-4 Change detection and echo

1. For each link and each side: the current value is compared by hash with `last_observed`. A match means no change.
2. If the current value matches `last_written`, it is an echo: `last_observed` is updated and no change is recorded.
3. Otherwise it is a change. The set of changed fields is computed relative to `last_synced`.
4. The absence of an item in a successfully read, complete list is a deletion.

### FR-5 Conflict resolution

1. A change on one side only is propagated to the other side according to the direction rule.
2. Changes on both sides with non-overlapping sets of fields are merged. The merged result is written to a side only if the direction rule toward that side allows `update` (or `complete`) and the node supports it (FR-1.3). If neither side may be written, both changes are accepted locally (FR-3.5).
3. Overlapping fields are taken from the side named by the pair policy (`prefer_a` default, `prefer_b`).
4. Deletion on one side and a change on the other: `prefer_a`/`prefer_b` determines whether the deletion wins (if the preferred side is the one that was deleted) or the re-creation wins (if `create` is allowed in the direction toward the side that deleted). Otherwise the link gets a tombstone with no actions.

### FR-6 Deletion

1. A deletion is propagated only if: reading the source node finished without error, the list was read completely, the item is missing, and the link is not a tombstone.
2. With `delete: false` in the direction, both links of the task in this pair get a tombstone, nothing changes on the other side, and the item on the other side is excluded from new-item detection in this pair.
3. With `delete: soft`, the item on the other side is marked as done, and both links get a tombstone.
4. With `delete: true`, the item is deleted on the other side, and both links get a tombstone.
5. A tombstone is kept for at least 30 days. After that it is removed at the end of a sync cycle, but only if the item it points to is absent from the node. A tombstone whose item still exists in the node (the `delete: false` case) is never removed, so the item does not reappear as a new one.
6. A tombstone belongs to one pair. Other pairs that contain the same node see the deletion or the "done" write as an ordinary change and apply their own rules (FR-12).

### FR-7 Idempotency and storage

1. Links are stored only in the internal HA `Store` (`.storage/halltasker`). No markers, prefixes, or hidden fields are added to user tasks.
2. The storage is saved after every successful write operation to an external node, so that a failure between the write and the save does not lead to a duplicate.
3. Re-running a cycle without external changes performs no writes at all.

### FR-8 Initial sync

1. Mode `merge` (default): all unlinked items on both sides are created on the opposite side according to the direction rules. No deletions are performed in the first cycle.
2. Mode `dry_run`: the cycle computes the actions and publishes them to the sensor and the service response; it makes no writes. A pair in `dry_run` stays in it until the configuration is changed.
3. Matching heuristic before creation: a pair of unlinked items with equal `title` and equal downgraded `due` is treated as one task and is linked without creating anything. The heuristic is never used for deletion.
4. Orphan matching: before a linked task is created on the side where its link is missing, the unlinked items of that side are searched with the same heuristic. A match is linked instead of created. This covers a `create` whose item was written but whose uid was not found (FR-1.4), so that no duplicates appear on either side. Known limitation: if that side holds both the orphan and a genuinely new item with the same `title` and `due`, the first one is linked and the other is treated as new; same acceptance as in item 3.

### FR-9 Polling and events

1. Each pair is polled every `interval` seconds (default 60, minimum 15).
2. A state change of any node entity (the `state_changed` event) triggers an out-of-schedule cycle for the pairs that contain this entity, with a 2-second delay to coalesce events. Events are a speed-up; polling is mandatory, because changing a title or a date does not change the state of a `todo.*` entity.
3. An error in one pair does not affect other pairs.
4. A cycle is limited to 120 seconds. A cycle that exceeds it is an error of that pair; the other pairs run as usual. Interrupting a cycle does not create duplicates (FR-7.2, FR-8.4).

### FR-10 Services, sensors, diagnostics

1. `halltasker.sync_now` with an optional `pair_id`: an immediate cycle.
2. `halltasker.dry_run` with an optional `pair_id`: returns the list of planned actions without writing.
3. A sensor per pair `sensor.halltasker_<pair_id>`: state `ok | error | dry_run | disabled`; attributes `last_run`, `links`, `last_error`, `last_actions` (counters by type), `planned_actions` (for dry_run).
4. `diagnostics.py` exports the configuration and the storage. HAlltasker has no secrets by construction; task titles and descriptions are redacted in the export, hashes, statuses and dates are kept.
5. `halltasker.reload` (admin service, no parameters): re-reads the `halltasker:` section of `configuration.yaml`, validates it, and restarts the integration with the new configuration. On a validation error the running configuration is kept and the error is logged. `homeassistant.reload_config_entry` does not re-read YAML and is therefore not a way to apply configuration changes.

### FR-11 YAML configuration

The full schema is in `docs/ARCHITECTURE.md` §7. On a schema error the integration does not start and writes a clear message to the log. Reload through the service `halltasker.reload` (FR-10.5) or by restarting HA.

### FR-12 Several pairs per node

1. The same `todo.*` entity may be a node of several pairs, for example `yandex ↔ icloud`, `yandex ↔ google`, `yandex ↔ home_list`.
2. Each pair keeps its own links and tombstones. A write that one pair makes into a shared node is an ordinary external change for every other pair that contains this node; this is how a change travels across pairs. No pair reads another pair's links.
3. Configuration constraints, checked on load: the two nodes of a pair differ; no two pairs connect the same two nodes; the pairs do not form a cycle (the graph of nodes and pairs is a forest). A violation is a configuration error (FR-11).
4. Sync cycles of different pairs never run concurrently.
5. If an existing pair id is pointed at other nodes, its stored links are discarded with a warning in the log, and the next cycle of this pair is an initial sync (FR-8).
6. After a pair has written into a node, the other pairs that contain this node are run out of schedule (with the FR-9.2 delay), so a change crosses several pairs within seconds rather than one polling interval per pair.

## 6. Non-functional requirements

1. Code follows HA core standards: asyncio, type annotations, `ruff` with no findings, configuration in `pyproject.toml`.
2. Tests: `pytest` + `pytest-homeassistant-custom-component`. The core (`core/`) is tested without HA. The `ha_todo` plugin is tested with substituted services. In addition, end-to-end tests run the real `todo.*` services of HA against an in-memory `todo` platform defined inside `tests/`. Core coverage is not below 90 %.
3. Logs: `INFO` one line per pair cycle with counters, `DEBUG` action details, `WARNING` for node errors. Task content appears in logs only at `DEBUG`.
4. HACS: `hacs.json` and `manifest.json` with a version; they pass `hassfest` and `hacs/action`.
5. External dependencies: only what already exists in HA. New packages in the manifest `requirements` are forbidden for the MVP.

## 7. Acceptance scenarios

Split by confidence level.

### A. Core and confirmed `todo.*` (mandatory)

Environment: two `local_todo` entities in a test HA.

1. Create in A → it appears in B with the same `title`, `due`, `description`.
2. Change `title` in B → it changes in A. A repeated cycle makes no writes.
3. `status: done` in A → `done` in B; back to `open` → `open` in B.
4. Delete in A with `delete: true` → deleted in B; with `delete: soft` → `done` in B; with `delete: false` → B unchanged, A is not re-created.
5. Simultaneous change of `title` in A and `due` in B → both changes are applied on both sides.
6. Simultaneous change of `title` on both sides → the side named by the policy wins.
7. Node B with `supported_features` lacking `SET_DUE_DATETIME_ON_ITEM`: a `due` with time from A is written as a date in B; reading the date back is not counted as a change.
8. `dry_run`: actions are listed, no writes.
9. Initial `merge` sync with identical existing tasks on both sides: they are linked without duplicates.
10. Three nodes A, B, C and two pairs A↔B, B↔C. Create in A → it appears in B after the first pair's cycle and in C after the second pair's cycle. Delete in A with `delete: true` in both pairs → deleted in B and then in C. Repeated cycles of both pairs make no writes.
11. Direction A→B with `update: false`. Change `title` in A → B unchanged; a later change of `due` in B → `due` changes in A, `title` in B stays as it was.
12. `create` on B succeeded, but the uid lookup failed (simulated): the next cycle links the orphan item in B instead of creating a second one; no duplicate appears in A or B.

### B. Integration tests with stock integrations (mandatory, manual)

1. Pair `local_todo` ↔ Google Tasks: scenarios A1–A4, A7.
2. Pair `local_todo` ↔ iCloud CalDAV: scenarios A1–A4. Environment requirement: on the iPhone, iCloud is connected as a CalDAV account, or a list that was not migrated to "upgraded" Reminders is used.

### C. Yandex (experimental, depends on the stage 0 results)

1. Pair Yandex CalDAV `todos-*` ↔ `local_todo`: «Алиса, добавь в список дел на сегодня помыть полы» (Alice, add "wash the floors" to today's to-do list) → a task with `due` set to today appears in `local_todo` no later than two CalDAV intervals (~30 min).
2. Voice reminder with a time: «Алиса, напомни сегодня в 19:00 помыть полы» (Alice, remind me today at 19:00 to wash the floors) → check whether it reaches CalDAV with the time. The result is recorded in `docs/RESEARCH.md`. Failing this scenario does not block the MVP release.

## 8. Risks

| Risk | Mitigation |
|---|---|
| Alice reminders do not reach CalDAV | Scenario C is marked experimental; the source is added by an external PR to YandexStation |
| Stock HA CalDAV refreshes only about every 15 min | Accepted; the pair interval does not speed up another integration |
| iCloud CalDAV does not see "upgraded" lists | Environment requirement in the README |
| Google Tasks loses the time of day | `date_only` downgrade, not a conflict |
| The `add_item` service does not return a uid | Re-read and match by content (FR-1.4) |
| Duplicates when a failure occurs between the write and the storage save | Save after every write (FR-7.2) |
| HA is migrating its schemas from voluptuous to probatio (probatio ships since 2026.9; most of core is still on voluptuous) | The schema is isolated in a single file `schema.py`; the HA version is pinned in `requirements_dev.txt`; re-check on every HA upgrade |

## 9. Changes in v1.1 (2026-10-26)

Source: the initial acceptance of the T-01…T-21 implementation (`docs/IMPLEMENTATION_NOTES.md`, `docs/LINK_CHECK.md`, Q-1). No requirement of v1.0 was withdrawn.

- §2 Routing, FR-12: several pairs per node, with per-pair links and tombstones; forest-only configuration; no concurrent cycles.
- FR-3.5: a change that a rule does not propagate is accepted locally.
- FR-6.2–6.4: tombstones are set on both links of the pair. FR-6.5: the purge happens at the end of a cycle and only for items that are gone. FR-6.6: tombstones are per pair.
- FR-8.4: orphan matching before `create`.
- FR-10.5, FR-11: own `halltasker.reload` service, because `homeassistant.reload_config_entry` does not re-read YAML.
- §6.2: end-to-end tests with an in-memory `todo` platform.
- §7 A10–A12: acceptance scenarios for the above.
- §8: corrected probatio/voluptuous facts.
- From the implementer's review of v1.1: FR-9.4 cycle timeout (Q-2), FR-10.4 redaction of task texts in diagnostics (Q-3), FR-12.6 chained runs across a shared node, FR-8.4 known limitation of orphan matching.
