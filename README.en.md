# HAlltasker

Language: [Русский](README.md) | English

Custom integration for Home Assistant: two-way task synchronization between any `todo.*` entities. Through stock HA integrations this links Yandex Calendar (CalDAV), iCloud Reminders (CalDAV), Google Tasks, Local To-do, and Shopping List.

Status: in development, MVP not released.

- Requirements: [docs/SPEC.md](docs/SPEC.md)
- Architecture: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
- Tasks: [docs/TASKS.md](docs/TASKS.md)
- Research and constraints of external systems: [docs/RESEARCH.md](docs/RESEARCH.md)
- Verification of external sources: [docs/LINK_CHECK.md](docs/LINK_CHECK.md)

## Installation via HACS

1. HACS → ⋮ (three dots) → **Custom repositories**.
2. Add the repository `s-parfyenov/HAlltasker`, category **Integration**.
3. Find **HAlltasker** in HACS and install it.
4. Restart Home Assistant.

The integration ships no dependencies of its own: only stock HA capabilities are used.

## Connecting external systems

Every external list is connected through a stock HA integration and becomes an ordinary `todo.*` entity. HAlltasker treats them all the same.

### Yandex Calendar (experimental)

1. Create an app password: Yandex ID → Security → App passwords → **Calendar** (CalDAV).
2. Add the stock **CalDAV** integration in HA: URL `https://caldav.yandex.ru`, login is the full `LOGIN@yandex.ru` address, password is the app password.
3. Wait for `todo.*` entities of the to-do lists (`todos-*`) to appear.

Notes:

- The stock CalDAV integration refreshes roughly every 15 minutes; a smaller pair interval in HAlltasker does not speed up the external integration.
- The to-do list ("Alice, add … to the to-do list") is available as ordinary CalDAV to-do items (date without time).
- Alice reminders with an exact time are an experimental scenario; there is no public reminders API (see [docs/RESEARCH.md](docs/RESEARCH.md) and [docs/LINK_CHECK.md](docs/LINK_CHECK.md)).
- The Yandex shopping list is not supported.

### iCloud Reminders

1. Create an app-specific password at appleid.apple.com → Sign-In and Security → App-Specific Passwords.
2. Add the stock **CalDAV** integration in HA: URL `https://caldav.icloud.com`, login is your Apple ID, password is the app-specific password.
3. On the iPhone, connect iCloud as a separate CalDAV account (Settings → Calendar → Accounts → Add Account → Other → CalDAV): the lists then appear in Reminders as "third-party" lists, without tags and smart lists.

Important: "upgraded" Reminders lists are stored in Apple's private store and are not visible over CalDAV. Use lists that were not migrated to the new format.

### Google Tasks

Add the stock **Google Tasks** integration. API limitation: the time of day of a due date is not kept — only the date. HAlltasker downgrades `datetime` to `date` automatically; that is not a conflict.

### Local To-do and Shopping List

Work as ordinary `todo.*` entities. Shopping List has no due date and no description — those fields are simply not synchronized for it.

## Configuration

YAML only, in `configuration.yaml`. Reload with the `homeassistant.reload_config_entry` service or by restarting HA.

```yaml
halltasker:
  pairs:
    - id: yandex_to_icloud          # required, unique, [a-z0-9_]+
      a: todo.yandex_dela           # required, entity of the todo domain
      b: todo.icloud_reminders      # required
      interval: 60                  # seconds, >= 15, default 60
      conflict: prefer_a            # prefer_a | prefer_b (default prefer_a)
      initial_sync: merge           # merge | dry_run (default merge)
      enabled: true                 # default true
      a_to_b:                       # all keys are optional
        create: true
        update: true
        complete: true
        delete: true                # true | false | soft
        filter:
          title_regex: "^(?!#).*"   # valid regex
          require_due: false
        transform:
          due: keep                 # keep | date_only | drop
          title_prefix: ""
      b_to_a: {}
```

Any number of pairs; one entity may take part in several pairs.

## Services

| Service | Parameters | Description |
|---|---|---|
| `halltasker.sync_now` | `pair_id` (optional) | Immediate sync cycle of one pair or of all pairs. |
| `halltasker.dry_run` | `pair_id` (optional) | Returns the planned actions without writing (service response: `{"pairs": {pair_id: [actions]}}`). |

## Sensors

One `sensor.halltasker_<pair_id>` per pair:

- state: `ok` | `error` | `dry_run` | `disabled`;
- attributes: `last_run`, `links`, `last_error`, `last_actions` (counters by type), `planned_actions` (in dry_run mode).

## How it works

- Links between tasks live only in the internal HA storage (`.storage/halltasker`). Nothing is written into your tasks: no prefixes, no hidden fields.
- The conflict policy is per pair: `prefer_a` or `prefer_b`. Changes to different fields on both sides are merged; tasks in HA expose no modification time, so true last-write-wins is impossible.
- Deletion: `true` — delete on the other side; `soft` — mark it done; `false` — leave it alone and never re-create. The memory of deletions (tombstones) is kept for at least 30 days.
- A repeated cycle with no external changes performs no writes at all.

## Limitations

- Recurring tasks (RRULE), subtasks, attachments, tags, priorities are not supported.
- Google Tasks: date only, no time of day.
- CalDAV integrations refresh roughly every 15 minutes.
- No UI configuration; YAML is the source of truth.
- Diagnostics (downloaded from the integration page) contain no secrets by construction.
