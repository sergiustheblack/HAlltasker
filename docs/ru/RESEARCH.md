# HAlltasker — исследование внешних систем и этап 0

> Язык: русская версия (основной язык для людей). Английская версия: [docs/RESEARCH.md](../RESEARCH.md).

## 1. Ограничения внешних систем (проверено 2026-09/10)

### Яндекс Алиса

- Публичного API напоминаний нет. Сообщество HA использует приватные API `iot.quasar.yandex.ru` и `rpc.alice.yandex.ru` через [AlexxIT/YandexStation](https://github.com/AlexxIT/YandexStation). Подтверждено 2026-11-01 (§4 шаг 5): `POST rpc.alice.yandex.ru/gproxy/get_reminders` с заголовками будильников возвращает напоминания учётной записи с временем; HAlltasker использует его через живую сессию YandexStation (SPEC FR-14, ARCHITECTURE §4b). YandexStation держит `YandexQuasar` на запись конфигурации в `hass.data["yandex_station"][<unique_id записи>]`, а колонки — в `hass.data["yandex_station"]["speakers"]` (исходники, master 2026-11-01). В YandexStation есть будильники (`gproxy/get_alarms`, `create_alarm`, `change_alarm`, `cancel_alarms` → сущность `calendar`) и синхронизация списка покупок с любой `todo.*` через текстовую команду колонке и парсинг ответа (`hass/todo_list.py`, `hass/shopping_list.py`). Напоминаний нет ни в каком виде; [issue #587 «Add reminders support»](https://github.com/AlexxIT/YandexStation/issues/587) открыт с 2024-12 без активности и является точкой входа для будущего внешнего PR.
- Алиса добавляет дела только в коллекцию «Мои дела», но зачитывает все VTODO-коллекции учётной записи (наблюдение владельца, 2026-11-01); поэтому цель синхронизации — «Мои дела», остальные коллекции не трогаются.
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
- Статус дел в штатном CalDAV (проверено в 2026.9.4 и в ветке `dev` core, 2026-11-01): `_todo_item` выводит `status` только из свойства VTODO `STATUS`; VTODO с `COMPLETED` (или `PERCENT-COMPLETE:100`) без `STATUS` отдаётся как `needs_action`. Яндекс Календарь отмечает выполнение только свойством `COMPLETED` (RFC 5545 это допускает), поэтому закрытие в Яндексе не видно через `todo.get_items`. Решение (IT-48, 2026-11-01): без PR в core; HAlltasker содержит собственную платформу `todo` для CalDAV, адаптированную из core, с правилами выполненности по RFC 5545 и выбором коллекций (SPEC FR-13). В `dev` при закрытии из HA уже пишется `COMPLETED` и заполняется `TodoItem.completed` при `STATUS:COMPLETED`; 2026.9.4 пишет только `STATUS`.
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

Только если шаг 2 показал, что напоминание с временем в CalDAV не попало. Из сессии YandexStation (`self.quasar.session`) выполнить `POST https://rpc.alice.yandex.ru/gproxy/get_reminders` с заголовками `ALARM_HEADERS` из `core/yandex_quasar.py`. Любой ответ, кроме 404, записать целиком. Результат: см. §4 шаг 5; он стал основой SPEC FR-14 и этапа 1 (§2b).

## 2b. Этап 1: приватный API напоминаний (для SPEC FR-14)

Выполняет владелец, как этап 0. Два способа: (а) одноразовый скрипт из §4 шаг 5 в контейнере HA с сессией YandexStation; (б) перехват трафика приложения «Дом с Алисой» через mitmproxy — надёжный способ для вызовов записи. Всё записать в §5 без учётных данных.

1. **Чтение.** При трёх напоминаниях, поставленных голосом (разовое, ежедневное, на вторую колонку, если есть), вызвать `POST gproxy/get_reminders` и записать полный JSON: все ключи `trigger_policy` и `play_settings`, формат `id`, возвращаются ли напоминания всех колонок учётной записи.
2. **Запись.** Найти вызовы создания, изменения и отмены: URL, метод, заголовки сверх `ALARM_HEADERS`, тело запроса, тело ответа (возвращает ли создание `id`?). Гипотезы по аналогии с будильниками в `yandex_quasar.py`: `gproxy/create_reminder`, `gproxy/change_reminder`, `gproxy/cancel_reminders` с `{"reminder": {...}}` / `{"reminder_ids": [...]}`; `device_id` в `play_location`, вероятно, обязателен. Каждую гипотезу проверить реальным вызовом и записать код и тело ответа.
3. **Сработавшие напоминания.** Поставить напоминание через две минуты, дать сработать, затем вызвать `get_reminders` сразу, через 10 минут и через час: возвращается ли оно и какие поля изменились?
4. **Часовой пояс.** Поставить напоминание на известное настенное время и сравнить с naive-строкой `datetime`; записать часовой пояс HA.
5. **Отмена голосом.** «Алиса, удали напоминание …» → исчезает ли напоминание из `get_reminders` сразу?

| Результат | Следствие |
|---|---|
| Вызовы записи найдены | FR-14.5 реализуется полностью (задача «FR-14 writes») |
| Вызовы записи не найдены | Узел остаётся только для чтения: напоминания → другие системы; пары в его сторону ставят `create: false`, `update: false`, `complete: false`, `delete: false` |
| Сработавшее напоминание исчезает | `delete_past_due: false` в сторону другой системы обязателен в примере README |
| Сработавшее напоминание остаётся | Ничего не делать; элемент остаётся открытым с обеих сторон |

## 3. Как результаты влияют на проект

| Результат шага 2 | Следствие |
|---|---|
| Дело попало в `todos-*` с DUE-датой | Сценарий C1 из SPEC §7 выполним через штатную CalDAV. README описывает фразу «Добавь в список дел» |
| Напоминание с временем попало с DUE datetime | Сценарий C2 выполним. README описывает фразу «Напомни в …» |
| Напоминание не попало или попало без времени | C2 остаётся experimental; источник — внешний PR в YandexStation по результатам шага 5 |

Код MVP не зависит от результатов: узел Яндекса — обычная `todo.*`.

## 4. Результаты этапа 0

### 2026-10-31 — шаги 1–4

**Шаг 1: коллекции.** PROPFIND вернул HTTP 207 и такие коллекции:

| href | displayname | компонент |
|---|---|---|
| `/calendars/sergius%40goes.black/todos-2736030/` | Не забыть | VTODO |
| `/calendars/sergius%40goes.black/todos-7315205/` | Мои дела | VTODO |
| `/calendars/sergius%40goes.black/events-28169661/` | Мои события | VEVENT |

**Шаг 2: голосовые команды.** Алиса сообщила о двух напоминаниях: «проверить Халтаскер» в 23:45 и «проверить Халтаскер 1» в 23:47. Оба попали в `todos-7315205` как VTODO, но только с датой:

| SUMMARY | UID | DUE | VALARM | STATUS |
|---|---|---|---|---|
| `проверка helltaker 1` | `JlvjjusKyandex.ru` | `DUE;VALUE=DATE:20261031` | нет | нет |
| `проверка халтаскер 1` | `I0Pr4XtZyandex.ru` | `DUE;VALUE=DATE:20261031` | нет | нет |

Ни один VTODO не содержит `DTSTAMP`. Соответствующего VEVENT не найдено. Время напоминаний, известное Алисе, через CalDAV не отдаётся, поэтому сценарий C2 остаётся experimental; сценарий C1 выполним с DUE только из даты.

**Шаг 3: запись снаружи.** Прямой PUT создал UID `halltasker-it42-alice-20261031-01` с HTTP 201. Его summary изменён на «проверить синхронизацию календаря», чтобы избежать двусмысленности распознавания речи. Алиса перечислила созданный снаружи элемент. PUT с `If-Match` успешно поставил `STATUS:COMPLETED`, но Алиса при следующей проверке всё ещё перечисляла элемент. DELETE с `If-Match` вернул HTTP 204, последующий GET — 404, после чего Алиса перестала его перечислять. Эти наблюдения не разделяют обработку STATUS и распространение/кэширование. Тестовый элемент удалён; личные элементы не менялись.

**Шаг 4: штатная HA CalDAV.** Интеграция загрузилась и создала `todo.ne_zabyt` («Не забыть») и `todo.moi_dela` («Мои дела»), обе с `supported_features: 119` (всё, кроме MOVE).

- Проверки записи из HA выполнялись только на изначально пустом `todo.ne_zabyt`. Создание элемента с `due_date: 2026-11-01` и описанием вернуло те же поля, UID и `status: needs_action`.
- Обновление до `completed` перенесло его из запроса needs-action в запрос completed. Удаление по UID прошло.
- Создание элемента с `due_datetime: 2026-11-01 23:45:00` вернуло `due: 2026-11-01T23:45:00+03:00`. Удаление прошло.
- После очистки оба запроса (needs-action и completed) для `todo.ne_zabyt` вернули пустые списки.
- Клиент CalDAV многократно предупреждал, что VTODO Яндекса не содержат `DTSTAMP`; он добавляет поле перед разбором (`components/caldav/todo.py:69`). Проверки записи прошли несмотря на это предупреждение совместимости.

**Дополнение: закрытие средствами Яндекса.** Созданный вручную VTODO (`UID:523PFmF5yandex.ru`) изначально имел `DUE;VALUE=DATE:20261031` и не имел STATUS; HA показывал его как `needs_action`. Закрытие в Яндекс Календаре добавило только `COMPLETED:20261031T204636Z` и изменило ETag с `1793479427741` на `1793479596610`; `STATUS:COMPLETED` не появился. Штатная HA CalDAV продолжила отдавать элемент как `needs_action`, запрос completed остался пустым. Закрытие средствами Яндекса, таким образом, невидимо для HAlltasker через штатный todo API. Отслеживается как IT-48.

**Шаг 5: приватный API напоминаний (2026-11-01).** Одноразовый скрипт в контейнере HA переиспользовал стороннюю интеграцию YandexStation через импорты:

```python
from custom_components.yandex_station.core.yandex_quasar import ALARM_HEADERS
from custom_components.yandex_station.core.yandex_session import YandexSession
```

Скрипт загрузил данные существующей записи конфигурации YandexStation без вывода учётных данных, построил из них `YandexSession`, вызвал `refresh_cookies()` и отправил POST `https://rpc.alice.yandex.ru/gproxy/get_reminders` с `ALARM_HEADERS` интеграции и без тела запроса. HAlltasker сам не выполнял авторизацию Яндекса и не хранил cookies. Адаптер напоминаний УД поэтому планируется вокруг YandexStation как поставщика сессии, а не дублирует авторизацию Яндекса. Ответ был HTTP 200:

```json
{"reminders":[{"id":"7e5e294d-980e-0adc-c299-eba7e0c914dc","text":"Тест ручной","trigger_policy":{"single_trigger_policy":{"datetime":"2026-10-31T21:05:00"}},"play_settings":{"send_push":{"state":"Disabled"},"play_location":{"selected_devices":{"selected_device_ids":["R103BE300ZXT2T"]}}}}]}
```

Приватный API отдаёт напоминания с временем как отдельные объекты с `id`, `text`, `trigger_policy.single_trigger_policy.datetime` и идентификаторами устройств воспроизведения. Это подтверждает, что напоминания Алисы/УД и VTODO Яндекс Календаря нужно обрабатывать раздельно; представление CalDAV только с датой не может дать время напоминания.

## 5. Результаты этапа 1

_Не выполнен. Заполнить после §2b: дата, полный JSON `get_reminders` (id можно сократить), endpoint-ы записи с телами и ответами, поведение сработавших напоминаний, часовой пояс, поведение при отмене голосом._
