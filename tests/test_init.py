"""Tests for loading the integration from YAML."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.setup import async_setup_component

from custom_components.halltasker.const import DOMAIN

CONFIG = {
    "halltasker": {
        "pairs": [
            {
                "id": "p1",
                "a": "todo.list_a",
                "b": "todo.list_b",
                "interval": 30,
                "a_to_b": {"delete": "soft", "transform": {"due": "date_only"}},
            }
        ]
    }
}


async def test_setup_from_yaml_creates_one_entry_and_parses_pairs(hass) -> None:
    assert await async_setup_component(hass, DOMAIN, CONFIG)
    await hass.async_block_till_done()
    entries: list[ConfigEntry] = hass.config_entries.async_entries(DOMAIN)
    assert len(entries) == 1
    coordinator = hass.data[DOMAIN]["coordinator"]
    pair = coordinator.pairs["p1"]
    assert pair.a == "todo.list_a"
    assert pair.b == "todo.list_b"
    assert pair.interval == 30
    assert pair.a_to_b.delete == "soft"
    assert pair.a_to_b.transform.due == "date_only"
    assert pair.b_to_a.delete == "true"


async def test_invalid_interval_fails_setup_with_log(hass, caplog) -> None:
    bad_config = {
        "halltasker": {
            "pairs": [{"id": "p1", "a": "todo.list_a", "b": "todo.list_b", "interval": 5}]
        }
    }
    with caplog.at_level(logging.ERROR):
        assert await async_setup_component(hass, DOMAIN, bad_config) is False
    assert any("interval" in record.message.lower() for record in caplog.records)
