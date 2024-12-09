"""Sensor platform for Traeger."""

from typing import Any, cast

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import StateType

from . import TraegerData
from .const import GRILL_MIN_TEMP_C, GRILL_MIN_TEMP_F
from .entity import TraegerBaseEntity, TraegerGrillMonitor
from .model import GrillMode
from .traeger import traeger

GRILL_MODE_MAPPING = {
    GrillMode.COOL_DOWN: "cool_down",
    GrillMode.CUSTOM_COOK: "cook_custom",
    GrillMode.MANUAL_COOK: "cook_manual",
    GrillMode.PREHEATING: "preheating",
    GrillMode.IGNITING: "igniting",
    GrillMode.IDLE: "idle",
    GrillMode.SLEEPING: "sleeping",
    GrillMode.OFFLINE: "offline",
    GrillMode.SHUTDOWN: "shutdown",
}


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry[TraegerData], async_add_entities: AddEntitiesCallback
) -> bool:
    """Setup sensor platform."""
    client = entry.runtime_data.client
    grills = client.get_grills()
    for grill in grills:
        grill_id = grill.thingName
        async_add_entities(
            [
                PelletSensor(client, grill_id, "Pellet Level", "pellet_level"),
                ValueTemperature(client, grill_id, "Ambient Temperature", "ambient"),
                GrillTimer(client, grill_id, "Cook Timer Start", "cook_timer_start"),
                GrillTimer(client, grill_id, "Cook Timer End", "cook_timer_end"),
                GrillState(client, grill_id, "Grill State", "grill_state"),
                HeatingState(client, grill_id, "Heating State", "heating_state"),
            ]
        )
        TraegerGrillMonitor(client, grill_id, async_add_entities, ProbeState)
    return True


class TraegerBaseSensor(TraegerBaseEntity, SensorEntity):
    """Base Sensor Class Common to All"""

    def __init__(self, client: traeger, grill_id: str, friendly_name: str, value: str) -> None:
        super().__init__(client, grill_id)
        self.value = value
        self.friendly_name = friendly_name
        self.grill_register_callback()

    # Generic Properties
    @property
    def available(self) -> bool:
        """Reports unavailable when the grill is powered off"""
        return bool(self.grill_state and self.grill_state.connected)

    @property
    def name(self) -> str:
        """Return the name of the grill"""
        if self.grill_details is None:
            return f"{self.grill_id} {self.friendly_name}"
        name = self.grill_details.friendlyName
        return f"{name} {self.friendly_name}"

    @property
    def unique_id(self) -> str:
        """Return the unique id."""
        return f"{self.grill_id}_{self.value}"

    # Sensor Properties
    @property
    def native_value(self) -> Any:
        """Return the current state of entity."""
        return getattr(self.grill_state, self.value, None)


class ValueTemperature(TraegerBaseSensor):
    """Traeger Temperature Value class."""

    # Generic Properties
    @property
    def icon(self) -> str:
        """Set the default MDI Icon"""
        return "mdi:thermometer"

    # Sensor Properties
    @property
    def native_unit_of_measurement(self) -> str:
        """Return the unit the value is expressed in."""
        return self.grill_units

    # Sensor Properties
    @property
    def device_class(self) -> SensorDeviceClass:
        """Return the class of the sensor"""
        return SensorDeviceClass.TEMPERATURE

    # Sensor Properties
    @property
    def suggested_unit_of_measurement(self) -> str:
        """Return the suggested UOM"""
        return self.grill_units


class PelletSensor(TraegerBaseSensor):
    """Traeger Pellet Sensor class."""

    # Generic Properties
    @property
    def available(self) -> bool:
        """Reports unavailable when the pellet sensor is not connected"""
        return bool(self.grill_features and self.grill_features.pellet_sensor_connected == 1)

    @property
    def icon(self) -> str:
        """Set the default MDI Icon"""
        return "mdi:gauge"

    # Sensor Properties
    @property
    def native_unit_of_measurement(self) -> str:
        """Return the unit the value is expressed in."""
        return PERCENTAGE


class GrillTimer(TraegerBaseSensor):
    """Traeger Timer class."""

    # Generic Properties
    @property
    def icon(self) -> str:
        """Set the default MDI Icon"""
        return "mdi:timer"

    # Sensor Properties
    @property
    def native_unit_of_measurement(self) -> str:
        """Return the unit the value is expressed in."""
        return "sec"


class GrillState(TraegerBaseSensor):
    """
    Traeger Grill State class.
    These states correlate with the Traeger application.
    """

    # Generic Properties
    @property
    def icon(self) -> str:
        """Set the default MDI Icon"""
        return "mdi:grill"

    # Sensor Properties
    @property
    def native_value(self) -> Any:
        """Return the state of the sensor."""
        if self.grill_state is None:
            return "unknown"

        return GRILL_MODE_MAPPING.get(self.grill_state.system_status, "unknown")


class HeatingState(TraegerBaseSensor):
    """Traeger Heating State class."""

    def __init__(self, client: traeger, grill_id: str, friendly_name: str, value: str) -> None:
        super().__init__(client, grill_id, friendly_name, value)
        self.previous_target_temp: int | None = None
        self.previous_state = "idle"
        self.preheat_modes = [GrillMode.PREHEATING, GrillMode.IGNITING]
        self.cook_modes = [GrillMode.CUSTOM_COOK, GrillMode.MANUAL_COOK]

    # Generic Properties
    @property
    def icon(self) -> str:
        """Set the default MDI Icon"""
        if self.state == "over_temp":
            return "mdi:fire-alert"
        return "mdi:fire"

    # Sensor Properties
    @property
    def native_value(self) -> Any:  # pylint: disable=too-many-branches,too-many-statements
        """Return the state of the sensor."""
        if self.grill_state is None:
            return "idle"

        target_temp = self.grill_state.set
        grill_mode = self.grill_state.system_status
        current_temp = self.grill_state.grill
        target_changed = target_temp != self.previous_target_temp
        min_cook_temp = (
            GRILL_MIN_TEMP_C if self.grill_units == UnitOfTemperature.CELSIUS else GRILL_MIN_TEMP_F
        )
        temp_swing = 11 if self.grill_units == UnitOfTemperature.CELSIUS else 20
        low_temp = target_temp - temp_swing
        high_temp = target_temp + temp_swing

        state = "idle"
        if grill_mode in self.preheat_modes:
            state = "preheating" if current_temp < min_cook_temp else "heating"
        elif grill_mode in self.cook_modes:
            if self.previous_state in ("heating", "preheating"):
                state = "at_temp" if current_temp >= target_temp else "heating"
            elif self.previous_state == "cooling":
                state = "at_temp" if current_temp <= target_temp else "cooling"
            elif self.previous_state == "at_temp":
                state = (
                    "over_temp"
                    if current_temp > high_temp
                    else "under_temp" if current_temp < low_temp else "at_temp"
                )
            elif self.previous_state == "under_temp":
                state = "at_temp" if current_temp > low_temp else "under_temp"
            elif self.previous_state == "over_temp":
                state = "at_temp" if current_temp < high_temp else "over_temp"
            # Catch all if coming from idle/unavailable
            else:
                target_changed = True

            if target_changed:
                state = "heating" if current_temp <= target_temp else "cooling"
        elif grill_mode == GrillMode.COOL_DOWN:
            state = "cool_down"

        self.previous_target_temp = target_temp
        self.previous_state = state
        return state


class ProbeState(TraegerBaseSensor):
    """Traeger Probe Heating State class."""

    def __init__(self, client: traeger, grill_id: str, sensor_id: str) -> None:
        super().__init__(client, grill_id, f"Probe State {sensor_id}", f"probe_state_{sensor_id}")
        self.sensor_id = sensor_id
        self.grill_accessory = self.client.get_details_for_accessory(self.grill_id, self.sensor_id)
        self.previous_target_temp = None
        self.probe_alarm = False
        self.active_modes = [
            GrillMode.PREHEATING,
            GrillMode.IGNITING,
            GrillMode.CUSTOM_COOK,
            GrillMode.MANUAL_COOK,
        ]

        # Tell the Traeger client to call grill_accessory_update() when it gets an update
        self.client.set_callback_for_grill(self.grill_id, self.grill_accessory_update)

    def grill_accessory_update(self) -> None:
        """This gets called when the grill has an update. Update state variable"""
        self.grill_refresh_state()
        self.grill_accessory = self.client.get_details_for_accessory(self.grill_id, self.sensor_id)

        if self.hass is None:
            return

        # Tell HA we have an update
        self.schedule_update_ha_state()

    # Generic Properties
    @property
    def available(self) -> bool:
        """Reports unavailable when the probe is not connected"""
        if not self.grill_state or not self.grill_state.connected or not self.grill_accessory:
            # Reset probe alarm if accessory becomes unavailable
            self.probe_alarm = False
            return False
        connected = self.grill_accessory.con
        # Reset probe alarm if accessory is not connected
        if not connected:
            self.probe_alarm = False
        return bool(connected)

    @property
    def unique_id(self) -> str:
        """Return the unique id."""
        return f"{self.grill_id}_probe_state_{self.sensor_id}"

    @property
    def icon(self) -> str:
        """Set the default MDI Icon"""
        return "mdi:thermometer"

    # Sensor Properties
    @property
    def native_value(self) -> Any:
        """Return the state of the sensor."""
        if self.grill_accessory is None:
            return "idle"

        assert self.grill_state is not None

        acc_type = self.grill_accessory.type
        acc = getattr(self.grill_accessory, acc_type)
        # TODO: need to add type here!
        target_temp = acc.set_temp
        probe_temp = acc.get_temp
        target_changed = target_temp != self.previous_target_temp
        grill_mode = self.grill_state.system_status
        fell_out_temp = 102 if self.grill_units == UnitOfTemperature.CELSIUS else 215

        # Latch probe alarm, reset if target changed or grill leaves active modes
        if not hasattr(acc, "alarm_fired"):
            self.probe_alarm = False
        elif getattr(acc, "alarm_fired"):
            self.probe_alarm = True
        elif (target_changed and target_temp != 0) or (grill_mode not in self.active_modes):
            self.probe_alarm = False

        state = "idle"
        if probe_temp >= fell_out_temp:
            state = "fell_out"
        elif self.probe_alarm:
            state = "at_temp"
        elif target_temp != 0 and grill_mode in self.active_modes:
            close_temp = 3 if self.grill_units == UnitOfTemperature.CELSIUS else 5
            state = "close" if probe_temp + close_temp >= target_temp else "set"
        else:
            self.probe_alarm = False

        self.previous_target_temp = target_temp
        return state
