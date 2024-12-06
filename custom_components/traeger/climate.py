"""Climate platform for Traeger grills"""
from homeassistant.components.climate import (
    PRESET_NONE,
    ClimateEntity,
    ClimateEntityFeature,
    HVACMode,
)
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import TraegerConfigEntry
from .const import GRILL_MIN_TEMP_C, GRILL_MIN_TEMP_F, PROBE_PRESET_MODES, GrillMode
from .entity import TraegerBaseEntity, TraegerGrillMonitor
from .traeger import traeger


async def async_setup_entry(hass: HomeAssistant, entry: TraegerConfigEntry, async_add_entities: AddEntitiesCallback):
    """Setup climate platform."""
    client = entry.runtime_data.client
    grills = client.get_grills()
    for grill in grills:
        grill_id = grill["thingName"]
        async_add_entities([TraegerClimateEntity(client, grill_id, "Climate")])
        TraegerGrillMonitor(client, grill_id, async_add_entities,
                            AccessoryTraegerClimateEntity)


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

    def __init__(self, client, grill_id, friendly_name):
        super().__init__(client, grill_id)
        self.friendly_name = friendly_name

    # Generic Properties
    @property
    def name(self):
        """Return the name of the grill"""
        if self.grill_details is None:
            return f"{self.grill_id} {self.friendly_name}"
        name = self.grill_details["friendlyName"]
        return f"{name} {self.friendly_name}"

    # Climate Properties
    @property
    def temperature_unit(self):
        """Return the unit of measurement used by the grill."""
        if self.grill_units == UnitOfTemperature.CELSIUS:
            return UnitOfTemperature.CELSIUS
        return UnitOfTemperature.FAHRENHEIT

    @property
    def target_temperature_step(self):
        """Return the supported step of target temperature."""
        return 5

    @property
    def supported_features(self):
        """Return the list of supported features for the grill"""
        return (ClimateEntityFeature.TARGET_TEMPERATURE |
                ClimateEntityFeature.TURN_OFF | ClimateEntityFeature.TURN_ON)


class TraegerClimateEntity(TraegerBaseClimate):
    """Climate entity for Traeger grills"""

    def __init__(self, client: traeger, grill_id: str, friendly_name: str):
        super().__init__(client, grill_id, friendly_name)
        self.grill_register_callback()

    @property
    def unique_id(self):
        """Return the unique id."""
        return f"{self.grill_id}_climate"

    @property
    def icon(self):
        """Set the default MDI Icon"""
        return "mdi:grill"

    @property
    def available(self):
        """Reports unavailable when the grill is powered off"""
        if self.grill_state is None:
            return False
        return self.grill_state["connected"]

    # Climate Properties
    @property
    def current_temperature(self):
        """Return the current temperature."""
        if self.grill_state is None:
            return 0
        return self.grill_state["grill"]

    @property
    def target_temperature(self):
        """Return the temperature we try to reach."""
        if self.grill_state is None:
            return 0
        return self.grill_state["set"]

    @property
    def extra_state_attributes(self):
        """Return the extra state attributes."""
        custom_attributes = {
            "grill_native_cur_val": self.grill_state["grill"],
            "grill_native_set_val": self.grill_state["set"],
        }
        attributes = {}
        attributes.update(custom_attributes)
        return attributes

    @property
    def max_temp(self):
        """Return the maximum temperature."""
        if self.grill_limits is None:
            return self.min_temp
        return self.grill_limits["max_grill_temp"]

    @property
    def min_temp(self):
        """Return the minimum temperature."""
        if self.grill_units == UnitOfTemperature.CELSIUS:
            return GRILL_MIN_TEMP_C
        return GRILL_MIN_TEMP_F

    @property
    def hvac_mode(self):
        """Return HVAC operation mode (heat, cool, off). Must be member of HVACMode."""
        if self.grill_state is None:
            return HVACMode.OFF

        state = self.grill_state["system_status"]
        return GRILL_MODE_TO_HVAC_MODE.get(state, HVACMode.OFF)

    @property
    def hvac_modes(self):
        """
        Return the list of available hvac operation modes.
        Need to be a subset of HVAC_MODES.
        """
        return (HVACMode.HEAT, HVACMode.OFF, HVACMode.COOL)

    # Climate Methods
    async def async_set_temperature(self, **kwargs):
        """Set new target temperature."""
        if self.grill_state is None:
            return
        state = self.grill_state["system_status"]
        if GrillMode.IGNITING <= state <= GrillMode.CUSTOM_COOK:
            temperature = kwargs.get(ATTR_TEMPERATURE)
            await self.client.set_temperature(self.grill_id, round(temperature))
            return
        raise NotImplementedError("Set Temp not supported in current state.")

    async def async_set_hvac_mode(self, hvac_mode):
        """Start grill shutdown sequence"""
        if self.grill_state is None:
            return
        state = self.grill_state["system_status"]
        if (hvac_mode in (HVACMode.OFF, HVACMode.COOL) and
                GrillMode.IGNITING <= state <= GrillMode.CUSTOM_COOK):
            await self.client.shutdown_grill(self.grill_id)
            return
        raise NotImplementedError(
            "Set HVAC mode not supported in current state.")


class AccessoryTraegerClimateEntity(TraegerBaseClimate):
    """Climate entity for Traeger grills"""

    def __init__(self, client, grill_id, sensor_id):
        super().__init__(client, grill_id, f"Probe {sensor_id}")
        self.sensor_id = sensor_id
        self.grill_accessory = self.client.get_details_for_accessory(
            self.grill_id, self.sensor_id)
        self.current_preset_mode = PRESET_NONE

        # Tell the Traeger client to call grill_accessory_update() when it gets an update
        self.client.set_callback_for_grill(self.grill_id,
                                           self.grill_accessory_update)

    def grill_accessory_update(self):
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
    def available(self):
        """Reports unavailable when the grill is powered off"""
        if (self.grill_state is None or
                self.grill_state["connected"] is False or
                self.grill_accessory is None):
            return False
        return self.grill_accessory["con"]

    @property
    def unique_id(self):
        """Return the unique id."""
        return f"{self.grill_id}_probe_{self.sensor_id}"

    @property
    def icon(self):
        """Set the default MDI Icon"""
        return "mdi:thermometer"

    # Climate Properties
    @property
    def current_temperature(self):
        """Return the current temperature."""
        if self.grill_accessory is None:
            return 0
        acc_type = self.grill_accessory["type"]
        return self.grill_accessory[acc_type]["get_temp"]

    @property
    def target_temperature(self):
        """Return the temperature we try to reach."""
        if self.grill_accessory is None:
            return 0
        acc_type = self.grill_accessory["type"]
        return self.grill_accessory[acc_type]["set_temp"]

    @property
    def extra_state_attributes(self):
        """Return the extra state attributes."""
        if self.grill_accessory is None:
            return 0
        acc_type = self.grill_accessory["type"]
        custom_attributes = {
            "grill_native_cur_val": self.grill_accessory[acc_type]["get_temp"],
            "grill_native_set_val": self.grill_accessory[acc_type]["set_temp"],
        }
        attributes = {}
        attributes.update(custom_attributes)
        return attributes

    @property
    def max_temp(self):
        """Return the maximum temperature."""
        # this was the max the traeger would let me set
        return 100 if self.grill_units == UnitOfTemperature.CELSIUS else 215

    @property
    def min_temp(self):
        """Return the minimum temperature."""
        # this was the min the traeger would let me set
        return 27 if self.grill_units == UnitOfTemperature.CELSIUS else 80

    @property
    def hvac_mode(self):
        """
        Return hvac operation ie. heat, cool mode.
        Need to be one of HVAC_MODE_*.
        """
        if self.grill_state is None:
            return HVACMode.OFF

        state = self.grill_accessory["con"]

        if state == 1:  # Probe Connected
            return HVACMode.HEAT
        return HVACMode.OFF

    @property
    def hvac_modes(self):
        """
        Return the list of available hvac operation modes.
        Need to be a subset of HVAC_MODES.
        """
        return (HVACMode.HEAT, HVACMode.OFF)

    @property
    def preset_mode(self):
        """Return the current preset mode, e.g., home, away, temp."""
        if (self.grill_state is None or self.grill_state["probe_con"] == 0 or
                self.target_temperature == 0):
            # Reset current preset mode
            self.current_preset_mode = PRESET_NONE

        return self.current_preset_mode

    @property
    def preset_modes(self):
        """Return a list of available preset modes."""
        return list(PROBE_PRESET_MODES.keys())

    @property
    def supported_features(self):
        """Return the list of supported features for the grill"""
        return (ClimateEntityFeature.TARGET_TEMPERATURE |
                ClimateEntityFeature.PRESET_MODE |
                ClimateEntityFeature.TURN_OFF | ClimateEntityFeature.TURN_ON)

    # Climate Methods
    async def async_set_temperature(self, **kwargs):
        """Set new target temperature."""
        self.current_preset_mode = PRESET_NONE
        temperature = kwargs.get(ATTR_TEMPERATURE)
        await self.client.set_probe_temperature(self.grill_id,
                                                round(temperature))

    async def async_set_hvac_mode(self, hvac_mode):
        """Start grill shutdown sequence"""
        if hvac_mode in (HVACMode.OFF, HVACMode.COOL):
            raise NotImplementedError(
                "HVAC Mode is determined based on the probe being plugged in.")

    async def async_set_preset_mode(self, preset_mode):
        """Set new target preset mode"""
        self.current_preset_mode = preset_mode
        temperature = PROBE_PRESET_MODES[preset_mode][self.grill_units]
        await self.client.set_probe_temperature(self.grill_id,
                                                round(temperature))
