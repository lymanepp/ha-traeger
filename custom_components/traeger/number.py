"""Number/Timer platform for Traeger."""

import asyncio
import logging
import re
from typing import Any

from homeassistant.components.number import NumberEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import entity_platform
from homeassistant.helpers.entity_platform import AddEntitiesCallback
import voluptuous as vol

from . import TraegerData
from .entity import TraegerBaseEntity
from .model import GrillMode
from .traeger import traeger

SERVICE_CUSTOMCOOK = "set_custom_cook"
ENTITY_ID = "entity_id"
SCHEMA_CUSTOMCOOK = {
    vol.Required(ENTITY_ID): cv.string,
    vol.Required("steps", default=dict): list,
}

_LOGGER: logging.Logger = logging.getLogger(__package__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry[TraegerData], async_add_entities: AddEntitiesCallback
) -> bool:
    """
    Setup Number/Timer platform.
    Setup Service platform.
    """
    if (platform := entity_platform.current_platform.get()) is None:
        return False

    platform.async_register_entity_service(SERVICE_CUSTOMCOOK, SCHEMA_CUSTOMCOOK, "set_custom_cook")
    client = entry.runtime_data.client
    grills = client.get_grills()
    for grill in grills:
        async_add_entities(
            [
                TraegerNumberEntity(client, grill.thingName, "cook_timer"),
                CookCycNumberEntity(client, grill.thingName, "cook_cycle", hass),
            ]
        )
    return True


class CookCycNumberEntity(NumberEntity, TraegerBaseEntity):
    """Traeger Number/Timer Value class."""

    def __init__(self, client: traeger, grill_id: str, devname: str, hass: HomeAssistant) -> None:
        super().__init__(client, grill_id)
        self.devname = devname
        self.num_value = 0
        self.old_num_value = 0
        self.cook_cycle: list[Any] = []
        self.hass = hass
        self.grill_register_callback()

    # Generic Properties
    @property
    def name(self) -> str:
        """Return the name of the grill"""
        if self.grill_details is None:
            return f"{self.grill_id}_{self.devname}"
        name = self.grill_details.friendlyName
        return f"{name} {self.devname.capitalize()}"

    @property
    def unique_id(self) -> str:
        """Return the unique id."""
        return f"{self.grill_id}_{self.devname}"

    @property
    def icon(self) -> str:
        """Set the default MDI Icon"""
        return "mdi:chef-hat"

    @property
    def native_step(self) -> int:
        """Return the supported step."""
        return 1

    # Value Properties
    @property
    def native_value(self) -> int:
        """
        Return the value reported by the number.
        This also serves the cook cycle.
        """
        # pylint: disable=too-many-branches,too-many-statements
        if self.grill_state is None:
            self.num_value = 0
            return self.num_value
        if self.num_value > len(self.cook_cycle):
            _LOGGER.info("B.Cook Cycles out of indexes.")
            self.num_value = 0
            return self.num_value
        if self.num_value > 0 and self.grill_state.system_status in [
            GrillMode.COOL_DOWN,
            GrillMode.SLEEPING,
            GrillMode.SHUTDOWN,
            GrillMode.IDLE,
        ]:
            _LOGGER.info("Steps not available when not cooking. Revert to 0.")
            self.num_value = 0
            return self.num_value
        ########################################################################
        # Scan for next step advance
        if self.num_value > 0 and self.num_value == self.old_num_value:
            curstep = self.cook_cycle[self.num_value - 1]
            if "use_timer" in curstep:
                if curstep.use_timer:
                    if self.grill_state.cook_timer_complete:
                        self.num_value = self.num_value + 1
            elif self.grill_state.probe_alarm_fired:
                self.num_value = self.num_value + 1
            elif "act_temp_adv" in curstep:
                if self.grill_state.grill > curstep.act_temp_adv:
                    self.num_value = self.num_value + 1
            elif "probe_act_temp_adv" in curstep:
                if self.grill_state.probe > curstep.probe_act_temp_adv:
                    self.num_value = self.num_value + 1
            ####################################################################
            # In step change
            if "min_delta" in curstep and "max_grill_delta_temp" in curstep:
                if (
                    self.grill_limits
                    and curstep.max_grill_delta_temp > self.grill_limits.max_grill_temp
                ):
                    curstep.max_grill_delta_temp = self.grill_limits.max_grill_temp
                if self.grill_state.set < curstep.max_grill_delta_temp:
                    if self.grill_state.probe > self.grill_state.set - curstep.min_delta:
                        set_temp = self.grill_state.set + 5
                        self.hass.async_create_task(
                            self.hass.services.async_call(
                                "climate",
                                "set_temperature",
                                {
                                    "entity_id": f"climate.{self.grill_id}_climate",
                                    "temperature": round(set_temp),
                                },
                                False,
                            )
                        )
        ########################################################################
        # Implement next step
        # Only hit once per step.
        if self.num_value > 0 and self.num_value != self.old_num_value:
            curstep = self.cook_cycle[self.num_value - 1]
            if "time_set" in curstep:
                self.hass.async_create_task(
                    self.hass.services.async_call(
                        "number",
                        "set_value",
                        {
                            "entity_id": f"number.{self.grill_id}_cook_timer",
                            "value": round(curstep.time_set),
                        },
                        False,
                    )
                )
            if "probe_set_temp" in curstep:
                self.hass.async_create_task(
                    self.hass.services.async_call(
                        "climate",
                        "set_temperature",
                        {
                            "entity_id": f"climate.{self.grill_id}_probe_p0",
                            "temperature": round(curstep.probe_set_temp),
                        },
                        False,
                    )
                )
            if "set_temp" in curstep:
                self.hass.async_create_task(
                    self.hass.services.async_call(
                        "climate",
                        "set_temperature",
                        {
                            "entity_id": f"climate.{self.grill_id}_climate",
                            "temperature": round(curstep.set_temp),
                        },
                        False,
                    )
                )
            if "smoke" in curstep:
                if (
                    self.grill_features
                    and self.grill_features.super_smoke_enabled == 1
                    and self.grill_state.smoke != curstep.smoke
                    and self.grill_state.set <= 225
                ):
                    if curstep.smoke == 1:
                        self.hass.async_create_task(
                            self.hass.services.async_call(
                                "switch",
                                "turn_on",
                                {"entity_id": f"switch.{self.grill_id}_smoke"},
                                False,
                            )
                        )
                    else:
                        self.hass.async_create_task(
                            self.hass.services.async_call(
                                "switch",
                                "turn_off",
                                {"entity_id": f"switch.{self.grill_id}_smoke"},
                                False,
                            )
                        )
            if "keepwarm" in curstep:
                if self.grill_state.keepwarm != curstep.keepwarm:
                    if curstep.keepwarm == 1:
                        self.hass.async_create_task(
                            self.hass.services.async_call(
                                "switch",
                                "turn_on",
                                {"entity_id": f"switch.{self.grill_id}_keepwarm"},
                                False,
                            )
                        )
                    else:
                        self.hass.async_create_task(
                            self.hass.services.async_call(
                                "switch",
                                "turn_off",
                                {"entity_id": f"switch.{self.grill_id}_keepwarm"},
                                False,
                            )
                        )
            if "shutdown" in curstep:
                if curstep.shutdown == 1:
                    self.hass.async_create_task(
                        self.hass.services.async_call(
                            "climate",
                            "set_hvac_mode",
                            {
                                "entity_id": f"climate.{self.grill_id}_climate",
                                "hvac_mode": "cool",
                            },
                            False,
                        )
                    )
                    self.num_value = 0
        self.old_num_value = self.num_value
        _LOGGER.debug("CookCycle Steps:%s", self.cook_cycle)
        if self.num_value > len(self.cook_cycle):
            _LOGGER.info("A.Cook Cycles out of indexes.")
            self.num_value = 0
        return self.num_value

    @property
    def native_min_value(self) -> int:
        """Return the minimum value."""
        return 0

    @property
    def native_max_value(self) -> int:
        """Return the maximum value."""
        return 999

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the optional state attributes."""
        # default_attributes = super().state_attributes
        prev_step = ""
        curr_step = ""
        next_step = ""
        if self.num_value > 1:
            prev_step = f"{self.num_value - 1}: {self.cook_cycle[self.num_value - 2]}"
        if self.num_value > 0:
            curr_step = f"{self.num_value}: {self.cook_cycle[self.num_value - 1]}"
        if self.num_value < len(self.cook_cycle):
            next_step = f"{self.num_value + 1}: {self.cook_cycle[self.num_value]}"
        custom_attributes = {
            "prev_step": prev_step,
            "curr_step": curr_step,
            "next_step": next_step,
        }
        intstep = 1
        for step in self.cook_cycle:
            custom_attributes[f"_step{intstep:02d}"] = str(step)
            intstep += 1
        attributes = {}
        attributes.update(custom_attributes)
        return attributes

    # Value Set Method
    async def async_set_native_value(self, value: float) -> None:
        """Set new Val and callback to update value above."""
        self.num_value = round(value)
        # Need to call callback now so that it fires step #1 or commanded step immediatlly.
        await self.client.grill_callback(self.grill_id)

    # Receive Custom Cook Command
    def set_custom_cook(self, **kwargs: Any) -> None:
        """From Service, Update the number's cook cycle steps."""
        self.cook_cycle = kwargs["steps"]
        _LOGGER.info("Traeger: Set Cook Cycle:%s", self.cook_cycle)
        # Need to call callback now so that it fires state cust atrib update.
        asyncio.run_coroutine_threadsafe(self.client.grill_callback(self.grill_id), self.hass.loop)


class TraegerNumberEntity(NumberEntity, TraegerBaseEntity):
    """Traeger Number/Timer Value class."""

    def __init__(self, client: traeger, grill_id: str, devname: str) -> None:
        super().__init__(client, grill_id)
        self.devname = devname
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
            return f"{self.grill_id}_{self.devname}"
        name = self.grill_details.friendlyName
        return f"{name} {self.devname.capitalize()}"

    @property
    def unique_id(self) -> str:
        """Return the unique id."""
        return f"{self.grill_id}_{self.devname}"

    @property
    def icon(self) -> str:
        """Set the default MDI Icon"""
        return "mdi:timer"

    @property
    def native_step(self) -> int:
        """Return the supported step."""
        return 1

    # Timer Properties
    @property
    def native_value(self) -> float:
        """Return the value reported by the number."""
        if self.grill_state is None:
            return 0
        end_time: float = getattr(self.grill_state, f"{self.devname}_end")
        start_time: float = getattr(self.grill_state, f"{self.devname}_start")
        tot_time = (end_time - start_time) / 60
        return tot_time

    @property
    def native_min_value(self) -> int:
        """Return the minimum value."""
        return 0

    @property
    def native_max_value(self) -> int:
        """Return the maximum value."""
        return 1440

    @property
    def native_unit_of_measurement(self) -> str:
        """Return the unit of measurement of the entity, if any."""
        return "min"

    # Timer Methods
    async def async_set_native_value(self, value: float) -> None:
        """Set new Timer Val."""
        if self.grill_state is None:
            return
        state = self.grill_state.system_status
        if GrillMode.IGNITING <= state <= GrillMode.CUSTOM_COOK:
            if value >= 1:
                await self.client.set_timer_sec(self.grill_id, (round(value) * 60))
            else:
                await self.client.reset_timer(self.grill_id)
            return
        raise NotImplementedError("Set Timer not supported in current state.")
