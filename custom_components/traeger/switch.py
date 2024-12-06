"""Switch platform for Traeger."""
from homeassistant.components.switch import SwitchEntity
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import TraegerConfigEntry
from .const import GrillMode, SUPER_SMOKE_MAX_TEMP_C, SUPER_SMOKE_MAX_TEMP_F
from .entity import TraegerBaseEntity
from .traeger import traeger


async def async_setup_entry(hass: HomeAssistant, entry: TraegerConfigEntry, async_add_entities: AddEntitiesCallback):
    """Setup Switch platform."""
    client = entry.runtime_data.client
    grills = client.get_grills()
    for grill in grills:
        async_add_entities([
            TraegerSuperSmokeEntity(
                client, grill["thingName"], "smoke", "Super Smoke Enabled", "mdi:weather-fog", 20, 21),
            TraegerSwitchEntity(
                client, grill["thingName"], "keepwarm", "Keep Warm Enabled", "mdi:beach", 18, 19),
            TraegerConnectEntity(
                client, grill["thingName"], "connect", "Connect")
        ])


class TraegerBaseSwitch(SwitchEntity, TraegerBaseEntity):
    """Base Switch Class Common to All"""

    def __init__(self, client: traeger, grill_id: str, devname: str, friendly_name: str):
        TraegerBaseEntity.__init__(self, client, grill_id)
        self.devname = devname
        self.friendly_name = friendly_name
        self.grill_register_callback()

    # Generic Properties
    @property
    def name(self):
        """Return the name of the grill"""
        if self.grill_details is None:
            return f"{self.grill_id}_{self.devname}"  # Returns EntID
        name = self.grill_details["friendlyName"]
        return f"{name} {self.friendly_name}"  # Returns Friendly Name

    @property
    def unique_id(self):
        """Return the unique id."""
        return f"{self.grill_id}_{self.devname}"  # SeeminglyDoes Nothing?


class TraegerConnectEntity(TraegerBaseSwitch):
    """Traeger Switch class."""
    # Generic Properties
    @property
    def icon(self):
        """Set the default MDI Icon"""
        return "mdi:lan-connect"

    # Switch Properties
    @property
    def is_on(self):
        """Return true if device is on."""
        if self.grill_state is None:
            return 0
        return self.grill_cloudconnect

    # Switch Methods
    async def async_turn_on(self, **kwargs):  # pylint: disable=unused-argument
        """Set new Switch Val."""
        await self.client.start(1)

    async def async_turn_off(self, **kwargs):  # pylint: disable=unused-argument
        """Set new Switch Val."""
        await self.client.kill()


class TraegerSwitchEntity(TraegerBaseSwitch):
    """Traeger Switch class."""

    # pylint: disable=too-many-arguments
    # pylint: disable=too-many-positional-arguments
    def __init__(self, client: traeger, grill_id: str, devname: str, friendly_name: str,
                 iconinp: str, on_cmd: str, off_cmd: str):
        super().__init__(client, grill_id, devname, friendly_name)
        self.grill_register_callback()
        self.iconinp = iconinp
        self.on_cmd = on_cmd
        self.off_cmd = off_cmd

    # Generic Properties
    @property
    def icon(self):
        """Set the default MDI Icon"""
        return self.iconinp

    @property
    def available(self):
        """Reports unavailable when the grill is powered off"""
        if self.grill_state is None or not self.grill_state["connected"]:
            return False
        if GrillMode.IGNITING <= self.grill_state[
                'system_status'] <= GrillMode.CUSTOM_COOK:
            return True
        return False

    # Switch Properties
    @property
    def is_on(self):
        """Return true if device is on."""
        if self.grill_state is None:
            return 0
        return self.grill_state[self.devname]

    # Switch Methods
    async def async_turn_on(self, **kwargs):  # pylint: disable=unused-argument
        """Set new Switch Val."""
        if GrillMode.IGNITING <= self.grill_state[
                'system_status'] <= GrillMode.CUSTOM_COOK:
            await self.client.set_switch(self.grill_id, self.on_cmd)

    async def async_turn_off(self, **kwargs):  # pylint: disable=unused-argument
        """Set new Switch Val."""
        if GrillMode.IGNITING <= self.grill_state[
                'system_status'] <= GrillMode.CUSTOM_COOK:
            await self.client.set_switch(self.grill_id, self.off_cmd)


class TraegerSuperSmokeEntity(TraegerSwitchEntity):
    """Traeger Super Smoke Switch class."""

    @property
    def available(self):
        if self.grill_state is None or not self.grill_state["connected"]:
            return False
        if GrillMode.IGNITING <= self.grill_state[
                'system_status'] <= GrillMode.CUSTOM_COOK:
            super_smoke_supported = 0
            if self.grill_features["super_smoke_enabled"] == 1:
                super_smoke_supported = 1
            if self.grill_units == UnitOfTemperature.CELSIUS:
                super_smoke_max_temp = SUPER_SMOKE_MAX_TEMP_C
            else:
                super_smoke_max_temp = SUPER_SMOKE_MAX_TEMP_F
            super_smoke_within_temp = self.grill_state[
                "set"] <= super_smoke_max_temp
            return super_smoke_supported and super_smoke_within_temp
        return False
