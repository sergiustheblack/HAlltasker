# Yandex Tracker mirror

The project work is mirrored in Yandex Tracker. This file tells any agent where and how.

- **Queue:** `IT` (org id `815076`). Credentials: `~/.yandex_tracker` (see the `yandex-tracker` skill for the API details).
- **Milestone:** `IT-9` — «HAlltasker — синхронизация задач между todo.* сущностями». All task issues are children of it.
- **Source of truth:** T-01…T-31 live in `docs/TASKS.md` and are mirrored (below). All newer tasks are written **only in the tracker** as `IT-<N>` and are not added to `TASKS.md`.
- **Mapping (T-01…T-31):** issue `IT-<N+9>` corresponds to task `T-<NN>` from `docs/TASKS.md` (T-01 → IT-10, …, T-31 → IT-40). `docs/TASKS.md` stays the source of truth; the tracker is a view.
- **Status:** closed with resolution `fixed` means the task is implemented and committed; open means pending.

## Tags and agent routing (tracker-native tasks)

- **Agent name:** a new executor or architect agent must, before its first piece of work, ask the owner what name to use in tags, comment signatures and branch name (e.g. `zcode`, `claude-architect`), and use exactly that name afterwards. Do not invent a name. Do not touch the tracker before the owner answers.

- **Author tag:** every issue written by the architect carries the tag `claude-architect`, plus the project tag `halltasker` that all issues already have.
- **Executor tag:** `agent:<name>` (e.g. `agent:zcode`) assigns the issue to one executor agent. Matches the agent's git branch name. An issue without an `agent:*` tag is not assigned: no agent takes it.
- **Queue for an agent:** `Queue: IT Tags: agent:<name> Status: open, inProgress Sort by: Key asc`. Take the lowest key; work strictly in key order. If a task depends on another, link it (`depends on`) and the dependency has the lower key.
- **Description format:** same as a TASKS.md entry: **Read**, **Files**, **Done when**. The common check (`ruff check . && ruff format --check . && pytest -q`) still applies.
- **Commit message:** `IT-<N>: <issue summary>`. Branch: the agent's own.
- **Mirrored T-NN tasks** have no `agent:*` tag; T-26…T-31 stay in the existing flow.

## Workflow for tracker-native tasks

Statuses: `open` → `inProgress` → closed (`fixed`). `needInfo` is the "waiting for the architect" state. All parties act under one account, so every comment is signed `— <name>` and starts with a marker.

1. **Take:** the executor takes the lowest-key issue from its queue, reads the description **and all comments** (a reopened issue carries the reason in the latest architect comment), moves it to `inProgress`.
2. **Question or dispute:** if the task is unclear, contradicts the docs, or the executor disagrees with the decision, it stops, comments with marker `QUESTION:` or `DISPUTE:` (what was done, the problem, options, its own proposal) and moves the issue to `needInfo`. It does not guess and does not start the next issue until answered; other `agent:<name>` issues in `open` may continue.
3. **Answer:** the architect watches `Queue: IT Status: needInfo`. It replies with marker `ANSWER:` or `DECISION:`. A dispute may be accepted (then the architect also patches the description and says so) or rejected with reasons; the decision is final. Then it moves the issue back to `open`.
4. **Done:** the executor makes the commit, comments with the hash (`DONE:`) and closes with `fixed`.
5. **Review remarks:** after closing, the architect may review the commit. If something must change, it comments `REWORK:` with exact points and reopens the issue (`reopen`). The issue re-enters the executor queue; the executor fixes it in a new commit `IT-<N>: <what>`, comments `DONE:` and closes again.
6. **Architect-found defects in other tasks** go into a new issue, not into a comment on an unrelated one.

For mirrored tasks T-01…T-40 the same markers apply, but the task text stays in `docs/TASKS.md` and questions go to `docs/QUESTIONS.md` as before.

## Maintenance protocol

Issues are closed by the executor agent that did the work. The architect never closes issues; it may comment on any issue and reopen a closed one (`reopen` transition) so that the executor sees it.

After completing a mirrored task `T-NN` (checks passed, commit `T-NN: …` made, TASKS.md marked):

1. `PATCH /v2/issues/IT-<N+9>` if the description needs updating (it holds the original task text from TASKS.md).
2. `POST /v2/issues/IT-<N+9>/comments/` — a short note: done, date, commit hash; sign it `— <agent name>` (e.g. `— zcode`).
3. `POST /v3/issues/IT-<N+9>/transitions/close/_execute` with `{"resolution": {"key": "fixed"}}`.

For tracker-native tasks: no TASKS.md edit; steps 2 and 3 only (comment with commit hash and `— <agent name>`, then close with `fixed`).

Known defects found during a task go into `docs/QUESTIONS.md` as usual and, if they block the task, also as a comment on its issue.

State as of 2026-10-26: IT-10…IT-34 (T-01…T-25) closed; IT-35…IT-40 (T-26…T-31) open; milestone IT-9 has a project-history comment. Issue IT-8 is a probe awaiting manual deletion in the UI (issues cannot be deleted via the API).
