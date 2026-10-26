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

## T-01. Manifest and package skeleton

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

## T-02. Canonical model

**Read:** ARCHITECTURE §2 (CanonicalTask, Snapshot, FIELDS).
**Files:** `custom_components/halltasker/core/__init__.py` (empty), `core/model.py`, `tests/__init__.py`, `tests/core/__init__.py`, `tests/core/test_model.py`.

Implement `CanonicalTask`, `Snapshot`, `FIELDS`, and the functions `due_to_str(due) -> str | None` and `due_from_str(s) -> Due`. No imports from `homeassistant`.

Tests (minimum): round-trip `to_dict/from_dict` for due None/date/datetime; naive datetime → `ValueError`; the hash is the same for equal tasks and differs when any field changes; the order of keys in `extensions` does not affect the hash.

## T-03. Remaining model structures

**Read:** ARCHITECTURE §2 (Link, Capabilities, Filter, Transform, DirectionRule, SyncPair).
**Files:** `core/model.py`, `tests/core/test_model.py`.

Add the dataclasses. `Link` has the methods `to_dict()`/`from_dict()` (snapshots as nested dicts `{"data":..., "hash":...}`). Test: round-trip of `Link` with filled and empty snapshots.

## T-04. Link store

**Read:** ARCHITECTURE §9.
**Files:** `core/link_store.py`, `tests/core/test_link_store.py`, `tests/core/fakes.py`.

In `fakes.py` create `FakeStorage` with `data: dict | None`, `async def async_load()`, `async def async_save(data)`, and a `saves` counter. Implement `LinkStore` following the signatures in §9. Indexes are built in `load()` and maintained in `upsert()`.

Tests: load of an empty store; upsert + get + links_of; `links_for_pair` returns tasks that have a link to at least one node of the pair; `save` serializes and a repeated `load` restores; `purge_tombstones` removes only old tombstones; `mark_pair_initialized` survives save/load.

## T-05. Downgrade

**Read:** ARCHITECTURE §5.
**Files:** `core/downgrade.py`, `tests/core/test_downgrade.py`.

Functions `downgrade(task, caps)` and `equivalent(observed, expected, caps)`. For the datetime → date conversion use the time zone passed as the parameter `tz: dt.tzinfo` (the core does not import HA): the signature is `downgrade(task, caps, tz)`. In the engine, `tz` is taken from `dt_util.get_default_time_zone()`.

Tests: datetime 2026-10-05 23:30+03:00 with `caps.due="date"` and tz=+03:00 → date 2026-10-05; the same datetime with tz=UTC → 2026-10-05 (20:30 UTC); `caps.due="none"` → None; description is dropped; `equivalent` is true for a date against a datetime with `caps.due="date"`.

## T-06. Change classification

**Read:** ARCHITECTURE §6.1 step 4.
**Files:** `core/diff.py`, `tests/core/test_diff.py`.

`SideState` and `classify(link, current, caps, tz) -> SideState`. The field `changed_fields` is computed relative to `link.last_synced`; if `last_synced is None`, relative to `last_observed`; if both are `None`, all non-empty fields.

Tests: one per each `kind`; echo case: `last_written` with a datetime, current with a date and `caps.due="date"` → `echo`.

## T-07. Router

**Read:** ARCHITECTURE §6.1 step 5, §7 (rules), SPEC FR-3.
**Files:** `core/router.py`, `tests/core/test_router.py`.

```python
def passes_filter(rule: DirectionRule, task: CanonicalTask) -> bool
def apply_transform(rule: DirectionRule, task: CanonicalTask, tz) -> CanonicalTask
def allows(rule: DirectionRule, op: Literal["create","update","complete"]) -> bool
def op_for_change(changed: frozenset[str]) -> Literal["update","complete"]   # only {"status"} → complete
```

Tests: regex filter; `require_due`; `due: date_only` gives a date; `title_prefix` is added once (if the prefix is already there, do not duplicate it); `op_for_change`.

## T-08. Conflicts and merging

**Read:** ARCHITECTURE §6.1 step 5, SPEC FR-5.
**Files:** `core/conflict.py`, `tests/core/test_conflict.py`.

```python
def merge(task_a, changed_a, task_b, changed_b, policy) -> tuple[CanonicalTask, frozenset[str], frozenset[str]]
# returns the resulting task and the sets of fields that must be written to A and to B
```

Non-overlapping fields are merged. Overlapping fields follow the policy. Tests: SPEC §7 scenarios A5 and A6.

## T-09. Matching during the initial sync

**Read:** SPEC FR-8.3.
**Files:** `core/matching.py`, `tests/core/test_matching.py`.

```python
def pair_up(new_a: dict[str, CanonicalTask], new_b: dict[str, CanonicalTask],
            caps_a, caps_b, tz) -> list[tuple[str, str]]
```

A match: equal `title` and equal downgraded `due` (downgrade to the weaker of the two capabilities). Each item takes part in at most one pair. Tests: one match; two identical titles with different due; duplicates on one side are linked one by one.

## T-10. Actions and result

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

## v1.1 tasks (2026-10-26)

Source: SPEC v1.1 §9 and ARCHITECTURE v1.1 §14. Execute in order, one commit per task, same rules as above. If a task makes you deviate from the architecture text, record the deviation under a new heading `## v1.1` in `docs/IMPLEMENTATION_NOTES.md` in the same commit.

## T-22. Store: per-pair link namespaces

**Read:** ARCHITECTURE §2 (paragraph "Links are scoped to a pair"), §6 (first paragraph after the class), §8 (`engine_factory`), §9 (whole section), §10 (diagnostics line).
**Files:** `core/link_store.py`, `core/engine.py`, `coordinator.py`, `__init__.py`, `diagnostics.py`, `tests/core/test_link_store.py`, `tests/core/test_engine_plan.py`, `tests/core/test_engine_apply.py`, `tests/test_coordinator.py`, `tests/test_diagnostics.py`.

Exact changes:

- `core/link_store.py`: new class `PairLinks` and the new `LinkStore` with exactly the methods of §9 (including `PairLinks.purge_tombstones` with the `present` argument; it is not called by the engine until T-27). Storage format schema 2. Rules of §9: same object per pair id, reset with a `WARNING` when the nodes of a pair id change, untouched namespaces of removed pairs, outdated format discarded with a `WARNING`. Remove the v1.0 per-link methods from `LinkStore`.
- `core/engine.py`: the constructor takes `store: PairLinks`; `_live_links` counts the namespace. No other logic changes.
- `coordinator.py`: the constructor takes `engine_factory: Callable[[SyncPair], SyncEngine]` instead of `engine`; `async_run_pair` builds the engine per cycle. Keep the per-pair locks as they are (T-23 replaces them).
- `__init__.py`: `engine_factory = lambda pair: SyncEngine(store.for_pair(pair), registry, clock=dt_util.now)`.
- `diagnostics.py`: `"store": store.to_dict()` and `"results"`, both passed through `async_redact_data(..., {"title", "description"})` (§10).
- Tests: `test_link_store.py` rewritten for the new API (namespace isolation: the same `(node, external_id)` in two pairs gives two independent links; `for_pair` identity; reset on re-pointed nodes with the warning in `caplog`; v1.0 data discarded with the warning; `to_dict` round-trips through `load`). Engine tests build the store as `LinkStore(FakeStorage()).for_pair(PAIR)`. Coordinator and diagnostics tests follow the new constructor and the schema 2 dump.

**Done when:** the common check passes; `pytest -q tests/core/test_link_store.py` has at least 5 new tests.

## T-23. Coordinator: one global lock

**Read:** ARCHITECTURE §8 (the comment in `async_run_pair`, "Why one global lock", "Cycle timeout", "Chained run"), SPEC FR-9.4, FR-12.6.
**Files:** `coordinator.py`, `const.py`, `tests/test_coordinator.py`.

Replace the per-pair locks with one `asyncio.Lock`; wrap the engine call in `asyncio.timeout(CYCLE_TIMEOUT_SECONDS)` (`const.py`, 120); add the chained run. Tests: two different pairs started at the same time run one after another (record the order of `run_pair` entry/exit in a fake engine and assert they do not interleave); a fake engine that never returns → after the timeout the result is `ok=False, error="cycle timeout"` and another pair can run; a fake engine whose result has an applied `update` on node B in pair `ab` → pair `bc` runs once after the debounce, pair `ab` is not re-run, and a dry run of `ab` triggers nothing.

## T-24. Schema: node and cycle validation

**Read:** ARCHITECTURE §7 (the four validation rules), SPEC FR-12.3.
**Files:** `schema.py`, `tests/test_schema.py` (new; validates `CONFIG_SCHEMA` directly, no `hass` fixture needed).

Add to `CONFIG_SCHEMA`: `a != b`; no two pairs with the same node set; forest check by union-find in configuration order with the error text from §7. Tests: each rule rejected with `vol.Invalid`; a star of three pairs on one node is accepted; `A↔B, B↔C, A↔C` is rejected naming the third pair.

## T-25. Engine: orphan matching before create

**Read:** ARCHITECTURE §6.1 steps 3a and 5 ("Orphan matching"), SPEC FR-8.4.
**Files:** `core/matching.py`, `core/engine.py`, `tests/core/test_matching.py`, `tests/core/test_engine_plan.py`, `tests/core/test_engine_apply.py`.

`matching.find_match(task, candidates, caps_task, caps_candidates, tz) -> str | None` with the same key as `pair_up`. In the engine: `new_a`/`new_b` are computed before the loop over canonical tasks (step 3a) and are mutated by orphan matching and consumed by step 6. Tests: `find_match` with and without a match; plan test — a canonical task with a link on A only and an equal unlinked item on B plans `link` on B and no `create`; apply test for SPEC scenario A12 — make `FakePlugin.create` write the item but raise `NodeUnavailable("created item not found")`, run two cycles, assert exactly one item on each side and both linked.

## T-26. Engine: locally accepted change

**Read:** ARCHITECTURE §6.1 step 5 ("Locally accepted change") and step 8 (last bullet), SPEC FR-3.5.
**Files:** `core/engine.py`, `tests/core/test_engine_apply.py`.

Implement `context.accepted` and its application after the action loop (one save if non-empty). Test for SPEC scenario A11: `a_to_b.update = False`; change `title` in A → no action, store saved once; second cycle → no action and no save; then change `due` in B → `update` on A with `changed == {"due"}` only, and the title in B is unchanged.

## T-27. Engine: tombstone purge in the cycle

**Read:** ARCHITECTURE §6.1 step 8a, §9 (`purge_tombstones`), SPEC FR-6.5.
**Files:** `core/engine.py`, `tests/core/test_link_store.py`, `tests/core/test_engine_apply.py`.

Call `purge_tombstones` at the end of every successful non-dry cycle with `present` built from the two snapshots; save once if something was purged. Tests: store — a tombstone older than 30 days whose item is still present is kept, one whose item is absent is removed, a fresh one is kept; engine — after `delete: false` and a clock advanced by 31 days the Y item is still not re-created and its tombstone link still exists; the deleted X link is gone.

## T-28. Engine: two pairs on a shared node

**Read:** ARCHITECTURE §6 (first paragraph after the class), §6.2 (last paragraph), SPEC FR-12, scenario A10.
**Files:** `tests/core/test_engine_multi_pair.py` (new), `core/engine.py` (only if a test exposes a defect; describe the fix in `docs/IMPLEMENTATION_NOTES.md`).

One `LinkStore`, one `FakePlugin` with three nodes A, B, C, two engines built with `store.for_pair(pair_ab)` and `store.for_pair(pair_bc)`, cycles run alternately AB, BC, AB, BC. Tests: create in A reaches C after the second BC cycle; rename in C reaches A; delete in A with `delete: true` in both pairs removes the item in B and then in C; after all that, one more AB and BC cycle apply nothing and do not save; `delete: false` in AB and `delete: true` in BC: delete in A → B keeps the item, C keeps the item, nothing is re-created on later cycles.

## T-29. Service `halltasker.reload`

**Read:** ARCHITECTURE §7 ("Reload"), §10, SPEC FR-10.5.
**Files:** `__init__.py`, `services.yaml`, `strings.json`, `translations/en.json`, `translations/ru.json`, `tests/test_services.py`.

Register `reload` in `async_setup` with `async_register_admin_service` exactly as in §7; import `async_integration_yaml_config` by name into `__init__.py`. Tests: patch `custom_components.halltasker.async_integration_yaml_config` to return a config with a second pair → after the service call `coordinator.pairs` has two pairs and the old coordinator is stopped; patch it to return `None` → an error in `caplog`, pairs unchanged, the integration still loaded.

## T-30. End-to-end tests with an in-memory todo platform

**Read:** ARCHITECTURE §12 (the `tests/todo_platform.py` bullet and the two bullets after it), §4.
**Files:** `tests/todo_platform.py` (new), `tests/test_e2e.py` (new).

`tests/todo_platform.py`: `MemoryTodoEntity(TodoListEntity)` with a `supported_features` constructor argument and an `async def setup_memory_todo(hass, entity_id_suffix, features) -> MemoryTodoEntity` helper that registers the `test` integration and its `todo` platform through `mock_integration` / `mock_platform` / `MockConfigEntry` and waits until the entity state exists. `tests/test_e2e.py`: set up HAlltasker from YAML with a pair of two such entities and run cycles through `halltasker.sync_now`. Scenarios from SPEC §7: A1, A2, A3, A4 (`delete: true`), A7 with the B entity lacking `SET_DUE_DATETIME_ON_ITEM` (bit 32), A9. Assert through `todo.get_items` responses, not through plugin internals.

## T-31. User documentation v1.1

**Files:** `README.md` (Russian, see the exception in AGENTS.md), `README.en.md`.

Update both files from `docs/` only: several pairs per node with the forest rule and a three-pair example sharing one Yandex node (SPEC FR-12, ARCHITECTURE §7); the `halltasker.reload` service in the services table and in the configuration section, replacing the "in progress" sentences; a note that to-do lists of the stock CalDAV integration require UI setup (RESEARCH §1); the Yandex app-password type is "Календарь" (RESEARCH §1); one sentence that a change crosses a shared node within seconds thanks to chained runs (SPEC FR-12.6), while external integrations such as CalDAV still add their own refresh delay; the cycle timeout (FR-9.4) in the limitations section. Keep the two files section-for-section equivalent.

## Stage 0 tasks (research)

Performed by a human or by an agent with access to the accounts. See `docs/RESEARCH.md`. Results are recorded in `docs/RESEARCH.md` §4 and affect only the README and the acceptance scenarios of group C. The MVP code does not depend on them.
