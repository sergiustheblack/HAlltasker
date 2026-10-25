# HAlltasker — исследование внешних систем и этап 0

> Язык: русская версия (основной язык для людей). Английская версия: [docs/RESEARCH.md](../RESEARCH.md).

## 1. Ограничения внешних систем (проверено 2026-09/10)

### Яндекс Алиса

- Публичного API напоминаний нет. Сообщество HA использует приватные API `iot.quasar.yandex.ru` и `rpc.alice.yandex.ru` через [AlexxIT/YandexStation](https://github.com/AlexxIT/YandexStation). В YandexStation есть будильники (`gproxy/get_alarms`, `create_alarm`, `change_alarm`, `cancel_alarms` → сущность `calendar`) и синхронизация списка покупок с любой `todo.*` через текстовую команду колонке и парсинг ответа (`hass/todo_list.py`, `hass/shopping_list.py`). Напоминаний нет ни в каком виде; [issue #587 «Add reminders support»](https://github.com/AlexxIT/YandexStation/issues/587) открыт с 2024-12 без активности и является точкой входа для будущего внешнего PR.
- События и дела Алисы попадают в Яндекс Календарь как VEVENT и VTODO (справка Яндекса, см. источники под картой сущностей; один ответ на [qna.habr.com](https://qna.habr.com/q/637480) указывает на боковую панель дел Календаря). Где хранятся напоминания с временем — **не подтверждено**: статья 2021 года на [iphones.ru](https://www.iphones.ru/iNotes/kak-sozdavat-napominaniya-na-iphone-pri-pomoshchi-alisy-ot-yandeks-12-29-2021) видела «Напомни купить хлеб завтра» как запись в iPhone Reminders через CalDAV Яндекса, а другой ответ на qna.habr утверждает, что напоминания хранятся локально. Этап 0 (§2) решает этот вопрос.
- Перехват голосовых фраз в HA: [dext0r/ha-yandex-station-intents](https://github.com/dext0r/ha-yandex-station-intents). [dext0r/yandex_smart_home](https://github.com/dext0r/yandex_smart_home) работает в обратную сторону (HA → Алиса) и для чтения напоминаний не подходит.

### Яндекс Календарь CalDAV

- Сервер `https://caldav.yandex.ru`, логин — полный e-mail, пароль приложения типа «Календарь» (в старых страницах справки — «Календарь CalDAV») ([справка](https://yandex.ru/support/calendar/common/sync/sync-desktop.html)).
- Дела лежат в коллекциях `/calendars/<login>@yandex.ru/todos-<id>/` как VTODO, `PRODID:-//Yandex LLC//Yandex Calendar//EN` ([tasks/tasks#1537](https://github.com/tasks/tasks/issues/1537)). Автодискавери `calendar-home-set` у некоторых клиентов ломается.

### Карта сущностей Алисы

| Сущность | Фразы | Хранение | Доступ извне |
|---|---|---|---|
| Напоминание (дата+время) | «Напомни завтра в 10 утра …», «Перечисли напоминания», «Удали напоминание». Ставится только с колонки; регулярные только день/неделя/месяц/год | Аккаунт Яндекса; видно в «Дом с Алисой» → Продуктивность → Напоминания | Частично CalDAV Календаря (не подтверждено); надёжно только приватный API |
| Дело (список дел) | «Добавь в список дел (на сегодня) …», «Удали из списка дел …», «Какие у меня дела в списке дел?» | Яндекс Календарь, списки дел; поля: название + дата без времени | CalDAV `todos-*` как VTODO |
| Событие | «Поставь тренировку на завтра в 9 утра на 40 минут», «Какие встречи сегодня?» | Основной календарь «Алиса» | CalDAV VEVENT, штатная HA CalDAV даёт `calendar.*` |
| Список покупок | «Добавь молоко в список покупок», «Попроси Список покупок список» | Отдельный навык | API нет; мост в YandexStation через речь |
| Будильник, таймер | «Буди меня по субботам в 9», «Таймер на 45 секунд» | Локально на колонке | Будильники в YandexStation; вне scope |

Источники: [yaboard wiki](https://wiki.yaboard.com/w/%D0%94%D0%B5%D0%BB%D0%B0,_%D0%BD%D0%B0%D0%BF%D0%BE%D0%BC%D0%B8%D0%BD%D0%B0%D0%BD%D0%B8%D1%8F,_%D0%B1%D1%83%D0%B4%D0%B8%D0%BB%D1%8C%D0%BD%D0%B8%D0%BA%D0%B8_%D0%B8_%D1%82%D0%B0%D0%B9%D0%BC%D0%B5%D1%80%D1%8B) (доступна только из российских сетей), [Управление с помощью Алисы](https://yandex.ru/support/yandex-360/customers/calendar/web/ru/alice), [Список дел](https://yandex.ru/support/yandex-360/customers/calendar/web/ru/reminders/to-do), [команды напоминаний](https://alice.yandex.ru/support/ru/station/skills/reminder), [настройка напоминаний](https://alice.yandex.ru/support/ru/station/settings/reminder).

### Apple Reminders

- С iOS 13 «upgraded» списки Reminders хранятся в приватном хранилище синхронизации Apple (CloudKit) и через CalDAV не видны ([2Do FAQ](https://www.2doapp.com/docs/faqs/data-deleted-after-ios-13-catalina-upgrade/), [Apple Community](https://discussions.apple.com/thread/253490589) — тред закрыт проверкой Apple на ботов и может не загружаться автоматическими сборщиками; [BusyCal FAQ](https://www.busymac.com/docs/faqs/112990-reminders-in-ios-13-and-macos-catalina-drops-support-for-caldav)). Актуально и в конце 2026.
- `caldav.icloud.com` отдаёт оставшиеся не-«upgraded» списки как VTODO-коллекции с паролем приложения; на некоторых аккаунтах это ноль списков ([icloud-reminders-mcp](https://github.com/Lingnik/icloud-reminders-mcp)). На iPhone iCloud нужно добавить как отдельный CalDAV-аккаунт, тогда такие списки видны в Reminders как «сторонние», без тегов и smart lists ([heywoodlh.io](https://heywoodlh.io/cross-platform-icloud/)).
- HA Companion iOS доступа к Reminders не даёт ([feature request](https://community.home-assistant.io/t/apple-reminders/687188), всё ещё открыт; [тред WTH](https://community.home-assistant.io/t/wth-apple-reminders-in-todo/802169) закрыт в день открытия). Обходы: Shortcuts, только в направлении HA → Reminders ([simplyexplained](https://simplyexplained.com/blog/integrate-home-assistant-with-apple-reminders/)), двусторонний скрипт на Mac через EventKit ([sabbaken](https://github.com/sabbaken/apple-reminders-sync-to-home-assistant), мало пользователей), CalDAV частично ([community](https://community.home-assistant.io/t/caldav-and-to-do/652642)).

### Google

- Assistant reminders переезжают в Google Tasks с 2023 года; Keep reminders последовали во второй половине 2025 ([9to5google](https://9to5google.com/2025/10/14/google-keep-tasks-reminders-rolling-out/), [support.google.com](https://support.google.com/tasks/answer/16540694?hl=en)).
- Публичный [Tasks API](https://developers.google.com/workspace/tasks/reference/rest) хранит только дату в `due`, время отбрасывается, recurrence недоступна ([Tasks.org](https://tasks.org/docs/sync_google_tasks/)). Keep API только enterprise, без напоминаний.

### Home Assistant

- Домен `todo`: `TodoItem(uid, summary, status, due, description, completed)`, `TodoListEntityFeature` биты 1/2/4/8/16/32/64, сервисы `get_items`, `add_item`, `update_item`, `remove_item`, `remove_completed_items` ([документация для разработчиков](https://contributors.home-assistant.io/core/entities/todo/)). Исходники проверены для 2026.9.4. `add_item` не возвращает ответ в 2026.9 и 2026.10.
- Штатные интеграции: [CalDAV](https://www.home-assistant.io/integrations/caldav/) (обновление ~15 мин, iCloud поддерживается, datetime поддерживается по исходному коду; списки дел требуют настройки через UI, у YAML-настройки CalDAV списков дел нет), [Google Tasks](https://www.home-assistant.io/integrations/google_tasks/) (без datetime), Local To-do, Shopping List (без due и description).
- Стабильная версия на 2026-10-05: 2026.9.4, Python ≥ 3.14.2. HA зависит от `probatio` с 2026.9 ([блог contributors](https://contributors.home-assistant.io/blog/2026/09/30/probatio-validation-engine)) и начал переводить свои схемы; почти весь core всё ещё на `voluptuous` — это настоящий пакет, подтягиваемый через зависимости HA. `schema.py` остаётся на `voluptuous`; перепроверять при каждом обновлении HA.

## 2. Этап 0: проверка CalDAV Яндекса

Выполняется на аккаунте владельца. Нужны: логин `LOGIN@yandex.ru`, пароль приложения типа «Календарь» (id.yandex.ru → Безопасность → Пароли приложений). Результаты записать в §4.

### Шаг 1. Список коллекций

```bash
curl -s -u 'LOGIN@yandex.ru:APP_PASSWORD' -X PROPFIND \
  -H 'Depth: 1' -H 'Content-Type: application/xml' \
  --data '<d:propfind xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav"><d:prop><d:displayname/><d:resourcetype/><c:supported-calendar-component-set/></d:prop></d:propfind>' \
  'https://caldav.yandex.ru/calendars/LOGIN@yandex.ru/'
```

Ожидание: коллекции `todos-*` с `<c:comp name="VTODO"/>`. Записать их href и displayname.

### Шаг 2. Голосовые команды

На колонке сказать с интервалом в минуту:

1. «Алиса, добавь в список дел на сегодня проверка халлтаскер один».
2. «Алиса, напомни сегодня в 23:45 проверка халлтаскер два».

Через 2 минуты для каждой `todos-*` коллекции:

```bash
curl -s -u 'LOGIN@yandex.ru:APP_PASSWORD' -X REPORT \
  -H 'Depth: 1' -H 'Content-Type: application/xml' \
  --data '<c:calendar-query xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav"><d:prop><d:getetag/><c:calendar-data/></d:prop><c:filter><c:comp-filter name="VCALENDAR"><c:comp-filter name="VTODO"/></c:comp-filter></c:filter></c:calendar-query>' \
  'https://caldav.yandex.ru/calendars/LOGIN@yandex.ru/todos-XXXX/'
```

Записать для каждой фразы: попала ли в VTODO; значение `DUE` (дата или дата+время, с TZ или без); есть ли `VALARM`; есть ли `STATUS`; `UID`.

Также проверить VEVENT-коллекции тем же REPORT с `comp-filter name="VEVENT"`: не ушло ли напоминание туда событием.

### Шаг 3. Запись извне

Создать VTODO через PUT:

```bash
curl -s -u 'LOGIN@yandex.ru:APP_PASSWORD' -X PUT -H 'Content-Type: text/calendar' \
  --data $'BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//HAlltasker//EN\r\nBEGIN:VTODO\r\nUID:halltasker-test-1\r\nDTSTAMP:20261005T120000Z\r\nSUMMARY:проверка халлтаскер три\r\nDUE;VALUE=DATE:20261006\r\nSTATUS:NEEDS-ACTION\r\nEND:VTODO\r\nEND:VCALENDAR\r\n' \
  'https://caldav.yandex.ru/calendars/LOGIN@yandex.ru/todos-XXXX/halltasker-test-1.ics'
```

Спросить колонку «Какие у меня дела?» — названо ли дело. Затем изменить `STATUS:COMPLETED` тем же PUT с `If-Match` по etag и проверить, исчезло ли у Алисы. Затем DELETE и проверить.

### Шаг 4. Штатная HA CalDAV

В HA добавить интеграцию CalDAV: URL `https://caldav.yandex.ru`, логин, пароль приложения. Проверить, что появились `todo.*` для `todos-*` и `supported_features` = 119 (все кроме MOVE). Записать entity_id.

### Шаг 5. Гипотеза приватного API напоминаний

Только если шаг 2 показал, что напоминание с временем в CalDAV не попало. Из сессии YandexStation (`self.quasar.session`) выполнить `POST https://rpc.alice.yandex.ru/gproxy/get_reminders` с заголовками `ALARM_HEADERS` из `core/yandex_quasar.py`. Любой ответ, кроме 404, записать целиком. Это материал для внешнего PR в YandexStation, не для кода HAlltasker.

## 3. Как результаты влияют на проект

| Результат шага 2 | Следствие |
|---|---|
| Дело попало в `todos-*` с DUE-датой | Сценарий C1 из SPEC §7 выполним через штатную CalDAV. README описывает фразу «Добавь в список дел» |
| Напоминание с временем попало с DUE datetime | Сценарий C2 выполним. README описывает фразу «Напомни в …» |
| Напоминание не попало или попало без времени | C2 остаётся experimental; источник — внешний PR в YandexStation по результатам шага 5 |

Код MVP не зависит от результатов: узел Яндекса — обычная `todo.*`.

## 4. Результаты этапа 0

_Не выполнен. Заполнить после прогона шагов 1–5: дата, коллекции, содержимое VTODO по каждой фразе, поведение при записи извне, entity_id в HA._
