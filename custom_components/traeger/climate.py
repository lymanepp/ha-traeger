"""Climate platform for Traeger grills"""

from typing import Any

from homeassistant.components.climate import ClimateEntity
from homeassistant.components.climate.const import PRESET_NONE, ClimateEntityFeature, HVACMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import TraegerData
from .const import GRILL_MIN_TEMP_C, GRILL_MIN_TEMP_F, PROBE_PRESET_MODES, GrillMode
from .entity import TraegerBaseEntity, TraegerGrillMonitor
from .traeger import traeger


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry[TraegerData], async_add_entities: AddEntitiesCallback
) -> bool:
    """Setup climate platform."""
    client = entry.runtime_data.client
    assert client is not None
    grills = client.get_grills()
    for grill in grills:
        grill_id = grill.thingName
        async_add_entities([TraegerClimateEntity(client, grill_id, "Climate")])

        monitor = TraegerGrillMonitor(
            client, grill_id, async_add_entities, AccessoryTraegerClimateEntity)
        monitor.attach_monitor()
    return True


# Mapping GrillMode to HVACMode
GRILL_MODE_TO_HVAC_MODE = {
    GrillMode.COOL_DOWN: HVACMode.COOL,
    GrillMode.CUSTOM_COOK: HVACMode.HEAT,
    GrillMode.MANUAL_COOK: HVACMode.HEAT,
    GrillMode.PREHEATING: HVACMode.HEAT,
    GrillMode.IGNITING: HVACMode.HEAT,
    GrillMode.IDLE: HVACMode.OFF,
    GrillMode.SLEEPING: HVACMode.OFF,
    GrillMode.OFFLINE: HVACMode.OFF,
    GrillMode.SHUTDOWN: HVACMode.OFF,
}


class TraegerBaseClimate(ClimateEntity, TraegerBaseEntity):
    """Base Climate Class Common to All"""

    _enable_turn_on_off_backwards_compatibility = False

    def __init__(self, client: traeger, grill_id: str, friendly_name: str) -> None:
        super().__init__(client, grill_id)
        self.friendly_name = friendly_name

    # Generic Properties
    @property
    def name(self) -> str:
        """Return the name of the grill"""
        if self.grill_details is None:
            return f"{self.grill_id} {self.friendly_name}"
        name = self.grill_details.friendlyName
        return f"{name} {self.friendly_name}"

    # Climate Properties
    @property
    def temperature_unit(self) -> str:
        """Return the unit of measurement used by the grill."""
        return (
            UnitOfTemperature.CELSIUS
            if self.grill_units == UnitOfTemperature.CELSIUS
            else UnitOfTemperature.FAHRENHEIT
        )

    @property
    def target_temperature_step(self) -> int:
        """Return the supported step of target temperature."""
        return 5

    @property
    def supported_features(self) -> ClimateEntityFeature:
        """Return the list of supported features for the grill"""
        return (
            ClimateEntityFeature.TARGET_TEMPERATURE
            | ClimateEntityFeature.TURN_OFF
            | ClimateEntityFeature.TURN_ON
        )


class TraegerClimateEntity(TraegerBaseClimate):
    """Climate entity for Traeger grills"""

    def __init__(self, client: traeger, grill_id: str, friendly_name: str) -> None:
        super().__init__(client, grill_id, friendly_name)
        self.grill_register_callback()

    @property
    def unique_id(self) -> str:
        """Return the unique id."""
        return f"{self.grill_id}_climate"

    @property
    def icon(self) -> str:
        """Set the default MDI Icon"""
        return "mdi:grill"

    @property
    def available(self) -> bool:
        """Reports unavailable when the grill is powered off"""
        if self.grill_state is None:
            return False
        return self.grill_state.connected

    # Climate Properties
    @property
    def current_temperature(self) -> int:
        """Return the current temperature."""
        if self.grill_state is None:
            return 0
        return self.grill_state.grill

    @property
    def target_temperature(self) -> int:
        """Return the temperature we try to reach."""
        if self.grill_state is None:
            return 0
        return self.grill_state.set

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the extra state attributes."""
        attributes = {}
        if self.grill_state:
            custom_attributes = {
                "grill_native_cur_val": self.grill_state.grill,
                "grill_native_set_val": self.grill_state.set,
            }
            attributes.update(custom_attributes)
        return attributes

    @property
    def max_temp(self) -> int:
        """Return the maximum temperature."""
        if self.grill_limits is None:
            return self.min_temp
        return self.grill_limits.max_grill_temp

    @property
    def min_temp(self) -> int:
        """Return the minimum temperature."""
        if self.grill_units == UnitOfTemperature.CELSIUS:
            return GRILL_MIN_TEMP_C
        return GRILL_MIN_TEMP_F

    @property
    def hvac_mode(self) -> HVACMode:
        """Return HVAC operation mode (heat, cool, off)."""
        if self.grill_state is None:
            return HVACMode.OFF

        state = self.grill_state.system_status
        return GRILL_MODE_TO_HVAC_MODE.get(state, HVACMode.OFF)

    @property
    def hvac_modes(self) -> list[HVACMode]:
        """Return the list of available hvac operation modes."""
        return [HVACMode.HEAT, HVACMode.OFF, HVACMode.COOL]

    # Climate Methods
    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set new target temperature."""
        if self.grill_state is None:
            return
        state = self.grill_state.system_status
        if GrillMode.IGNITING <= state <= GrillMode.CUSTOM_COOK:
            if temperature := kwargs.get(ATTR_TEMPERATURE):
                await self.client.set_temperature(self.grill_id, round(float(temperature)))
            return
        raise NotImplementedError("Set Temp not supported in current state.")

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Start grill shutdown sequence"""
        if self.grill_state is None:
            return
        state = self.grill_state.system_status
        if (
            hvac_mode in (HVACMode.OFF, HVACMode.COOL)
            and GrillMode.IGNITING <= state <= GrillMode.CUSTOM_COOK
        ):
            await self.client.shutdown_grill(self.grill_id)
            return
        raise NotImplementedError(
            "Set HVAC mode not supported in current state.")


class AccessoryTraegerClimateEntity(TraegerBaseClimate):
    """Climate entity for Traeger grills"""

    def __init__(self, client: traeger, grill_id: str, sensor_id: str) -> None:
        super().__init__(client, grill_id, f"Probe {sensor_id}")
        self.sensor_id = sensor_id
        self.grill_accessory = self.client.get_details_for_accessory(
            self.grill_id, self.sensor_id)
        self.current_preset_mode = PRESET_NONE

        # Tell the Traeger client to call grill_accessory_update() when it gets an update
        self.client.set_callback_for_grill(
            self.grill_id, self.grill_accessory_update)

    def grill_accessory_update(self) -> None:
        """This gets called when the grill has an update. Update state variable"""
        self.grill_refresh_state()
        self.grill_accessory = self.client.get_details_for_accessory(
            self.grill_id, self.sensor_id)

        if self.hass is None:
            return

        # Tell HA we have an update
        self.schedule_update_ha_state()

    # Generic Properties
    @property
    def available(self) -> bool:
        """Reports unavailable when the grill is powered off"""
        if (
            self.grill_state is None
            or self.grill_state.connected is False
            or self.grill_accessory is None
        ):
            return False
        return self.grill_accessory.con == 1

    @property
    def unique_id(self) -> str:
        """Return the unique id."""
        return f"{self.grill_id}_probe_{self.sensor_id}"

    @property
    def icon(self) -> str:
        """Set the default MDI Icon"""
        return "mdi:thermometer"

    # Climate Properties
    @property
    def current_temperature(self) -> int:
        """Return the current temperature."""
        if self.grill_accessory is None:
            return 0
        acc_type = self.grill_accessory.type
        acc = getattr(self.grill_accessory, acc_type)
        return int(acc.get_temp)

    @property
    def target_temperature(self) -> int:
        """Return the temperature we try to reach."""
        if self.grill_accessory is None:
            return 0
        acc_type = self.grill_accessory.type
        acc = getattr(self.grill_accessory, acc_type)
        return int(acc.set_temp)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the extra state attributes."""
        if self.grill_accessory is None:
            return {}
        acc_type = self.grill_accessory.type
        acc = getattr(self.grill_accessory, acc_type)
        custom_attributes = {
            "grill_native_cur_val": acc.get_temp,
            "grill_native_set_val": acc.set_temp,
        }
        attributes = {}
        attributes.update(custom_attributes)
        return attributes

    @property
    def max_temp(self) -> int:
        """Return the maximum temperature."""
        # this was the max the traeger would let me set
        return 100 if self.grill_units == UnitOfTemperature.CELSIUS else 215

    @property
    def min_temp(self) -> int:
        """Return the minimum temperature."""
        # this was the min the traeger would let me set
        return 27 if self.grill_units == UnitOfTemperature.CELSIUS else 80

    @property
    def hvac_mode(self) -> HVACMode:
        """
        Return hvac operation ie. heat, cool mode.
        Need to be one of HVAC_MODE_*.
        """
        return (
            HVACMode.HEAT
            if self.grill_accessory and self.grill_accessory.con == 1
            else HVACMode.OFF
        )

    @property
    def hvac_modes(self) -> list[HVACMode]:
        """
        Return the list of available hvac operation modes.
        Need to be a subset of HVAC_MODES.
        """
        return [HVACMode.HEAT, HVACMode.OFF]

    @property
    def preset_mode(self) -> str:
        """Return the current preset mode, e.g., home, away, temp."""
        if (
            self.grill_state is None
            or self.grill_state.probe_con == 0
            or self.target_temperature == 0
        ):
            # Reset current preset mode
            self.current_preset_mode = PRESET_NONE

        return self.current_preset_mode

    @property
    def preset_modes(self) -> list[str]:
        """Return a list of available preset modes."""
        return list(PROBE_PRESET_MODES.keys())

    @property
    def supported_features(self) -> ClimateEntityFeature:
        """Return the list of supported features for the grill"""
        return (
            ClimateEntityFeature.TARGET_TEMPERATURE
            | ClimateEntityFeature.PRESET_MODE
            | ClimateEntityFeature.TURN_OFF
            | ClimateEntityFeature.TURN_ON
        )

    # Climate Methods
    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set new target temperature."""
        self.current_preset_mode = PRESET_NONE
        if temperature := kwargs.get(ATTR_TEMPERATURE):
            await self.client.set_probe_temperature(self.grill_id, round(float(temperature)))

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Start grill shutdown sequence"""
        if hvac_mode in (HVACMode.OFF, HVACMode.COOL):
            raise NotImplementedError(
                "HVAC Mode is determined based on the probe being plugged in."
            )

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        """Set new target preset mode"""
        self.current_preset_mode = preset_mode
        temperature = PROBE_PRESET_MODES[preset_mode][self.grill_units]
        await self.client.set_probe_temperature(self.grill_id, round(temperature))
