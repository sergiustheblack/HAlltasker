# HAlltasker — research on external systems and stage 0

> Language: English (canonical for agents). Russian version: [docs/ru/RESEARCH.md](ru/RESEARCH.md).

## 1. Constraints of external systems (verified 2026-09/10)

### Yandex Alice

- There is no public reminders API. The HA community uses the private APIs `iot.quasar.yandex.ru` and `rpc.alice.yandex.ru` through [AlexxIT/YandexStation](https://github.com/AlexxIT/YandexStation). YandexStation has alarms (`gproxy/get_alarms`, `create_alarm`, `change_alarm`, `cancel_alarms` → a `calendar` entity) and synchronization of the shopping list with any `todo.*` by sending a text command to the speaker and parsing the reply (`hass/todo_list.py`, `hass/shopping_list.py`). There are no reminders in any form.
- Alice data ends up in Yandex Calendar (Яндекс Календарь): part as events, part as to-do items (дело), and reminders with a trigger date "off to the side" ([iphones.ru](https://www.iphones.ru/iNotes/kak-sozdavat-napominaniya-na-iphone-pri-pomoshchi-alisy-ot-yandeks-12-29-2021), [qna.habr.com](https://qna.habr.com/q/637480)). The author of the iphones.ru article saw «Напомни купить хлеб завтра» (Remind me to buy bread tomorrow) as an entry in iPhone Reminders through Yandex CalDAV.
- Intercepting voice phrases in HA: [dext0r/ha-yandex-station-intents](https://github.com/dext0r/ha-yandex-station-intents). [dext0r/yandex_smart_home](https://github.com/dext0r/yandex_smart_home) works in the opposite direction (HA → Alice) and is not suitable for reading reminders.

### Yandex Calendar CalDAV

- Server `https://caldav.yandex.ru`, login is the full e-mail, the password is an app password for "Календарь CalDAV" (Calendar CalDAV) ([help page](https://yandex.ru/support/calendar/common/sync/sync-desktop.html)).
- To-do items (дело) are stored in the collections `/calendars/<login>@yandex.ru/todos-<id>/` as VTODO, `PRODID:-//Yandex LLC//Yandex Calendar//EN` ([tasks/tasks#1537](https://github.com/tasks/tasks/issues/1537)). Auto-discovery of `calendar-home-set` breaks in some clients.

### Map of Alice entities

| Entity | Phrases | Storage | Access from outside |
|---|---|---|---|
| Reminder (date+time) | «Напомни завтра в 10 утра …» (Remind me tomorrow at 10 am …), «Перечисли напоминания» (List the reminders), «Удали напоминание» (Delete the reminder). Can be set only from the speaker; recurring ones only day/week/month/year | Yandex account; visible in "Дом с Алисой" (Home with Alice) → Productivity (Продуктивность) → Reminders (Напоминания) | Partly through Calendar CalDAV (not confirmed); reliably only through the private API |
| To-do item (дело) (to-do list) | «Добавь в список дел (на сегодня) …» (Add … to the to-do list (for today)), «Удали из списка дел …» (Delete … from the to-do list), «Какие у меня дела в списке дел?» (What items do I have in the to-do list?) | Yandex Calendar (Яндекс Календарь), to-do lists; fields: title + date without time | CalDAV `todos-*` as VTODO |
| Event | «Поставь тренировку на завтра в 9 утра на 40 минут» (Schedule a workout for tomorrow at 9 am for 40 minutes), «Какие встречи сегодня?» (What meetings are there today?) | The main calendar named "Алиса" (Alice) | CalDAV VEVENT; the stock HA CalDAV provides `calendar.*` |
| Shopping list | «Добавь молоко в список покупок» (Add milk to the shopping list), «Попроси Список покупок список» (Ask the "Список покупок" skill for the list) | A separate skill | No API; a bridge in YandexStation through speech |
| Alarm, timer | «Буди меня по субботам в 9» (Wake me up on Saturdays at 9), «Таймер на 45 секунд» (Timer for 45 seconds) | Locally on the speaker | Alarms in YandexStation; out of scope |

Sources: [yaboard wiki](https://wiki.yaboard.com/w/%D0%94%D0%B5%D0%BB%D0%B0,_%D0%BD%D0%B0%D0%BF%D0%BE%D0%BC%D0%B8%D0%BD%D0%B0%D0%BD%D0%B8%D1%8F,_%D0%B1%D1%83%D0%B4%D0%B8%D0%BB%D1%8C%D0%BD%D0%B8%D0%BA%D0%B8_%D0%B8_%D1%82%D0%B0%D0%B9%D0%BC%D0%B5%D1%80%D1%8B), [Managing with Alice](https://yandex.ru/support/yandex-360/customers/calendar/web/ru/alice), [To-do list](https://yandex.ru/support/yandex-360/customers/calendar/web/ru/reminders/to-do), [reminder commands](https://alice.yandex.ru/support/ru/station/skills/reminder), [reminder settings](https://alice.yandex.ru/support/ru/station/settings/reminder).

### Apple Reminders

- Since iOS 13, "upgraded" Reminders lists are stored in private CloudKit and are not visible through CalDAV ([2Do FAQ](https://www.2doapp.com/docs/faqs/data-deleted-after-ios-13-catalina-upgrade/), [Apple Community](https://discussions.apple.com/thread/253490589)).
- `caldav.icloud.com` serves VTODO collections with an app password; on the iPhone, iCloud must be added as a separate CalDAV account, and then the lists are visible in Reminders as "third-party" lists, without tags and smart lists ([icloud-reminders-mcp](https://lobehub.com/mcp/lingnik-icloud-reminders-mcp), [heywoodlh.io](https://heywoodlh.io/cross-platform-icloud/)).
- HA Companion for iOS gives no access to Reminders ([feature request](https://community.home-assistant.io/t/apple-reminders/687188), [WTH](https://community.home-assistant.io/t/wth-apple-reminders-in-todo/802169)). Workarounds: Shortcuts ([simplyexplained](https://simplyexplained.com/blog/integrate-home-assistant-with-apple-reminders/)), a script on a Mac ([sabbaken](https://github.com/sabbaken/apple-reminders-sync-to-home-assistant)), CalDAV partially ([community](https://community.home-assistant.io/t/caldav-and-to-do/652642)).

### Google

- Keep reminders and Assistant reminders were migrated to Google Tasks in 2025–2026 ([9to5google](https://9to5google.com/2025/10/14/google-keep-tasks-reminders-rolling-out/), [support.google.com](https://support.google.com/tasks/answer/16540694?hl=en)).
- The public [Tasks API](https://developers.google.com/workspace/tasks/reference/rest) stores only a date in `due`; the time is discarded; recurrence is unavailable ([Tasks.org](https://tasks.org/docs/sync_google_tasks/)). The Keep API is enterprise-only and has no reminders.

### Home Assistant

- The `todo` domain: `TodoItem(uid, summary, status, due, description)`, `TodoListEntityFeature` bits 1/2/4/8/16/32/64, services `get_items`, `add_item`, `update_item`, `remove_item`, `remove_completed_items` ([dev docs](https://developers.home-assistant.io/docs/core/entity/todo/)). Sources checked for 2026.9.
- Stock integrations: [CalDAV](https://www.home-assistant.io/integrations/caldav/) (refresh ~15 min, iCloud supported, datetime supported), [Google Tasks](https://www.home-assistant.io/integrations/google_tasks/) (no datetime), Local To-do, Shopping List (no due and no description).
- Stable version on 2026-10-05: 2026.9.4, Python ≥ 3.14.2, schemas on voluptuous. The dev branch (2026.11) moves to `probatio`.

## 2. Stage 0: checking Yandex CalDAV

Performed on the owner's account. Required: the login `LOGIN@yandex.ru` and an app password for "Календарь CalDAV" (Calendar CalDAV) (id.yandex.ru → Security (Безопасность) → App passwords (Пароли приложений)). Record the results in §4.

### Step 1. List the collections

```bash
curl -s -u 'LOGIN@yandex.ru:APP_PASSWORD' -X PROPFIND \
  -H 'Depth: 1' -H 'Content-Type: application/xml' \
  --data '<d:propfind xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav"><d:prop><d:displayname/><d:resourcetype/><c:supported-calendar-component-set/></d:prop></d:propfind>' \
  'https://caldav.yandex.ru/calendars/LOGIN@yandex.ru/'
```

Expected: `todos-*` collections with `<c:comp name="VTODO"/>`. Record their href and displayname.

### Step 2. Voice commands

Say the following to the speaker, one minute apart:

1. «Алиса, добавь в список дел на сегодня проверка халлтаскер один» (Alice, add to the to-do list for today "проверка халлтаскер один", i.e. "halltasker check one").
2. «Алиса, напомни сегодня в 23:45 проверка халлтаскер два» (Alice, remind me today at 23:45 "проверка халлтаскер два", i.e. "halltasker check two").

After 2 minutes, for each `todos-*` collection:

```bash
curl -s -u 'LOGIN@yandex.ru:APP_PASSWORD' -X REPORT \
  -H 'Depth: 1' -H 'Content-Type: application/xml' \
  --data '<c:calendar-query xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav"><d:prop><d:getetag/><c:calendar-data/></d:prop><c:filter><c:comp-filter name="VCALENDAR"><c:comp-filter name="VTODO"/></c:comp-filter></c:filter></c:calendar-query>' \
  'https://caldav.yandex.ru/calendars/LOGIN@yandex.ru/todos-XXXX/'
```

For each phrase, record: whether it reached a VTODO; the value of `DUE` (date or date+time, with or without a TZ); whether a `VALARM` is present; whether a `STATUS` is present; the `UID`.

Also check the VEVENT collections with the same REPORT using `comp-filter name="VEVENT"`: whether the reminder went there as an event.

### Step 3. Writing from outside

Create a VTODO through PUT:

```bash
curl -s -u 'LOGIN@yandex.ru:APP_PASSWORD' -X PUT -H 'Content-Type: text/calendar' \
  --data $'BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//HAlltasker//EN\r\nBEGIN:VTODO\r\nUID:halltasker-test-1\r\nDTSTAMP:20261005T120000Z\r\nSUMMARY:проверка халлтаскер три\r\nDUE;VALUE=DATE:20261006\r\nSTATUS:NEEDS-ACTION\r\nEND:VTODO\r\nEND:VCALENDAR\r\n' \
  'https://caldav.yandex.ru/calendars/LOGIN@yandex.ru/todos-XXXX/halltasker-test-1.ics'
```

Ask the speaker «Какие у меня дела?» (What to-do items do I have?) and check whether the item is named. Then change it to `STATUS:COMPLETED` with the same PUT using `If-Match` with the etag, and check whether it disappears for Alice. Then DELETE it and check again.

### Step 4. Stock HA CalDAV

Add the CalDAV integration in HA: URL `https://caldav.yandex.ru`, login, app password. Check that `todo.*` entities appeared for `todos-*` and that `supported_features` = 119 (all except MOVE). Record the entity_id values.

### Step 5. Hypothesis: private reminders API

Only if step 2 showed that a reminder with a time did not reach CalDAV. From a YandexStation session (`self.quasar.session`) run `POST https://rpc.alice.yandex.ru/gproxy/get_reminders` with the `ALARM_HEADERS` headers from `core/yandex_quasar.py`. Record any response other than 404 in full. This is material for an external PR to YandexStation, not for HAlltasker code.

## 3. How the results affect the project

| Result of step 2 | Consequence |
|---|---|
| The to-do item (дело) reached `todos-*` with a DUE date | Scenario C1 from SPEC §7 is feasible through the stock CalDAV. The README describes the phrase «Добавь в список дел» (Add to the to-do list) |
| The reminder with a time reached CalDAV with a DUE datetime | Scenario C2 is feasible. The README describes the phrase «Напомни в …» (Remind me at …) |
| The reminder did not arrive, or arrived without a time | C2 stays experimental; the source is an external PR to YandexStation based on the results of step 5 |

The MVP code does not depend on the results: the Yandex node is an ordinary `todo.*`.

## 4. Stage 0 results

_Not performed. Fill in after running steps 1–5: date, collections, VTODO content for each phrase, behavior on writes from outside, entity_id values in HA._
