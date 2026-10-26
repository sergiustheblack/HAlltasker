# Questions from agents to the owner

> Language: English only. The format is described in `AGENTS.md`. Append new questions at the end. Do not delete closed ones.

## Q-1 (docs) — closed 2026-10-26
Answer: option 1, with one correction. Checked in the installed HA 2026.9.4: `probatio==0.11.4` is a dependency and `helpers/config_validation.py` imports both libraries, but `voluptuous` is **not** an alias of probatio — it is the real package (`voluptuous==0.16.0`), pulled in through `annotatedyaml` and `hass_nabucasa`, and ~2000 core files still import it. SPEC §8, ARCHITECTURE §7 and RESEARCH §1 are updated (v1.1). `schema.py` stays on voluptuous; re-check on every HA upgrade. The dev-docs URL and `TodoItem.completed` are fixed in RESEARCH §1 and ARCHITECTURE §4.
Context: link verification of external sources (2026-10-25) against docs/SPEC.md §8 (risk table), docs/ARCHITECTURE.md §7, docs/RESEARCH.md §1.
Problem: all three docs state that HA moves from voluptuous to probatio in 2026.11 (future). In fact, per the HA contributors blog (2026-09-30) and the installed homeassistant==2026.9.4 (which requires probatio==0.11.4), probatio already shipped in 2026.9. The voluptuous API keeps working in 2026.9 through a compatibility alias, so the planned `schema.py` on voluptuous is unaffected.
Options: 1) Update the three docs to say "probatio shipped in 2026.9; voluptuous API still works via compatibility alias". 2) Keep the docs as is and note the discrepancy here only.
Impact: none on the code; documentation accuracy only. Also found during the same check: the dev-docs link https://developers.home-assistant.io/docs/core/entity/todo/ now redirects to contributors.home-assistant.io, and TodoItem gained a `completed` field not covered by the canonical model (MVP scope is unaffected).

## Q-2 (T-23) — closed 2026-10-26
Answer: option 1. `CYCLE_TIMEOUT_SECONDS = 120` in `const.py`, caught in the coordinator as `RunResult(ok=False, error="cycle timeout")`. Interruption is safe because the store is saved after every action and an interrupted `create` is picked up by orphan matching. ARCHITECTURE §8 ("Cycle timeout"), SPEC FR-9.4, T-23 updated. The same T-23 now also includes the chained run of the other pairs of a written node (ARCHITECTURE §8 "Chained run", SPEC FR-12.6), which answers your star-latency note: the latency becomes the 2-second debounce per hop instead of one interval per hop.
Context: review of architecture v1.1 (2026-10-26). The coordinator serializes all pairs with one global lock (§8), and `async_run_pair` awaits the engine while holding the lock.
Problem: a hanging `todo.*` service call (a stuck CalDAV handler, an integration without internal HTTP timeouts) holds the global lock for an unbounded time and stalls every pair, including pairs whose nodes are healthy.
Options: 1) Wrap `engine.run_pair` in `asyncio.timeout(...)` in the coordinator (a constant in `const.py`, e.g. `CYCLE_TIMEOUT_SECONDS = 120`); a timeout becomes a normal `RunResult(ok=False, error="cycle timeout")`. No architecture changes beyond §8. 2) Keep as-is and rely on the timeouts inside the target integrations.
Recommendation: option 1; natural place is T-23.

## Q-3 (T-22/T-30) — closed 2026-10-26
Answer: neither option as written. Hash-only snapshots lose `status` and `due`, which are needed to reason about downgrade and echo. Use the standard HA helper: `async_redact_data(data, {"title", "description"})` from `homeassistant.components.diagnostics` on both `store` and `results`. Texts become `**REDACTED**`, hashes, statuses and dates stay. ARCHITECTURE §10, SPEC FR-10.4, T-22 updated. Your orphan-matching note is recorded as a known limitation in SPEC FR-8.4; no change.
Context: review of architecture v1.1. `diagnostics.py` exports `"store": link_store.to_dict()` (§10), and `Link.to_dict()` embeds full snapshots (`data` with `title`, `description`).
Problem: the diagnostics file then contains the user's task texts. There are no secrets by construction (FR-10.4 holds), but task content is personal data the user may not expect in a file they upload to a bug report.
Options: 1) Keep full snapshots (matches v1.0 behavior and helps debugging). 2) Export snapshots as `{"hash": ...}` only, dropping `data` from the diagnostics copy.
Recommendation: option 2; the hashes are enough to reason about change detection in a bug report.
