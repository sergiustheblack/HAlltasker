"""Config flow: import-only, one entry created from YAML."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigFlow

from .const import DOMAIN


class HalltaskerFlowHandler(ConfigFlow, domain=DOMAIN):
    """Handle a flow initiated from configuration.yaml."""

    VERSION = 1

    async def async_step_import(self, import_config: dict[str, Any] | None = None) -> Any:
        """Create the single config entry; YAML stays the source of truth."""
        await self.async_set_unique_id("halltasker")
        self._abort_if_unique_id_configured()
        return self.async_create_entry(title="HAlltasker", data={})
