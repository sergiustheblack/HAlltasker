"""Test fakes for the core: storage and plugin doubles."""

from __future__ import annotations

from typing import Any


class FakeStorage:
    """In-memory replacement for the HA storage helper."""

    def __init__(self, data: dict[str, Any] | None = None) -> None:
        self.data = data
        self.saves = 0

    async def async_load(self) -> dict[str, Any] | None:
        return self.data

    async def async_save(self, data: dict[str, Any]) -> None:
        self.data = data
        self.saves += 1
