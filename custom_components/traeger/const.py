"""Constants for traeger."""

from enum import IntEnum

from homeassistant.const import UnitOfTemperature

# Base component constants
NAME = "Traeger"
DOMAIN = "traeger"
DOMAIN_DATA = f"{DOMAIN}_data"
VERSION = "2024.12.06"
ATTRIBUTION = ""
ISSUE_URL = "https://github.com/njobrien1006/hass_traeger/issues"

# Icons
ICON = "mdi:format-quote-close"

# Platforms
CLIMATE = "climate"
SENSOR = "sensor"
SWITCH = "switch"
NUMBER = "number"
BINARY_SENSOR = "binary_sensor"
PLATFORMS = [CLIMATE, SENSOR, SWITCH, NUMBER, BINARY_SENSOR]

# Configuration and options
CONF_ENABLED = "enabled"
CONF_USERNAME = "username"
CONF_PASSWORD = "password"

# Defaults
DEFAULT_NAME = DOMAIN


class GrillMode(IntEnum):
    OFFLINE = 99  # Offline
    SHUTDOWN = 9  # Cooled down, heading to sleep
    COOL_DOWN = 8  # Cool down cycle
    CUSTOM_COOK = 7  # Custom cook
    MANUAL_COOK = 6  # Manual cook
    PREHEATING = 5  # Preheating
    IGNITING = 4  # Igniting
    IDLE = 3  # Idle (Power switch on, screen on)
    SLEEPING = 2  # Sleeping (Power switch on, screen off)


# Grill Temps
# these are the min temps the traeger app would set
GRILL_MIN_TEMP_C = 75
GRILL_MIN_TEMP_F = 165

# Super Smoke is available until this temperature
SUPER_SMOKE_MAX_TEMP_C = 107
SUPER_SMOKE_MAX_TEMP_F = 225

# Probe Preset Modes
PROBE_PRESET_MODES = {
    "Chicken": {
        UnitOfTemperature.FAHRENHEIT: 165,
        UnitOfTemperature.CELSIUS: 74,
    },
    "Turkey": {
        UnitOfTemperature.FAHRENHEIT: 165,
        UnitOfTemperature.CELSIUS: 74,
    },
    "Beef (Rare)": {
        UnitOfTemperature.FAHRENHEIT: 125,
        UnitOfTemperature.CELSIUS: 52,
    },
    "Beef (Medium Rare)": {
        UnitOfTemperature.FAHRENHEIT: 135,
        UnitOfTemperature.CELSIUS: 57,
    },
    "Beef (Medium)": {
        UnitOfTemperature.FAHRENHEIT: 140,
        UnitOfTemperature.CELSIUS: 60,
    },
    "Beef (Medium Well)": {
        UnitOfTemperature.FAHRENHEIT: 145,
        UnitOfTemperature.CELSIUS: 63,
    },
    "Beef (Well Done)": {
        UnitOfTemperature.FAHRENHEIT: 155,
        UnitOfTemperature.CELSIUS: 68,
    },
    "Beef (Ground)": {
        UnitOfTemperature.FAHRENHEIT: 160,
        UnitOfTemperature.CELSIUS: 71,
    },
    "Lamb (Rare)": {
        UnitOfTemperature.FAHRENHEIT: 125,
        UnitOfTemperature.CELSIUS: 52,
    },
    "Lamb (Medium Rare)": {
        UnitOfTemperature.FAHRENHEIT: 135,
        UnitOfTemperature.CELSIUS: 57,
    },
    "Lamb (Medium)": {
        UnitOfTemperature.FAHRENHEIT: 140,
        UnitOfTemperature.CELSIUS: 60,
    },
    "Lamb (Medium Well)": {
        UnitOfTemperature.FAHRENHEIT: 145,
        UnitOfTemperature.CELSIUS: 63,
    },
    "Lamb (Well Done)": {
        UnitOfTemperature.FAHRENHEIT: 155,
        UnitOfTemperature.CELSIUS: 68,
    },
    "Lamb (Ground)": {
        UnitOfTemperature.FAHRENHEIT: 160,
        UnitOfTemperature.CELSIUS: 71,
    },
    "Pork (Medium Rare)": {
        UnitOfTemperature.FAHRENHEIT: 135,
        UnitOfTemperature.CELSIUS: 57,
    },
    "Pork (Medium)": {
        UnitOfTemperature.FAHRENHEIT: 140,
        UnitOfTemperature.CELSIUS: 60,
    },
    "Pork (Well Done)": {
        UnitOfTemperature.FAHRENHEIT: 155,
        UnitOfTemperature.CELSIUS: 68,
    },
    "Fish": {
        UnitOfTemperature.FAHRENHEIT: 145,
        UnitOfTemperature.CELSIUS: 63,
    },
}

STARTUP_MESSAGE = f"""
-------------------------------------------------------------------
{NAME}
Version: {VERSION}
This is a custom integration!
If you have any issues with this you need to open an issue here:
{ISSUE_URL}
-------------------------------------------------------------------
"""
