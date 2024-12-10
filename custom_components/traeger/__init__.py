"""
Custom integration to integrate traeger with Home Assistant.

For more details about this integration, please refer to
https://github.com/njobrien1006/hass_traeger
"""

from dataclasses import dataclass
from datetime import timedelta
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_HOMEASSISTANT_STOP
from homeassistant.core import Event, HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import CONF_PASSWORD, CONF_USERNAME, DOMAIN, PLATFORMS, STARTUP_MESSAGE
from .traeger import traeger

SCAN_INTERVAL = timedelta(seconds=30)

_LOGGER: logging.Logger = logging.getLogger(__package__)


@dataclass
class TraegerData:
    client: traeger | None


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry[TraegerData]) -> bool:
    """Set up this integration using UI."""
    if hass.data.get(DOMAIN) is None:
        hass.data.setdefault(DOMAIN, {})
        _LOGGER.info(STARTUP_MESSAGE)

    username: str = entry.data.get(CONF_USERNAME, "")
    password: str = entry.data.get(CONF_PASSWORD, "")

    session = async_get_clientsession(hass)

    client = traeger(username, password, hass, session)

    await client.start(30)

    entry.runtime_data = TraegerData(client)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    async def async_shutdown(event: Event[Any]) -> None:  # pylint: disable=unused-argument
        """Shut down the client."""
        await client.kill()

    hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, async_shutdown)
    entry.add_update_listener(async_reload_entry)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry[TraegerData]) -> bool:
    """Handle removal of an entry."""
    client = entry.runtime_data.client
    if client is not None:
        if unloaded := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
            entry.runtime_data.client = None
        await client.kill()

    return unloaded


async def async_reload_entry(hass: HomeAssistant, entry: "ConfigEntry[TraegerData]") -> None:
    """Reload config entry."""
    await async_unload_entry(hass, entry)
    await async_setup_entry(hass, entry)
