"""Persistent link index: one namespace per pair on top of a storage object."""

from __future__ import annotations

from collections.abc import Collection, Mapping
import datetime as dt
import logging
from typing import Any, Protocol
import uuid

from .model import Link, SyncPair

_LOGGER = logging.getLogger(__package__)

SCHEMA_VERSION = 2


class StorageLike(Protocol):
    """The subset of homeassistant.helpers.storage.Store the core relies on."""

    async def async_load(self) -> dict[str, Any] | None: ...

    async def async_save(self, data: dict[str, Any]) -> None: ...


class PairLinks:
    """One pair's namespace: links and canonical ids invisible to other pairs."""

    def __init__(
        self,
        pair_id: str,
        nodes: tuple[str, str],
        store: LinkStore,
        initialized: bool = False,
    ) -> None:
        self.pair_id = pair_id
        self.nodes = nodes
        self._store = store
        self._initialized = initialized
        self._by_canonical: dict[str, dict[str, Link]] = {}
        self._by_external: dict[tuple[str, str], Link] = {}

    async def save(self) -> None:
        """Persist the whole store, not only this namespace."""
        await self._store.save()

    def get(self, node: str, external_id: str) -> Link | None:
        return self._by_external.get((node, external_id))

    def links_of(self, canonical_id: str) -> dict[str, Link]:
        return dict(self._by_canonical.get(canonical_id, {}))

    def links_for_pair(self, a: str, b: str) -> dict[str, dict[str, Link]]:
        result: dict[str, dict[str, Link]] = {}
        for canonical_id, node_links in self._by_canonical.items():
            selected = {node: link for node, link in node_links.items() if node in (a, b)}
            if selected:
                result[canonical_id] = selected
        return result

    def upsert(self, link: Link) -> None:
        node_links = self._by_canonical.setdefault(link.canonical_id, {})
        old = node_links.get(link.node)
        if old is not None and old.external_id != link.external_id:
            self._by_external.pop((link.node, old.external_id), None)
        node_links[link.node] = link
        self._by_external[(link.node, link.external_id)] = link

    def new_canonical_id(self) -> str:
        return uuid.uuid4().hex

    def pair_initialized(self, pair_id: str) -> bool:
        self._require_same_pair(pair_id)
        return self._initialized

    def mark_pair_initialized(self, pair_id: str) -> None:
        self._require_same_pair(pair_id)
        self._initialized = True

    def purge_tombstones(
        self,
        *,
        older_than_days: int = 30,
        now: dt.datetime,
        present: Mapping[str, Collection[str]],
    ) -> int:
        """Drop tombstones older than the TTL whose items are gone from the node."""
        cutoff = now - dt.timedelta(days=older_than_days)
        removed = 0
        for canonical_id, node_links in list(self._by_canonical.items()):
            for node, link in list(node_links.items()):
                if not link.tombstone or not link.tombstone_at:
                    continue
                if dt.datetime.fromisoformat(link.tombstone_at) >= cutoff:
                    continue
                if link.external_id in present.get(link.node, ()):
                    continue
                self._remove(canonical_id, node, link)
                removed += 1
        return removed

    def _require_same_pair(self, pair_id: str) -> None:
        if pair_id != self.pair_id:
            raise ValueError(f"namespace of pair {self.pair_id!r} got a call for pair {pair_id!r}")

    def _remove(self, canonical_id: str, node: str, link: Link) -> None:
        self._by_external.pop((node, link.external_id), None)
        node_links = self._by_canonical.get(canonical_id)
        if node_links is not None and node in node_links:
            del node_links[node]
            if not node_links:
                del self._by_canonical[canonical_id]

    def _links(self) -> list[Link]:
        return [link for node_links in self._by_canonical.values() for link in node_links.values()]


class LinkStore:
    """Owns the namespaces of all pairs and serializes them as one storage blob."""

    def __init__(self, storage: StorageLike) -> None:
        self._storage = storage
        self._pairs: dict[str, PairLinks] = {}

    async def load(self) -> None:
        data = await self._storage.async_load()
        self._pairs = {}
        if not data:
            return
        if data.get("schema") != SCHEMA_VERSION:
            _LOGGER.warning("halltasker: link storage format is outdated and was discarded")
            return
        for pair_id, payload in data.get("pairs", {}).items():
            namespace = PairLinks(
                pair_id,
                tuple(payload["nodes"]),
                self,
                initialized=bool(payload.get("initialized")),
            )
            for link_data in payload.get("links", []):
                namespace.upsert(Link.from_dict(link_data))
            self._pairs[pair_id] = namespace

    async def save(self) -> None:
        await self._storage.async_save(self.to_dict())

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": SCHEMA_VERSION,
            "pairs": {
                pair_id: {
                    "nodes": list(namespace.nodes),
                    "initialized": namespace._initialized,
                    "links": [link.to_dict() for link in namespace._links()],
                }
                for pair_id, namespace in sorted(self._pairs.items())
            },
        }

    def for_pair(self, pair: SyncPair) -> PairLinks:
        """Return the namespace of the pair, resetting it if its nodes changed."""
        existing = self._pairs.get(pair.id)
        if existing is not None:
            if set(existing.nodes) == {pair.a, pair.b}:
                return existing
            _LOGGER.warning(
                "halltasker: pair %s now connects %s and %s; its links were reset",
                pair.id,
                pair.a,
                pair.b,
            )
        namespace = PairLinks(pair.id, (pair.a, pair.b), self)
        self._pairs[pair.id] = namespace
        return namespace

    def pair_ids(self) -> list[str]:
        return sorted(self._pairs)
