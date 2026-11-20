# Stage: tests — write the test suite

Coordinator keeps after this stage: the issue key.

On failure (a test needs a file outside the plan): stop and report to the
owner.

## Subagent prompt

> TASK: Write the tests for issue __ISSUE__.
>
> READ: `/tmp/halltasker/__ISSUE__/spec.md`, then
> `/tmp/halltasker/__ISSUE__/plan.md`, then `AGENTS.md` and
> `docs/rules/testing.md`. No other files.
>
> RULES: this prompt's READ list is exhaustive; read the files in the given
> order. If you need anything beyond it, delegate to a further subagent with
> a prompt in the same shape (TASK, READ, RULES, MAY TOUCH, OUTPUT) instead
> of doing it yourself.
>
> MAY TOUCH: only the test files listed in the plan.
>
> OUTPUT: the tests named in the plan's test list, one per behavior of the
> spec's "Done when". Do not change implementation code; if a test exposes
> an implementation bug, report the bug instead of fixing it. Do not commit.
> Done when every test from the plan exists.
