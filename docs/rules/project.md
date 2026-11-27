# Project rules

## What this project is

HAlltasker is a custom integration for Home Assistant on Python 3.14. It
synchronizes tasks between `todo.*` entities. Requirements: `docs/SPEC.md`.
Design: `docs/ARCHITECTURE.md`. Yandex Tracker is the only source of tasks.

## Forbidden

- Do not add dependencies: `requirements` in `manifest.json` stays empty,
  `requirements_dev.txt` does not change.
- Do not import `homeassistant` inside `custom_components/halltasker/core/`.
  The core is pure.
- Do not invent Home Assistant methods and services. Everything you need is
  listed in `docs/ARCHITECTURE.md` §4, §7, §8, §9. If something is missing,
  route a question to the architect as described in `docs/rules/workflow.md`.
- Do not change `docs/SPEC.md` and `docs/ARCHITECTURE.md`. If you find a
  contradiction, route a question to the architect as described in
  `docs/rules/workflow.md`.
- Do not do several tasks in one commit. Do not start the next task until the
  current one passes the checks.
- Do not write service markers, prefixes, or hidden fields into the user's
  tasks. All links are stored in the internal store.
- Do not touch `.idea/`.
- Do not create or edit files under `docs/ru/`. They are human reading copies
  maintained by the owner.

## Checking the Home Assistant API

The HA version is pinned in `requirements_dev.txt`. If you need to confirm a
signature, look at the installed package:

```
python -c "import homeassistant.components.todo.const as c; print([f.name for f in c.TodoListEntityFeature])"
```

Do not look for answers on the internet: behavior in other versions differs.

## HACS releases

HACS releases must use semantic version tags in the format `MAJOR.MINOR.PATCH`
(for example, `1.2.3`).
