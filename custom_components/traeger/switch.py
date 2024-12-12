"""Switch platform for Traeger."""

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import TraegerData
from .const import SUPER_SMOKE_MAX_TEMP_C, SUPER_SMOKE_MAX_TEMP_F, GrillMode
from .entity import TraegerBaseEntity
from .traeger import traeger


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry[TraegerData], async_add_entities: AddEntitiesCallback
) -> bool:
    """Setup Switch platform."""
    client = entry.runtime_data.client
    assert client is not None
    grills = client.get_grills()
    for grill in grills:
        async_add_entities(
            [
                TraegerSuperSmokeEntity(
                    client,
                    grill.thingName,
                    "smoke",
                    "Super Smoke Enabled",
                    "mdi:weather-fog",
                    20,
                    21,
                ),
                TraegerSwitchEntity(
                    client, grill.thingName, "keepwarm", "Keep Warm Enabled", "mdi:beach", 18, 19
                ),
                TraegerConnectEntity(client, grill.thingName, "connect", "Connect"),
            ]
        )
    return True


class TraegerBaseSwitch(SwitchEntity, TraegerBaseEntity):
    """Base Switch Class Common to All"""

    def __init__(self, client: traeger, grill_id: str, devname: str, friendly_name: str):
        TraegerBaseEntity.__init__(self, client, grill_id)
        self.devname = devname
        self.friendly_name = friendly_name
        self.grill_register_callback()

    # Generic Properties
    @property
    def name(self) -> str:
        """Return the name of the grill"""
        if self.grill_details is None:
            return f"{self.grill_id}_{self.devname}"  # Returns EntID
        name = self.grill_details.friendlyName
        return f"{name} {self.friendly_name}"  # Returns Friendly Name

    @property
    def unique_id(self) -> str:
        """Return the unique id."""
        return f"{self.grill_id}_{self.devname}"  # SeeminglyDoes Nothing?


class TraegerConnectEntity(TraegerBaseSwitch):
    """Traeger Switch class."""

    # Generic Properties
    @property
    def icon(self) -> str:
        """Set the default MDI Icon"""
        return "mdi:lan-connect"

    # Switch Properties
    @property
    def is_on(self) -> bool:
        """Return true if device is on."""
        return bool(self.grill_state and self.grill_cloudconnect)

    # Switch Methods
    async def async_turn_on(self, **kwargs: Any) -> None:  # pylint: disable=unused-argument
        """Set new Switch Val."""
        await self.client.start(1)

    async def async_turn_off(self, **kwargs: Any) -> None:  # pylint: disable=unused-argument
        """Set new Switch Val."""
        await self.client.kill()


class TraegerSwitchEntity(TraegerBaseSwitch):
    """Traeger Switch class."""

    # pylint: disable=too-many-arguments
    # pylint: disable=too-many-positional-arguments
    def __init__(
        self,
        client: traeger,
        grill_id: str,
        devname: str,
        friendly_name: str,
        iconinp: str,
        on_cmd: int,
        off_cmd: int,
    ) -> None:
        super().__init__(client, grill_id, devname, friendly_name)
        self.grill_register_callback()
        self.iconinp = iconinp
        self.on_cmd = on_cmd
        self.off_cmd = off_cmd

    # Generic Properties
    @property
    def icon(self) -> str:
        """Set the default MDI Icon"""
        return self.iconinp

    @property
    def available(self) -> bool:
        """Reports unavailable when the grill is powered off."""
        return (
            self.grill_state is not None
            and self.grill_state.connected
            and GrillMode.IGNITING <= self.grill_state.system_status <= GrillMode.CUSTOM_COOK
        )

    # Switch Properties
    @property
    def is_on(self) -> bool:
        """Return true if device is on."""
        return bool(self.grill_state and getattr(self.grill_state, self.devname))

    # Switch Methods
    async def async_turn_on(self, **kwargs: Any) -> None:  # pylint: disable=unused-argument
        """Set new Switch Val."""
        if (
            self.grill_state is not None
            and GrillMode.IGNITING <= self.grill_state.system_status <= GrillMode.CUSTOM_COOK
        ):
            await self.client.set_switch(self.grill_id, self.on_cmd)

    async def async_turn_off(self, **kwargs: Any) -> None:  # pylint: disable=unused-argument
        """Set new Switch Val."""
        if (
            self.grill_state is not None
            and GrillMode.IGNITING <= self.grill_state.system_status <= GrillMode.CUSTOM_COOK
        ):
            await self.client.set_switch(self.grill_id, self.off_cmd)


class TraegerSuperSmokeEntity(TraegerSwitchEntity):
    """Traeger Super Smoke Switch class."""

    @property
    def available(self) -> bool:
        if (
            self.grill_state is not None
            and self.grill_state.connected
            and GrillMode.IGNITING <= self.grill_state.system_status <= GrillMode.CUSTOM_COOK
        ):
            super_smoke_supported = bool(
                self.grill_features and self.grill_features.super_smoke_enabled == 1
            )
            if self.grill_units == UnitOfTemperature.CELSIUS:
                super_smoke_max_temp = SUPER_SMOKE_MAX_TEMP_C
            else:
                super_smoke_max_temp = SUPER_SMOKE_MAX_TEMP_F
            super_smoke_within_temp = self.grill_state.set <= super_smoke_max_temp
            return bool(super_smoke_supported and super_smoke_within_temp)
        return False
