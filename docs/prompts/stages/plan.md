# Stage: plan — turn the context pack into an implementation plan

Coordinator keeps after this stage: the issue key and the path
`/tmp/halltasker/__ISSUE__/plan.md`.

On failure (plan needs a file outside the whitelist): stop and report to the
owner.

## Subagent prompt

> TASK: Write the implementation plan for issue __ISSUE__.
>
> READ: `/tmp/halltasker/__ISSUE__/spec.md` only. The spec pack already
> contains the task spec, the file whitelist, and the referenced document
> sections.
>
> RULES: this prompt's READ list is exhaustive. If you need anything beyond
> it, delegate to a further subagent with a prompt in the same shape (TASK,
> READ, RULES, MAY TOUCH, OUTPUT) instead of doing it yourself.
>
> MAY TOUCH: nothing in the repository. Write only to
> `/tmp/halltasker/__ISSUE__/plan.md`.
>
> OUTPUT: `/tmp/halltasker/__ISSUE__/plan.md` containing:
> 1. Implementation steps in order, each one small enough to write without
>    holding the whole codebase in memory.
> 2. The files that will be created or edited — a subset of the whitelist in
>    the spec pack, nothing else.
> 3. The list of tests to write, one per behavior of the spec's "Done when".
> Done when the file exists and every "Done when" item maps to a step or a
> test.
