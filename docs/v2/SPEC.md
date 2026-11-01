# HAlltasker — technical specification v2 (draft 2.0, 2026-11-01)

Status: approved by the owner as the target of v2; not yet in development. Until the owner starts the v2 implementation, [docs/SPEC.md](../SPEC.md) (v1.4) stays binding for every open v1 issue. Changes against v1.4 are listed in §10. The design is in [docs/v2/ARCHITECTURE.md](ARCHITECTURE.md).

> Language: English only (agent-facing, binding). There is no Russian reading copy yet; the owner maintains `docs/ru/`.

## 1. Goal

Two-way synchronization of tasks between ecosystems (Yandex, Apple Reminders, Google Tasks, Home Assistant lists, later task trackers), implemented as a custom integration for Home Assistant (HA) installed through HACS. v2 keeps the v1 sync semantics and adds three things:

1. **A core with plugins over a field schema.** A task is a `CanonicalItem(kind, fields)` whose fields are described by an `ItemSchema` built per pair, with per-field capabilities `none | partial | full` (decision record IT-41, document issue IT-46). The `SyncEngine` algorithm of v1 is kept.
2. **Direct plugins.** Sources that HAlltasker had to wrap into its own `todo.*` platforms in v1 (CalDAV, Alice reminders) become plugins that read and write the external system directly and declare their full set of native fields. Stock HA integrations stay reachable through the `ha_todo` plugin.
3. **A configuration panel.** A custom HA panel where the owner creates connections, nodes and pairs, picks the target list from the lists the system really has, matches fields one to one while seeing what each side provides, and chooses the sync direction.

## 2. Key decisions

| Question | Decision |
|---|---|
| Platform, language | HA custom integration, Python 3.14+, stable HA 2026.9.x (as v1.4) |
| Sources | **Direct plugins.** `caldav` and `yandex_reminders` talk to their systems directly; future `jira`, `yandex_tracker` the same way. `ha_todo` serves any `todo.*` entity of a stock or community integration (Google Tasks, Local To-do, stock CalDAV). HAlltasker's own `todo.*` platforms of v1.4 FR-13/FR-14 are **removed** from v2 |
| Responsibility boundary | The core contains no authorization and no external API. A plugin carries its own client only when no HA integration covers the system (v1.2 rule kept); when an HA component already holds a session (YandexStation), the plugin uses it and stores no credentials |
| Topology | **Pairs only.** Several independent synchronizers may exist side by side (for example `yandex ↔ apple`, `jira ↔ tracker`, and a one-way `yandex → tracker`). Nodes and pairs form a forest (v1.4 FR-12). N-node groups and hub groups are not introduced: every conflict stays a conflict between two sides, the v1 decision table and link namespaces are unchanged, and every configured pair is exactly what runs |
| Credentials reuse | **Connections.** A `Connection` = plugin + credentials + non-secret settings. `yandex1` and `yandex2` are two connections of the same plugin (two accounts) and may take part in different pairs; a password is changed in one place. Plugins without credentials of their own (`ha_todo`; `yandex_reminders`, which works entirely through the YandexStation component) have built-in connections without a credentials form |
| Conflicts | Policy per pair: `prefer_a` (default) or `prefer_b`, **plus a per-field override** in the field mapping row. Fields changed on one side only are merged (v1.4 FR-5) |
| Configuration | **UI first.** The panel edits the configuration through an admin-only websocket API. Credentials live in the HAlltasker ConfigEntry (one subentry per connection); nodes, pairs and mappings live in an own HA `Store` |
| YAML | Kept as **import/export**: the panel exports the whole configuration as a `halltasker:` YAML section and imports it back; at startup a `halltasker:` section is imported once into an empty store. Purpose: backup and restore |
| Target lists | **Only existing containers**, chosen from the plugin's discovery list. Creating a list from HAlltasker is reserved in the plugin contract and not implemented |
| Field mapping | Stored in the pair. Plugins know their own native fields only and never another plugin (the "star" of v1 is kept); the core renames native fields to pair slots and back |
| Frontend | Lit + TypeScript. The built bundle is committed into `custom_components/halltasker/frontend/`, because HACS installs only the integration folder; Node.js is needed only by the panel developer |
| Users | One. Several accounts are supported through several connections |
| Recurring tasks, calendar events | Out of scope (RRULE; calendar events stay a low-priority idea, decision of 2026-10-28) |
| Notifications | Duplicate notifications from different systems are accepted; the core does not interfere |

## 3. Scope v2

Included:

- Connections with credentials stored once and reused by any number of nodes; several connections of one plugin.
- Nodes = connection + container; containers are chosen from the plugin's discovery list.
- Pairs of nodes with a direction preset (`both`, `a_to_b`, `b_to_a`), the v1 direction rules, a pair conflict policy and per-field overrides.
- Field mapping per pair: native field of A ↔ slot ↔ native field of B, prefilled by field roles, with dropped fields and value maps for enum fields.
- `CanonicalItem` over a per-pair `ItemSchema`, per-field capabilities and per-field downgrade.
- Plugins `ha_todo`, `caldav`, `yandex_reminders`.
- Configuration store, link store schema 3, credentials in ConfigEntry subentries.
- YAML import/export of the whole configuration.
- The custom panel: Connections, Nodes, Pairs, Pair editor, Status, Export/Import.
- Admin-only websocket API; services `sync_now`, `dry_run`, `reload`; sensors and diagnostics without secrets.

Not included:

- HAlltasker's own `todo.*` platforms for CalDAV and Alice reminders (v1.4 FR-13, FR-14, ARCHITECTURE v1.3 §4a/§4b). Their client knowledge moves into the `caldav` and `yandex_reminders` plugins.
- N-node groups, hub groups, chains as a configuration entity.
- Creating containers (`create_container` is reserved in the contract only).
- Plugins `jira`, `yandex_tracker`, BuyMeAPie: v2 states only the contract they must satisfy (FR-13.4).
- Calendar events, RRULE, subtasks, attachments, item ordering, suppression of duplicate notifications.
- Migration of v1 link data and of the v1 YAML format (§9).

## 4. Terms

- **Plugin** — an internal HAlltasker module with one contract (ARCHITECTURE v2 §4): it describes its native fields, validates credentials, discovers containers, reads and writes items. A plugin is not a separate HA integration.
- **Connection** — a configured use of one plugin: plugin id, display name, credentials (for plugins that have them) and non-secret settings. Identified by a stable uuid.
- **Built-in connection** — a connection of a plugin whose `credential_kind` is `none` (`ha_todo`, `yandex_reminders`): it has no credentials form and no ConfigEntry subentry.
- **Container** — a list inside a connection, as the external system names it: a `todo.*` entity, a CalDAV collection, the reminders list of an account, later a tracker project with a query. Obtained only from the plugin's discovery.
- **Node** — a connection plus one container; the unit that takes part in pairs. Identified by a stable uuid; its name is a separate display field.
- **Pair** — two nodes A and B with a direction preset, direction rules, a field mapping, a polling interval, a conflict policy and an initial sync mode. Identified by a stable uuid.
- **Direction preset** — `both`, `a_to_b` or `b_to_a`; it expands into the two direction rules (a one-way preset switches off every operation of the opposite direction).
- **Direction rule (DirectionRule)** — as in v1.4: allowed operations, filter and transforms for the direction X→Y.
- **Native field** — a field as the plugin names it (`summary`, `STATUS`, `CATEGORIES`, `text`). Described by a `FieldSpec`: type, suggested role, readable, writable, enum values.
- **Role** — the suggested meaning of a native field (`title`, `description`, `status`, `due`, `priority`, `tags`), used to prefill the mapping.
- **Slot** — a field of the pair's canonical item. The core works with slots only.
- **FieldMap** — one row of a pair's mapping: slot, native field of A, native field of B (either may be dropped), conflict override, value maps.
- **ValueMap** — translation of enum values between a native field and its slot, in both directions, with a default for unknown values.
- **ItemSchema** — the field schema of a pair: kind, one `FieldSpec` per mapped slot, and the matching key. Built from the mapping; there is no global field list.
- **CanonicalItem** — an item as `kind` plus a mapping of field name to value; at the plugin boundary the names are native, inside the core they are slots.
- **Capabilities** — the operations (`create`, `update`, `delete`) and the per-field capability (`none`, `partial`, `full`) of a specific node. `partial` for `due` means date only.
- **Downgrade** — reducing an item to the capabilities of a node, field by field. A downgrade is not a change and does not create a conflict (as in v1).
- **Snapshot, Link, Echo, Tombstone** — as in v1.4 §4; links are scoped to a pair.

## 5. Functional requirements

### FR-1 Connections

1. A connection holds: a stable uuid `id`, a display `name` (unique among connections), the `plugin_id`, non-secret `settings` described by the plugin's `settings_schema`, credentials described by the plugin's `credentials_schema`, and `interval` (seconds).
2. Credentials are entered once per connection and used by every node of that connection. Changing them changes them for every pair that uses the connection; nodes, pairs and links are not touched.
3. Several connections of the same plugin may exist (`yandex1`, `yandex2` — two accounts); each has its own credentials and its own nodes. Nodes of different connections may be paired with each other or with nodes of other plugins.
4. Before a connection with credentials is saved, the plugin validates the credentials against the external system. `AuthFailed` or `NodeUnavailable` rejects the save with the error shown in the panel; nothing is stored.
5. Built-in connections: a plugin with `credential_kind: none` has no credentials form. `ha_todo` has exactly one built-in connection, created automatically. `yandex_reminders` uses the session of the installed YandexStation component; its connection has only the non-secret setting `yandex_station_entry` (which YandexStation config entry to use, required when there are several) and is created by the owner in the panel without entering any credentials.
6. Deleting a connection that is referenced by a node is refused with the list of referencing nodes. Deleting an unreferenced connection removes its ConfigEntry subentry (and with it the credentials).
7. When a plugin raises `AuthFailed` during a cycle, the pairs of that connection are in `error`, and one HA repairs issue per connection asks to re-enter the credentials through the connection's reconfigure flow. The issue is removed after the next successful cycle. For `yandex_reminders` the repairs issue points to the YandexStation integration instead: HAlltasker never asks for Yandex credentials.
8. The effective polling interval of a pair is the maximum of `pair.interval` and the `interval` of the connections of its two nodes, so that a slow external system (CalDAV, default 300 s, minimum 60) is not polled more often than its connection allows. Defaults per plugin: `ha_todo` 15, `yandex_reminders` 60, `caldav` 300. Events, chained runs and `sync_now` are not limited by the connection interval.

### FR-2 Nodes and discovery

1. A node holds: a stable uuid `id`, a display `name` (unique among nodes), `connection_id`, the `container`, and `kind` (`task` in v2).
2. The container is chosen only from the list returned by the plugin's discovery for the node's connection (`ha_todo`: every `todo.*` entity; `caldav`: every collection of the principal that supports VTODO; `yandex_reminders`: the single `reminders` container). A container that does not exist cannot be configured; HAlltasker never creates containers.
3. The container is stored with its plugin-specific identity (`id`; `path` for CalDAV collections; `query` reserved for trackers) and its display name at the time of selection. A node keeps working when the external system renames the container, as long as its `id` (and `path`) still resolves.
4. Renaming a node or a pair never resets links: links are keyed by uuids.
5. Changing the container of an existing node (or the nodes of an existing pair) resets the links of every pair that contains it; the panel asks for confirmation and states which pairs are affected. The next cycle of those pairs is an initial sync (v1.4 FR-8).
6. A container that has disappeared from the external system makes the node unavailable: its pairs are in `error`, their links are kept, nothing is written.

### FR-3 Pairs and directions

1. A pair holds: a stable uuid `id`, a display `name` (unique among pairs), node `a`, node `b`, the direction preset, the two direction rules, the field mapping (FR-4), `interval` (default 60, minimum 15), `conflict` (`prefer_a` default, `prefer_b`), `initial_sync` (`merge` default, `dry_run`), `enabled`.
2. Pairs only. Constraints, checked on every save and import (a violation rejects the whole document, the running configuration is kept): `a != b`; no two pairs connect the same two nodes; the graph of nodes and pairs is a forest (v1.4 FR-12.3). Several independent forests may exist side by side.
3. The direction preset: `both` uses the two rules as configured; `a_to_b` forces every operation of `b_to_a` off (`create`, `update`, `complete` false, `delete: false`); `b_to_a` the reverse. Changes on the switched-off side are accepted locally (v1.4 FR-3.5). The preset is stored; the panel shows the effective rules.
4. Direction rules keep the v1.4 FR-3 semantics (operations, `delete_past_due`, `filter`, `transform`). The filter and transform refer to the slots `title` and `due`; a rule that refers to a slot the pair does not map is a validation error.
5. v1.4 FR-12.2, FR-12.4 and FR-12.6 apply unchanged: per-pair links, no concurrent cycles, chained runs after a write into a shared node.

### FR-4 Field mapping and value maps

1. The pair's mapping is a list of rows `slot ↔ native field of A ↔ native field of B`. A slot name is unique within the pair. Each side of a row is either a native field of that side's node or empty (dropped).
2. The panel shows two columns — the native fields of node A and of node B with their types and capabilities — and prefills the mapping by role: native fields with the same role form one row whose slot is the role name. Fields without a counterpart stay unmapped.
3. The owner may drop any row or one side of a row, and may re-bind a native field to another row, as long as the types are compatible (ARCHITECTURE v2 §2). A row is synchronized only if both sides are set; a row with one side set is kept in the configuration but does nothing and is shown as dropped.
4. The slot `title` must be mapped on both sides. If the slot `status` is mapped, its canonical values are `open` and `done`, so that `complete` and `delete: soft` keep their v1 meaning.
5. An enum field whose value set differs from the slot's canonical values needs a value map on that side: `read` (native → canonical), `write` (canonical → native) and `default` (canonical value used when a read native value is not in `read`). Without the needed value map the save is rejected. Default value maps for the known plugins are prefilled (ARCHITECTURE v2 §4).
6. Each row may override the pair conflict policy: `prefer: pair | a | b` (FR-6.3).
7. When a pair is saved, the panel lists every native field that is not synchronized and every slot that one node does not provide ("slot `priority` dropped: not provided by node B"). In a forest of pairs a field travels only through nodes that provide it; the warning makes this visible.

### FR-5 Item schema and capabilities

1. A `CanonicalItem` is `kind` plus a mapping `field name → value`. Inside the core the names are the pair's slots; at the plugin boundary they are native names.
2. The `ItemSchema` of a pair is built from its mapping and the two nodes' field specs: one field per synchronized slot, typed (`str`, `text`, `enum`, `due`, `datetime`, `int`, `str_list`), plus the matching key (`title`, `due` — those of the two that are mapped). There is no global field list.
3. Capabilities are per node: operations `create`, `update`, `delete`, and per native field `none | partial | full`. `partial` for `due` means date only (the v1 `date`). A field with capability `none` on the target is neither written nor compared.
4. The downgrade of v1.4 FR-2.4 applies per field: `due` with time → date in the HA time zone when the target field is `partial`; any field → absent when the target field is `none`. Comparison of a read value with the expected one uses the downgraded form (v1.4 FR-2.5).
5. Values are serialized per type; dates without time stay dates (v1.4 FR-2.2).

### FR-6 Change detection and conflicts

1. Change detection and echo: v1.4 FR-4 unchanged, over the pair's slots.
2. A change on one side and changes on both sides with non-overlapping slots: v1.4 FR-5.1–5.2 unchanged.
3. Overlapping slots are taken, slot by slot, from the side named by the row's `prefer` (`a` or `b`); a row with `prefer: pair` uses the pair policy (`prefer_a` → A, `prefer_b` → B).
4. Deletion on one side and a change on the other: v1.4 FR-5.4 with the pair policy (per-field overrides do not apply to deletion).

### FR-7 Deletion

1. v1.4 FR-6 applies unchanged (conditions, `true`/`false`/`soft`, tombstones per pair, 30-day purge, `delete_past_due`).
2. `delete: soft` writes `status = done` and therefore needs a mapped, writable `status` slot on the target; without it the deletion is handled as a capability that is off: tombstone only.

### FR-8 Storage

1. Configuration (connections without credentials, nodes, pairs, mappings) is kept in the HA store `halltasker_config`, schema 1.
2. Credentials are kept only in the `data` of the HAlltasker ConfigEntry subentry of their connection. They never appear in `halltasker_config`, in the link store, in websocket responses, in logs or in diagnostics.
3. Links and tombstones are kept in the HA store `halltasker`, schema 3, one namespace per pair uuid; v1.4 FR-7 (no markers in user items, save after every write, idempotent cycles) applies unchanged.
4. A configuration save is atomic: the whole document is validated, then written, then the coordinator restarts with it. A rejected document leaves the store and the running configuration untouched.
5. Namespaces of pairs removed from the configuration are kept (as v1); the panel can reset them explicitly (FR-10.6).

### FR-9 YAML import and export

1. The YAML format of v2 is one `halltasker:` section with three lists `connections`, `nodes`, `pairs`. The export format equals the import format. Entities reference each other by `name`; `id` (uuid) is optional on import and always present on export, so that an export → import round trip keeps the links.
2. Import at startup: if `configuration.yaml` holds a `halltasker:` section and `halltasker_config` is empty, the section is validated and imported once (connections with credentials become subentries). If the store is not empty, the section is ignored and a repairs issue says so; the store is not touched. An invalid section is logged and reported by a repairs issue; nothing is imported.
3. Import from the panel replaces the whole configuration after validation and an explicit confirmation; `!secret` references are resolved against the HA `secrets.yaml`, and an unresolved reference rejects the import.
4. Export renders the current configuration. Every credentials key that the plugin marks as secret is rendered as `!secret halltasker_<connection name>_<key>`, and a `secrets.yaml` template with these keys and empty values is returned next to it. Exporting secret values in clear text requires an explicit confirmation in the panel and is never the default.
5. Example (export of a configuration with two connections of one plugin):

```yaml
halltasker:
  connections:
    - id: 3f1c9a0e2b7d4c51a8e6f0b9d2c4e7a1
      name: yandex1
      plugin: caldav
      interval: 300
      credentials:
        url: https://caldav.yandex.ru
        username: user1@yandex.ru
        password: !secret halltasker_yandex1_password
        verify_ssl: true
    - name: yandex2
      plugin: caldav
      credentials:
        url: https://caldav.yandex.ru
        username: user2@yandex.ru
        password: !secret halltasker_yandex2_password
    - name: ha
      plugin: ha_todo
  nodes:
    - name: yandex1_dela
      connection: yandex1
      container: {id: "/calendars/user1%40yandex.ru/todos-7315205/", name: "Мои дела"}
    - name: icloud
      connection: ha
      container: {id: todo.icloud_reminders, name: "Reminders"}
  pairs:
    - name: yandex_icloud
      a: yandex1_dela
      b: icloud
      direction: both
      conflict: prefer_a
      mapping:
        - {slot: title, a: SUMMARY, b: summary}
        - {slot: due, a: DUE, b: due}
        - slot: status
          a: STATUS
          b: status
          prefer: b
          value_map_a:
            read: {NEEDS-ACTION: open, IN-PROCESS: open, COMPLETED: done, CANCELLED: done}
            write: {open: NEEDS-ACTION, done: COMPLETED}
            default: open
          value_map_b:
            read: {needs_action: open, completed: done}
            write: {open: needs_action, done: completed}
        - {slot: description, a: DESCRIPTION, b: null}
```

The full schema is in ARCHITECTURE v2 §8.

### FR-10 Panel

1. HAlltasker registers one custom panel in the HA sidebar, visible to administrators only.
2. **Connections**: list with plugin, status and the nodes that use each connection; create (plugin choice → credentials form from the plugin's schema, then validation), reconfigure credentials, edit settings, delete (FR-1.6). Built-in connections are listed without a credentials form.
3. **Nodes**: list; create = choose a connection, then a container from discovery (FR-2.2); rename; change container with confirmation (FR-2.5); delete is refused while a pair uses the node.
4. **Pairs**: list with nodes, direction, status and last run; the graph of nodes and pairs, with the cycle check before save; enable/disable.
5. **Pair editor**: node A and node B; direction preset; the two columns of native fields with the prefilled mapping, drop and re-bind, per-row `prefer`, value-map editor for enum rows; direction rules (operations, filter, transform); interval, conflict, initial sync; the warnings of FR-4.7. A new pair can be run as a dry run from the editor before it is enabled, and the planned actions are shown.
6. **Status**: per pair state, last run, counters, last error, planned actions in dry run; buttons "sync now" and "dry run"; links count and "reset links" with confirmation (the next cycle is an initial sync).
7. **Export/Import**: export YAML with the `secrets.yaml` template (FR-9.4); import YAML with validation errors shown per entity (FR-9.3).
8. Credentials are write-only in the panel: forms show which keys are set, never their values.
9. Texts in English and Russian.

### FR-11 Websocket API and services

1. The panel talks to HAlltasker only through websocket commands of the `halltasker/` namespace; every command requires an administrator. The list and payloads are in ARCHITECTURE v2 §9.
2. Commands cover: plugin descriptors; configuration get (without credentials) and save (whole document, atomic); container discovery of a connection; fields and capabilities of a node; dry run and sync of a pair; status subscription; link listing and reset of a pair; YAML export and import.
3. Services: `halltasker.sync_now` and `halltasker.dry_run` with an optional `pair_id` (the pair uuid or its name) keep the v1.4 FR-10 semantics. `halltasker.reload` (admin) re-reads the configuration: it retries the YAML import when the store is empty (FR-9.2), otherwise re-reads `halltasker_config`, and restarts the coordinator.
4. Sensors: one `sensor.halltasker_<pair name>` per pair, with the v1.4 FR-10.3 states and attributes; the `unique_id` is built from the pair uuid, so a rename keeps the entity.

### FR-12 Security and diagnostics

1. Every websocket command and the panel are admin-only.
2. No response, event, log line or diagnostics export contains credentials. `halltasker/config/get` never returns subentry data.
3. Diagnostics export the configuration (without credentials), the link store and the last results; task texts are redacted as in v1.4 FR-10.4, connection settings are kept.
4. Task content appears in logs only at `DEBUG` (v1.4 §6.3).
5. The YandexStation session is used in memory only and never stored by HAlltasker.

### FR-13 Plugins

1. **`ha_todo`** — any `todo.*` entity of a stock or community integration. v1.4 FR-1 applies (services, `supported_features`, uid lookup after `add_item`, unavailability). Native fields: `summary`, `description`, `status` (`needs_action | completed`), `due`, each according to `supported_features`. Built-in connection; containers = all `todo.*` entities.
2. **`caldav`** — a CalDAV account read and written directly. Credentials: `url`, `username`, `password` (secret), `verify_ssl`. Containers = the principal's collections that support VTODO. Native fields: `SUMMARY`, `DESCRIPTION`, `STATUS` (`NEEDS-ACTION | IN-PROCESS | COMPLETED | CANCELLED`), `DUE`, `PRIORITY` (0–9), `CATEGORIES` (list), `COMPLETED` (read-only). Completion follows RFC 5545 exactly as v1.4 FR-13.4 (a VTODO without `STATUS` but with `COMPLETED` or `PERCENT-COMPLETE:100` reads as `COMPLETED`; writing `COMPLETED` also writes `PERCENT-COMPLETE:100` and keeps an existing `COMPLETED` time; writing `NEEDS-ACTION` removes both). A VTODO without `DTSTAMP` is accepted and gets one on write (v1.4 FR-13.5). Uses the `caldav` library pinned as in v1.4 §6.5.
3. **`yandex_reminders`** — Alice reminders with a time, read and written through the private reminders API of the Alice app using the live session of the installed YandexStation component. HAlltasker has no Yandex credentials and no credentials form for it (FR-1.5). One container `reminders` per connection. Native fields: `text` (title), `due` (datetime only), `status` (`active | cancelled`, write = cancel only). Settings: `yandex_station_entry`, `device` (speaker for reminders created from HA), `push`. The mapping of v1.4 FR-14.4 and the write semantics of FR-14.5 apply: completion cancels the reminder and the item is kept as `cancelled` in local retention until one day after its due time; reopening is not supported; recurring reminders are ignored. The direction rule toward such a node must set `filter.require_due: datetime`. If YandexStation is not installed, not loaded or the entry is missing, the node is unavailable (FR-1.7). The stage 1 gate of v1.4 FR-14.6 still applies to the write path.
4. **Future plugins with their own client** (`jira`, `yandex_tracker`): only through the plugin contract of ARCHITECTURE v2 §4, credentials only in a connection subentry, no imports in the core, containers by discovery (project plus `query`), native fields declared with roles.

### FR-14 Migration from v1

The migration rules are in §9: no conversion of schema 2 links or of the v1 YAML format; own `todo.*` platforms are not created; v1 documents stay binding for open v1 issues until the v2 implementation starts.

## 6. Non-functional requirements

1. Code follows HA core standards: asyncio, type annotations, `ruff` with no findings (v1.4 §6.1).
2. The core (`core/`) does not import `homeassistant` and is tested without HA; core coverage is not below 90 %. Plugins are tested with fakes of their external system; no network in tests.
3. Logs as v1.4 §6.3; credentials never logged.
4. HACS: `hacs.json` and `manifest.json` pass `hassfest` and `hacs/action`; HACS releases use `MAJOR.MINOR.PATCH` tags.
5. Manifest `requirements`: only the CalDAV libraries of v1.4 §6.5, pinned to the versions of the HA core `caldav` manifest.
6. Frontend: Lit + TypeScript sources and the build configuration live in the repository; the built bundle is committed into `custom_components/halltasker/frontend/`, so installing through HACS needs no Node.js. Node.js is a developer tool of the panel only; Python checks (`ruff`, `pytest`) do not need it.
7. The panel works in the HA frontend of the pinned HA version without extra HACS frontend dependencies.

## 7. Acceptance scenarios

### A. Core regression (mandatory)

Environment: two `local_todo` entities in a test HA, as two nodes of the built-in `ha_todo` connection; the pair maps `title`, `description`, `status`, `due` by role. The v1.4 scenarios hold unchanged:

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

v1.4 §7 B1–B2 unchanged, over `ha_todo` nodes.

### C. v2 scenarios (mandatory)

The Yandex scenarios of v1.4 §7 C are replaced by C2 and C10 below; voice checks against real Yandex stay manual.

1. **Two connections of one plugin.** Connections `yandex1` and `yandex2` of `caldav` with different credentials; pair P1 `yandex1/list ↔ icloud`, pair P2 `yandex2/list ↔ home_list`. Each pair syncs its own account. Changing the password of `yandex1` in the panel affects only P1; links of P1 and P2 are unchanged.
2. **Value map of CalDAV status.** CalDAV node ↔ `ha_todo` node with the default value maps. Setting `STATUS:IN-PROCESS` on the CalDAV side does not change the `ha_todo` item (both read as `open`); `CANCELLED` → `completed`; completing the `ha_todo` item writes `STATUS:COMPLETED`, `PERCENT-COMPLETE:100` and `COMPLETED`. A repeated cycle makes no writes.
3. **Per-field prefer.** Pair with `conflict: prefer_a` and the `status` row `prefer: b`. Simultaneous change of `title` and `status` on both sides → `title` from A, `status` from B on both sides.
4. **Dropped field.** Pair with the `description` row dropped on B. A change of `description` in A writes nothing to B and is not reported again; a `title` change still syncs.
5. **Extended fields.** Two CalDAV nodes with `PRIORITY` and `CATEGORIES` mapped: a priority and a category set on one side appear on the other.
6. **Rename keeps links.** Renaming a connection, a node and a pair in the panel: the next cycle makes no writes and plans no creates; the sensor keeps its `unique_id`.
7. **Container change resets links.** Changing the container of a node after confirmation: the next cycle of its pairs is an initial `merge`.
8. **YAML round trip.** Export → empty store → import of the exported text with a filled `secrets.yaml`: the configuration is equal, the ids are equal, the next cycle of every pair makes no writes. The exported text contains no secret value.
9. **Import into a non-empty store at startup** creates a repairs issue and leaves the store unchanged.
10. **Reminders without credentials.** With YandexStation installed, a `yandex_reminders` connection and node are created and paired without entering any credentials. When YandexStation is unloaded, the node is unavailable, the pair is in `error`, a repairs issue points to YandexStation, and the links are kept.
11. **Validation.** Saving a configuration with a cycle of pairs or a pair whose two sides are the same node is rejected; the running configuration keeps working.
12. **Deletion guard.** Deleting a connection used by a node is refused with the node list.
13. **Security.** `halltasker/config/get`, diagnostics and the log at `DEBUG` contain no credential value; a non-admin user gets an authorization error from every `halltasker/` command.

## 8. Risks

| Risk | Mitigation |
|---|---|
| Fields are lost silently in a forest of pairs: a slot that an intermediate node lacks does not travel further | Warning in the pair editor on save (FR-4.7); the owner may connect the richer nodes directly as long as the forest rule holds |
| Two simultaneous changes of one field in different pairs of a shared node are resolved by the order in which the pairs run | Known behavior, as v1.4 FR-12; the pair order is the configuration order and is shown in the panel |
| Reauth exists in HA per config entry, not per subentry | Connection credentials are fixed through the subentry reconfigure flow plus a repairs issue per connection (FR-1.7) |
| The YandexStation session or the private reminders API changes | The `yandex_reminders` plugin isolates it; failure makes only its nodes unavailable; no credentials are stored, so nothing has to be migrated |
| Open v1 issues build the v1 platforms that v2 removes | §9.4: they continue only as research of the clients, reused by the plugins |
| The frontend adds a JavaScript toolchain to a Python repository | The bundle is committed; Python checks do not need Node.js (§6.6) |
| HA migrates schemas from voluptuous to probatio | Schemas stay isolated (configuration validation in one module); re-check on every HA upgrade (v1.4 §8) |
| A large configuration document is saved as a whole | Atomic save with full validation (FR-8.4); the panel saves only on explicit action |

## 9. Migration from v1

1. **Link data.** The link store moves to schema 3 (keys are pair and node uuids). Schema 2 data is not converted: on load it is discarded with a `WARNING`, and the first cycle of every pair is an initial `merge`, which re-links existing items by the matching heuristic (as v1.1 did with schema 1). The project is pre-release.
2. **Configuration.** The v1 `halltasker:` YAML format (node strings `todo.*`, `caldav:` and `yandex_reminders:` sections) is not imported: the format changed. The owner rebuilds the configuration in the panel or writes a v2 `halltasker:` section (FR-9). A v1 section found at startup is reported by a repairs issue and otherwise ignored.
3. **Own `todo.*` platforms.** v2 does not create `todo.halltasker_*` entities. Pairs that used them are rebuilt over `caldav` and `yandex_reminders` nodes.
4. **Open v1 issues.** Until the v2 implementation starts, v1.4 and ARCHITECTURE v1.3 stay binding for open v1 issues. Work on the v1 platforms of ARCHITECTURE v1.3 §4a/§4b (IT-43, IT-57) is useful only as research of the clients: the CalDAV mapping and RFC 5545 completion rules and the Alice reminders API findings are reused by the `caldav` and `yandex_reminders` plugins. The owner decides whether IT-57 is redirected to the plugin.
5. **Switching documents.** When the v2 implementation starts, the owner decides when `docs/v2/` replaces `docs/SPEC.md` and `docs/ARCHITECTURE.md`.

## 10. Changes against v1.4

Source: the owner's decisions in the v2 planning session of 2026-11-01 (plan `halltasker-architecture-v2-docs`), IT-41 verdict, IT-46. v2 is a new document; v1.4 is not edited.

- §2: UI-first configuration with a store; YAML becomes import/export; direct plugins instead of own `todo.*` platforms; connections for credentials reuse; pairs only, stated explicitly; per-field conflict override; discovery-only containers; Lit + TypeScript panel.
- §3: own `todo.*` platforms, N-node groups and container creation are out of scope; tags, priorities and other extended fields are in scope through the field mapping.
- §4: new terms Connection, Built-in connection, Container, Native field, Role, Slot, FieldMap, ValueMap, ItemSchema, CanonicalItem, Direction preset; Node is a connection plus a container instead of a `todo.*` string.
- FR-1, FR-2, FR-4, FR-8–FR-12: new (connections, discovery, mapping, storage, YAML import/export, panel, websocket API, security).
- FR-3: direction presets; validation on save instead of on YAML load. FR-5 replaces v1.4 FR-2 (field schema per pair, per-field capabilities). FR-6 adds per-field `prefer` to v1.4 FR-4/FR-5. FR-7 keeps v1.4 FR-6 and states `soft` without a `status` slot.
- FR-13 replaces v1.4 FR-1, FR-13 and FR-14: `ha_todo`, `caldav` and `yandex_reminders` as plugins; the RFC 5545 completion rules and the reminder retention are kept; `yandex_reminders` has no credentials of its own.
- FR-14, §9: migration without conversion of links or of the v1 YAML.
- §6: frontend bundle rule. §7: group A kept as regression, group C replaced by v2 scenarios. §8: risks of the v2 model.
