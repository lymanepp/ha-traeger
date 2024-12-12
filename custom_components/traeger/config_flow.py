"""Adds config flow for Traeger."""

import logging
from typing import Any

from homeassistant.config_entries import (
    CONN_CLASS_CLOUD_POLL,
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_create_clientsession
import voluptuous as vol

from . import TraegerData
from .const import CONF_PASSWORD, CONF_USERNAME, DOMAIN, PLATFORMS
from .traeger import traeger

_LOGGER: logging.Logger = logging.getLogger(__package__)


class TraegerFlowHandler(ConfigFlow, domain=DOMAIN):
    """Traeger config flow."""

    VERSION = 1
    CONNECTION_CLASS = CONN_CLASS_CLOUD_POLL

    def __init__(self) -> None:
        """Initialize."""
        self._errors: dict[str, str] = {}

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Handle a flow initialized by the user."""
        self._errors = {}

        # Uncomment the next 2 lines if only a single instance of the integration is allowed:
        # if self._async_current_entries():
        #     return self.async_abort(reason="single_instance_allowed")

        if user_input is not None:
            valid = await self._test_credentials(
                user_input[CONF_USERNAME], user_input[CONF_PASSWORD]
            )
            if valid:
                return self.async_create_entry(title=user_input[CONF_USERNAME], data=user_input)
            self._errors["base"] = "auth"
            return await self._show_config_form(user_input)

        user_input = {
            CONF_USERNAME: "",
            CONF_PASSWORD: "",
        }

        return await self._show_config_form(user_input)

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: ConfigEntry[TraegerData],
    ) -> OptionsFlow:
        """Get the options flow for this handler."""
        return TraegerOptionsFlowHandler(config_entry)

    async def _show_config_form(self, user_input: dict[str, Any]) -> ConfigFlowResult:
        """Show the configuration form to edit location data."""
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_USERNAME, default=user_input[CONF_USERNAME]): str,
                    vol.Required(CONF_PASSWORD, default=user_input[CONF_PASSWORD]): str,
                }
            ),
            errors=self._errors,
        )

    async def _test_credentials(self, username: str, password: str) -> bool:
        """Return true if credentials is valid."""
        try:
            session = async_create_clientsession(self.hass)
            client = traeger(username, password, self.hass, session)
            await client.get_user_data()
            return True
        except Exception as exception:  # pylint: disable=broad-except
            _LOGGER.error("Failed to login %s", exception)
        return False


class TraegerOptionsFlowHandler(OptionsFlow):
    """Traeger config flow options handler."""

    def __init__(self, config_entry: ConfigEntry[TraegerData]) -> None:
        """Initialize HACS options flow."""
        self.config_entry = config_entry
        self.options = dict(config_entry.options)

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:  # pylint: disable=unused-argument
        """Manage the options."""
        return await self.async_step_user()

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Handle a flow initialized by the user."""
        if user_input is not None:
            self.options.update(user_input)
            return await self._update_options()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(x, default=self.options.get(x, True)): bool
                    for x in sorted(PLATFORMS)
                }
            ),
        )

    async def _update_options(self) -> ConfigFlowResult:
        """Update config entry options."""
        return self.async_create_entry(
            title=self.config_entry.data.get(CONF_USERNAME), data=self.options
        )
