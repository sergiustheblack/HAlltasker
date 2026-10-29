# Rules for implementation agents

> Language: English only. All agent-facing documentation in this repository is English. Do not write Russian in code, comments, commit messages, tests, or docs/QUESTIONS.md. The only exception is `README.md`, a human-facing document in Russian: a task that lists it says so explicitly.

Every agent reads this file before working in the repository. The rules are short and mandatory.

## What this project is

HAlltasker is a custom integration for Home Assistant on Python 3.14. It synchronizes tasks between `todo.*` entities. Requirements: `docs/SPEC.md`. Design: `docs/ARCHITECTURE.md`. Task list: `docs/TASKS.md`.

The work is also tracked in Yandex Tracker. After finishing a task, mirror it per `docs/TRACKER.md`. Tasks newer than T-31 exist only in the tracker: take the lowest-key open issue tagged `role:executor` (see `docs/TRACKER.md`), and commit as `IT-<N>: <summary>`.

The issue's `role:*` tag defines your role for that issue. `agent:<name>` and `review:<name>` record participation for statistics; they do not assign work. Code review is optional unless the issue description says `Code review: required`.

## Order of work on a task

0. If you have not yet been given a name by the owner, ask: "What name should I use in tracker tags, comment signatures and my branch?" Wait for the answer before doing anything else (see `docs/TRACKER.md`).

1. Open `docs/TASKS.md` and take the first unfinished task (for T-32 and later: the tracker, see above). Tasks are executed strictly in order.
2. Read the sections of `docs/ARCHITECTURE.md` named in the task. Do not change signatures and names from the architecture.
3. Create and change only the files listed in the task. If you need another file, stop and record a question in `docs/QUESTIONS.md` (format below). For tracker-native tasks (T-32 and later) the question goes into the issue as a `QUESTION:`/`DISPUTE:` comment and the issue moves to `needInfo` (see `docs/TRACKER.md`, "Workflow"). Read all comments on the issue before starting; a reopened issue means the architect or reviewer left `REWORK:` remarks.
4. Write the code and the tests of the task.
5. Run the checks:

   ```
   ruff check . && ruff format --check . && pytest -q
   ```

   All three commands must finish without errors. If `ruff format --check` complains, run `ruff format .` and repeat.
6. Make one commit with the message `T-NN: <task title from TASKS.md>`.
7. In `docs/TASKS.md` mark the task: add `✅` at the start of the heading.

## Forbidden

- Do not add dependencies: `requirements` in `manifest.json` stays empty, `requirements_dev.txt` does not change.
- Do not import `homeassistant` inside `custom_components/halltasker/core/`. The core is pure.
- Do not invent Home Assistant methods and services. Everything you need is listed in `docs/ARCHITECTURE.md` §4, §7, §8, §9. If something is missing, record a question in `docs/QUESTIONS.md`.
- Do not change `docs/SPEC.md` and `docs/ARCHITECTURE.md`. If you find a contradiction, record a question in `docs/QUESTIONS.md`.
- Do not do several tasks in one commit. Do not start the next task until the current one passes the checks.
- Do not write service markers, prefixes, or hidden fields into the user's tasks. All links are stored in the internal store.
- Do not touch `.idea/`.
- Do not create or edit files under docs/ru/. They are human reading copies maintained by the owner.

## Question format in docs/QUESTIONS.md

```
## Q-<number> (T-<task>) — open
Context: what you were doing.
Problem: what is unclear or contradictory.
Options: 1) … 2) …
```

After recording the question, stop work on the task. The answer will appear in the same file marked `— closed`.

## Code style

- Type annotations everywhere. `from __future__ import annotations` in every module.
- Dataclasses from the architecture are `frozen=True`, except `Link`.
- Core functions are pure: input → output, no global state, no access to the time (`now` is passed as a parameter).
- Logger: `_LOGGER = logging.getLogger(__package__)`.
- Tests: `pytest`, names `test_<what we check>_<expectation>`. One assert block per behavior. Fakes from `tests/core/fakes.py`, not `MagicMock` for plugins and the store.
- Comments and docstrings in English, one line, only where the name does not explain the purpose.

## Checking the Home Assistant API

The HA version is pinned in `requirements_dev.txt`. If you need to confirm a signature, look at the installed package:

```
python -c "import homeassistant.components.todo.const as c; print([f.name for f in c.TodoListEntityFeature])"
```

Do not look for answers on the internet: behavior in other versions differs.
