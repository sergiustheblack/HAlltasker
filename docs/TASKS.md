# HAlltasker — tasks for implementation agents

> Language: English only (agent-facing).

Rules for executing tasks are in AGENTS.md. Binding requirements: docs/SPEC.md. Binding design: docs/ARCHITECTURE.md.

Each task is atomic: one task = one commit. Execute strictly in order, task N+1 builds on N. Before starting a task, read the listed sections of `docs/ARCHITECTURE.md`.

Legend: **Files** — what to create or change, do not touch any other files. **Done when** — commands that must pass without errors.

Common check for every task (added to "Done when"):

```
ruff check . && ruff format --check . && pytest -q
```

---

## ✅ T-01. Manifest and package skeleton

**Read:** ARCHITECTURE §1.
**Files:** `custom_components/halltasker/__init__.py`, `manifest.json`, `const.py`.

Content of `manifest.json` (exact):

```json
{
  "domain": "halltasker",
  "name": "HAlltasker",
  "codeowners": [],
  "config_flow": true,
  "dependencies": ["todo"],
  "documentation": "https://github.com/s-parfyenov/HAlltasker",
  "integration_type": "service",
  "iot_class": "local_polling",
  "issue_tracker": "https://github.com/s-parfyenov/HAlltasker/issues",
  "requirements": [],
  "version": "0.1.0"
}
```

`const.py`:

```python
DOMAIN = "halltasker"
STORAGE_KEY = "halltasker"
STORAGE_VERSION = 1
DEFAULT_INTERVAL = 60
MIN_INTERVAL = 15
EVENT_DEBOUNCE_SECONDS = 2.0
TOMBSTONE_TTL_DAYS = 30
```

`__init__.py`: only a docstring and `from .const import DOMAIN`. The logic is added in T-14.

**Done when:** `python -c "import json; json.load(open('custom_components/halltasker/manifest.json'))"`.

## ✅ T-02. Canonical model

**Read:** ARCHITECTURE §2 (CanonicalTask, Snapshot, FIELDS).
**Files:** `custom_components/halltasker/core/__init__.py` (empty), `core/model.py`, `tests/__init__.py`, `tests/core/__init__.py`, `tests/core/test_model.py`.

Implement `CanonicalTask`, `Snapshot`, `FIELDS`, and the functions `due_to_str(due) -> str | None` and `due_from_str(s) -> Due`. No imports from `homeassistant`.

Tests (minimum): round-trip `to_dict/from_dict` for due None/date/datetime; naive datetime → `ValueError`; the hash is the same for equal tasks and differs when any field changes; the order of keys in `extensions` does not affect the hash.

## ✅ T-03. Remaining model structures

**Read:** ARCHITECTURE §2 (Link, Capabilities, Filter, Transform, DirectionRule, SyncPair).
**Files:** `core/model.py`, `tests/core/test_model.py`.

Add the dataclasses. `Link` has the methods `to_dict()`/`from_dict()` (snapshots as nested dicts `{"data":..., "hash":...}`). Test: round-trip of `Link` with filled and empty snapshots.

## ✅ T-04. Link store

**Read:** ARCHITECTURE §9.
**Files:** `core/link_store.py`, `tests/core/test_link_store.py`, `tests/core/fakes.py`.

In `fakes.py` create `FakeStorage` with `data: dict | None`, `async def async_load()`, `async def async_save(data)`, and a `saves` counter. Implement `LinkStore` following the signatures in §9. Indexes are built in `load()` and maintained in `upsert()`.

Tests: load of an empty store; upsert + get + links_of; `links_for_pair` returns tasks that have a link to at least one node of the pair; `save` serializes and a repeated `load` restores; `purge_tombstones` removes only old tombstones; `mark_pair_initialized` survives save/load.

## ✅ T-05. Downgrade

**Read:** ARCHITECTURE §5.
**Files:** `core/downgrade.py`, `tests/core/test_downgrade.py`.

Functions `downgrade(task, caps)` and `equivalent(observed, expected, caps)`. For the datetime → date conversion use the time zone passed as the parameter `tz: dt.tzinfo` (the core does not import HA): the signature is `downgrade(task, caps, tz)`. In the engine, `tz` is taken from `dt_util.get_default_time_zone()`.

Tests: datetime 2026-10-05 23:30+03:00 with `caps.due="date"` and tz=+03:00 → date 2026-10-05; the same datetime with tz=UTC → 2026-10-05 (20:30 UTC); `caps.due="none"` → None; description is dropped; `equivalent` is true for a date against a datetime with `caps.due="date"`.

## ✅ T-06. Change classification

**Read:** ARCHITECTURE §6.1 step 4.
**Files:** `core/diff.py`, `tests/core/test_diff.py`.

`SideState` and `classify(link, current, caps, tz) -> SideState`. The field `changed_fields` is computed relative to `link.last_synced`; if `last_synced is None`, relative to `last_observed`; if both are `None`, all non-empty fields.

Tests: one per each `kind`; echo case: `last_written` with a datetime, current with a date and `caps.due="date"` → `echo`.

## ✅ T-07. Router

**Read:** ARCHITECTURE §6.1 step 5, §7 (rules), SPEC FR-3.
**Files:** `core/router.py`, `tests/core/test_router.py`.

```python
def passes_filter(rule: DirectionRule, task: CanonicalTask) -> bool
def apply_transform(rule: DirectionRule, task: CanonicalTask, tz) -> CanonicalTask
def allows(rule: DirectionRule, op: Literal["create","update","complete"]) -> bool
def op_for_change(changed: frozenset[str]) -> Literal["update","complete"]   # only {"status"} → complete
```

Tests: regex filter; `require_due`; `due: date_only` gives a date; `title_prefix` is added once (if the prefix is already there, do not duplicate it); `op_for_change`.

## ✅ T-08. Conflicts and merging

**Read:** ARCHITECTURE §6.1 step 5, SPEC FR-5.
**Files:** `core/conflict.py`, `tests/core/test_conflict.py`.

```python
def merge(task_a, changed_a, task_b, changed_b, policy) -> tuple[CanonicalTask, frozenset[str], frozenset[str]]
# returns the resulting task and the sets of fields that must be written to A and to B
```

Non-overlapping fields are merged. Overlapping fields follow the policy. Tests: SPEC §7 scenarios A5 and A6.

## ✅ T-09. Matching during the initial sync

**Read:** SPEC FR-8.3.
**Files:** `core/matching.py`, `tests/core/test_matching.py`.

```python
def pair_up(new_a: dict[str, CanonicalTask], new_b: dict[str, CanonicalTask],
            caps_a, caps_b, tz) -> list[tuple[str, str]]
```

A match: equal `title` and equal downgraded `due` (downgrade to the weaker of the two capabilities). Each item takes part in at most one pair. Tests: one match; two identical titles with different due; duplicates on one side are linked one by one.

## ✅ T-10. Actions and result

**Read:** ARCHITECTURE §6.3, §6.1 step 9.
**Files:** `core/actions.py`, `tests/core/test_actions.py`.

`Action`, `RunResult`, `def action_to_dict(a: Action) -> dict`. Test: serialization without `None` fields.

## T-11. Plugin contract and registry

**Read:** ARCHITECTURE §3.
**Files:** `plugins/__init__.py` (empty), `plugins/base.py`, `plugins/registry.py`, `tests/core/fakes.py`, `tests/plugins/__init__.py`, `tests/plugins/test_registry.py`.

`Plugin` ABC with the signature `create(node, task, known_ids)`. `PluginRegistry.register(plugin)`, `for_node(node) -> Plugin` (raises `KeyError` with a clear message). In `fakes.py` add `FakePlugin`: dicts `items[node][external_id] = CanonicalTask`, `caps[node]`, a list `calls`, a flag `fail[node]` to simulate `NodeUnavailable`, and a counter for generating external_id.

## T-12. Engine: read, classify, plan without writing

**Read:** ARCHITECTURE §6 in full.
**Files:** `core/engine.py`, `tests/core/test_engine_plan.py`.

Implement `SyncEngine.run_pair` up to and including step 7, always returning the plan with `dry_run=True`. Execution (step 8) is in T-13. Plan tests: new item in A → `create` in B; change in A → `update` in B; `complete`; deletion with the three `delete` values; conflict between two sides; the initial cycle discards deletions; `NodeUnavailable` → `ok=False`, empty plan.

## T-13. Engine: execution and saving

**Read:** ARCHITECTURE §6.1 step 8, SPEC FR-7.
**Files:** `core/engine.py`, `tests/core/test_engine_apply.py`.

Execute actions through the plugin, update `Link`, call `store.save()` after every write, collect `actions_failed`. Tests: SPEC §7 scenarios A1–A9 on `FakePlugin` and `FakeStorage`; a repeated cycle without changes → `actions_applied` is empty and `saves` does not grow; a failed `create` on B does not block the other actions.

## T-14. YAML schema and integration loading

**Read:** ARCHITECTURE §7, SPEC FR-11.
**Files:** `schema.py`, `__init__.py`, `config_flow.py`, `strings.json`, `translations/en.json`, `translations/ru.json`, `tests/conftest.py` (already exists), `tests/test_init.py`.

`CONFIG_SCHEMA` on `voluptuous` with `cv.entity_domain("todo")` for nodes, `cv.positive_int` and `vol.Range(min=15)` for the interval, regex validation through `vol.Coerce` with `re.compile`. `parse_pairs`. `config_flow.py`: a class with `VERSION = 1`, only `async_step_import`, `_abort_if_unique_id_configured` with `unique_id="halltasker"`. `__init__.py`: `async_setup`, `async_setup_entry` (no coordinator yet: store the pairs in `hass.data`), `async_unload_entry`.

Test: `async_setup_component(hass, "halltasker", {"halltasker": {"pairs": [...]}})` → one ConfigEntry, pairs parsed; invalid YAML (interval 5) → `False` and an error in the log.

## T-15. Plugin `ha_todo`

**Read:** ARCHITECTURE §4.
**Files:** `plugins/ha_todo.py`, `tests/plugins/test_ha_todo.py`.

`HaTodoPlugin(hass)`. In the test, register fake services `todo.get_items/add_item/update_item/remove_item` through `hass.services.async_register(..., supports_response=SupportsResponse.OPTIONAL)` for `get_items`. Tests: mapping of the three kinds of due; status; capabilities from `supported_features`; `update` passes only the changed fields and does not pass unsupported ones; `create` finds the uid among the items not excluded by `known_ids`; an `unavailable` entity → `NodeUnavailable`.

## T-16. Coordinator

**Read:** ARCHITECTURE §8.
**Files:** `coordinator.py`, `__init__.py` (connect the coordinator, `LinkStore` on top of `homeassistant.helpers.storage.Store`), `tests/test_coordinator.py`.

Tests with `async_fire_time_changed` from `pytest_homeassistant_custom_component.common`: a cycle starts on the interval; a `state_changed` event of a node starts the cycle once after the debounce; two simultaneous calls of `async_run_pair` are serialized.

## T-17. Services

**Read:** ARCHITECTURE §10.
**Files:** `__init__.py`, `services.yaml`, `strings.json`, `translations/*.json`, `tests/test_services.py`.

`halltasker.sync_now`, `halltasker.dry_run` (with a response). Test: calling `dry_run` returns the plan for the given pair.

## T-18. Sensor

**Read:** ARCHITECTURE §10, SPEC FR-10.3.
**Files:** `sensor.py`, `__init__.py` (`async_forward_entry_setups(entry, ["sensor"])`), `tests/test_sensor.py`.

Test: after a cycle the sensor `sensor.halltasker_<pair_id>` has the state `ok` and the attribute `links`.

## T-19. Diagnostics and logging

**Read:** ARCHITECTURE §11, SPEC FR-10.4.
**Files:** `diagnostics.py`, `engine.py`/`coordinator.py` (log lines), `tests/test_diagnostics.py`.

`async_get_config_entry_diagnostics` returns `{"pairs": [...], "store": {...}, "results": {...}}`. Rate-limit the `NodeUnavailable` warnings.

## T-20. User documentation

**Files:** `README.md`, `README.en.md`.

The README must be written in Russian (primary) in `README.md` and in English in `README.en.md`, with a language switch line at the top of each. Sections: installation through HACS; environment requirements for iCloud (a CalDAV account on the iPhone) and Yandex (the app password "Календарь CalDAV", connecting the stock HA CalDAV); the YAML example from ARCHITECTURE §7; services and sensors; limitations (Google Tasks without time, CalDAV once every 15 minutes, no RRULE). The README must not contain facts that are not in `docs/`: only what is in `docs/`.

## T-21. CI

**Files:** `.github/workflows/ci.yml` (already exists, check it), edit `pyproject.toml` if needed.

**Done when:** `ruff`, `pytest`, `hassfest`, `hacs/action` pass locally or in GitHub Actions.

---

## Stage 0 tasks (research)

Performed by a human or by an agent with access to the accounts. See `docs/RESEARCH.md`. Results are recorded in `docs/RESEARCH.md` §4 and affect only the README and the acceptance scenarios of group C. The MVP code does not depend on them.
