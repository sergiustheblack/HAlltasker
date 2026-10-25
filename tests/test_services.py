"""Tests for the halltasker services."""

from __future__ import annotations

import logging

from homeassistant.exceptions import ServiceValidationError
from homeassistant.setup import async_setup_component
import pytest

from custom_components.halltasker.const import DOMAIN

CONFIG = {
    "halltasker": {
        "pairs": [
            {"id": "p1", "a": "todo.list_a", "b": "todo.list_b"},
            {"id": "p2", "a": "todo.list_c", "b": "todo.list_d"},
        ]
    }
}


async def _setup(hass) -> None:
    assert await async_setup_component(hass, DOMAIN, CONFIG)
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
