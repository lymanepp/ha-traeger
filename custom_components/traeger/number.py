"""Number/Timer platform for Traeger."""

import asyncio
import logging
from typing import Any

from homeassistant.components.number import NumberEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.entity_platform import AddEntitiesCallback, current_platform
import voluptuous as vol

from . import TraegerData
from .const import GrillMode
from .entity import TraegerBaseEntity
from .model import Step
from .traeger import traeger

SERVICE_CUSTOMCOOK = "set_custom_cook"
ENTITY_ID = "entity_id"
SCHEMA_CUSTOMCOOK = cv.make_entity_service_schema(
    {
        vol.Required(ENTITY_ID): cv.string,
        vol.Required("steps", default=dict): list,
    }
)

_LOGGER: logging.Logger = logging.getLogger(__package__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry[TraegerData], async_add_entities: AddEntitiesCallback
) -> bool:
    """
    Setup Number/Timer platform.
    Setup Service platform.
    """
    if (platform := current_platform.get()) is None:
        return False

    platform.async_register_entity_service(
        SERVICE_CUSTOMCOOK, SCHEMA_CUSTOMCOOK, "set_custom_cook")
    client = entry.runtime_data.client
    assert client is not None
    grills = client.get_grills()
    for grill in grills:
        async_add_entities(
            [
                TraegerNumberEntity(client, grill.thingName, "cook_timer"),
                CookCycNumberEntity(client, grill.thingName,
                                    "cook_cycle", hass),
            ]
        )
    return True


class CookCycNumberEntity(NumberEntity, TraegerBaseEntity):
    """Traeger Number/Timer Value class."""

    def __init__(self, client: traeger, grill_id: str, devname: str, hass: HomeAssistant) -> None:
        super().__init__(client, grill_id)
        self.devname = devname
        self.current_step = 0
        self.previous_step = 0
        self.cook_cycle: list[Step] = []
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

    def set_temperature(self, entity_id: str, temperature: int) -> None:
        """Helper function to create temperature setting tasks"""
        self.hass.async_create_task(
            self.hass.services.async_call(
                "climate",
                "set_temperature",
                {
                    "entity_id": entity_id,
                    "temperature": round(temperature),
                },
                False,
            )
        )

    def set_switch(self, entity_id: str, state: int) -> None:
        """Helper function to create switch on/off tasks"""
        action = "turn_on" if state == 1 else "turn_off"
        self.hass.async_create_task(
            self.hass.services.async_call(
                "switch",
                action,
                {"entity_id": entity_id},
                False,
            )
        )

    def is_step_complete(self, step: Step) -> bool:
        """Helper function to check if the step conditions are met to advance"""
        if not self.grill_state:
            return False
        if step.use_timer and self.grill_state.cook_timer_complete:
            return True
        if self.grill_state.probe_alarm_fired:
            return True
        if hasattr(step, "act_temp_adv") and self.grill_state.grill > step.act_temp_adv:
            return True
        if hasattr(step, "probe_act_temp_adv") and self.grill_state.probe > step.probe_act_temp_adv:
            return True
        return False

    def is_valid_cooking_state(self) -> bool:
        """Helper function to check if the grill is in a valid cooking state"""
        return (
            self.grill_state is not None
            and self.current_step <= len(self.cook_cycle)
            and (
                self.current_step == 0
                or self.grill_state.system_status
                not in [
                    GrillMode.COOL_DOWN,
                    GrillMode.SLEEPING,
                    GrillMode.SHUTDOWN,
                    GrillMode.IDLE,
                ]
            )
        )

    def handle_in_step_changes(self, step: Step) -> None:
        """Handle all actions for in-step changes like setting temperatures, smoke, keepwarm, etc."""
        if getattr(step, "time_set", None):
            self.hass.async_create_task(
                self.hass.services.async_call(
                    "number",
                    "set_value",
                    {
                        "entity_id": f"number.{self.grill_id}_cook_timer",
                        "value": round(step.time_set),
                    },
                    False,
                )
            )

        if getattr(step, "probe_set_temp", None):
            self.set_temperature(
                f"climate.{self.grill_id}_probe_p0", step.probe_set_temp)

        if getattr(step, "set_temp", None):
            self.set_temperature(
                f"climate.{self.grill_id}_climate", step.set_temp)

        if (
            getattr(step, "smoke", None)
            and getattr(self.grill_features, "super_smoke_enabled", 0) == 1
            and getattr(self.grill_state, "smoke", 0) != step.smoke
            and getattr(self.grill_state, "set", 0) <= 225
        ):
            self.set_switch(f"switch.{self.grill_id}_smoke", step.smoke)

        if getattr(step, "keepwarm", None):
            if self.grill_state.keepwarm != step.keepwarm:
                self.set_switch(
                    f"switch.{self.grill_id}_keepwarm", step.keepwarm)

        if getattr(step, "shutdown", None) == 1:
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
            self.current_step = 0

    @property
    def native_value(self) -> int:
        if not self.is_valid_cooking_state():
            self.current_step = 0
            return self.current_step

        if self.current_step > 0 and self.current_step == self.previous_step:
            step = self.cook_cycle[self.current_step - 1]
            if self.is_step_complete(step):
                self.current_step += 1

        if self.current_step > 0 and self.current_step != self.previous_step:
            step = self.cook_cycle[self.current_step - 1]
            self.handle_in_step_changes(step)

        self.previous_step = self.current_step

        _LOGGER.debug("CookCycle Steps:%s", self.cook_cycle)

        if self.current_step > len(self.cook_cycle):
            _LOGGER.info("A.Cook Cycles out of indexes.")
            self.current_step = 0

        return self.current_step

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
        if self.current_step > 1:
            prev_step = f"{self.current_step -
                           1}: {self.cook_cycle[self.current_step - 2]}"
        if self.current_step > 0:
            curr_step = f"{self.current_step}: {
                self.cook_cycle[self.current_step - 1]}"
        if self.current_step < len(self.cook_cycle):
            next_step = f"{self.current_step +
                           1}: {self.cook_cycle[self.current_step]}"
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
        self.current_step = round(value)
        # Need to call callback now so that it fires step #1 or commanded step immediatlly.
        await self.client.grill_callback(self.grill_id)

    # Receive Custom Cook Command
    def set_custom_cook(self, **kwargs: Any) -> None:
        """From Service, Update the number's cook cycle steps."""
        self.cook_cycle = kwargs["steps"]
        _LOGGER.info("Traeger: Set Cook Cycle:%s", self.cook_cycle)
        # Need to call callback now so that it fires state cust atrib update.
        asyncio.run_coroutine_threadsafe(
            self.client.grill_callback(self.grill_id), self.hass.loop)


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
