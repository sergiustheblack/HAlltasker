# Coordinator operating instructions

You are the coordinator for the HAlltasker repository. You write no code, run
no shell commands, and use no external tools yourself. Your only primitives
are: read/write files, and launch subagents. Every action is a subagent with
an explicit prompt.

## Profile selector — pick ONE and follow only that profile

**Profile S — small-context model** (short context window, may skip long
files, prone to improvising): follow this entire document exactly. The
file-based handoffs, read restrictions, and per-stage subagents are mandatory
for you — they compensate for what your context cannot hold.

**Profile L — capable model** (large context, reads and retains all
instructions): follow only the "Hard stops" and "Mandatory for both profiles"
parts of this document. In addition:
- Keep the spec, plan, and check results in your own context; skip the
  intermediate files and the `/tmp/halltasker/` directory entirely.
- You may read any project file; the whitelist restricts only what you edit.
- You may write code and its tests in one pass; run a separate review pass
  (yourself or a fresh subagent) comparing `git diff` against the spec before
  committing.

## Mandatory for both profiles

- Verify loop: `ruff check . && ruff format --check . && pytest -q` (venv
  activated) is green before any commit; failures go back to implementation
  with the output quoted.
- Review before commit: the diff is compared against the spec's file whitelist
  and "Done when" list; only then the single commit `IT-N: <issue summary>`.
- One actor never both writes the code and alone declares it reviewed.
- Hard stops below apply unconditionally.

## Context you are allowed to keep (Profile S)

Per issue, at most: the issue key, the stage you are at, the paths of its
context pack and plan, and the file whitelist from the spec. Everything else
lives in files and is read by the subagent that needs it. When a stage
finishes, keep only its output path.

## Subagent prompt contract — mandatory in every subagent prompt (Profile S;
also use it for any subagent you launch under Profile L)

1. TASK: one unambiguous goal.
2. READ: exact paths the subagent must read before starting, named down to the
   section (e.g. `docs/ARCHITECTURE.md §2`, not the whole file). `AGENTS.md`
   is always required, plus the stage-specific rules file. The subagent may
   not read any other project file. When it is given a source document
   instead of an extract, it locates the named section by its heading and
   reads only that section plus the document's table of contents, following
   explicit cross-references as needed — never the whole document by default.
3. RULES: this contract applies to the subagent itself. If it needs shell,
   the tracker CLI, or any research, it delegates to a further subagent
   instead of doing it itself, with the same 5-block prompt.
4. MAY TOUCH: explicit list of paths it may create or edit. If it believes
   another file is needed, it must stop and return a question — never
   improvise, never edit outside the list.
5. OUTPUT: the exact output file path and the definition of done.

## Working directory for intermediate files (Profile S only)

Never write intermediate files inside the repository. Use a per-issue
directory outside it, e.g. `/tmp/halltasker/<ISSUE>/`, and delete that
directory after the issue is closed. Profile L keeps intermediates in its own
context instead.

## Pipeline for one issue (IT-N)

The stages below describe the Profile S mechanics (each stage is a subagent,
handoff via files). Profile L runs the same stages in its own context without
files, keeping the mandatory parts from above.

Stage 0 fetch — subagent reads `docs/TRACKER.md`, runs `yt show IT-N`, writes
  `/tmp/halltasker/IT-N/spec.md`: the current spec verbatim, the file
  whitelist, and the list of doc sections the spec names. The subagent also
  extracts those named sections from `docs/ARCHITECTURE.md` (and any other
  named document) into the pack, each from its heading to the next heading of
  the same level, plus the document's table of contents (all headings) so
  later agents can resolve cross-references without reading the source.
Stage 1 plan — subagent reads the spec pack and the named doc sections,
  writes `/tmp/halltasker/IT-N/plan.md`: implementation steps, files (from the
  whitelist only), and the test list.
Stage 2 code — subagent reads the spec pack, the plan, and
  `docs/rules/style.md`; writes the code. Then a separate subagent writes the
  tests, reading `docs/rules/testing.md`. No commit yet.
Stage 3 verify — subagent activates the venv and runs exactly:
  `source ./.venv/bin/activate && ruff check . && ruff format --check . && pytest -q`
  Writes the verbatim result to `/tmp/halltasker/IT-N/verify.txt`. On failure,
  go back to stage 1 or 2 with the failing output quoted. Repeat until green.
Stage 4 review — subagent reads `docs/TRACKER.reviewer.md`, runs `git status`
  and `git diff`, compares the diff against the spec pack (whitelist, "Done
  when" list, rules from `AGENTS.md`). Writes `APPROVED` or a numbered REWORK
  list to `/tmp/halltasker/IT-N/review.txt`. It must not edit code. On
  REWORK, go back to stage 1.
Stage 5 finish — subagent reads `docs/TRACKER.md` and the role file, makes the
  single commit `IT-N: <issue summary>`, then runs the tracker flow
  (claim/done or REWORK comment + route). Then delete `/tmp/halltasker/IT-N/`.

## Hard stops

- A subagent reports it needs a file outside the whitelist: stop the pipeline
  and report to the owner; do not proceed.
- The spec is contradictory or an API is missing: write the question per
  `docs/rules/project.md` (QUESTIONS.md format) and stop.
- Never let one subagent both write the code and declare it reviewed.
