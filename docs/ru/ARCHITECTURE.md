# HAlltasker — архитектура (v1.0, 2026-10-05)

> Язык: русская копия для чтения (основной язык для людей). Обязательная версия для агентов — английская: [docs/ARCHITECTURE.md](../ARCHITECTURE.md). При расхождении действует английская.

Документ описывает, **как** реализуется `docs/SPEC.md`. Сигнатуры и структуры данных здесь обязательны к исполнению: задачи в `docs/TASKS.md` ссылаются на них по именам.

## 1. Обзор

```
Home Assistant
│
├── todo.icloud_reminders   (штатная CalDAV)      ─┐
├── todo.google_tasks_my    (штатная Google Tasks) ─┤  узлы = сущности todo.*
├── todo.yandex_dela        (штатная CalDAV)       ─┤
└── todo.home_list          (local_todo)           ─┘
            ▲  │  сервисы todo.get_items / add_item / update_item / remove_item
            │  ▼
custom_components/halltasker
├── __init__.py        загрузка YAML → ConfigEntry, регистрация сервисов
├── coordinator.py     расписание: таймер на пару + события state_changed → engine.run_pair
├── core/
│   ├── model.py       CanonicalTask, Snapshot, Link, SyncPair, DirectionRule, Capabilities
│   ├── link_store.py  LinkStore поверх homeassistant.helpers.storage.Store
│   ├── diff.py        изменённые поля, echo-детекция
│   ├── downgrade.py   понижение под capabilities, сравнение с учётом понижения
│   ├── router.py      правила направления: операции, фильтр, трансформации
│   ├── conflict.py    объединение полей и политика prefer_a / prefer_b
│   ├── matching.py    эвристика линковки при первичной синхронизации
│   ├── engine.py      SyncEngine.run_pair — единственное место, где всё соединяется
│   └── actions.py     Action (create/update/delete/complete/link/tombstone), план действий
├── plugins/
│   ├── base.py        Plugin (ABC), PluginSchema
│   ├── registry.py    выбор плагина по строке узла
│   └── ha_todo.py     HaTodoPlugin: todo.* ↔ CanonicalTask
├── sensor.py          сенсор состояния на пару
├── diagnostics.py
├── schema.py          CONFIG_SCHEMA (voluptuous) и разбор YAML в dataclass-ы
├── const.py
├── config_flow.py     только import из YAML
├── services.yaml, strings.json, translations/{en,ru}.json, manifest.json
```

Топология «звезда»: плагин знает только каноническую модель. Прямых преобразований плагин↔плагин нет.

## 2. Каноническая модель (`core/model.py`)

Все структуры — `dataclasses`, неизменяемые (`frozen=True`), с явной сериализацией в JSON-совместимые словари.

```python
from __future__ import annotations
import datetime as dt
from dataclasses import dataclass, field
from typing import Any, Literal

Status = Literal["open", "done"]
Due = dt.date | dt.datetime | None          # datetime всегда с tzinfo

@dataclass(frozen=True)
class CanonicalTask:
    title: str
    description: str | None = None
    status: Status = "open"
    due: Due = None
    extensions: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]: ...
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CanonicalTask": ...

FIELDS: tuple[str, ...] = ("title", "description", "status", "due")
```

Сериализация `due`: `None` → `null`; `date` → `"YYYY-MM-DD"`; `datetime` → ISO 8601 с offset. Разбор: строка длиной 10 без `T` — `date`; иначе `datetime`; naive datetime при разборе запрещён (ошибка). Инвариант проверяется в `__post_init__`: `datetime` без `tzinfo` → `ValueError`.

```python
@dataclass(frozen=True)
class Snapshot:
    data: dict[str, Any]       # CanonicalTask.to_dict()
    hash: str                  # sha256 от канонического JSON (sort_keys=True, separators=(",", ":"))

    @classmethod
    def of(cls, task: CanonicalTask) -> "Snapshot": ...
    def task(self) -> CanonicalTask: ...
```

```python
@dataclass
class Link:                    # изменяемый: обновляется движком
    canonical_id: str          # uuid4 hex
    node: str                  # строка узла, напр. "todo.icloud_reminders"
    external_id: str           # uid элемента в узле
    last_observed: Snapshot | None = None
    last_written: Snapshot | None = None
    last_synced: Snapshot | None = None
    last_seen_at: str = ""     # ISO UTC
    tombstone: bool = False
    tombstone_at: str | None = None
```

Одна каноническая задача имеет по одной `Link` на узел. Хранилище индексируется двумя словарями в памяти: `by_canonical[canonical_id][node] -> Link` и `by_external[(node, external_id)] -> Link`.

```python
@dataclass(frozen=True)
class Capabilities:
    create: bool
    update: bool
    delete: bool
    due: Literal["datetime", "date", "none"]
    description: bool
```

```python
DeletePolicy = Literal["true", "false", "soft"]   # в YAML: true | false | soft

@dataclass(frozen=True)
class Filter:
    title_regex: str | None = None
    require_due: bool = False

@dataclass(frozen=True)
class Transform:
    due: Literal["keep", "date_only", "drop"] = "keep"
    title_prefix: str = ""

@dataclass(frozen=True)
class DirectionRule:
    create: bool = True
    update: bool = True
    complete: bool = True
    delete: DeletePolicy = "true"
    filter: Filter = Filter()
    transform: Transform = Transform()

@dataclass(frozen=True)
class SyncPair:
    id: str
    a: str                                   # узел
    b: str                                   # узел
    interval: int = 60                       # секунды, >= 15
    conflict: Literal["prefer_a", "prefer_b"] = "prefer_a"
    initial_sync: Literal["merge", "dry_run"] = "merge"
    a_to_b: DirectionRule = DirectionRule()
    b_to_a: DirectionRule = DirectionRule()
    enabled: bool = True
```

## 3. Контракт плагина (`plugins/base.py`)

```python
class PluginSchema:                 # frozen dataclass
    plugin_id: str                  # "ha_todo"
    fields: frozenset[str]          # подмножество FIELDS, которые плагин умеет читать/писать
    extensions: frozenset[str]      # имена полей-расширений, объявленных плагином (MVP: пусто)

class Plugin(ABC):
    schema: PluginSchema

    @abstractmethod
    def matches(self, node: str) -> bool:
        """Обслуживает ли плагин строку узла (ha_todo: node.startswith('todo.'))."""

    @abstractmethod
    async def capabilities(self, node: str) -> Capabilities:
        """Возможности конкретного узла. Бросает NodeUnavailable."""

    @abstractmethod
    async def list(self, node: str) -> dict[str, CanonicalTask]:
        """Полный список: external_id -> задача. Бросает NodeUnavailable при любой ошибке.
        Частичный результат возвращать запрещено."""

    @abstractmethod
    async def create(self, node: str, task: CanonicalTask,
                     known_ids: frozenset[str]) -> str:
        """Создаёт элемент, возвращает external_id. known_ids — id, уже известные ядру в узле."""

    @abstractmethod
    async def update(self, node: str, external_id: str, task: CanonicalTask,
                     changed: frozenset[str]) -> None:
        """Записывает только поля из changed."""

    @abstractmethod
    async def delete(self, node: str, external_id: str) -> None: ...

class NodeUnavailable(Exception): ...
```

Правило: плагин получает уже **пониженную** задачу (см. §5). Плагин не принимает решений о синхронизации.

## 4. Плагин `ha_todo` (`plugins/ha_todo.py`)

Факты об API HA (проверены по исходникам `homeassistant/components/todo` версии 2026.9):

| Что | Как |
|---|---|
| Чтение | `await hass.services.async_call("todo", "get_items", {"entity_id": node}, blocking=True, return_response=True)` → `{node: {"items": [ {uid, summary, status, due?, description?} ]}}`. Поля с `None` опущены. `due` — строка ISO: дата `YYYY-MM-DD` или datetime с offset. `status`: `needs_action` или `completed` |
| Создание | `todo.add_item` с `{"entity_id": node, "item": title, "due_date": date}` или `"due_datetime": datetime`, `"description": str}`. Ответа нет |
| Обновление | `todo.update_item` с `{"entity_id": node, "item": uid, "rename": str, "status": "needs_action"\|"completed", "due_date"\|"due_datetime": ..., "description": ...}`. Поле `item` ищется по uid или по summary; передавать всегда uid. Для очистки `due` передать `"due_date": None` |
| Удаление | `todo.remove_item` с `{"entity_id": node, "item": [uid]}` |
| Capabilities | `hass.states.get(node).attributes.get("supported_features", 0)`; биты: CREATE=1, DELETE=2, UPDATE=4, MOVE=8, SET_DUE_DATE=16, SET_DUE_DATETIME=32, SET_DESCRIPTION=64 |
| Недоступность | `hass.states.get(node)` вернул `None`, или `state in ("unavailable", "unknown")` → `NodeUnavailable` |
| Сервис отклоняет поле, не поддерживаемое сущностью | `ServiceValidationError`; поэтому поля фильтруются по capabilities до вызова |

Известные capabilities штатных интеграций (из исходников): CalDAV — всё кроме MOVE (datetime поддерживается); Google Tasks — без SET_DUE_DATETIME (только дата); Local To-do — всё; Shopping List — без due и description.

Маппинг:

| `todo` | Канон |
|---|---|
| `summary` | `title` |
| `description` | `description` |
| `status == "completed"` | `status = "done"`, иначе `"open"` |
| `due` строка | `date` если 10 символов без `T`; иначе `dt_util.parse_datetime`; если результат naive — `replace(tzinfo=dt_util.get_default_time_zone())` |

Создание (SPEC FR-1, п. 4): после `add_item` плагин вызывает `get_items`, берёт элементы, чьи `uid` не входят в переданный набор `known_ids`, и выбирает тот, у которого каноническая форма равна пониженной создаваемой задаче. Если таких несколько — любой первый. Если ни одного — повторная попытка чтения через 1 с, максимум 3 попытки, затем `NodeUnavailable("created item not found")`. Для этого базовый контракт `Plugin.create` (§3) принимает `known_ids: frozenset[str]` — идентификаторы, уже известные ядру на момент вызова.

## 5. Понижение (`core/downgrade.py`)

```python
def downgrade(task: CanonicalTask, caps: Capabilities) -> CanonicalTask:
    # due: datetime и caps.due == "date"  -> dt_util.as_local(due).date()
    # due: любой и caps.due == "none"     -> None
    # description и not caps.description  -> None
    # extensions -> {} (ha_todo расширений не объявляет)

def equivalent(observed: CanonicalTask, expected: CanonicalTask, caps: Capabilities) -> bool:
    return Snapshot.of(observed).hash == Snapshot.of(downgrade(expected, caps)).hash
```

Трансформация `due: date_only` из правила направления выполняется до понижения тем же преобразованием, что и для `caps.due == "date"`.

## 6. Движок (`core/engine.py`)

Один цикл для одной пары. Весь алгоритм — последовательность чистых функций плюс операции записи. Никакого параллелизма внутри пары.

```python
class SyncEngine:
    def __init__(self, store: LinkStore, registry: PluginRegistry, clock: Callable[[], dt.datetime]): ...

    async def run_pair(self, pair: SyncPair, *, dry_run: bool) -> RunResult:
        ...
```

### 6.1 Шаги

1. **Плагины и capabilities.** `pa = registry.for_node(pair.a)`, `pb = ...`. `caps_a = await pa.capabilities(pair.a)`, `caps_b`. `NodeUnavailable` → `RunResult(error=...)`, выход.
2. **Полное чтение.** `snap_a = await pa.list(pair.a)`, `snap_b`. Исключение → выход с ошибкой. Дальше считается, что оба списка полные (FR-6.1).
3. **Состояние связей.** `links = store.links_for_pair(pair.a, pair.b)` — все канонические задачи, у которых есть связь хотя бы с одним из двух узлов. Tombstone-связи попадают в `tombstoned_ext_ids` по узлу и дальше пропускаются.
4. **Классификация по каждой канонической задаче** (`core/diff.py`):

   ```python
   @dataclass(frozen=True)
   class SideState:
       kind: Literal["unchanged", "changed", "deleted", "echo", "missing_link"]
       current: CanonicalTask | None
       changed_fields: frozenset[str]     # относительно link.last_synced
   def classify(link: Link | None, current: CanonicalTask | None, caps: Capabilities) -> SideState
   ```

   Правила `classify`:
   - `link is None` → `missing_link` (задача на этой стороне ещё не создана).
   - `current is None` → `deleted`.
   - `hash(current) == link.last_observed.hash` → `unchanged`.
   - `link.last_written` и `equivalent(current, link.last_written.task(), caps)` → `echo`.
   - иначе `changed`, `changed_fields = {f for f in FIELDS if current[f] != last_synced[f]}` с учётом понижения для `due`.

5. **Решение** (`core/conflict.py` + `core/router.py`) → список `Action`:

   | A | B | Действие |
   |---|---|---|
   | unchanged/echo | unchanged/echo | обновить `last_observed` при echo |
   | changed | unchanged/echo | `router.plan_update(pair.a_to_b, task_a, changed_a)` → `UpdateAction(B)` или ничего, если операция запрещена |
   | unchanged/echo | changed | симметрично через `b_to_a` |
   | changed | changed | `conflict.merge(task_a, changed_a, task_b, changed_b, pair.conflict)` → итоговая задача; `UpdateAction` на обе стороны для полей, которые у стороны отличаются от итога |
   | deleted | unchanged/echo/changed | см. §6.2 |
   | unchanged/echo/changed | deleted | симметрично |
   | deleted | deleted | `TombstoneAction` |
   | missing_link | changed/unchanged | `router.plan_create(pair.b_to_a, task_b)` → `CreateAction(A)` или `TombstoneAction`-подобная пометка «не синхронизировать» (`LinkOnlyAction` с `tombstone=True` на стороне A) |
   | changed/unchanged | missing_link | симметрично |

   `complete`: изменение только поля `status` считается операцией `complete` и проверяется правилом `complete`, а не `update`.

6. **Новые элементы.** `new_a = {eid for eid in snap_a if (pair.a, eid) not in store.by_external}`; аналогично `new_b`. Сначала `matching.pair_up(new_a, new_b, caps_a, caps_b)` (FR-8.3): совпадение `title` и пониженного `due` → `LinkAction` на обе стороны без записи. Остальные — `CreateAction` на противоположную сторону через `router.plan_create`, если разрешено и фильтр пройден; иначе `LinkOnlyAction` (связь с одной стороной, чтобы не переобрабатывать).
7. **Первичный цикл.** Если `store.pair_initialized(pair.id)` ложно: все `DeleteAction` и `SoftDeleteAction` отбрасываются (FR-8.1), после успешного цикла `store.mark_pair_initialized(pair.id)`.
8. **Исполнение.** Если `dry_run or pair.initial_sync == "dry_run"` — вернуть план без записи. Иначе для каждого действия по порядку: выполнить, обновить `Link` (`last_written = Snapshot.of(downgrade(task, caps))`, `last_synced = Snapshot.of(task)`, `last_observed` обновляется при следующем чтении), `await store.save()`. Ошибка действия → записать в результат, продолжить остальные.
9. **Результат.** `RunResult(ok: bool, error: str | None, actions_planned: list[Action], actions_applied: list[Action], actions_failed: list[tuple[Action, str]], links: int)`.

### 6.2 Удаление (FR-5.4, FR-6)

Сторона X удалена, сторона Y в состоянии S, правило `rule = направление X→Y`:

| S | rule.delete | Действие |
|---|---|---|
| unchanged/echo | `true` | `DeleteAction(Y)` + tombstone |
| unchanged/echo | `soft` | `SoftDeleteAction(Y)` (update status=done) + tombstone |
| unchanged/echo | `false` | только tombstone |
| changed | политика предпочитает X | как для unchanged |
| changed | политика предпочитает Y и обратное правило `create` разрешено | `CreateAction(X)` с задачей Y, связь обновляется на новый external_id |
| changed | иначе | только tombstone |

### 6.3 Действия (`core/actions.py`)

```python
@dataclass(frozen=True)
class Action:
    kind: Literal["create", "update", "complete", "delete", "soft_delete", "link", "tombstone"]
    node: str
    canonical_id: str
    task: CanonicalTask | None = None
    external_id: str | None = None
    changed: frozenset[str] = frozenset()
    reason: str = ""
```

План сериализуется в список словарей для сенсора и ответа сервиса `dry_run`.

## 7. Конфигурация YAML (`schema.py`)

```yaml
halltasker:
  pairs:
    - id: yandex_to_icloud          # обязателен, уникален, [a-z0-9_]+
      a: todo.yandex_dela           # обязателен, entity_id домена todo
      b: todo.icloud_reminders      # обязателен
      interval: 60                  # >= 15, дефолт 60
      conflict: prefer_a            # prefer_a | prefer_b
      initial_sync: merge           # merge | dry_run
      enabled: true
      a_to_b:                       # все ключи необязательны
        create: true
        update: true
        complete: true
        delete: true                # true | false | soft
        filter:
          title_regex: "^(?!#).*"   # валидный regex, проверяется при загрузке
          require_due: false
        transform:
          due: keep                 # keep | date_only | drop
          title_prefix: ""
      b_to_a: {}
```

Схема на `voluptuous` (HA 2026.9). `schema.py` экспортирует `CONFIG_SCHEMA` и `def parse_pairs(conf: dict) -> list[SyncPair]`. При переходе HA на `probatio` меняется только этот файл.

`__init__.py`: `async_setup(hass, config)` сохраняет `config[DOMAIN]` в `hass.data[DOMAIN]["yaml"]` и запускает import-flow (`hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_IMPORT}, data={})`), если ConfigEntry ещё нет. `async_setup_entry` строит `SyncCoordinator` из YAML (не из `entry.data`), регистрирует сервисы и платформу `sensor`. `async_unload_entry` останавливает координатор.

## 8. Координатор (`coordinator.py`)

```python
class SyncCoordinator:
    def __init__(self, hass, pairs: list[SyncPair], engine: SyncEngine): ...
    async def async_start(self) -> None:
        # для каждой пары: async_track_time_interval(hass, cb, timedelta(seconds=pair.interval))
        # для всех узлов: async_track_state_change_event(hass, entity_ids, on_state) → debounce 2 с → run пар с этим узлом
        # первый запуск всех пар через 10 с после старта
    async def async_stop(self) -> None: ...
    async def async_run_pair(self, pair_id: str, *, dry_run: bool = False) -> RunResult:
        # asyncio.Lock на пару: одновременные запуски сериализуются
    @property
    def results(self) -> dict[str, RunResult]:   # последний результат на пару, читает сенсор
    def subscribe(self, cb: Callable[[str], None]) -> Callable[[], None]:   # уведомление сенсоров
```

## 9. Хранилище (`core/link_store.py`)

`Store(hass, version=1, key="halltasker")`. Формат:

```json
{
  "links": [ {Link как dict} ],
  "initialized_pairs": ["yandex_to_icloud"]
}
```

```python
class LinkStore:
    async def load(self) -> None
    async def save(self) -> None            # Store.async_save, без задержки
    def get(self, node: str, external_id: str) -> Link | None
    def links_of(self, canonical_id: str) -> dict[str, Link]
    def links_for_pair(self, a: str, b: str) -> dict[str, dict[str, Link]]   # canonical_id -> {node: Link}
    def upsert(self, link: Link) -> None
    def new_canonical_id(self) -> str
    def pair_initialized(self, pair_id: str) -> bool
    def mark_pair_initialized(self, pair_id: str) -> None
    def purge_tombstones(self, older_than_days: int = 30, now: dt.datetime) -> int
```

Ядро не импортирует HA: `LinkStore` принимает объект с методами `async_load() -> dict | None` и `async_save(dict)` (duck typing), в тестах подменяется in-memory.

## 10. Сенсор и сервисы

- `sensor.py`: по одному `SensorEntity` на пару, `unique_id = f"halltasker_{pair.id}"`, `name = f"HAlltasker {pair.id}"`, состояние из `RunResult`: `error` если `not ok`, `dry_run` если режим dry_run, `disabled` если `not pair.enabled`, иначе `ok`. Атрибуты по FR-10.3. Обновление по `coordinator.subscribe`.
- Сервисы в `__init__.py`: `sync_now` (`pair_id` optional) и `dry_run` (`pair_id` optional, `SupportsResponse.ONLY`, возвращает `{"pairs": {pair_id: [actions]}}`). Описания в `services.yaml`.

## 11. Логирование

`_LOGGER = logging.getLogger(__package__)`. На каждый цикл одна строка `INFO`: `pair=%s ok=%s planned=%d applied=%d failed=%d links=%d duration=%.2fs`. Действия с содержимым задач — `DEBUG`. `NodeUnavailable` — `WARNING` не чаще раза в 10 минут на узел (простейший rate-limit в координаторе).

## 12. Тестирование

- `tests/core/`: чистый Python, без HA. `FakeStorage` с `async_load/async_save` в памяти. `FakePlugin` с управляемыми списками и capabilities, записывающий вызовы. Через него проверяются все сценарии приёмки группы A из SPEC §7 на уровне движка.
- `tests/plugins/test_ha_todo.py`: `hass` фикстура из `pytest-homeassistant-custom-component`; сервисы домена `todo` регистрируются вручную через `hass.services.async_register` с записью вызовов; состояние сущности через `hass.states.async_set("todo.x", "0", {"supported_features": 127})`.
- `tests/test_init.py`: загрузка интеграции из YAML, создание ConfigEntry, появление сенсора.
- `tests/conftest.py`: `pytest_plugins = "pytest_homeassistant_custom_component"`, автофикстура `auto_enable_custom_integrations`.

Команды: см. `CLAUDE.md`.

## 13. Расширение в будущем

- Новый плагин: модуль в `plugins/`, класс наследует `Plugin`, регистрируется в `registry.py`; строка узла с префиксом `jira:PROJ-123` разбирается через `matches`. Ядро не меняется.
- Группы из N узлов: движок уже работает с канонической задачей и набором связей; потребуется расширить `SyncPair` до `SyncGroup` и обобщить таблицу решений §6.1.
- UI: config/options flow поверх той же `parse_pairs`; YAML остаётся источником истины до отдельного решения.
