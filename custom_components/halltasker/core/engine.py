"""The sync engine: one cycle for one pair of nodes."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field, replace
import datetime as dt

from ..plugins.base import NodeUnavailable
from ..plugins.registry import PluginRegistry
from .actions import Action, RunResult
from .conflict import merge
from .diff import SideState, classify
from .downgrade import downgrade, equivalent
from .link_store import PairLinks
from .matching import find_match, pair_up
from .model import FIELDS, CanonicalTask, Capabilities, DirectionRule, Link, Snapshot, SyncPair
from .router import Operation, allowed, apply_transform, op_for_change, passes_filter

_RULE_ONLY_CAPS = Capabilities(
    create=True, update=True, delete=True, due="datetime", description=True
)


@dataclass
class _CycleContext:
    """Everything the execution step needs from the planning step."""

    snaps: dict[str, dict[str, CanonicalTask]]
    caps: dict[str, Capabilities]
    tz: dt.tzinfo
    echo_updates: list[tuple[Link, Snapshot]] = field(default_factory=list)
    accepted: list[tuple[Link, Snapshot]] = field(default_factory=list)
    targeted: set[tuple[str, str]] = field(default_factory=set)


class SyncEngine:
    """Joins plugins, the store, and the decision rules into one pair cycle."""

    def __init__(
        self, store: PairLinks, registry: PluginRegistry, clock: Callable[[], dt.datetime]
    ) -> None:
        self._store = store
        self._registry = registry
        self._clock = clock

    async def run_pair(self, pair: SyncPair, *, dry_run: bool) -> RunResult:
        try:
            plan, live_links, context = await self._plan(pair)
            if dry_run or pair.initial_sync == "dry_run":
                return RunResult(ok=True, error=None, actions_planned=plan, links=live_links)
            was_initialized = self._store.pair_initialized(pair.id)
            applied, failed = await self._execute(plan, context)
            if not was_initialized:
                self._store.mark_pair_initialized(pair.id)
            purged = self._store.purge_tombstones(
                now=self._clock(),
                present={
                    pair.a: frozenset(context.snaps[pair.a]),
                    pair.b: frozenset(context.snaps[pair.b]),
                },
            )
            if not was_initialized or context.echo_updates or context.accepted or purged:
                await self._store.save()
            return RunResult(
                ok=True,
                error=None,
                actions_planned=plan,
                actions_applied=applied,
                actions_failed=failed,
                links=_live_links(self._store, pair),
            )
        except NodeUnavailable as err:
            return RunResult(ok=False, error=str(err))
        except Exception as err:
            return RunResult(ok=False, error=f"{type(err).__name__}: {err}")

    async def _plan(self, pair: SyncPair) -> tuple[list[Action], int, _CycleContext]:
        plugin_a = self._registry.for_node(pair.a)
        plugin_b = self._registry.for_node(pair.b)
        caps_a = await plugin_a.capabilities(pair.a)
        caps_b = await plugin_b.capabilities(pair.b)
        snap_a = await plugin_a.list(pair.a)
        snap_b = await plugin_b.list(pair.b)
        tz = self._clock().tzinfo or dt.UTC
        context = _CycleContext(
            snaps={pair.a: snap_a, pair.b: snap_b},
            caps={pair.a: caps_a, pair.b: caps_b},
            tz=tz,
        )

        links = self._store.links_for_pair(pair.a, pair.b)
        plan: list[Action] = []

        # Step 3a: unlinked items, computed before the loop; orphan matching
        # (step 5) removes entries, step 6 consumes the rest. Tombstoned ids
        # are excluded by the store lookup: a tombstone link is still indexed.
        new_a = {ext: task for ext, task in snap_a.items() if self._store.get(pair.a, ext) is None}
        new_b = {ext: task for ext, task in snap_b.items() if self._store.get(pair.b, ext) is None}

        for canonical_id, node_links in links.items():
            link_a = node_links.get(pair.a)
            link_b = node_links.get(pair.b)
            if _is_tombstoned(link_a) or _is_tombstoned(link_b):
                continue
            current_a = snap_a.get(link_a.external_id) if link_a is not None else None
            current_b = snap_b.get(link_b.external_id) if link_b is not None else None
            state_a = classify(link_a, current_a, caps_a, tz)
            state_b = classify(link_b, current_b, caps_b, tz)
            if state_a.kind == "echo" and link_a is not None and current_a is not None:
                context.echo_updates.append((link_a, Snapshot.of(current_a)))
            if state_b.kind == "echo" and link_b is not None and current_b is not None:
                context.echo_updates.append((link_b, Snapshot.of(current_b)))
            plan.extend(
                self._decide(
                    pair,
                    canonical_id,
                    link_a,
                    state_a,
                    link_b,
                    state_b,
                    tz,
                    new_a,
                    new_b,
                    caps_a,
                    caps_b,
                    context,
                )
            )

        plan.extend(await self._plan_new_items(pair, new_a, new_b, caps_a, caps_b, tz))

        if not self._store.pair_initialized(pair.id):
            plan = [
                action
                for action in plan
                if action.kind not in ("delete", "soft_delete", "tombstone")
            ]
        return plan, _live_links(self._store, pair), context

    async def _execute(
        self, plan: list[Action], context: _CycleContext
    ) -> tuple[list[Action], list[tuple[Action, str]]]:
        applied: list[Action] = []
        failed: list[tuple[Action, str]] = []
        failed_deletes: set[str] = set()
        now = self._clock().isoformat()
        context.targeted = {
            (action.node, action.canonical_id)
            for action in plan
            if action.kind in ("update", "complete")
        }
        for action in plan:
            if action.kind == "tombstone" and action.canonical_id in failed_deletes:
                continue
            try:
                await self._apply(action, context, now)
            except Exception as err:
                failed.append((action, f"{type(err).__name__}: {err}"))
                if action.kind in ("delete", "soft_delete"):
                    failed_deletes.add(action.canonical_id)
                continue
            applied.append(action)
            await self._store.save()
        for link, snapshot in context.echo_updates:
            link.last_observed = snapshot
        for link, snapshot in context.accepted:
            self._adopt(link, snapshot, context.caps[link.node], context.tz)
        return applied, failed

    async def _apply(self, action: Action, context: _CycleContext, now: str) -> None:
        plugin = self._registry.for_node(action.node)
        caps = context.caps[action.node]
        tz = context.tz
        if action.kind == "create":
            if action.task is None:
                raise ValueError("create action without a task")
            task = downgrade(action.task, caps, tz)
            known_ids = frozenset(context.snaps[action.node])
            external_id = await plugin.create(action.node, task, known_ids)
            self._store.upsert(
                Link(
                    canonical_id=action.canonical_id,
                    node=action.node,
                    external_id=external_id,
                    last_written=Snapshot.of(task),
                    last_synced=Snapshot.of(action.task),
                    last_seen_at=now,
                )
            )
            self._refresh_source(action, context, now)
            return
        if action.kind in ("update", "complete"):
            if action.task is None or action.external_id is None:
                raise ValueError("update action without task or external_id")
            task = downgrade(action.task, caps, tz)
            await plugin.update(action.node, action.external_id, task, action.changed)
            self._written(action.node, action.external_id, task, action.task, now)
            self._refresh_source(action, context, now)
            return
        if action.kind == "soft_delete":
            if action.task is None or action.external_id is None:
                raise ValueError("soft_delete action without task or external_id")
            done = replace(action.task, status="done")
            task = downgrade(done, caps, tz)
            await plugin.update(action.node, action.external_id, task, frozenset({"status"}))
            link = self._store.get(action.node, action.external_id)
            if link is not None:
                link.last_written = Snapshot.of(task)
                link.last_synced = Snapshot.of(done)
                link.last_seen_at = now
                link.tombstone = True
                link.tombstone_at = now
            return
        if action.kind == "delete":
            if action.external_id is None:
                raise ValueError("delete action without external_id")
            await plugin.delete(action.node, action.external_id)
            self._entomb(action.node, action.canonical_id, action.external_id, now)
            return
        if action.kind == "tombstone":
            self._entomb(action.node, action.canonical_id, action.external_id or "", now)
            return
        if action.kind == "link":
            if action.external_id is None:
                raise ValueError("link action without external_id")
            task = context.snaps[action.node].get(action.external_id)
            if task is None:
                raise ValueError(f"link action for unknown item {action.external_id}")
            snapshot = Snapshot.of(task)
            self._store.upsert(
                Link(
                    canonical_id=action.canonical_id,
                    node=action.node,
                    external_id=action.external_id,
                    last_observed=snapshot,
                    last_synced=snapshot,
                    last_seen_at=now,
                )
            )
            return
        raise ValueError(f"unknown action kind {action.kind}")

    def _written(
        self,
        node: str,
        external_id: str,
        written: CanonicalTask,
        synced: CanonicalTask,
        now: str,
    ) -> None:
        link = self._store.get(node, external_id)
        if link is None:
            return
        link.last_written = Snapshot.of(written)
        link.last_synced = Snapshot.of(synced)
        link.last_seen_at = now

    def _adopt(self, link: Link, snapshot: Snapshot, caps: Capabilities, tz: dt.tzinfo) -> None:
        """Adopt a synced state not produced by a write on this link."""
        link.last_observed = snapshot
        link.last_synced = snapshot
        if link.last_written is not None and not equivalent(
            snapshot.task(), link.last_written.task(), caps, tz
        ):
            link.last_written = None

    def _refresh_source(self, action: Action, context: _CycleContext, now: str) -> None:
        """Record the consumed change on the opposite side of the same canonical task."""
        for link in self._store.links_of(action.canonical_id).values():
            if link.node == action.node or link.tombstone:
                continue
            if (link.node, action.canonical_id) in context.targeted:
                continue
            current = context.snaps.get(link.node, {}).get(link.external_id)
            if current is None:
                continue
            self._adopt(link, Snapshot.of(current), context.caps[link.node], context.tz)
            link.last_seen_at = now

    def _entomb(self, node: str, canonical_id: str, external_id: str, now: str) -> None:
        link = self._store.get(node, external_id) if external_id else None
        if link is None:
            link = Link(canonical_id=canonical_id, node=node, external_id=external_id)
            self._store.upsert(link)
        link.tombstone = True
        link.tombstone_at = now
        link.last_seen_at = now

    def _decide(
        self,
        pair: SyncPair,
        canonical_id: str,
        link_a: Link | None,
        state_a: SideState,
        link_b: Link | None,
        state_b: SideState,
        tz: dt.tzinfo,
        new_a: dict[str, CanonicalTask],
        new_b: dict[str, CanonicalTask],
        caps_a: Capabilities,
        caps_b: Capabilities,
        context: _CycleContext,
    ) -> list[Action]:
        if state_a.kind == "deleted" and state_b.kind == "deleted":
            return self._tombstone_both(pair, canonical_id, link_a, link_b, "deleted on both")
        if state_a.kind == "deleted":
            return self._plan_delete(
                pair, canonical_id, link_a, state_a, link_b, state_b, caps_a, caps_b, tz
            )
        if state_b.kind == "deleted":
            return self._plan_delete(
                pair, canonical_id, link_b, state_b, link_a, state_a, caps_a, caps_b, tz
            )
        if state_a.kind == "missing_link":
            return self._plan_missing(
                pair, canonical_id, pair.a, state_b, link_b, tz, new_a, caps_a, caps_b, context
            )
        if state_b.kind == "missing_link":
            return self._plan_missing(
                pair, canonical_id, pair.b, state_a, link_a, tz, new_b, caps_b, caps_a, context
            )
        if state_a.kind == "changed" and state_b.kind == "changed":
            actions = self._plan_conflict(
                pair, canonical_id, link_a, state_a, link_b, state_b, caps_a, caps_b, tz
            )
            _accept_locally(actions, context, (link_a, state_a), (link_b, state_b))
            return actions
        if state_a.kind == "changed":
            actions = self._plan_update(
                pair.a_to_b,
                state_a.current,
                state_a.changed_fields,
                pair.b,
                canonical_id,
                link_b.external_id if link_b is not None else None,
                caps_b,
                tz,
                "changed on A",
            )
            _accept_locally(actions, context, (link_a, state_a))
            return actions
        if state_b.kind == "changed":
            actions = self._plan_update(
                pair.b_to_a,
                state_b.current,
                state_b.changed_fields,
                pair.a,
                canonical_id,
                link_a.external_id if link_a is not None else None,
                caps_a,
                tz,
                "changed on B",
            )
            _accept_locally(actions, context, (link_b, state_b))
            return actions
        return []

    def _plan_update(
        self,
        rule: DirectionRule,
        source: CanonicalTask,
        changed: frozenset[str],
        node: str,
        canonical_id: str,
        external_id: str | None,
        caps: Capabilities,
        tz: dt.tzinfo,
        reason: str,
    ) -> list[Action]:
        operation = op_for_change(changed)
        if not allowed(rule, caps, operation) or not passes_filter(rule, source):
            return []
        kind = "complete" if operation == "complete" else "update"
        return [
            Action(
                kind=kind,
                node=node,
                canonical_id=canonical_id,
                task=apply_transform(rule, source, tz),
                external_id=external_id,
                changed=changed,
                reason=reason,
            )
        ]

    def _plan_conflict(
        self,
        pair: SyncPair,
        canonical_id: str,
        link_a: Link | None,
        state_a: SideState,
        link_b: Link | None,
        state_b: SideState,
        caps_a: Capabilities,
        caps_b: Capabilities,
        tz: dt.tzinfo,
    ) -> list[Action]:
        if state_a.current is None or state_b.current is None:
            return []
        result, write_a, write_b = merge(
            state_a.current,
            state_a.changed_fields,
            state_b.current,
            state_b.changed_fields,
            pair.conflict,
        )
        actions: list[Action] = []
        if write_a and link_a is not None and allowed(pair.b_to_a, caps_a, "update"):
            actions.append(
                Action(
                    kind="update",
                    node=pair.a,
                    canonical_id=canonical_id,
                    task=apply_transform(pair.b_to_a, result, tz),
                    external_id=link_a.external_id,
                    changed=write_a,
                    reason="conflict merged",
                )
            )
        if write_b and link_b is not None and allowed(pair.a_to_b, caps_b, "update"):
            actions.append(
                Action(
                    kind="update",
                    node=pair.b,
                    canonical_id=canonical_id,
                    task=apply_transform(pair.a_to_b, result, tz),
                    external_id=link_b.external_id,
                    changed=write_b,
                    reason="conflict merged",
                )
            )
        return actions

    def _plan_delete(
        self,
        pair: SyncPair,
        canonical_id: str,
        link_x: Link,
        state_x: SideState,
        link_y: Link | None,
        state_y: SideState,
        caps_a: Capabilities,
        caps_b: Capabilities,
        tz: dt.tzinfo,
    ) -> list[Action]:
        node_x = link_x.node
        node_y = pair.b if node_x == pair.a else pair.a
        caps_x = caps_a if node_x == pair.a else caps_b
        caps_y = caps_b if node_x == pair.a else caps_a
        rule_x_to_y = pair.a_to_b if node_x == pair.a else pair.b_to_a
        rule_y_to_x = pair.b_to_a if node_x == pair.a else pair.a_to_b
        prefers_x = (pair.conflict == "prefer_a") == (node_x == pair.a)

        if state_y.kind == "changed" and state_y.current is not None and not prefers_x:
            if allowed(rule_y_to_x, caps_x, "create") and passes_filter(
                rule_y_to_x, state_y.current
            ):
                return [
                    Action(
                        kind="create",
                        node=node_x,
                        canonical_id=canonical_id,
                        task=apply_transform(rule_y_to_x, state_y.current, tz),
                        reason="re-created from the other side after deletion",
                    )
                ]
            return self._tombstone_both(
                pair,
                canonical_id,
                link_x,
                link_y,
                _reason_with_capability(rule_y_to_x, caps_x, "create", "create not allowed"),
            )

        if link_y is None:
            return [
                Action(
                    kind="tombstone",
                    node=node_x,
                    canonical_id=canonical_id,
                    external_id=link_x.external_id,
                    reason="deleted here, absent on the other side",
                )
            ]

        actions: list[Action] = []
        if allowed(rule_x_to_y, caps_y, "delete"):
            actions.append(
                Action(
                    kind="delete",
                    node=node_y,
                    canonical_id=canonical_id,
                    external_id=link_y.external_id,
                    reason="deleted on the other side",
                )
            )
        elif allowed(rule_x_to_y, caps_y, "soft_delete"):
            actions.append(
                Action(
                    kind="soft_delete",
                    node=node_y,
                    canonical_id=canonical_id,
                    task=state_y.current,
                    external_id=link_y.external_id,
                    reason="deleted on the other side",
                )
            )
        operation = "delete" if allowed(rule_x_to_y, _RULE_ONLY_CAPS, "delete") else "soft_delete"
        reason = _reason_with_capability(rule_x_to_y, caps_y, operation, "deleted")
        actions.extend(self._tombstone_both(pair, canonical_id, link_x, link_y, reason))
        return actions

    def _plan_missing(
        self,
        pair: SyncPair,
        canonical_id: str,
        missing_node: str,
        present_state: SideState,
        present_link: Link | None,
        tz: dt.tzinfo,
        new_missing: dict[str, CanonicalTask],
        caps_missing: Capabilities,
        caps_present: Capabilities,
        context: _CycleContext,
    ) -> list[Action]:
        rule = pair.b_to_a if missing_node == pair.a else pair.a_to_b
        if present_state.current is None or present_link is None:
            return []
        expected = apply_transform(rule, present_state.current, tz)
        orphan = find_match(expected, new_missing, caps_present, caps_missing, tz)
        if orphan is not None:
            orphan_current = new_missing.pop(orphan)
            actions = [
                Action(
                    kind="link",
                    node=missing_node,
                    canonical_id=canonical_id,
                    external_id=orphan,
                    reason="orphan matched",
                )
            ]
            if not equivalent(orphan_current, expected, caps_missing, tz):
                downgraded = downgrade(expected, caps_missing, tz)
                changed = frozenset(
                    field
                    for field in FIELDS
                    if getattr(downgraded, field) != getattr(orphan_current, field)
                )
                operation = op_for_change(changed)
                if changed and allowed(rule, caps_missing, operation):
                    actions.append(
                        Action(
                            kind=operation,
                            node=missing_node,
                            canonical_id=canonical_id,
                            task=expected,
                            external_id=orphan,
                            changed=changed,
                            reason="orphan differs",
                        )
                    )
            _accept_locally(actions, context, (present_link, present_state))
            return actions
        if allowed(rule, caps_missing, "create") and passes_filter(rule, present_state.current):
            return [
                Action(
                    kind="create",
                    node=missing_node,
                    canonical_id=canonical_id,
                    task=expected,
                    reason="created on the other side",
                )
            ]
        return [
            Action(
                kind="tombstone",
                node=missing_node,
                canonical_id=canonical_id,
                reason=_reason_with_capability(rule, caps_missing, "create", "create not allowed"),
            )
        ]

    async def _plan_new_items(
        self,
        pair: SyncPair,
        new_a: dict[str, CanonicalTask],
        new_b: dict[str, CanonicalTask],
        caps_a: Capabilities,
        caps_b: Capabilities,
        tz: dt.tzinfo,
    ) -> list[Action]:
        actions: list[Action] = []
        for ext_a, ext_b in pair_up(new_a, new_b, caps_a, caps_b, tz):
            canonical_id = self._store.new_canonical_id()
            actions.append(
                Action(
                    kind="link",
                    node=pair.a,
                    canonical_id=canonical_id,
                    external_id=ext_a,
                    reason="matched during initial sync",
                )
            )
            actions.append(
                Action(
                    kind="link",
                    node=pair.b,
                    canonical_id=canonical_id,
                    external_id=ext_b,
                    reason="matched during initial sync",
                )
            )
            del new_a[ext_a]
            del new_b[ext_b]
        for external_id, task in new_a.items():
            canonical_id = self._store.new_canonical_id()
            if allowed(pair.a_to_b, caps_b, "create") and passes_filter(pair.a_to_b, task):
                actions.append(
                    Action(
                        kind="link",
                        node=pair.a,
                        canonical_id=canonical_id,
                        external_id=external_id,
                        reason="new on A",
                    )
                )
                actions.append(
                    Action(
                        kind="create",
                        node=pair.b,
                        canonical_id=canonical_id,
                        task=apply_transform(pair.a_to_b, task, tz),
                        reason="new on A",
                    )
                )
            else:
                actions.append(
                    Action(
                        kind="link",
                        node=pair.a,
                        canonical_id=canonical_id,
                        external_id=external_id,
                        reason=_reason_with_capability(
                            pair.a_to_b, caps_b, "create", "not propagated to B"
                        ),
                    )
                )
        for external_id, task in new_b.items():
            canonical_id = self._store.new_canonical_id()
            if allowed(pair.b_to_a, caps_a, "create") and passes_filter(pair.b_to_a, task):
                actions.append(
                    Action(
                        kind="link",
                        node=pair.b,
                        canonical_id=canonical_id,
                        external_id=external_id,
                        reason="new on B",
                    )
                )
                actions.append(
                    Action(
                        kind="create",
                        node=pair.a,
                        canonical_id=canonical_id,
                        task=apply_transform(pair.b_to_a, task, tz),
                        reason="new on B",
                    )
                )
            else:
                actions.append(
                    Action(
                        kind="link",
                        node=pair.b,
                        canonical_id=canonical_id,
                        external_id=external_id,
                        reason=_reason_with_capability(
                            pair.b_to_a, caps_a, "create", "not propagated to A"
                        ),
                    )
                )
        return actions

    def _tombstone_both(
        self,
        pair: SyncPair,
        canonical_id: str,
        link_a: Link | None,
        link_b: Link | None,
        reason: str,
    ) -> list[Action]:
        actions: list[Action] = []
        if link_a is not None:
            actions.append(
                Action(
                    kind="tombstone",
                    node=pair.a,
                    canonical_id=canonical_id,
                    external_id=link_a.external_id,
                    reason=reason,
                )
            )
        if link_b is not None:
            actions.append(
                Action(
                    kind="tombstone",
                    node=pair.b,
                    canonical_id=canonical_id,
                    external_id=link_b.external_id,
                    reason=reason,
                )
            )
        return actions


def _accept_locally(
    actions: list[Action],
    context: _CycleContext,
    *sides: tuple[Link | None, SideState],
) -> None:
    """Accept changed sides when the decision contains no external write."""
    if any(
        action.kind in ("create", "update", "complete", "delete", "soft_delete")
        for action in actions
    ):
        return
    for link, state in sides:
        if link is not None and state.kind == "changed" and state.current is not None:
            context.accepted.append((link, Snapshot.of(state.current)))


def _reason_with_capability(
    rule: DirectionRule, caps: Capabilities, op: Operation, reason: str
) -> str:
    if not allowed(rule, caps, op) and allowed(rule, _RULE_ONLY_CAPS, op):
        return f"{reason} (not supported by node)"
    return reason


def _is_tombstoned(link: Link | None) -> bool:
    return link is not None and link.tombstone


def _live_links(store: PairLinks, pair: SyncPair) -> int:
    return sum(
        1
        for node_links in store.links_for_pair(pair.a, pair.b).values()
        for link in node_links.values()
        if not link.tombstone
    )
