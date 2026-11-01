# Reviewer Tracker flow

Read `docs/TRACKER.md` first. Role: `role:reviewer`.

1. Run `yt next --role reviewer --queue IT`, then `yt claim <KEY> --agent <name>`. The output contains the current specification and the latest `REWORK:` and `DONE:` in chronological order. Do not print full history unless needed.
2. Review the committed changes against the current specification. Do not edit requirements or publish `SPEC:` comments.
3. If accepted, add a signed `APPROVED:` comment and close with `fixed`. Only the reviewer closes work whose current specification says `Code review: required`.
4. If changes are needed, add a signed `REWORK:` with exact actionable points, then route to `open` + `role:developer`, preserving all attribution and other tags.

A post-closure code review adds `review:<name>`. If no changes are needed, leave the issue closed. Otherwise add `REWORK:`, reopen, route to `open` + `role:developer`, and follow the normal rework flow. Put unrelated defects in a new linked issue.
