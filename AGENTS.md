# Rules for implementation agents

Every agent reads this file before working in the repository. This file is an
index: the full rule lives behind each link. Hard limits in one line each:

1. English only in code, comments, commit messages, tests, and docs. The only
   exception is `README.md` (human-facing, Russian).
2. Do not add dependencies; do not import `homeassistant` inside
   `custom_components/halltasker/core/`. Details: `docs/rules/project.md`.
3. Touch only the files listed in your task's current specification. Need
   another file — stop and route a question, never improvise.
4. Never change `docs/SPEC.md`, `docs/ARCHITECTURE.md`, or anything under
   `docs/ru/`. Contradictions and missing APIs go to `docs/QUESTIONS.md`.
5. One task, one commit `IT-<N>: <issue summary>`; all checks green first.
6. Subagents are orchestrated only via the contract in
   `docs/prompts/orchestrator.md`.

Full rules:

- Project overview, forbidden actions, releases, question format:
  `docs/rules/project.md`
- Task workflow, tracker CLI, commits: `docs/rules/workflow.md`
- Code style: `docs/rules/style.md`
- Tests and running checks: `docs/rules/testing.md`
- Coordinator and subagent contract: `docs/prompts/orchestrator.md`
