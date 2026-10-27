# HAlltasker — архитектура (v1.1.1, 2026-10-28)

> Язык: русская копия для чтения (основной язык для людей). Обязательная версия для агентов — английская: [docs/ARCHITECTURE.md](../ARCHITECTURE.md). При расхождении действует английская.

Документ описывает, **как** реализуется `docs/SPEC.md`. Сигнатуры и структуры данных здесь обязательны к исполнению: задачи в `docs/TASKS.md` ссылаются на них по именам. Изменения относительно v1.0 перечислены в §14.

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
├── __init__.py        загрузка YAML → ConfigEntry, регистрация сервисов (включая reload)
├── coordinator.py     расписание: таймер на пару + события state_changed → engine.run_pair; один глобальный lock
├── core/
│   ├── model.py       CanonicalTask, Snapshot, Link, SyncPair, DirectionRule, Capabilities
│   ├── link_store.py  LinkStore (все пары) и PairLinks (пространство имён одной пары) поверх Store
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

**Связи привязаны к паре.** У каждой пары своё пространство имён связей и канонических id (`PairLinks`, §9). Внутри пространства имён одна каноническая задача имеет не более одной `Link` на узел, то есть не более двух связей. Один и тот же элемент `todo.*` имеет по одной независимой связи в каждой паре, в которой участвует. Пары никогда не читают и не пишут связи друг друга.

Пространство имён индексируется двумя словарями в памяти: `by_canonical[canonical_id][node] -> Link` и `by_external[(node, external_id)] -> Link`.

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
| Поле `completed` | С HA 2026.9 у `TodoItem` есть `completed: datetime \| None` (время выполнения), и `get_items` возвращает его, если оно задано. Плагин его игнорирует; в каноническую модель оно не входит |
| Сервис отклоняет поле, не поддерживаемое сущностью | `ServiceValidationError`; поэтому поля фильтруются по capabilities до вызова |

Известные capabilities штатных интеграций (из исходников): CalDAV — всё кроме MOVE (datetime поддерживается); Google Tasks — без SET_DUE_DATETIME (только дата); Local To-do — всё; Shopping List — без due и description.

Маппинг:

| `todo` | Канон |
|---|---|
| `summary` | `title` |
| `description` | `description` |
| `status == "completed"` | `status = "done"`, иначе `"open"` |
| `due` строка | `date` если 10 символов без `T`; иначе `dt_util.parse_datetime`; если результат naive — `replace(tzinfo=dt_util.get_default_time_zone())` |

Создание (SPEC FR-1, п. 4): после `add_item` плагин вызывает `get_items`, берёт элементы, чьи `uid` не входят в переданный набор `known_ids`, и выбирает тот, у которого каноническая форма равна пониженной создаваемой задаче **со `status`, принудительно равным `open`**: штатный `todo.add_item` не принимает статус и всегда создаёт открытый элемент. Если создаваемая задача `done`, то после нахождения элемента плагин вызывает `todo.update_item` со `status: "completed"` (id элемента — найденный uid) и только затем возвращает uid; сбой этого вызова поднимает `NodeUnavailable("created item not completed")`. Движок промежуточное открытое состояние не видит. Если процесс умер между двумя вызовами, следующий цикл найдёт сироту (шаг 5 ниже), и движок приведёт её к ожидаемому состоянию через `update`. Если таких несколько — любой первый. Если ни одного — повторная попытка чтения через 1 с, максимум 3 попытки, затем `NodeUnavailable("created item not found")`. Для этого базовый контракт `Plugin.create` (§3) принимает `known_ids: frozenset[str]` — идентификаторы, уже известные ядру на момент вызова.

## 5. Понижение (`core/downgrade.py`)

```python
def downgrade(task: CanonicalTask, caps: Capabilities, tz: dt.tzinfo) -> CanonicalTask:
    # due: datetime и caps.due == "date"  -> due.astimezone(tz).date()
    # due: любой и caps.due == "none"     -> None
    # description и not caps.description  -> None
    # extensions -> {} (ha_todo расширений не объявляет)

def equivalent(observed: CanonicalTask, expected: CanonicalTask, caps: Capabilities,
               tz: dt.tzinfo) -> bool:
    return Snapshot.of(observed).hash == Snapshot.of(downgrade(expected, caps, tz)).hash
```

`tz` — локальная тайм-зона HA. Ядро не импортирует HA, поэтому движок получает её как `clock().tzinfo` (fallback `dt.UTC`); интеграция передаёт `clock=dt_util.now`.

Трансформация `due: date_only` из правила направления выполняется до понижения тем же преобразованием, что и для `caps.due == "date"`.

## 6. Движок (`core/engine.py`)

Один цикл для одной пары. Весь алгоритм — последовательность чистых функций плюс операции записи. Никакого параллелизма внутри пары и никакого параллелизма между парами: координатор выполняет не более одного цикла одновременно (§8).

```python
class SyncEngine:
    def __init__(self, store: PairLinks, registry: PluginRegistry, clock: Callable[[], dt.datetime]): ...

    async def run_pair(self, pair: SyncPair, *, dry_run: bool) -> RunResult:
        ...
```

Экземпляр движка работает с **пространством имён одной пары**: координатор строит его на каждый цикл как `SyncEngine(link_store.for_pair(pair), registry, clock)`. Внутри движка `self._store` — это `PairLinks` (§9) с теми же методами работы со связями, что и у `LinkStore` v1.0. Поскольку пара видит только свои связи, запись, сделанная парой P1 в узел Y, для любой другой пары, содержащей Y, — обычное внешнее изменение. Так изменения проходят через общий узел (SPEC FR-12).

### 6.1 Шаги

1. **Плагины и capabilities.** `pa = registry.for_node(pair.a)`, `pb = ...`. `caps_a = await pa.capabilities(pair.a)`, `caps_b`. `NodeUnavailable` → `RunResult(error=...)`, выход.
2. **Полное чтение.** `snap_a = await pa.list(pair.a)`, `snap_b`. Исключение → выход с ошибкой. Дальше считается, что оба списка полные (FR-6.1).
3. **Состояние связей.** `links = store.links_for_pair(pair.a, pair.b)` — все канонические задачи пространства имён этой пары. Если хотя бы одна связь канонической задачи — tombstone, оба её external id попадают в множества `tombstoned` по узлу, и задача дальше пропускается.
3a. **Новые элементы.** До цикла по каноническим задачам вычислить `new_a = {eid: task for eid, task in snap_a.items() if store.get(pair.a, eid) is None and eid not in tombstoned_a}` и аналогично `new_b`. Эти словари изменяемы до конца цикла: шаг 5 (сопоставление сирот) может удалять записи; шаг 6 планирует остальное.
4. **Классификация по каждой канонической задаче** (`core/diff.py`):

   ```python
   @dataclass(frozen=True)
   class SideState:
       kind: Literal["unchanged", "changed", "deleted", "echo", "missing_link"]
       current: CanonicalTask | None
       changed_fields: frozenset[str]     # относительно link.last_synced
   def classify(link: Link | None, current: CanonicalTask | None, caps: Capabilities,
                tz: dt.tzinfo) -> SideState
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
   | missing_link на X | changed/unchanged | **сначала сопоставление сирот** (ниже); если сирота не найден: `create` на X, когда правило в сторону X разрешает `create` и фильтр пройден, иначе `tombstone` на X («create not allowed») |
   | changed/unchanged | missing_link | симметрично |

   `complete`: изменение только поля `status` считается операцией `complete` и проверяется правилом `complete`, а не `update`.

   **Проверка capabilities** (SPEC FR-1.3). Запись на целевую сторону X планируется, только если правило направления в сторону X разрешает операцию **и** `caps_X` её поддерживает. Один хелпер в `core/router.py` содержит всё правило, и каждый путь планирования использует его; ни один путь не проверяет `rule.*` или `caps.*` по месту:

   ```python
   Operation = Literal["create", "update", "complete", "delete", "soft_delete"]
   def allowed(rule: DirectionRule, caps: Capabilities, op: Operation) -> bool:
       # create       -> rule.create and caps.create
       # update       -> rule.update and caps.update
       # complete     -> rule.complete and caps.update
       # delete       -> rule.delete == "true" and caps.delete
       # soft_delete  -> rule.delete == "soft" and caps.update   (это update статуса, а не удаление)
   ```

   Вызывающие: `_plan_update` (строки 2–3 таблицы), `_plan_missing` и `_plan_new_items` (`create`), `_plan_delete` (`delete`/`soft_delete` в сторону Y и воскрешающий `create` в сторону X из §6.2), `_plan_conflict` (`update` каждой стороны; в v1.1 там не проверялись ни правило, ни capabilities — это дефект; фильтр к объединению по-прежнему не применяется) и обновление сироты ниже. Выключенная capability ведёт себя ровно как правило, запрещающее операцию: `update`/`complete` → нет действия, изменение принимается локально (ниже); `create` нового элемента → только `link` («not propagated»); `create` при отсутствующей связи → `tombstone` («create not allowed»); `delete`/`soft_delete` → только tombstone, как при `delete: false`. `delete: true` на узле без `caps.delete` **не** откатывается к `soft`. Причины остаются прежними; `link`/`tombstone`, запланированный из-за capability, добавляет к своей причине « (not supported by node)».

   **Сопоставление сирот** (SPEC FR-8.4). Отсутствие связи на стороне X может означать, что более ранний `create` на X удался, но его uid не был найден (§4), и в X уже лежит несвязанный элемент-«сирота». Перед планированием `create` на X вызвать `matching.find_match(expected, new_X, caps_present, caps_X, tz) -> str | None` (`core/matching.py`; тот же ключ, что у `pair_up`: равные `title` и равные `due`, пониженные до более слабых capabilities; `status` и `description` в ключ не входят; побеждает первое совпадение в порядке словаря) с `expected = apply_transform(rule_toward_X, present.current, tz)` — задачей, которую записал бы `create` на X (шаг 6 и §6.2 строят действие create из того же выражения). `find_match` сам понижает `due`; дополнительное понижение не нужно. Сопоставление нетрансформированной задачи пропустило бы сироту, созданную из трансформированной (`title_prefix`, `due: date_only`/`drop`), и дало бы дубликат на обеих сторонах. Если вернулся external id: запланировать `link` на X с этим id и удалить id из `new_X`, чтобы шаг 6 не обработал его повторно. Затем, если `equivalent(orphan_current, expected, caps_X, tz)` (§5) ложно, запланировать после `link` ещё `update`/`complete` на X: `task = expected`, `changed = {f for f in FIELDS if getattr(downgrade(expected, caps_X, tz), f) != getattr(orphan_current, f)}`, вид по `op_for_change(changed)`, `reason = "orphan differs"`, с проверкой `allowed`, как любой update; если проверка не пройдена, остаётся только `link`. Это доводит до `done` сироту, оставшуюся открытой после неудачного завершения (§4), и сводит устаревшую сироту вместо того, чтобы оставить пару расходящейся. Если `find_match` вернул `None`: планировать по таблице.

   **Локально принятое изменение** (SPEC FR-3.5). Когда решение по канонической задаче не планирует ни одного действия записи (`create`, `update`, `complete`, `delete`, `soft_delete`), каждая сторона в состоянии `changed`, у которой есть связь, принимается локально: добавить `(link, Snapshot.of(current))` в `context.accepted`. Шаг 8 устанавливает `last_observed` и `last_synced` этой связи в этот снапшот. Это покрывает одну изменённую сторону при операции, запрещённой правилом или capability, или задаче, отклонённой фильтром (v1.1), обе изменённые стороны, когда обе записи объединения отсечены, и сопоставленную сироту, обновление которой отсечено. Когда объединение пишет только на одну сторону, другая обновляется шагом 8 («обновить источник») и записи не требует. Без этого устаревшие `changed_fields` позже протащили бы запрещённое изменение на другую сторону через объединение при конфликте.

6. **Новые элементы.** Использовать `new_a`/`new_b`, оставшиеся после шага 5. Сначала `matching.pair_up(new_a, new_b, caps_a, caps_b, tz)` (FR-8.3): совпадение `title` и пониженного `due` → `link` на обе стороны без записи. Для каждого остального нового элемента на X, со свежим каноническим id:
   - если правило X→Y разрешает `create` и фильтр пройден: `link(X, eid)`, **затем** `create(Y)`. Связь источника идёт первой: если create не удался, следующий цикл увидит `missing_link` на Y и повторит попытку (с сопоставлением сирот);
   - иначе: только `link(X, eid)` (причина «not propagated»), чтобы элемент не переобрабатывался.
7. **Первичный цикл.** Если `store.pair_initialized(pair.id)` ложно: все действия `delete`, `soft_delete` и `tombstone` отбрасываются (FR-8.1; сохранённый tombstone запретил бы последующее воссоздание). После успешного цикла вызвать `store.mark_pair_initialized(pair.id)`.
8. **Исполнение.** Если `dry_run or pair.initial_sync == "dry_run"` — вернуть план без записи. Иначе для каждого действия по порядку: выполнить, обновить `Link`, `await store.save()`. Ошибка действия → записать в результат, продолжить остальные.
   - `create` на X: upsert связи X с `last_written = Snapshot.of(downgrade(task, caps_X, tz))`, `last_synced = Snapshot.of(task)`.
   - `update`/`complete` на X: установить те же два снапшота на связи X.
   - После `create`/`update`/`complete` на X **обновить источник**: для другой связи той же канонической задачи (сторона Y), если Y сама не является целью записи в этом цикле, установить `last_observed = last_synced = Snapshot.of(current_Y)`. Иначе уже обработанное изменение будет заново обнаруживаться на Y каждый цикл.
   - `last_observed` записанной связи обновляется при следующем чтении (тогда это `echo`).
   - После цикла: применить обновления echo (`last_observed`) и принятые изменения (`last_observed` и `last_synced`) из шага 5. Если было хотя бы одно, вызвать `await store.save()` один раз. Цикл без действий, без echo и без принятых изменений не пишет в хранилище.
8a. **Очистка tombstone** (SPEC FR-6.5). Не в dry run. `purged = store.purge_tombstones(now=clock(), present={pair.a: snap_a.keys(), pair.b: snap_b.keys()})`. Tombstone-связь удаляется, только если она старше 30 дней **и** её external id отсутствует в текущем снимке её узла. Tombstone, чей элемент ещё существует (случай `delete: false`: элемент Y остаётся живым для пользователя), не удаляется никогда, иначе элемент через 30 дней появился бы заново как «новый» и был бы воссоздан на другой стороне. Если `purged > 0`, ещё раз `await store.save()`.
9. **Результат.** `RunResult(ok: bool, error: str | None, actions_planned: list[Action], actions_applied: list[Action], actions_failed: list[tuple[Action, str]], links: int)`. `links` — число живых (не tombstone) записей связей в пространстве имён пары после исполнения: одна синхронизированная задача считается за 2. `run_pair` перехватывает `NodeUnavailable` и любое другое `Exception` в `RunResult(ok=False, error=...)`.

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

«Tombstone» в этой таблице означает: обе связи канонической задачи **в этой паре** получают `tombstone = True` (для `soft` связь Y помечается tombstone после записи «done»). С этого момента эта пара игнорирует оба элемента. Другие пары не затрагиваются: запись `delete` или `soft` в Y для них — обычное изменение (элемент исчезает или становится выполненным) и обрабатывается их собственными правилами. При `false` элемент Y остаётся живым для других пар.

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

Правила валидации сверх типов полей (все проверяются в `CONFIG_SCHEMA`, ошибка = интеграция не стартует):

1. Значения `id` уникальны.
2. `a != b` в каждой паре.
3. Никакие две пары не соединяют одни и те же два узла (в любом порядке).
4. **Без циклов:** неориентированный граф, вершины которого — узлы, а рёбра — пары, должен быть лесом. Проверка union-find по парам по порядку: если у обоих узлов пары уже один корень, бросить `vol.Invalid(f"pairs form a cycle at pair '{id}'")`.

Схема на `voluptuous`. Факты для HA 2026.9.4 (проверены в установленном пакете): HA уже зависит от `probatio==0.11.4` и начал миграцию на него (`helpers/config_validation.py` импортирует оба), но почти всё ядро HA по-прежнему использует `voluptuous` — реальный пакет, устанавливаемый через собственные зависимости HA (`annotatedyaml`, `hass_nabucasa`). `schema.py` остаётся на `voluptuous`; перепроверить при повышении закреплённой версии HA. При переходе на `probatio` меняется только `schema.py`. `schema.py` экспортирует `CONFIG_SCHEMA` и `def parse_pairs(conf: dict) -> list[SyncPair]`; HA читает `CONFIG_SCHEMA` из модуля интеграции, поэтому `__init__.py` реэкспортирует её (указана в `__all__`).

`__init__.py`:

- `async_setup(hass, config)` сохраняет `config[DOMAIN]` в `hass.data[DOMAIN]["yaml"]`, регистрирует сервис `reload` (ниже) и, если ConfigEntry ещё нет, запускает import-flow через `hass.async_create_task(hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_IMPORT}, data={}))`. `await` для `async_init` внутри `async_setup` приводит к deadlock при настройке.
- `async_setup_entry` строит `LinkStore`, `PluginRegistry` и `SyncCoordinator` из `hass.data[DOMAIN]["yaml"]` (не из `entry.data`), регистрирует `sync_now`/`dry_run` и подключает платформу `sensor` через `hass.config_entries.async_forward_entry_setups(entry, ["sensor"])`.
- `async_unload_entry` останавливает координатор, выгружает платформу через `hass.config_entries.async_unload_platforms(entry, ["sensor"])` и удаляет `sync_now`/`dry_run`.

**Перезагрузка** (SPEC FR-10.5). `homeassistant.reload_config_entry` **не** перечитывает `configuration.yaml`: запись пересобирается из YAML, загруженного при старте. Поэтому у HAlltasker есть собственный сервис `halltasker.reload`:

```python
from homeassistant.helpers.reload import async_integration_yaml_config
from homeassistant.helpers.service import async_register_admin_service

async def _handle_reload(call: ServiceCall) -> None:
    config = await async_integration_yaml_config(hass, DOMAIN)   # проверено CONFIG_SCHEMA; None при ошибке
    if config is None or DOMAIN not in config:
        _LOGGER.error("halltasker: reload skipped, configuration is missing or invalid")
        return
    hass.data[DOMAIN]["yaml"] = config[DOMAIN]
    for entry in hass.config_entries.async_entries(DOMAIN):
        await hass.config_entries.async_reload(entry.entry_id)

async_register_admin_service(hass, DOMAIN, "reload", _handle_reload)   # в async_setup
```

`async_integration_yaml_config` импортируется в пространство имён `__init__.py` по имени, чтобы тесты могли патчить `custom_components.halltasker.async_integration_yaml_config`.

## 8. Координатор (`coordinator.py`)

```python
class SyncCoordinator:
    def __init__(self, hass, pairs: list[SyncPair],
                 engine_factory: Callable[[SyncPair], SyncEngine]): ...
    async def async_start(self) -> None:
        # для каждой пары: async_track_time_interval(hass, cb, timedelta(seconds=pair.interval))
        # для всех узлов: async_track_state_change_event(hass, entity_ids, on_state) → debounce 2 с → run пар с этим узлом
        # первый запуск всех пар через 10 с после старта
    async def async_stop(self) -> None: ...
    async def async_run_pair(self, pair_id: str, *, dry_run: bool = False) -> RunResult:
        # ОДИН asyncio.Lock, общий для всех пар: в любой момент выполняется не более одного цикла
        # engine = self._engine_factory(pair)
        # async with asyncio.timeout(CYCLE_TIMEOUT_SECONDS): result = await engine.run_pair(pair, dry_run=dry_run)
        # TimeoutError -> RunResult(ok=False, error="cycle timeout"); lock освобождается
        # после цикла: цепной запуск (ниже)
    @property
    def results(self) -> dict[str, RunResult]:   # последний результат на пару, читает сенсор
    def subscribe(self, cb: Callable[[str], None]) -> Callable[[], None]:   # уведомление сенсоров
```

В `__init__.py`: `engine_factory = lambda pair: SyncEngine(link_store.for_pair(pair), registry, clock=dt_util.now)`.

Почему один глобальный lock: пары с общим узлом читают и пишут одну и ту же сущность `todo.*`. Два одновременных цикла могли бы перемешать `create` одной пары с поиском uid для `create` другой (§4), а хранилище сохраняется целиком. Циклы короткие (несколько вызовов сервисов), поэтому их сериализация ничего заметного не стоит.

**Таймаут цикла** (SPEC FR-9.4, Q-2). Зависший вызов сервиса `todo.*` держал бы глобальный lock вечно, поэтому вызов движка обёрнут в `asyncio.timeout(CYCLE_TIMEOUT_SECONDS)` (`const.py`, 120). Таймаут перехватывается в координаторе и превращается в `RunResult(ok=False, error="cycle timeout")` с пустыми списками действий; логируется как любая другая ошибка пары. Прерывать цикл безопасно: хранилище сохраняется после каждого применённого действия (§6.1 шаг 8), а `create`, отменённый между вызовом сервиса и поиском uid, оставляет сироту, которую шаг 5 линкует в следующем цикле.

**Цепной запуск** (SPEC FR-12.6). `state_changed` не срабатывает при правке title или due (FR-9.2), поэтому изменение, записанное парой P1 в общий узел Y, иначе дошло бы до остальных пар Y только на их следующем интервале (по одному `interval` на переход). Поэтому после цикла с непустым `actions_applied` координатор собирает узлы применённых действий `create`/`update`/`complete`/`delete`/`soft_delete` и ставит в очередь каждую другую включённую пару, содержащую один из этих узлов, через тот же debounce 2 с, что и для `state_changed`. Цепочка заканчивается сама: пара, узлы которой не изменились, ничего не применяет. Dry run цепочку не запускает.

Факты HA (2026.9): функция, передаваемая в `async_call_later` или `async_track_time_interval`, должна сама быть декорирована `@callback` (декорировать фабрику, которая её возвращает, недостаточно); иначе она выполняется в executor, и `hass.async_create_task` бросает `RuntimeError` о потокобезопасности.

## 9. Хранилище (`core/link_store.py`)

`Store(hass, version=1, key="halltasker")`. Версия HA store остаётся 1; наш собственный формат данных версионируется ключом `schema` внутри данных. Формат (schema 2):

```json
{
  "schema": 2,
  "pairs": {
    "yandex_to_icloud": {
      "nodes": ["todo.yandex_dela", "todo.icloud_reminders"],
      "initialized": true,
      "links": [ {Link as dict} ]
    }
  }
}
```

```python
class PairLinks:
    """Пространство имён одной пары. Те же методы работы со связями, что у LinkStore v1.0."""
    pair_id: str
    nodes: tuple[str, str]
    def get(self, node: str, external_id: str) -> Link | None
    def links_of(self, canonical_id: str) -> dict[str, Link]
    def links_for_pair(self, a: str, b: str) -> dict[str, dict[str, Link]]   # canonical_id -> {node: Link}
    def upsert(self, link: Link) -> None
    def new_canonical_id(self) -> str
    def pair_initialized(self, pair_id: str) -> bool        # pair_id должен равняться self.pair_id, иначе ValueError
    def mark_pair_initialized(self, pair_id: str) -> None   # pair_id должен равняться self.pair_id, иначе ValueError
    def purge_tombstones(self, *, older_than_days: int = 30, now: dt.datetime,
                         present: Mapping[str, Collection[str]]) -> int
        # удаляет tombstone-связь, только если tombstone_at < now - older_than_days
        # И link.external_id not in present.get(link.node, ()); возвращает количество
    async def save(self) -> None                            # делегирует владеющему LinkStore.save()

class LinkStore:
    async def load(self) -> None
    async def save(self) -> None            # Store.async_save от to_dict(), без задержки
    def to_dict(self) -> dict[str, Any]     # структура schema 2 выше; используется и диагностикой
    def for_pair(self, pair: SyncPair) -> PairLinks
    def pair_ids(self) -> list[str]         # отсортированы
```

`purge_tombstones` вызывается движком в конце каждого успешного не-dry цикла (§6.1 шаг 8a); другой очистки нет.

Правила:

- `for_pair(pair)` возвращает существующее пространство имён для `pair.id` или создаёт пустое с `nodes = (pair.a, pair.b)` и `initialized = False`. Для одного и того же id пары всегда возвращается один и тот же объект.
- Если у существующего пространства имён `nodes` отличаются от `{pair.a, pair.b}` (сравнение как множеств, так что перестановка `a` и `b` допустима), пользователь перенаправил существующий id пары на другие узлы: заменить пространство имён пустым для новых узлов и записать в лог `WARNING "halltasker: pair %s now connects %s and %s; its links were reset"`. Следующий цикл — первичный `merge` (SPEC FR-12.5).
- Пространства имён для id пар, которых больше нет в конфигурации, остаются нетронутыми (временно убранная пара сохраняет свои связи).
- `load()`: если данные `None` → пустое хранилище. Если `data.get("schema") != 2` (у данных v1.0 ключ `"links"` на верхнем уровне) → записать в лог `WARNING "halltasker: link storage format is outdated and was discarded"` и начать с пустого. Проект до релиза; первичный `merge` заново свяжет существующие задачи по эвристике сопоставления.

Ядро не импортирует HA: `LinkStore` принимает объект с методами `async_load() -> dict | None` и `async_save(dict)` (duck typing), в тестах подменяется in-memory. Ядро может использовать стандартный модуль `logging`.

## 10. Сенсор и сервисы

- `sensor.py`: по одному `SensorEntity` на пару, `unique_id = f"halltasker_{pair.id}"`, `name = f"HAlltasker {pair.id}"`, состояние из `RunResult`: `error` если `not ok`, `dry_run` если режим dry_run, `disabled` если `not pair.enabled`, иначе `ok`. Атрибуты по FR-10.3. Обновление по `coordinator.subscribe`.
- Сервисы в `__init__.py`: `sync_now` (`pair_id` optional) и `dry_run` (`pair_id` optional, `SupportsResponse.ONLY`, возвращает `{"pairs": {pair_id: [actions]}}`), оба регистрируются в `async_setup_entry`; `reload` (без полей), регистрируется в `async_setup` через `async_register_admin_service` (§7). Без `pair_id` `sync_now` выполняет пары одну за другой в порядке конфигурации. Описания в `services.yaml`.
- `diagnostics.py`: `{"pairs": [...], "store": async_redact_data(link_store.to_dict(), {"title", "description"}), "results": {...}}`, где `async_redact_data` из `homeassistant.components.diagnostics` (SPEC FR-10.4, Q-3): в снапшотах остаются `hash`, `status` и `due`, тексты задач заменяются на `**REDACTED**`. В `results` есть действия с задачами; их прогнать через тот же вызов.

## 11. Логирование

`_LOGGER = logging.getLogger(__package__)`. На каждый цикл одна строка `INFO`: `pair=%s ok=%s planned=%d applied=%d failed=%d links=%d duration=%.2fs`. Действия с содержимым задач — `DEBUG`. `NodeUnavailable` — `WARNING` не чаще раза в 10 минут на узел (простейший rate-limit в координаторе).

## 12. Тестирование

- `tests/core/`: чистый Python, без HA. `FakeStorage` с `async_load/async_save` в памяти. `FakePlugin` с управляемыми списками и capabilities, записывающий вызовы. Через него проверяются все сценарии приёмки группы A из SPEC §7 на уровне движка.
- `tests/plugins/test_ha_todo.py`: `hass` фикстура из `pytest-homeassistant-custom-component`; сервисы домена `todo` регистрируются вручную через `hass.services.async_register` с записью вызовов; состояние сущности через `hass.states.async_set("todo.x", "0", {"supported_features": 127})`.
- `tests/test_init.py`: загрузка интеграции из YAML, создание ConfigEntry, появление сенсора.
- `tests/conftest.py`: `pytest_plugins = "pytest_homeassistant_custom_component"`, автофикстура `auto_enable_custom_integrations`.
- `tests/todo_platform.py` + `tests/test_e2e.py`: сквозные (end-to-end) тесты через **настоящие** сервисы `todo.*`. `local_todo` в тестах использовать нельзя (ему нужен пакет `ical`, которого нет в `requirements_dev.txt`), поэтому тесты регистрируют in-memory платформу `TodoListEntity` под тестовым доменом (`MemoryTodoEntity`, устроен так же, как собственные хелперы HA в `tests/components/todo`). Это ловит то, что не могут поймать фейковые сервисы: `ServiceValidationError` на неподдерживаемых полях, настоящую сериализацию `get_items`, поиск uid.
- В интеграционных тестах зависимость манифеста `"todo"` загружает настоящие сервисы todo; тесты, подменяющие сервисы, должны регистрировать фейки **после** настройки интеграции (побеждает последняя регистрация).
- Часы `pytest-homeassistant-custom-component` стартуют с реального «сейчас»; использовать `dt_util.utcnow()` плюс дельты с `async_fire_time_changed`, а не фиксированные синтетические datetime.

Команды: см. `CLAUDE.md`.

## 13. Расширение в будущем

- Новый плагин для **задачеподобного** источника: модуль в `plugins/`, класс наследует `Plugin`, регистрируется в `registry.py`; строка узла с префиксом `jira:PROJ-123` разбирается через `matches`. Ядро не меняется, пока источник укладывается в каноническую модель §2 (`FIELDS`, `Capabilities`). `schema.py` сейчас принимает только строки узлов `todo.*`, поэтому для не-`todo` узла нужно ещё изменение схемы.
- Другие виды ресурсов (события календаря, покупки с количеством, задачи трекеров) **не** укладываются: `FIELDS`, `Capabilities`, `diff`, `conflict`, `downgrade` и `matching` написаны под четыре поля задачи, а `extensions` обнуляются при downgrade и не участвуют в diff. Их поддержка — architecture v2 (вид ресурса + профиль полей + capabilities на поле, тот же движок); решение записано в задаче Трекера IT-41. Не начинается, пока task-MVP не проверен в реальном HA.
- Группы из N узлов: в v1.1 узел уже может быть общим для нескольких пар (лес пар). Настоящая группа из N узлов с одной канонической задачей на все узлы потребовала бы нового вида пространства имён и обобщённой таблицы решений; не планируется.
- UI: config/options flow поверх той же `parse_pairs`; YAML остаётся источником истины до отдельного решения.

## 14. Изменения в v1.1 (2026-10-26)

Источник: реализация T-01…T-21 в ветке `zcode`, `docs/IMPLEMENTATION_NOTES.md`, `docs/LINK_CHECK.md`, Q-1.

Решения исполнителя, принятые как обязательные:

- Параметр `tz` у `downgrade`/`equivalent`/`classify`; движок получает его из `clock()` (§5).
- `purge_tombstones` принимает `now` только как keyword-аргумент (§9).
- Новый элемент: `link(source)` перед `create(target)` (§6.1 шаг 6).
- Обновление источника после `create`/`update`/`complete` (§6.1 шаг 8).
- Первый цикл отбрасывает `delete`, `soft_delete` и `tombstone` (§6.1 шаг 7).
- `RunResult.links` считает живые записи связей, по две на синхронизированную задачу (§6.1 шаг 9).
- Сохранения хранилища: после каждого применённого действия; одно дополнительное сохранение только для обновлений echo/принятых изменений или первого цикла; цикл без действий ничего не пишет.
- Факты HA 2026.9: `config_entries.async_forward_entry_setups`, `hass.async_create_task` для import-flow, `@callback` на замыканиях таймера, реэкспорт `CONFIG_SCHEMA`, порядок регистрации фейковых сервисов в тестах, часы phacc (§7, §8, §12).

Новое в v1.1:

- Несколько пар на узел (SPEC FR-12): пространства имён связей на пару (`PairLinks`, хранилище schema 2), движок на цикл через `engine_factory`, один глобальный lock, валидация «только лес» (§2, §6, §7, §8, §9).
- Сопоставление сирот перед `create` (§6.1 шаг 5, SPEC FR-8.4).
- Очистка tombstone перенесена в цикл движка и ограничена элементами, исчезнувшими из узла (§6.1 шаг 8a, §9, SPEC FR-6.5). В v1.0 очистка никогда не вызывалась.
- Локально принятые изменения для операций, запрещённых правилом (§6.1 шаг 5, SPEC FR-3.5).
- Сервис `halltasker.reload`, потому что `reload_config_entry` не перечитывает YAML (§7, SPEC FR-10.5).
- Сквозные тесты с in-memory платформой `todo` (§12).
- По ревью v1.1 исполнителем (Q-2, Q-3): таймаут цикла под глобальным lock и цепной запуск пар записанного узла (§8); скрытие текстов задач в диагностике (§10).
- Исправленные факты: статус probatio/voluptuous в HA 2026.9 (Q-1), `TodoItem.completed` (§4, §7).

Новое в v1.1.1 (2026-10-28), по замечаниям ревью IT-21, IT-24, IT-34:

- `router.allowed(rule, caps, op)` проверяет каждую планируемую запись по правилу **и** capabilities целевого узла, включая объединение при конфликте, которое v1.1 не проверяла вовсе; `soft_delete` требует `caps.update` (§6.1 шаг 5, «Проверка capabilities»).
- Локально принятое изменение обобщено: не запланировано ни одного действия записи → принимается каждая сторона `changed` (§6.1 шаг 5).
- `ha_todo.create` для done-задачи = `add_item` + поиск со `status`, принудительно равным open, + `update_item(status)` по uid (§4).
- Сопоставление сирот использует `apply_transform(rule, present.current, tz)` — то, что записал бы `create`, — и сводит отличающуюся сироту через `update`/`complete` с проверкой allowed (§6.1 шаг 5).
