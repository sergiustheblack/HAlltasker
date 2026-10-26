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

- Q-1 is closed (2026-10-26): probatio facts corrected in SPEC/ARCHITECTURE/RESEARCH v1.1;
  `schema.py` stays on voluptuous.
- Q-2 (cycle timeout under the global lock) and Q-3 (diagnostics snapshot content) are open —
  see docs/QUESTIONS.md.
- docs/LINK_CHECK.md: 3 outdated links, 1 half-supported claim, access notes — owner to decide
  on edits (RESEARCH/SPEC/ARCHITECTURE are frozen for agents).
- Acceptance groups B/C and stage 0 require the owner's real accounts.

## v1.1 acceptance review (2026-10-26, implementer)

Reviewed SPEC/ARCHITECTURE v1.1 and T-22…T-31. No blocking objections; the review fixed four real
defects of the T-01…T-21 implementation: orphan duplicates after a failed uid lookup (FR-8.4),
the leak of a rule-blocked change through a later conflict merge (FR-3.5), tombstone resurrection
of a live item after purge (FR-6.5 `present`), and the v1.0 README overclaiming multi-pair support.
The Q-1 correction (voluptuous is a real package, not a probatio alias) was verified against the
install log and accepted.

Two decisions requested (Q-2, Q-3 in docs/QUESTIONS.md): a cycle timeout under the global lock,
and hash-only snapshots in diagnostics.

Two non-blocking notes, recorded so they are not lost:

- **Star propagation latency (for T-31).** `state_changed` does not fire on a title/due edit
  (FR-9.2), so a field change crossing a shared node travels on the next pair's polling interval:
  worst case ≈ one `interval` per hop (≈ 2×interval through the center of a star). The README
  should say this in one sentence, or star users will read the delay as a broken sync.
- **Orphan-matching ambiguity (FR-8.4).** `find_match` takes the first item with an equal
  title+downgraded-due key. If the missing side holds both the orphan and a genuinely new item
  with the same key, the wrong one can be linked and a duplicate appears on the present side.
  This is inherent to the heuristic (FR-8.3 already accepts it for the initial sync); recorded as
  a known limitation, no change proposed.
