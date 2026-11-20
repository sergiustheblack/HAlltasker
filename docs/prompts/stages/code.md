# Stage: code — implement the plan

Coordinator keeps after this stage: the issue key and the list of files the
subagent reports as changed.

On failure (implementation needs a file outside the plan, or a spec point is
contradictory): stop and report to the owner.

## Subagent prompt

> TASK: Implement issue __ISSUE__ according to the plan.
>
> READ: `/tmp/halltasker/__ISSUE__/spec.md`, then
> `/tmp/halltasker/__ISSUE__/plan.md`, then `AGENTS.md` and
> `docs/rules/style.md`. No other files.
>
> RULES: this prompt's READ list is exhaustive; read the files in the given
> order. If you need anything beyond it, delegate to a further subagent with
> a prompt in the same shape (TASK, READ, RULES, MAY TOUCH, OUTPUT) instead
> of doing it yourself. Work in small, logically isolated pieces; do not
> hold the whole implementation in memory at once.
>
> MAY TOUCH: only the implementation (non-test) files listed in the plan.
> If you believe another file is needed, stop and say so — never improvise
> or edit outside the list.
>
> OUTPUT: the code itself, plus a one-line report listing every file you
> created or changed. Do not write tests in this stage. Do not commit.
> Done when every implementation step of the plan is done.
