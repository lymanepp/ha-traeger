from dataclasses import dataclass
from enum import IntEnum
from typing import Any, List


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


@dataclass
class Team:
    teamId: str
    teamName: str
    thingName: str
    userId: str


@dataclass
class Image:
    defaultHost: str
    endpoint: str
    name: str


@dataclass
class GrillModel:
    colors: Any | None
    controller: str
    description: str
    deviceTypeId: str
    group: str
    image: Image
    iotCapable: bool
    isTraegerBrand: bool
    make: str
    modelNumber: str
    name: str
    ownersManualUrl: str
    referenceProductId: str


@dataclass
class Thing:
    thingName: str
    friendlyName: str
    deviceTypeId: str
    userId: str
    status: str
    productId: str
    grillModel: GrillModel


@dataclass
class User:
    userId: str
    givenName: str
    familyName: str
    fullName: str
    email: str
    username: str
    cognito: str
    urbanAirshipId: str
    teams: List[Team]
    things: List[Thing]


@dataclass
class Probe:
    get_temp: int
    set_temp: int
    alarm_fired: int


@dataclass
class Acc:
    uuid: str
    channel: str
    type: str
    con: int
    probe: Probe


@dataclass
class Status:
    pellet_level: int
    real_time: int
    time: int
    errors: int
    sys_timer_start: int
    cook_id: str
    probe: int
    server_status: int
    units: int
    grill: int
    probe_set: int
    current_step: int
    system_status: GrillMode
    sys_timer_end: int
    set: int
    in_custom: int
    smoke: int
    cook_timer_complete: int
    current_cycle: int
    probe_alarm_fired: int
    ambient: int
    probe_con: int
    sys_timer_complete: int
    cook_timer_start: int
    cook_timer_end: int
    keepwarm: int
    connected: bool
    acc: List[Acc]


@dataclass
class Features:
    pellet_sensor_enabled: int
    pellet_sensor_connected: int
    open_loop_mode_enabled: int
    cold_smoke_enabled: int
    grill_mode_enabled: int
    time: int
    super_smoke_enabled: int


@dataclass
class Limits:
    max_grill_temp: int


@dataclass
class Settings:
    rssi: int
    units: int
    time: int
    config_version: str
    feature: int
    speaker: int
    device_type_id: int
    language: int
    fw_version: str
    ssid: str
    fw_build_num: str


@dataclass
class ErrorStats:
    bad_thermocouple: int
    ignite_fail: int
    auger_ovrcur: int
    overheat: int
    lowtemp: int
    auger_disco: int
    low_ambient: int
    fan_disco: int
    ign_disco: int


@dataclass
class Usage:
    auger: int
    grill_clean_countdown: int
    time: int
    error_stats: ErrorStats
    fan: int
    runtime: int
    hotrod: int
    grease_trap_clean_countdown: int
    cook_cycles: int


@dataclass
class Step:
    probe_set_temp: int
    time_set: int
    keepwarm: int
    smoke: int
    step_num: int
    set_temp: int
    use_timer: int


@dataclass
class CookCycle:
    cycle_name: str | None
    populated: int
    num_steps: int | None
    units: int | None
    slot_num: int
    steps: List[Step] | None


@dataclass
class CustomCook:
    cook_cycles: List[CookCycle]


@dataclass
class Details:
    thingName: str
    userId: str
    lastConnectedOn: int
    thingNameLower: str
    friendlyName: str
    lat: str
    long: str
    deviceType: str


@dataclass
class Device:
    thingName: str
    jobs: List[Any]
    status: Status
    features: Features
    limits: Limits
    settings: Settings
    usage: Usage
    custom_cook: CustomCook
    stateIndex: int
    schemaVersion: str
    details: Details
