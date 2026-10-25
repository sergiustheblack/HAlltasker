# HAlltasker — link verification report (2026-10-25)

Scope: every external link cited in `docs/RESEARCH.md`, `docs/SPEC.md` and `docs/ARCHITECTURE.md`.
Method: each URL was fetched and compared against the claim our docs make; GitHub repos/issues
were checked for current state (open/closed, archived, last activity). Related contradiction in
our own docs is recorded as Q-1 in `docs/QUESTIONS.md`.

Verdicts: **OK** (claim holds), **OUTDATED** (page no longer supports the claim as written),
**BROKEN**, **IRRELEVANT**.

## 1. Yandex

| # | Link | Verdict | Evidence |
|---|---|---|---|
| 1 | [AlexxIT/YandexStation](https://github.com/AlexxIT/YandexStation) | OK | Active (push 2026-10-22, release v3.22.3 2026-10-13). `rpc.alice.yandex.ru/gproxy/get_alarms`, `create_alarm`, `change_alarm`, `cancel_alarms`, `iot.quasar.yandex.ru`, `calendar.py`, `hass/todo_list.py`, `hass/shopping_list.py` all verified in source today. No reminders anywhere; [issue #587 "Add reminders support"](https://github.com/AlexxIT/YandexStation/issues/587) open since 2024-12-15 with 0 comments. |
| 2 | [iphones.ru article](https://iphones.ru/iNotes/kak-sozdavat-napominaniya-na-iphone-pri-pomoshchi-alisy-ot-yandeks-12-29-2021) | OK | Loads; 2021-12-29 article states verbatim that «Напомни купить хлеб завтра» produced a matching entry in iPhone Reminders via Yandex CalDAV. Historical anecdote, accurately supported. |
| 3 | [qna.habr.com/q/637480](https://qna.habr.com/q/637480) | **OUTDATED** | Page loads, but the >3-year-old answers do not describe our claim ("partly as events, partly as to-do items, date reminders off to the side"). One answer points to the Yandex Calendar to-do sidebar; the other says reminders are stored locally. Only the "to-do items" half is supported. **Action: reword or re-source the claim.** |
| 4 | [dext0r/ha-yandex-station-intents](https://github.com/dext0r/ha-yandex-station-intents) | OK | Not archived, pushed 2026-10-19. Intercepts phrases spoken to Station/Alice and emits HA events. |
| 5 | [dext0r/yandex_smart_home](https://github.com/dext0r/yandex_smart_home) | OK | Not archived, pushed 2026-09-02. Exposes HA devices to Yandex (HA → Alice); no calendar/reminder/to-do reading. |
| 6 | [Yandex Calendar CalDAV setup](https://yandex.ru/support/calendar/common/sync/sync-desktop.html) | OK | Server `https://caldav.yandex.ru`, full e-mail login, app password — confirmed. Nit: the app-password option is now labeled just «Календарь», not «Календарь CalDAV». |
| 7 | [tasks/tasks#1537](https://github.com/tasks/tasks/issues/1537) | OK | Still **open** (created 2021-06-19, 0 comments, never closed). `todos-*` collections and `PRODID:-//Yandex LLC//Yandex Calendar//EN` quoted verbatim; auto-discovery breakage described. Caveat: the literal string "VTODO" does not appear in the issue body (inferred from the .ics excerpt). |
| 8 | [yaboard wiki](https://wiki.yaboard.com/w/%D0%94%D0%B5%D0%BB%D0%B0,_%D0%BD%D0%B0%D0%BF%D0%BE%D0%BC%D0%B8%D0%BD%D0%B0%D0%BD%D0%B0%D1%8F,_%D0%B1%D1%83%D0%B4%D0%B8%D0%BB%D1%8C%D0%BD%D0%B8%D0%BA%D0%B8_%D0%B8_%D1%82%D0%B0%D0%B9%D0%BC%D0%B5%D1%80%D1%8B) | OK (RU-only) | Geo-blocked from non-Russian networks (all fetchers time out); the wiki itself is alive and the article is indexed. Full content could not be re-verified from outside RU. **Note "RU-only access" next to the link.** |
| 9 | [Yandex 360: managing with Alice](https://yandex.ru/support/yandex-360/customers/calendar/web/ru/alice) | OK | Documents voice commands for events and the to-do list («добавь в список дел поход в магазин»). |
| 10 | [Yandex 360: to-do list](https://yandex.ru/support/yandex-360/customers/calendar/web/ru/reminders/to-do) | OK | «Добавь в список дел…» commands; a task = title + optional срок, no time-of-day — matches "date without time". |
| 11 | [Alice reminder commands](https://alice.yandex.ru/support/ru/station/skills/reminder) | OK | Reminder phrases, recurring limited to daily/weekly/monthly/yearly, «Перечисли напоминания». |
| 12 | [Alice reminder settings](https://alice.yandex.ru/support/ru/station/settings/reminder) | OK | Reminders listed/edited in «Дом с Алисой» → Настройки → Продуктивность → Напоминания. |

Extra check: **"There is no public reminders API" still holds as of 2026-10-25.** YandexStation
release notes v3.19.1 (2025-06-20) … v3.22.3 (2026-10-13) mention напоминания zero times; #587 is
still open; the only known workaround is voice-phrase interception, which is not an API.

## 2. Apple Reminders

| # | Link | Verdict | Evidence |
|---|---|---|---|
| 1 | [2Do FAQ](https://www.2doapp.com/docs/faqs/data-deleted-after-ios-13-catalina-upgrade/) | OK | "With the Reminders upgrade, Apple moved those lists into a private Reminders sync store", separate from iCloud CalDAV task lists. (Page says "private sync store", not "CloudKit"; CloudKit attribution comes from other sources.) |
| 2 | [Apple discussions thread](https://discussions.apple.com/thread-253490589) | OK (bot-walled) | "Reminders no more syncing through CalDAV" (Dec 2021); matches the claim, but Apple blocks automated access (Security Verification) — note that the link is fragile for re-verification. |
| 3 | [lobehub icloud-reminders-mcp](https://lobehub.com/mcp/lingnik-icloud-reminders-mcp) | OK (half) | CalDAV half confirmed: `caldav.icloud.com` VTODO, app-specific password, "Only reminder lists that were never 'upgraded' … remain reachable. On some accounts that is zero lists." The iPhone-add-CalDAV-account / "third-party lists" half is **not** on this page (source: heywoodlh.io instead). URL now redirects to market.lobehub.com. |
| 4 | [heywoodlh.io cross-platform iCloud](https://heywoodlh.io/cross-platform-icloud/) | OK | 2026-01-21; "you must configure an external CardDav/CalDav account for iCloud on iOS" + app-specific password. |
| 5 | [HA community: apple-reminders/687188](https://community.home-assistant.io/t/apple-reminders/687188) | OK | Open request since 2024-02; still unimplemented ("Apple unfortunately doesn't provide a Cloud API for Reminders"); latest post (2025-10) is a third-party workaround. |
| 6 | [HA community: WTH apple-reminders-in-todo/802169](https://community.home-assistant.io/t/wth-apple-reminders-in-todo/802169) | OK (dead-ended) | Real WTH thread (2024-11-30), but HA founder closed the direction the same day ("not meant to request new integrations"); the tracking thread is #5. |
| 7 | [simplyexplained.com](https://simplyexplained.com/blog/integrate-home-assistant-with-apple-reminders/) | **OUTDATED** | 2022-07-27 article describes the **reverse** flow: HA automations write todos into an `input_text` and an iOS Shortcut pulls them **into Apple Reminders**. Nothing flows from Reminders into HA. **Action: reword the claim ("push HA todos into Reminders via Shortcuts") or drop the link.** |
| 8 | [sabbaken/apple-reminders-sync-to-home-assistant](https://github.com/sabbaken/apple-reminders-sync-to-home-assistant) | OK | Live, not archived; created 2026-07-30, last push 2026-10-19. Mac script doing two-way sync via an EventKit helper. Caveat: 4 stars, small adoption. |
| 9 | [HA community: caldav-and-to-do/652642](https://community.home-assistant.io/t/caldav-and-to-do/652642) | OK | Confirms partial exposure: only stale placeholder lists of upgraded Reminders appear ("this list has been upgraded"), items missing/undeletable (412); thread ends unresolved (2024-09). |

Extra check: **nothing changed by late 2026.** Upgraded Reminders lists are still unreachable over
CalDAV ([BusyCal FAQ](https://www.busymac.com/docs/faqs/112990-reminders-in-ios-13-and-macos-catalina-drops-support-for-caldav),
2Do FAQ, [Lingnik README](https://github.com/Lingnik/icloud-reminders-mcp) July 2026). The HA
Companion app still has no Reminders access; the only 2026 companion-app news (2026-07-07) is about
dropping iOS 15/watchOS 8/macOS 11.

## 3. Google

| # | Link | Verdict | Evidence |
|---|---|---|---|
| 1 | [9to5google 2025-10-14](https://9to5google.com/2025/10/14/google-keep-tasks-reminders-rolling-out/) | OK | Keep → Tasks migration rolling out Oct 2025. Nit: the Assistant-reminders half of our "2025–2026" claim actually started earlier (ongoing since 2023). |
| 2 | [support.google.com/tasks/answer/16540694](https://support.google.com/tasks/answer/16540694?hl=en) | OK | Official Keep-reminders-in-Tasks page (2nd half of 2025, "From Keep" labels, 100k-task cap). Covers Keep only, not Assistant — our phrasing slightly overstates this single page. |
| 3 | [tasks.org sync page](https://tasks.org/docs/sync_google_tasks/) | OK | "Time of day not supported by Google Tasks API"; recurrence "Not available through Google Tasks API". Page is old (2019 framing) but still factually correct. |
| 4 | [Tasks API reference](https://developers.google.com/workspace/tasks/reference/rest) | OK | `Task.due` is an RFC 3339 timestamp with "Only date information is recorded; the time portion … is discarded"; no recurrence fields exist. Could cite `/rest/v1/tasks` directly for precision. |

Extra check: **no 2026 API changes.** [Issue 36759725](https://issuetracker.google.com/issues/36759725)
("full API support for due time and repeat") is still the standing feature request; third-party
apps still cannot see/set recurrence ([Tasksboard guide, Oct 2026](https://tasksboard.com/blog/google-tasks-recurring-tasks-guide)).

## 4. Home Assistant

| # | Link | Verdict | Evidence |
|---|---|---|---|
| 1 | [developers.home-assistant.io/docs/core/entity/todo/](https://developers.home-assistant.io/docs/core/entity/todo/) | **OUTDATED URL** | 301-redirects to [contributors.home-assistant.io/core/entities/todo/](https://contributors.home-assistant.io/core/entities/todo/). TodoItem now also has a `completed` field (not in our canonical model; MVP scope unaffected). Feature names, the 5 services, and bit values 1/2/4/8/16/32/64 confirmed byte-for-byte against the installed homeassistant==2026.9.4. |
| 2 | [caldav integration](https://www.home-assistant.io/integrations/caldav/) | OK | To-do lists, iCloud, "updated roughly every 15 minutes" — confirmed. Two nits: "due datetime supported" is not stated on the page (comes from code); the page says YAML setup "does not support to-do lists" (UI setup required) — worth a README note. |
| 3 | [google_tasks integration](https://www.home-assistant.io/integrations/google_tasks/) | OK | "Only supports viewing or setting a task due date. A task due time is not supported." |
| 4 | [local_todo integration](https://www.home-assistant.io/integrations/local_todo/) | OK | Exists; all 7 feature flags set in the 2026.9.4 source (`components/local_todo/todo.py`). |

Extra checks:
- **`todo.add_item` still returns no uid/response in 2026.9 and 2026.10** (handler returns `None`;
  only `get_items` is registered with `supports_response`). The re-read-and-match-by-content
  workaround (SPEC FR-1.4) remains valid; no PR found that would change it.
- **Probatio already shipped in HA 2026.9** — see [contributors blog, 2026-09-30](https://contributors.home-assistant.io/blog/2026/09/30/probatio-validation-engine).
  Our docs (SPEC §8, ARCHITECTURE §7, RESEARCH §1) say this happens in 2026.11, which is wrong.
  `homeassistant==2026.9.4` requires `probatio==0.11.4` and aliases `voluptuous` to it, so the
  planned voluptuous-based `schema.py` keeps working. Recorded as **Q-1** in `docs/QUESTIONS.md`.

## 5. Summary for the architect

Load-bearing design assumptions — all verified, no code impact:

- No public Yandex reminders API (as of 2026-10-25).
- `todo.add_item` gives no uid; re-read matching is required.
- Google Tasks API: date-only due, no recurrence.
- HA CalDAV: ~15-minute refresh, iCloud, todo lists (UI setup only).
- Upgraded Apple Reminders lists are invisible over CalDAV; companion app has no Reminders access.

Documentation fixes worth making (owner's decision — SPEC/ARCHITECTURE are frozen for agents):

1. RESEARCH §1 Yandex: reword/re-source the qna.habr claim (OUTDATED).
2. RESEARCH §1 Apple: reword the simplyexplained claim (direction inverted) and re-source the
   iPhone-CalDAV-account half of the lobehub claim.
3. RESEARCH §1 HA: correct "2026.11 moves to probatio" → "shipped in 2026.9" (Q-1); update the
   todo dev-docs URL to contributors.home-assistant.io.
4. Access notes: Apple discussions thread is bot-walled; yaboard wiki is RU-only.
5. Minor: Yandex app password now labeled «Календарь»; WTH thread was closed on arrival;
   "2025–2026" Google migration phrasing is loose for the Assistant half.

## 6. Addendum (2026-10-26): Yandex shopping list workaround gist

Owner asked to evaluate [DivanX10's gist "Список покупок. Home Assistant + Яндекс"](https://gist.github.com/DivanX10/9f7bb76cd08516553b8a92dea278afd6).

What it does: voice access to the HA **Shopping List** through YandexStation — a `command_line`
sensor parses `.shopping_list.json` from disk; automations on `yandex_intent` phrases reply via
`tts.yandex_station_say`; synchronization with the Yandex skill runs through YandexStation's
speech bridge (`media_player.play_media` with `media_content_type: shopping_list`,
`media_content_id: update` — the `hass/shopping_list.py` feature already cited in RESEARCH §1).

Applicability to HAlltasker:

- **The file-reading half is obsolete for us.** Shopping List now exposes a `todo.*` entity;
  our `ha_todo` plugin already syncs it like any other node (capabilities drop due/description
  automatically). Pairing `todo.shopping_list` ↔ iCloud/Google/local works with zero new code.
- **The Yandex half is the same dead end as before.** The Yandex "Список покупок" skill has no
  API; the only bridge is YandexStation's speech round-trip — exactly the "existing YandexStation
  bridge" named in SPEC §2 as out of MVP. The gist's own comments confirm it is fragile:
  races between the 60 s sensor and Alice's update can wipe the list, some product names
  silently fail, rules are one-directional-ish, and the two platforms (Yandex skill vs HA list)
  stay separate. The author says he barely uses it now.
- **Recommendation:** do not put any of this into the core. At most a README recipe for
  after-MVP: HAlltasker pair on the HA side + YandexStation speech bridge on the Yandex side,
  with the fragility warning. If we ever want reliability there, the route is an external PR to
  YandexStation, same as for reminders.
