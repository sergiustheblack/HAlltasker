# Task workflow

Read `docs/TRACKER.md` and only the file for your assigned role:
`TRACKER.developer.md`, `TRACKER.architect.md`, or `TRACKER.reviewer.md`.
Take work with `yt next` and `yt claim`; commit as `IT-<N>: <issue summary>`.

The issue's `role:*` tag defines your role for that issue. `agent:<name>` and
`review:<name>` record participation for statistics; they do not assign work.
Code review is optional unless the current specification says
`Code review: required`.

## Order of work on a task

0. If you have not yet been given a name by the owner, ask: "What name should
   I use in tracker tags, comment signatures and my branch?" Wait for the
   answer before doing anything else (see `docs/TRACKER.md`).

1. Claim the lowest available Tracker issue for your role. The claim output
   provides the current specification and the role context.
2. Read the sections of `docs/ARCHITECTURE.md` named in the current
   specification. Do not change signatures and names from the architecture.
3. Create and change only the files listed in the current specification. If
   you need another file, stop and route a `QUESTION:`/`DISPUTE:` comment to
   the architect as described in your role file. A reopened issue's latest
   `REWORK:` comment gives the reason.
4. Write the code and the tests of the task.
5. Run the checks — see `docs/rules/testing.md`. All checks must finish
   without errors.
6. Make one commit with the message `IT-<N>: <issue summary>`, then finish or
   route the issue with `yt done` as described in your role file.
