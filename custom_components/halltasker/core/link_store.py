"""Persistent link index on top of a duck-typed storage object."""

from __future__ import annotations

import datetime as dt
from typing import Any, Protocol
import uuid

from .model import Link


class StorageLike(Protocol):
    """The subset of homeassistant.helpers.storage.Store the core relies on."""

    async def async_load(self) -> dict[str, Any] | None: ...

    async def async_save(self, data: dict[str, Any]) -> None: ...


class LinkStore:
    """In-memory link index; every save writes the full state to storage."""

    def __init__(self, storage: StorageLike) -> None:
        self._storage = storage
        self._by_canonical: dict[str, dict[str, Link]] = {}
        self._by_external: dict[tuple[str, str], Link] = {}
        self._initialized_pairs: set[str] = set()

    async def load(self) -> None:
        data = await self._storage.async_load()
        self._by_canonical = {}
        self._by_external = {}
        self._initialized_pairs = set()
        if not data:
            return
        for link_data in data.get("links", []):
            self.upsert(Link.from_dict(link_data))
        self._initialized_pairs = set(data.get("initialized_pairs", []))

    async def save(self) -> None:
        links = [link for node_links in self._by_canonical.values() for link in node_links.values()]
        await self._storage.async_save(
            {
                "links": [link.to_dict() for link in links],
                "initialized_pairs": sorted(self._initialized_pairs),
            }
        )

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
        return pair_id in self._initialized_pairs

    def mark_pair_initialized(self, pair_id: str) -> None:
        self._initialized_pairs.add(pair_id)

    def purge_tombstones(self, *, older_than_days: int = 30, now: dt.datetime) -> int:
        cutoff = now - dt.timedelta(days=older_than_days)
        removed = 0
        for canonical_id, node_links in list(self._by_canonical.items()):
            for node, link in list(node_links.items()):
                if not link.tombstone or not link.tombstone_at:
                    continue
                if dt.datetime.fromisoformat(link.tombstone_at) < cutoff:
                    self._remove(canonical_id, node, link)
                    removed += 1
        return removed

    def _remove(self, canonical_id: str, node: str, link: Link) -> None:
        self._by_external.pop((node, link.external_id), None)
        node_links = self._by_canonical.get(canonical_id)
        if node_links is not None and node in node_links:
            del node_links[node]
            if not node_links:
                del self._by_canonical[canonical_id]
