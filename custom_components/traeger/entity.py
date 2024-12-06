"""TraegerBaseEntity class"""
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import ATTRIBUTION, DOMAIN, NAME
from .traeger import traeger


class TraegerBaseEntity(Entity):  # pylint: disable=too-many-instance-attributes
    """Traeger BaseEntity Class."""

    def __init__(self, client, grill_id):
        super().__init__()
        self.grill_id = grill_id
        self.client = client
        self.grill_refresh_state()

    def grill_refresh_state(self):
        """Wrapper to parse different parse of Grill MQTT Response"""
        self.grill_state = self.client.get_state_for_device(self.grill_id)
        self.grill_units = self.client.get_units_for_device(self.grill_id)
        self.grill_details = self.client.get_details_for_device(self.grill_id)
        self.grill_features = self.client.get_features_for_device(
            self.grill_id)
        self.grill_settings = self.client.get_settings_for_device(
            self.grill_id)
        self.grill_limits = self.client.get_limits_for_device(self.grill_id)
        self.grill_cloudconnect = self.client.get_cloudconnect(self.grill_id)

    def grill_register_callback(self):
        """Tell the Traeger client to call grill_update() when it gets an update"""
        self.client.set_callback_for_grill(self.grill_id,
                                           self.grill_update_internal)

    def grill_update_internal(self):
        """Internal HA Update"""
        self.grill_refresh_state()

        if self.hass is None:
            return

        # Tell HA we have an update
        self.schedule_update_ha_state()

    @property
    def unique_id(self):
        """Return the unique id."""
        return self.grill_id

    @property
    def should_poll(self):
        """Return the polling state."""
        return False

    @property
    def device_info(self):
        """Return a device description for device registry."""
        if self.grill_settings is None:
            return {
                "identifiers": {(DOMAIN, self.grill_id)},
                "name": NAME,
                "manufacturer": NAME
            }

        return {
            "identifiers": {(DOMAIN, self.grill_id)},
            "name": self.grill_details["friendlyName"],
            "model": self.grill_settings["device_type_id"],
            "sw_version": self.grill_settings["fw_version"],
            "manufacturer": NAME
        }

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        return {
            "attribution": ATTRIBUTION,
            "integration": DOMAIN,
        }


class TraegerGrillMonitor:
    """TraegerGrillMonitor Class."""

    def __init__(self, client: traeger, grill_id: str, async_add_entities: AddEntitiesCallback, probe_entity=None):
        self.client = client
        self.grill_id = grill_id
        self.async_add_entities = async_add_entities
        self.probe_entity = probe_entity
        self.accessory_status = {}

        self.device_state = self.client.get_state_for_device(self.grill_id)
        self.grill_add_accessories()
        self.client.set_callback_for_grill(self.grill_id,
                                           self.grill_monitor_internal)

    def grill_monitor_internal(self):
        """Internal HA Update"""
        self.device_state = self.client.get_state_for_device(self.grill_id)
        self.grill_add_accessories()

    def grill_add_accessories(self):
        """
        Add acc after Orig Init.
        It would appear the dual probes don't show up instantly.
        """
        if self.device_state is None:
            return
        for accessory in self.device_state["acc"]:
            if accessory["type"] in ["probe", "btprobe", "hob"]:
                if accessory["uuid"] not in self.accessory_status:
                    if self.probe_entity:
                        self.async_add_entities([
                            self.probe_entity(
                                self.client, self.grill_id, accessory["uuid"])
                        ])
                        self.accessory_status[accessory["uuid"]] = True
