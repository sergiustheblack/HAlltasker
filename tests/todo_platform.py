"""In-memory todo platform for end-to-end tests through real HA services."""

from __future__ import annotations

from dataclasses import replace

from homeassistant.components.todo import TodoItem, TodoListEntity
from homeassistant.config_entries import ConfigEntry, ConfigFlow
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    MockModule,
    MockPlatform,
    mock_integration,
    mock_platform,
)


class MemoryConfigFlow(ConfigFlow, domain="test"):
    """Register the test domain for config entries."""


class MemoryTodoEntity(TodoListEntity):
    """A todo list stored in memory."""

    def __init__(self, supported_features: int) -> None:
        self._attr_supported_features = supported_features
        self._items: dict[str, TodoItem] = {}
        self._counter = 0

    @property
    def todo_items(self) -> list[TodoItem]:
        """Return the current items."""
        return list(self._items.values())

    async def async_create_todo_item(self, item: TodoItem) -> None:
        """Add an item."""
        self._counter += 1
        uid = f"item-{self._counter}"
        self._items[uid] = replace(item, uid=uid)
        self.async_write_ha_state()

    async def async_update_todo_item(self, item: TodoItem) -> None:
        """Replace an item updated by the todo service."""
        assert item.uid is not None
        self._items[item.uid] = item
        self.async_write_ha_state()

    async def async_delete_todo_items(self, uids: list[str]) -> None:
        """Delete items by uid."""
        for uid in uids:
            self._items.pop(uid)
        self.async_write_ha_state()


async def setup_memory_todo(
    hass: HomeAssistant, entity_id_suffix: str, features: int
) -> MemoryTodoEntity:
    """Register one in-memory todo entity and wait for its state."""
    entity = MemoryTodoEntity(features)
    entity._attr_name = entity_id_suffix
    entity._attr_unique_id = entity_id_suffix

    async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
        await hass.config_entries.async_forward_entry_setups(entry, ["todo"])
        return True

    async def async_setup_platform(
        hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
    ) -> None:
        async_add_entities([entity])

    mock_integration(hass, MockModule("test", async_setup_entry=async_setup_entry))
    mock_platform(hass, "test.config_flow")
    mock_platform(hass, "test.todo", MockPlatform(async_setup_entry=async_setup_platform))
    entry = MockConfigEntry(domain="test", unique_id=entity_id_suffix)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get(f"todo.{entity_id_suffix}") is not None
    return entity
