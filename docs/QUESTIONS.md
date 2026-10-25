# Questions from agents to the owner

> Language: English only. The format is described in `AGENTS.md`. Append new questions at the end. Do not delete closed ones.

## Q-1 (docs) — closed 2026-10-26
Answer: option 1, with one correction. Checked in the installed HA 2026.9.4: `probatio==0.11.4` is a dependency and `helpers/config_validation.py` imports both libraries, but `voluptuous` is **not** an alias of probatio — it is the real package (`voluptuous==0.16.0`), pulled in through `annotatedyaml` and `hass_nabucasa`, and ~2000 core files still import it. SPEC §8, ARCHITECTURE §7 and RESEARCH §1 are updated (v1.1). `schema.py` stays on voluptuous; re-check on every HA upgrade. The dev-docs URL and `TodoItem.completed` are fixed in RESEARCH §1 and ARCHITECTURE §4.
Context: link verification of external sources (2026-10-25) against docs/SPEC.md §8 (risk table), docs/ARCHITECTURE.md §7, docs/RESEARCH.md §1.
Problem: all three docs state that HA moves from voluptuous to probatio in 2026.11 (future). In fact, per the HA contributors blog (2026-09-30) and the installed homeassistant==2026.9.4 (which requires probatio==0.11.4), probatio already shipped in 2026.9. The voluptuous API keeps working in 2026.9 through a compatibility alias, so the planned `schema.py` on voluptuous is unaffected.
Options: 1) Update the three docs to say "probatio shipped in 2026.9; voluptuous API still works via compatibility alias". 2) Keep the docs as is and note the discrepancy here only.
Impact: none on the code; documentation accuracy only. Also found during the same check: the dev-docs link https://developers.home-assistant.io/docs/core/entity/todo/ now redirects to contributors.home-assistant.io, and TodoItem gained a `completed` field not covered by the canonical model (MVP scope is unaffected).
