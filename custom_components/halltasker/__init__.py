"""The HAlltasker integration: keeps todo.* entities in sync."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.config_entries import SOURCE_IMPORT, ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.exceptions import ServiceValidationError
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.storage import Store
from homeassistant.helpers.typing import ConfigType
from homeassistant.util import dt as dt_util
import voluptuous as vol

from .const import DOMAIN, STORAGE_KEY, STORAGE_VERSION
from .coordinator import SyncCoordinator
from .core.actions import action_to_dict
from .core.engine import SyncEngine
from .core.link_store import LinkStore
from .plugins.ha_todo import HaTodoPlugin
from .plugins.registry import PluginRegistry
from .schema import CONFIG_SCHEMA, parse_pairs

_LOGGER = logging.getLogger(__package__)

__all__ = ["CONFIG_SCHEMA", "DOMAIN"]

SERVICE_DRY_RUN = "dry_run"
SERVICE_SYNC_NOW = "sync_now"
ATTR_PAIR_ID = "pair_id"

SERVICE_SCHEMA = vol.Schema({vol.Optional(ATTR_PAIR_ID): cv.string})


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
    _async_register_services(hass)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Stop the coordinator and drop the runtime state."""
    coordinator: SyncCoordinator | None = hass.data[DOMAIN].pop("coordinator", None)
    if coordinator is not None:
        await coordinator.async_stop()
    hass.data[DOMAIN].pop("pairs", None)
    hass.services.async_remove(DOMAIN, SERVICE_SYNC_NOW)
    hass.services.async_remove(DOMAIN, SERVICE_DRY_RUN)
    return True


def _coordinator_or_raise(hass: HomeAssistant) -> SyncCoordinator:
    coordinator: SyncCoordinator | None = hass.data.get(DOMAIN, {}).get("coordinator")
    if coordinator is None:
        raise ServiceValidationError("halltasker is not loaded")
    return coordinator


def _pair_ids(call: ServiceCall, coordinator: SyncCoordinator) -> list[str]:
    pair_id: str | None = call.data.get(ATTR_PAIR_ID)
    if pair_id is None:
        return list(coordinator.pairs)
    if pair_id not in coordinator.pairs:
        raise ServiceValidationError(f"unknown pair_id: {pair_id}")
    return [pair_id]


def _async_register_services(hass: HomeAssistant) -> None:
    if hass.services.has_service(DOMAIN, SERVICE_SYNC_NOW):
        return

    async def handle_sync_now(call: ServiceCall) -> None:
        coordinator = _coordinator_or_raise(hass)
        for pair_id in _pair_ids(call, coordinator):
            await coordinator.async_run_pair(pair_id)

    async def handle_dry_run(call: ServiceCall) -> dict[str, Any]:
        coordinator = _coordinator_or_raise(hass)
        planned: dict[str, list[dict[str, Any]]] = {}
        for pair_id in _pair_ids(call, coordinator):
            result = await coordinator.async_run_pair(pair_id, dry_run=True)
            planned[pair_id] = [action_to_dict(action) for action in result.actions_planned]
        return {"pairs": planned}

    hass.services.async_register(DOMAIN, SERVICE_SYNC_NOW, handle_sync_now, schema=SERVICE_SCHEMA)
    hass.services.async_register(
        DOMAIN,
        SERVICE_DRY_RUN,
        handle_dry_run,
        schema=SERVICE_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )
