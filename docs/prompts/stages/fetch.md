# Stage: fetch — produce the context pack for issue __ISSUE__

Coordinator keeps after this stage: the issue key and the path
`/tmp/halltasker/__ISSUE__/spec.md`.

On failure (tracker unreachable, spec missing): stop and report to the owner.

## Subagent prompt

> TASK: Produce the context pack for tracker issue __ISSUE__.
> Run `yt show __ISSUE__` (CLI rules: read `docs/TRACKER.md` first).
>
> READ: `docs/TRACKER.md`. No other repository files.
>
> RULES: this prompt's READ list is exhaustive. If you need anything beyond
> it, delegate to a further subagent with a prompt in the same shape (TASK,
> READ, RULES, MAY TOUCH, OUTPUT) instead of doing it yourself.
>
> MAY TOUCH: nothing in the repository. Write only to
> `/tmp/halltasker/__ISSUE__/spec.md`.
>
> OUTPUT: `/tmp/halltasker/__ISSUE__/spec.md` containing, in this order:
> 1. The current spec verbatim (the issue description, or the latest comment
>    starting with `SPEC:` if one exists — that is a complete replacement).
> 2. The file whitelist from the spec (the "Files:" line).
> 3. The document sections the spec names. For each named section of
>    `docs/ARCHITECTURE.md` (or any other named document): extract it from
>    its heading to the next heading of the same level, and copy it here
>    verbatim. Then append the document's table of contents (all headings),
>    so later agents can resolve cross-references without opening the source.
> Done when the file exists and contains all three parts.
