# Architect Tracker flow

Read `docs/TRACKER.md` first. Role: `role:architect`.

Create open implementation issues under milestone `IT-9`, with native Project `4` and `role:developer`:

```bash
yt create --queue IT --project 4 --parent IT-9 --tags role:developer --summary "<summary>" --description "<specification>"
```

The description must contain **Read**, **Files**, and **Done when**; add `Code review: required` when review is mandatory. Do not require the legacy `halltasker` tag. Link dependencies explicitly.

The current specification must always be complete. Initially it is the description. Whenever requirements or decisions change it, publish a full replacement, not a delta:

```bash
yt spec <KEY> --agent <name> "<complete current specification>"
```

Use `yt spec ... -` to read the complete text from stdin. Never patch only part of an existing SPEC or let implementation define requirements.

For questions and disputes, run `yt next --role architect --queue IT`, then claim. The output contains the current specification and latest `QUESTION:`/`DISPUTE:`. Answer with signed `ANSWER:` or `DECISION:`. For an accepted dispute, publish the revised full SPEC and say so; for a rejected one, explain and make the final decision. Route back to `open` + `role:developer`, preserving all other tags.

An architectural review checks decisions against SPEC, ARCHITECTURE, and recorded decisions; it is not a code review and adds no `review:<name>` tag. Do not close implementation merely because an architectural review passed. If post-closure changes are needed, add `REWORK:`, reopen, and route to `open` + `role:developer`.
