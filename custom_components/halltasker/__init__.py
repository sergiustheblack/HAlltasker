"""The HAlltasker integration: keeps todo.* entities in sync."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.config_entries import SOURCE_IMPORT, ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.typing import ConfigType

from .const import DOMAIN
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
    """Build the runtime state from the YAML config, not from entry.data."""
    conf: dict[str, Any] | None = hass.data.get(DOMAIN, {}).get("yaml")
    if conf is None:
        _LOGGER.error("halltasker section is missing in configuration.yaml")
        return False
    hass.data[DOMAIN]["pairs"] = parse_pairs(conf)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Drop the runtime state; YAML reload recreates it."""
    hass.data[DOMAIN].pop("pairs", None)
    return True
