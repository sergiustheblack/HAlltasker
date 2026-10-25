# HAlltasker — implementation notes for the architect (2026-10-26)

Everything T-01…T-21 implemented on branch `zcode`; 102 tests, `ruff check`/`ruff format --check`
clean, hassfest docker locally: "Invalid integrations: 0". This file lists the decisions and
observations worth review. Link verification lives in `docs/LINK_CHECK.md`.

## Deviations and clarifications (all within task text; none change architecture signatures)

- **tz threading.** `downgrade()`/`classify()`/`equivalent()` take `tz` (per TASKS; ARCHITECTURE §5
  shows no tz but core may not import `homeassistant`). `SyncEngine.__init__` signature unchanged;
  the engine derives `tz = clock().tzinfo`; the coordinator passes `clock=dt_util.now`.
- **`LinkStore.purge_tombstones(older_than_days=30, now=…)`** — `now` is keyword-only (the §9
  signature is not valid Python as written).
- **New-item creation needs a source-side link action.** §6.1 step 6 plans only a CreateAction for
  allowed creates; without a link on the source item it stays "new" and is re-created every cycle.
  The engine emits `link(source) → create(target)`; the link-first order also gives free retry
  (next cycle plans missing_link → create again) when the create fails.
- **Source-side link refresh after propagation.** After an update/complete/create is applied, the
  opposite side's link gets `last_observed = last_synced = <its current>`; otherwise a change
  originating on one side is re-detected and re-sent every cycle (FR-7.3 violation). Skipped when
  the opposite side is itself a target of the same cycle (conflict merge).
- **First-cycle guard drops `delete`, `soft_delete` AND their companion `tombstone` actions**
  (FR-8.1 "no deletions in the first cycle" — a kept tombstone would forbid re-creation).
- **`RunResult.links`** = live link records for the pair's nodes, counted AFTER execution
  (one synced task = 2 records, one per side). Sensor attribute follows the same semantics.
- **Store writes:** save after every applied action (FR-7.2); `mark_pair_initialized` + one extra
  save only on the first cycle or when something was applied — a no-op cycle performs no writes.
- **Delete paths:** `delete:true/soft` tombstones both links; `delete:false` tombstones both too
  (FR-6.2 says "the link gets a tombstone" — we read it as the pair's relationship being over);
  re-creation on delete-vs-change follows §6.2 (policy + reverse create rule + filter).
- **Engine error isolation:** `run_pair` catches `NodeUnavailable` and any `Exception` into
  `RunResult(ok=False, error=…)`; per-action failures are collected in `actions_failed` and do
  not block the rest (§6.1 step 8).

## HA 2026.9 facts discovered during implementation

- `hass.async_forward_entry_setups` does not exist; it is
  `hass.config_entries.async_forward_entry_setups` / `async_unload_platforms`.
- Awaiting `flow.async_init` inside `async_setup` deadlocks setup; the import flow is started via
  `hass.async_create_task(...)`.
- Closures passed to `async_call_later` / `async_track_time_interval` must be decorated
  `@callback` themselves (a decorated factory is not enough), otherwise they run in the executor
  and `hass.async_create_task` raises a thread-safety RuntimeError.
- HA reads `CONFIG_SCHEMA` from the integration `__init__`; ours lives in `schema.py`, so
  `__init__` re-exports it (also `__all__` for ruff F401).
- The manifest dependency `"todo"` loads the real todo services; in integration tests the fake
  services must be registered AFTER setup (last registration wins).
- `local_todo` cannot be used in tests: it needs the `ical` package, which is not in
  `requirements_dev.txt` (adding dependencies is forbidden). Sensor tests override the todo
  services instead; plugin tests fake them without loading HA components.
- `phacc` test clock starts at real "now"; synthetic datetimes fire unrelated timers — tests use
  `dt_util.utcnow()` deltas.

## Tooling

- Env: uv venv on python3.14.7 (uv in pip-interface mode; `requirements_dev.txt` stays the single
  source of truth, no `uv.lock`; `.venv/` was already gitignored).
- ruff 0.16 formats python blocks inside markdown and would rewrite protected docs;
  `pyproject.toml` sets `extend-exclude = ["*.md"]` (commit `4e2ad20`).
- No git remote is configured yet, so GitHub Actions (incl. `hacs/action`) have not run;
  the workflow itself is in place.

## Open items

- Q-1 (docs/QUESTIONS.md): probatio shipped in HA 2026.9, not 2026.11 as SPEC/ARCHITECTURE say;
  voluptuous API still works via the compat alias, so `schema.py` is unaffected.
- docs/LINK_CHECK.md: 3 outdated links, 1 half-supported claim, access notes — owner to decide
  on edits (RESEARCH/SPEC/ARCHITECTURE are frozen for agents).
- Acceptance groups B/C and stage 0 require the owner's real accounts.
