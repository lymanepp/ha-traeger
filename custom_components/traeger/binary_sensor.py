"""Binary Sensor platform for Traeger."""

from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import TraegerConfigEntry
from .entity import TraegerBaseEntity


async def async_setup_entry(hass: HomeAssistant, entry: TraegerConfigEntry, async_add_entities: AddEntitiesCallback):
    """Setup Binary Sensor platform."""
    client = entry.runtime_data.client
    grills = client.get_grills()
    for grill in grills:
        async_add_entities([
            TraegerTimer(client, grill["thingName"], "Cook Timer Complete",
                         "cook_timer_complete"),
            TraegerProbe(client, grill["thingName"], "Probe Alarm Fired",
                         "probe_alarm_fired")
        ])


class TraegerBaseSensor(TraegerBaseEntity):
    """Base Binary Sensor Class Common to All"""

    def __init__(self, client, grill_id, friendly_name, value):
        super().__init__(client, grill_id)
        self.value = value
        self.friendly_name = friendly_name
        self.grill_register_callback()

    # Generic Properties
    @property
    def available(self):
        """Reports unavailable when the grill is powered off"""
        if self.grill_state is None:
            return False
        return self.grill_state["connected"]

    @property
    def name(self):
        """Return the name of the grill"""
        if self.grill_details is None:
            return f"{self.grill_id} {self.friendly_name}"
        name = self.grill_details["friendlyName"]
        return f"{name} {self.friendly_name}"

    @property
    def unique_id(self):
        """Return the unique id."""
        return f"{self.grill_id}_{self.value}"

    # Sensor Properties
    @property
    def state(self):
        """Return the state of the binary sensor."""
        return self.grill_state[self.value]


class TraegerTimer(TraegerBaseSensor):
    """Binary Sensor Specific to Timer"""
    # Generic Properties
    @property
    def icon(self):
        """Set the default MDI Icon"""
        return "mdi:timer"


class TraegerProbe(TraegerBaseSensor):
    """Binary Sensor Specific to Probe"""
    # Generic Properties
    @property
    def icon(self):
        """Set the default MDI Icon"""
        return "mdi:thermometer"
