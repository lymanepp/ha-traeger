"""Binary Sensor platform for Traeger."""

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import TraegerData
from .entity import TraegerBaseEntity
from .traeger import traeger


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry[TraegerData], async_add_entities: AddEntitiesCallback
) -> bool:
    """Setup Binary Sensor platform."""
    client = entry.runtime_data.client
    assert client is not None
    grills = client.get_grills()
    for grill in grills:
        async_add_entities(
            [
                TraegerTimer(client, grill.thingName,
                             "Cook Timer Complete", "cook_timer_complete"),
                TraegerProbe(client, grill.thingName,
                             "Probe Alarm Fired", "probe_alarm_fired"),
            ]
        )
    return True


class TraegerBaseSensor(TraegerBaseEntity):
    """Base Binary Sensor Class Common to All"""

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
        return f"{self.grill_details.friendlyName} {self.friendly_name}"

    @property
    def unique_id(self) -> str:
        """Return the unique id."""
        return f"{self.grill_id}_{self.value}"

    # Sensor Properties
    @property
    def state(self) -> Any:
        """Return the state of the binary sensor."""
        return getattr(self.grill_state, self.value)


class TraegerTimer(TraegerBaseSensor):
    """Binary Sensor Specific to Timer"""

    # Generic Properties
    @property
    def icon(self) -> str:
        """Set the default MDI Icon"""
        return "mdi:timer"


class TraegerProbe(TraegerBaseSensor):
    """Binary Sensor Specific to Probe"""

    # Generic Properties
    @property
    def icon(self) -> str:
        """Set the default MDI Icon"""
        return "mdi:thermometer"
