# Developer Tracker flow

Read `docs/TRACKER.md` first. Canonical role: `role:developer`; accept legacy `role:executor` without migrating it.

1. Run `yt next --role developer --queue IT`, then `yt claim <KEY> --agent <name>`. The claim output contains the current specification and latest `REWORK:`; this is sufficient context for normal work.
2. Read the architecture sections and change only the files named by the current specification. Do not change the specification or publish `SPEC:` comments.
3. For a blocker, stop instead of guessing. Use `yt question <KEY> --agent <name> "<what was done; problem; options; proposal>"`. For a dispute, add a signed `DISPUTE:` comment and route to `needInfo` + `role:architect`. Wait for the answer before continuing.
4. Implement, test, and make one commit: `IT-<N>: <issue summary>`. The usual checks are `ruff check . && ruff format --check . && pytest -q`, unless the specification says otherwise.
5. After a successful commit run `yt done <KEY> --hash <hash> --agent <name>`. It adds `DONE:` and either closes with `fixed` or routes to `open` + `role:reviewer` when the current specification contains `Code review: required`.

For rework, address every point in the latest `REWORK:`, commit again, and run `yt done` again. Preserve all attribution tags. Only the developer closes work that does not require review.
