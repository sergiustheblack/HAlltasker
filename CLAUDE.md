# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

HAlltasker is a Home Assistant custom integration (Python 3.14, HA 2026.9.x) that synchronizes tasks between any `todo.*` entities inside Home Assistant. External systems (iCloud Reminders, Google Tasks, Yandex Calendar) are reached only through stock HA integrations; this repo contains no external API clients or credentials.

Authoritative documents, in priority order:

- `docs/SPEC.md` — requirements. Do not change without the owner's decision.
- `docs/ARCHITECTURE.md` — module layout, data model, engine algorithm, HA API facts, YAML schema. Signatures there are binding.
- `docs/TASKS.md` — ordered atomic tasks T-01…T-31 for implementation agents. Mark done with `✅`. Newer tasks live only in Yandex Tracker (`docs/TRACKER.md`): `role:*` tags route work to the executor, architect, or reviewer; `agent:<name>` and `review:<name>` record participation for statistics.
- `docs/RESEARCH.md` — external constraints with sources, and the stage 0 protocol for Yandex CalDAV.
- `AGENTS.md` — working rules for weak self-hosted coding agents. Keep tasks and instructions compatible with those rules: one task per commit, listed files only, no new dependencies.

## Documentation language policy

- **Agent-facing docs are English only:** `AGENTS.md`, `CLAUDE.md`, `docs/SPEC.md`, `docs/ARCHITECTURE.md`, `docs/TASKS.md`, `docs/QUESTIONS.md`, `docs/RESEARCH.md`, plus all code, comments, tests and commit messages.
- **Human-facing docs are bilingual, Russian is primary:** `README.md` (Russian) + `README.en.md`; Russian reading copies of the spec, architecture and research live in `docs/ru/`. The English file in `docs/` is binding; `docs/ru/` copies are for the owner.
- When you change `docs/SPEC.md`, `docs/ARCHITECTURE.md` or `docs/RESEARCH.md`, update the matching `docs/ru/` copy in the same change (translate the changed sections; do not leave them out of sync).
- Reply to the owner in Russian, terse. Implementation agents never write Russian (see `AGENTS.md`).

The `.idea/` directory is IDE metadata (declares a Java module); it is irrelevant, the project is Python. Do not infer stack from it.

## Commands

```
python -m venv .venv && source .venv/bin/activate
pip install -r requirements_dev.txt

ruff check .                 # lint
ruff format .                # format (CI uses --check)
pytest -q                    # all tests
pytest -q tests/core         # core only, no HA fixtures
pytest -q tests/core/test_engine_plan.py -k "delete"   # single file / expression
```

`hassfest` and HACS validation run in GitHub Actions (`.github/workflows/ci.yml`); there is no local equivalent beyond the ruff/pytest pair.

## Architecture in one paragraph

Configuration is YAML only (`halltasker:` key in `configuration.yaml`, parsed in `schema.py`); an import-only config flow creates a single ConfigEntry so reload and diagnostics work. `coordinator.py` schedules one `SyncEngine.run_pair` per configured pair on an interval and on debounced `state_changed` events. The engine (`core/engine.py`) reads full snapshots of both nodes via a `Plugin`, classifies each linked task per side (`core/diff.py`: unchanged / changed / deleted / echo), plans `Action`s through direction rules (`core/router.py`) and the pair's conflict policy (`core/conflict.py`), downgrades tasks to node capabilities (`core/downgrade.py`), executes writes, and persists `Link` records (three snapshots plus tombstone) to `.storage/halltasker` after every write. The only plugin in MVP is `plugins/ha_todo.py`, which maps `todo.*` service calls to `CanonicalTask`. `core/` must never import `homeassistant`.

## Conventions worth knowing

- Dates without time are `datetime.date`; never midnight datetimes. Datetimes are always tz-aware.
- Capabilities of a `todo.*` node come from its `supported_features` bitmask; fields the node cannot hold are dropped before the service call, and reading back the degraded value is not a change.
- `todo.add_item` returns no uid: the plugin re-reads the list and matches the new item by content against ids it did not know before.
- Current stable HA uses `voluptuous`; the dev branch has moved to `probatio`. The schema is isolated in `schema.py` for that reason.
- Git branch is `gemma`; there is no `main` yet.
