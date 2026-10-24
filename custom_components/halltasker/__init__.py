"""The HAlltasker integration: keeps todo.* entities in sync."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.config_entries import SOURCE_IMPORT, ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store
from homeassistant.helpers.typing import ConfigType
from homeassistant.util import dt as dt_util

from .const import DOMAIN, STORAGE_KEY, STORAGE_VERSION
from .coordinator import SyncCoordinator
from .core.engine import SyncEngine
from .core.link_store import LinkStore
from .plugins.ha_todo import HaTodoPlugin
from .plugins.registry import PluginRegistry
from .schema import CONFIG_SCHEMA, parse_pairs

_LOGGER = logging.getLogger(__package__)

__all__ = ["CONFIG_SCHEMA", "DOMAIN"]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Store the YAML section and start the import flow once."""
    hass.data.setdefault(DOMAIN, {})
    conf: dict[str, Any] | None = config.get(DOMAIN)
    if conf is not None:
        hass.data[DOMAIN]["yaml"] = conf
    if not hass.config_entries.async_entries(DOMAIN):
        hass.async_create_task(
            hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_IMPORT}, data={})
        )
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Build the engine and the coordinator from the YAML config."""
    conf: dict[str, Any] | None = hass.data.get(DOMAIN, {}).get("yaml")
    if conf is None:
        _LOGGER.error("halltasker section is missing in configuration.yaml")
        return False
    pairs = parse_pairs(conf)
    store = LinkStore(Store(hass, STORAGE_VERSION, STORAGE_KEY))
    await store.load()
    registry = PluginRegistry()
    registry.register(HaTodoPlugin(hass))
    engine = SyncEngine(store, registry, clock=dt_util.now)
    coordinator = SyncCoordinator(hass, pairs, engine)
    hass.data[DOMAIN]["coordinator"] = coordinator
    await coordinator.async_start()
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Stop the coordinator and drop the runtime state."""
    coordinator: SyncCoordinator | None = hass.data[DOMAIN].pop("coordinator", None)
    if coordinator is not None:
        await coordinator.async_stop()
    hass.data[DOMAIN].pop("pairs", None)
    return True
