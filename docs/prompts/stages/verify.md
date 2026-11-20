# Stage: verify — run the checks

Coordinator keeps after this stage: the issue key and the verdict (green or
the verbatim failing output).

On failure (any check failed): re-read `docs/prompts/stages/code.md` or
`docs/prompts/stages/tests.md`, add the quoted failing output to the prompt
after "On failure (previous run):", and launch again. Repeat until green.

## Subagent prompt

> TASK: Run the project checks and report the result.
>
> READ: `AGENTS.md` (index only).
>
> RULES: this prompt's READ list is exhaustive. Run exactly:
> `source ./.venv/bin/activate && ruff check . && ruff format --check . && pytest -q`
> Do not fix anything.
>
> MAY TOUCH: nothing. Write only to `/tmp/halltasker/__ISSUE__/verify.txt`.
>
> OUTPUT: `/tmp/halltasker/__ISSUE__/verify.txt` with the verbatim command
> output, ending with one line: `VERDICT: GREEN` or `VERDICT: RED`.
> Done when the verdict line is written.
