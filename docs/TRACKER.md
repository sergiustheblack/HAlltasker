# Yandex Tracker core

Tracker is the only source of tasks. Queue: `IT`; native Project: **HAlltasker**, numeric Project ID `4` (the API exposes no separate `shortId`). Project `4` is mandatory for every new issue. An agent creating issues while working within a milestone must attach them to that milestone. Architects may create milestones at their discretion or at the owner's request. Commit as `IT-<N>: <issue summary>` on your own branch.

Use the `yandex-tracker` skill and its `yt` wrapper. Read this file and only your role file:

- `docs/TRACKER.developer.md` — `role:developer`; legacy issues may use `role:executor`.
- `docs/TRACKER.architect.md` — `role:architect`.
- `docs/TRACKER.reviewer.md` — `role:reviewer`.

## Shared protocol

Before your first Tracker work, ask the owner for your name if it is not already assigned; never invent one. Sign every comment with a final line `— <name>` and use the marker required by your role.

Every active issue has exactly one `role:*` tag. It determines who acts next; `agent:<name>` and `review:<name>` only record participation. Preserve all existing tags when routing: tag updates replace the whole array. New issues require Project `4`; the old `halltasker` tag is optional and remains valid on existing issues.

Routing states are `open` + developer/reviewer or `needInfo` + architect. Claimed work is `inProgress` with the same role. Finish your own claimed issue before taking another; never claim another agent's `inProgress` issue.

```bash
alias yt='~/.agents/skills/yandex-tracker/yt'
yt next --role <developer|architect|reviewer> --queue IT
yt claim <KEY> --agent <name>
```

`next` selects the lowest key with closed dependencies; for developer it includes legacy `role:executor`. `claim` adds `START:` and attribution, moves the issue, and prints its compact role context. Do not repeat `get` or `comments` afterwards. Use `yt show <KEY> --all-comments` only when full history is genuinely needed; `--comments-last N` selects recent history instead.

The current specification is the issue description unless a later comment starts exactly with `SPEC:`. The latest such comment is a complete replacement, not a delta. Only the architect or owner publishes it with `yt spec`; developers and reviewers never rewrite requirements to match implementation. `yt show` prints the current specification without duplicating its source comment.

Closed with `fixed` means implemented and committed; it says nothing about review coverage. Create dependencies with `yt link <KEY> <LOWER_KEY> --relationship "depends on"`. Record unrelated defects in new linked issues rather than unrelated comments.
