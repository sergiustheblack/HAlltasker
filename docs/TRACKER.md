# Yandex Tracker mirror

The project work is mirrored in Yandex Tracker. This file tells any agent where and how.

- **Queue:** `IT` (org id `815076`). Credentials: `~/.yandex_tracker` (see the `yandex-tracker` skill for the API details).
- **Milestone:** `IT-9` — «HAlltasker — синхронизация задач между todo.* сущностями». All task issues are children of it.
- **Mapping:** issue `IT-<N+9>` corresponds to task `T-<NN>` from `docs/TASKS.md` (T-01 → IT-10, …, T-31 → IT-40). `docs/TASKS.md` stays the source of truth; the tracker is a view.
- **Status:** closed with resolution `fixed` means the task is implemented and committed; open means pending.

## Maintenance protocol

After completing a task `T-NN` (checks passed, commit `T-NN: …` made, TASKS.md marked):

1. `PATCH /v2/issues/IT-<N+9>` if the description needs updating (it holds the original task text from TASKS.md).
2. `POST /v2/issues/IT-<N+9>/comments/` — a short note: done, date, commit hash; sign it `— <agent name>` (e.g. `— zcode`).
3. `POST /v3/issues/IT-<N+9>/transitions/close/_execute` with `{"resolution": {"key": "fixed"}}`.

Known defects found during a task go into `docs/QUESTIONS.md` as usual and, if they block the task, also as a comment on its issue.

State as of 2026-10-26: IT-10…IT-34 (T-01…T-25) closed; IT-35…IT-40 (T-26…T-31) open; milestone IT-9 has a project-history comment. Issue IT-8 is a probe awaiting manual deletion in the UI (issues cannot be deleted via the API).
