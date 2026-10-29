# Yandex Tracker mirror

The project work is mirrored in Yandex Tracker. This file tells any agent where and how.

- **Queue:** `IT` (org id `815076`). Credentials: `~/.yandex_tracker` (see the `yandex-tracker` skill for the API details).
- **Milestone:** `IT-9` — «HAlltasker — синхронизация задач между todo.* сущностями». All task issues are children of it.
- **Source of truth:** T-01…T-31 live in `docs/TASKS.md` and are mirrored (below). All newer tasks are written **only in the tracker** as `IT-<N>` and are not added to `TASKS.md`.
- **Mapping (T-01…T-31):** there is **no arithmetic relation** between `T-NN` and `IT-<N>`; matching numbers are a coincidence of creation order. The link is the issue summary, which starts with the task id: `T-26. Engine: locally accepted change`. Find the issue with `POST /v2/issues/_search` and `{"filter": {"queue": "IT"}, "query": "Summary: \"T-26.\""}`, then use its real key. `docs/TASKS.md` stays the source of truth; the tracker is a view.
- **Status:** closed with resolution `fixed` means the task is implemented and committed. It does not imply that a code review or an architectural review took place; open means pending.

## Roles and tags

Roles are task-scoped, not agent-scoped. Any agent may act as an executor, architect, or reviewer on different issues. The current `role:*` tag, not the agent's name or model, determines what the agent must do on that issue.

### Routing tags

- `role:executor` — implementation, tests, commits, closing the issue, and rework after review remarks.
- `role:architect` — task definition, answers to questions, decisions on disputes, and architectural review of technical decisions proposed or made by the executor.
- `role:reviewer` — code review of the implementation and tests. A reviewer is not a mandatory stage.

Every active issue has exactly one `role:*` tag. It identifies the role that must act next. Replace the previous role tag in the same update that assigns the next role; never leave an active issue with zero or multiple role tags.

### Attribution tags

- `agent:<name>` records that the agent participated in implementation or rework. The executor adds its tag when claiming the issue.
- `review:<name>` records that the agent performed a code review. The reviewer adds its tag when claiming the review.

Attribution tags are for history and statistics only. They do not assign work and must not be used in role queues. Keep all existing `agent:*` and `review:*` tags when other agents join: several tags of each kind are allowed. Do not remove them after rework, approval, or closure.

The generic `review` tag is not used. A pending code review is shown by `role:reviewer`; completed code reviews are shown by `review:<name>` and review comments. There is no separate architect-author tag: an architect's identity is recorded by signed comments.

The `halltasker` project tag remains on all issues. When patching tags, send the full merged list: the API replaces the array.

### Agent identity

A new agent must, before its first piece of tracker work, ask the owner what name to use in attribution tags, comment signatures, and its branch name (e.g. `zcode`). Use exactly that name afterwards; do not invent one. The name is independent of the branch currently checked out.

All parties act under one tracker account, so every comment is signed `— <name>` and starts with a marker.

## Statuses and role queues

| State | Meaning |
| --- | --- |
| `open` + `role:executor` | Available for implementation or rework |
| `inProgress` + `role:executor` | An executor has claimed the issue |
| `needInfo` + `role:architect` | Waiting for an architect's answer or decision |
| `inProgress` + `role:architect` | An architect has claimed the question |
| `open` + `role:reviewer` | An explicitly requested code review is available |
| `inProgress` + `role:reviewer` | A reviewer has claimed the code review |
| closed (`fixed`) | Implemented and committed; either kind of review may or may not have happened |

An agent finishes its own `inProgress` issue before taking a new one. It must not take an `inProgress` issue claimed by another agent. When claiming an issue, the agent adds `START: — <name>` and the applicable attribution tag, then moves it to `inProgress`.

Available-work queues, each sorted by key ascending:

- Executor: `Queue: IT Tags: role:executor Status: open`.
- Architect: `Queue: IT Tags: role:architect Status: needInfo`.
- Reviewer: `Queue: IT Tags: role:reviewer Status: open`.

Take the lowest key whose dependencies are closed. Link dependencies with `depends on`; the dependency must have the lower key.

## Workflow

1. **Create:** the architect writes the issue with `halltasker`, `role:executor`, and status `open`. The description has **Read**, **Files**, and **Done when**, like a TASKS.md entry. The common check (`ruff check . && ruff format --check . && pytest -q`) still applies. If the owner or architect requires code review before closure, the description also says `Code review: required`.
2. **Implement:** the executor takes the lowest available issue, reads the description **and all comments**, adds `agent:<its name>`, comments `START:`, and moves it to `inProgress`. A reopened issue carries the reason in the latest `REWORK:` comment.
3. **Question or dispute:** if the task is unclear, contradicts the docs, or the executor disagrees with a decision, it stops, comments `QUESTION:` or `DISPUTE:` (what was done, the problem, options, its own proposal), and sets `needInfo` + `role:architect`. It does not guess. It does not start the next issue until answered; other `role:executor` issues in `open` may continue.
4. **Answer:** the architect claims the `needInfo` issue with `START:` and `inProgress` + `role:architect`, then replies `ANSWER:` or `DECISION:`. If a dispute is accepted, the architect also patches the description and says so; if rejected, it gives reasons and its decision is final. It then sets `open` + `role:executor`.
5. **Done without requested code review:** after the checks and commit, the executor comments `DONE: <hash>` and closes with `fixed`. The final role tag remains `role:executor`.
6. **Done with requested code review:** if the description says `Code review: required`, the executor comments `DONE: <hash>` and sets `open` + `role:reviewer` instead of closing. The reviewer claims the issue, adds `review:<its name>`, and performs the code review. It comments `APPROVED:` and closes with `fixed`, or comments `REWORK:` with exact points and sets `open` + `role:executor`.
7. **Rework:** the executor fixes all `REWORK:` points in a new commit, comments `DONE: <new hash>`, and follows the same closure rule: close directly, or return to `role:reviewer` when `Code review: required` remains in the description. Attribution tags from all participants remain.

Commit messages are `IT-<N>: <issue summary>` for tracker-native tasks. Each agent works on its own branch.

## Architectural review and post-closure code review

An architectural review is a review of technical decisions against SPEC, ARCHITECTURE, and recorded decisions; it is not a code review. The architect signs its review comments but does not add `review:<name>`.

After closure, the architect may perform an architectural review and a reviewer may perform a code review. A post-closure code reviewer adds `review:<its name>` for attribution. If no changes are needed, the issue stays closed. If changes are needed, either reviewing role:

1. Comments `REWORK:` with exact, actionable points.
2. Reopens the issue with `reopen`.
3. Sets `open` + `role:executor`.

The issue then follows the rework workflow. A defect unrelated to the issue goes into a new linked issue instead of a comment on an unrelated one.

## Mirrored tasks and maintenance

For mirrored tasks T-01…T-31 the same role, review, and comment-marker rules apply, but the task text stays in `docs/TASKS.md` and questions go to `docs/QUESTIONS.md` as before. After completing a mirrored task `T-NN` (find `<key>` by the summary, see Mapping; checks passed, commit `T-NN: …` made, TASKS.md marked):

1. `PATCH /v2/issues/<key>` if the description needs updating (it holds the original task text from TASKS.md).
2. `POST /v2/issues/<key>/comments/` — `DONE:` with the date and commit hash, signed `— <agent name>`.
3. Close with `POST /v3/issues/<key>/transitions/close/_execute` and `{"resolution": {"key": "fixed"}}`, unless the description requires code review; in that case set `open` + `role:reviewer` instead.

For tracker-native tasks there is no TASKS.md edit. Known defects found during a task go into `docs/QUESTIONS.md` as usual and, if they block the task, also as a comment on its issue.

The executor closes issues that do not require code review. The reviewer closes issues after an explicitly requested code review. The architect does not close an issue merely because its architectural review passed.

## Migrating existing issues

New issues use role tags for routing from creation. Migrate an existing active issue before making it available in a role queue:

- `needInfo` gets `role:architect`.
- An issue with unresolved `REWORK:` remarks gets `role:executor`.
- An issue waiting for an explicitly requested code review gets `role:reviewer`.
- Every other active implementation issue gets `role:executor`.

Preserve all `agent:<name>` and `review:<name>` tags. Remove the generic `review` tag and the old architect-author tag when migrating the issue. Closed issues need no migration unless reopened; a reopened issue gets `role:executor`.

State as of 2026-10-26: IT-10…IT-34 (T-01…T-25) closed; IT-35…IT-40 (T-26…T-31) open; milestone IT-9 has a project-history comment. Issue IT-8 is a probe awaiting manual deletion in the UI (issues cannot be deleted via the API).
