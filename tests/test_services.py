"""Tests for the halltasker services."""

from __future__ import annotations

import logging
from unittest.mock import AsyncMock, patch

from homeassistant.config_entries import ConfigEntryState
from homeassistant.exceptions import ServiceValidationError
from homeassistant.setup import async_setup_component
import pytest

from custom_components.halltasker.const import DOMAIN
from custom_components.halltasker.schema import CONFIG_SCHEMA

CONFIG = {
    "halltasker": {
        "pairs": [
            {"id": "p1", "a": "todo.list_a", "b": "todo.list_b"},
            {"id": "p2", "a": "todo.list_c", "b": "todo.list_d"},
        ]
    }
}


async def _setup(hass, config=CONFIG) -> None:
    assert await async_setup_component(hass, DOMAIN, config)
    await hass.async_block_till_done()


async def test_dry_run_returns_plan_for_given_pair(hass) -> None:
    await _setup(hass)
    response = await hass.services.async_call(
        DOMAIN, "dry_run", {"pair_id": "p1"}, blocking=True, return_response=True
    )
    assert list(response["pairs"]) == ["p1"]
    assert isinstance(response["pairs"]["p1"], list)


async def test_dry_run_without_pair_id_plans_all_pairs(hass) -> None:
    await _setup(hass)
    response = await hass.services.async_call(
        DOMAIN, "dry_run", {}, blocking=True, return_response=True
    )
    assert sorted(response["pairs"]) == ["p1", "p2"]


async def test_sync_now_runs_without_error(hass, caplog) -> None:
    await _setup(hass)
    with caplog.at_level(logging.WARNING):
        await hass.services.async_call(DOMAIN, "sync_now", {"pair_id": "p1"}, blocking=True)
    assert hass.services.has_service(DOMAIN, "sync_now")


async def test_unknown_pair_id_is_rejected(hass) -> None:
    await _setup(hass)
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN, "dry_run", {"pair_id": "nope"}, blocking=True, return_response=True
        )


async def test_reload_reloads_yaml_and_stops_old_coordinator(hass) -> None:
    initial = {"halltasker": {"pairs": [CONFIG["halltasker"]["pairs"][0]]}}
    await _setup(hass, initial)
    old_coordinator = hass.data[DOMAIN]["coordinator"]

    with (
        patch(
            "custom_components.halltasker.async_integration_yaml_config",
            new=AsyncMock(return_value=CONFIG_SCHEMA(CONFIG)),
        ),
        patch.object(old_coordinator, "async_stop", wraps=old_coordinator.async_stop) as stop,
    ):
        await hass.services.async_call(DOMAIN, "reload", {}, blocking=True)
        await hass.async_block_till_done()

    stop.assert_awaited_once()
    new_coordinator = hass.data[DOMAIN]["coordinator"]
    assert new_coordinator is not old_coordinator
    assert list(new_coordinator.pairs) == ["p1", "p2"]


async def test_reload_with_invalid_yaml_keeps_running_configuration(hass, caplog) -> None:
    await _setup(hass)
    coordinator = hass.data[DOMAIN]["coordinator"]
    entry = hass.config_entries.async_entries(DOMAIN)[0]

    with (
        patch(
            "custom_components.halltasker.async_integration_yaml_config",
            new=AsyncMock(return_value=None),
        ),
        caplog.at_level(logging.ERROR),
    ):
        await hass.services.async_call(DOMAIN, "reload", {}, blocking=True)

    assert "halltasker: reload skipped, configuration is missing or invalid" in caplog.text
    assert hass.data[DOMAIN]["coordinator"] is coordinator
    assert list(coordinator.pairs) == ["p1", "p2"]
    assert entry.state is ConfigEntryState.LOADED
    assert hass.services.has_service(DOMAIN, "sync_now")
