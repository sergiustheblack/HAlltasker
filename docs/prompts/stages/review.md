# Stage: review — compare the diff against the spec

Coordinator keeps after this stage: the issue key and the verdict (APPROVED
or the numbered REWORK list).

On failure (review verdict is REWORK): re-read `docs/prompts/stages/plan.md`
or `docs/prompts/stages/code.md`, add the REWORK list to the prompt after
"On failure (previous review):", and launch again.

## Subagent prompt

> TASK: Review the uncommitted changes for issue __ISSUE__.
>
> READ: `/tmp/halltasker/__ISSUE__/spec.md`, then `AGENTS.md`, then
> `docs/TRACKER.reviewer.md`. No other repository files. Use `git status`
> and `git diff` to see the changes.
>
> RULES: this prompt's READ list is exhaustive. Compare the diff against the
> spec pack: every changed file must be in the whitelist, every "Done when"
> item must be implemented and tested, and the rules referenced from
> `AGENTS.md` must hold. Do not edit any code.
>
> MAY TOUCH: nothing. Write only to `/tmp/halltasker/__ISSUE__/review.txt`.
>
> OUTPUT: `/tmp/halltasker/__ISSUE__/review.txt` containing either the line
> `APPROVED` or a numbered list `REWORK:` items, each one exact and
> actionable (file, what is wrong, what to do).
> Done when the verdict is written.
