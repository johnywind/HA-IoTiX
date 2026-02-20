"""Constants for IoTiX Adam integration."""
from typing import Final

DOMAIN: Final = "iotix"
MANUFACTURER: Final = "IoTiX"
MODEL: Final = "Adam"

# Configuration
CONF_HOST: Final = "host"
CONF_MAC: Final = "mac"

# Update interval
UPDATE_INTERVAL: Final = 1  # seconds - very fast polling for real-time input detection

# Pin types
PIN_TYPE_LIGHT: Final = "light"
PIN_TYPE_SWITCH: Final = "switch"
PIN_TYPE_COVER: Final = "cover"
PIN_TYPE_BINARY_SENSOR: Final = "binary_sensor"

PIN_TYPES: Final = [
    PIN_TYPE_LIGHT,
    PIN_TYPE_SWITCH,
    PIN_TYPE_COVER,
    PIN_TYPE_BINARY_SENSOR,
]

# Button modes
BUTTON_MODE_CLASSIC: Final = "classic"
BUTTON_MODE_PUSH: Final = "push"

BUTTON_MODES: Final = [
    BUTTON_MODE_CLASSIC,
    BUTTON_MODE_PUSH,
]

# Button press types
BUTTON_PRESS_SHORT: Final = "short_press"
BUTTON_PRESS_LONG: Final = "long_press"
BUTTON_PRESS_DOUBLE: Final = "double_press"

# API endpoints
API_INFO: Final = "/api/info"
API_PINS_AVAILABLE: Final = "/api/pins/available"
API_PINS_CONFIG: Final = "/api/pins/config"
API_PIN_CONFIGURE: Final = "/api/pin/configure"
API_PIN_STATE: Final = "/api/pin/state"
API_PIN_CONTROL: Final = "/api/pin/control"
API_INPUT_TRIGGERS: Final = "/api/input/triggers"
API_INPUT_TRIGGER_SET: Final = "/api/input/trigger/set"
API_BUTTON_EVENTS: Final = "/api/button/events"
