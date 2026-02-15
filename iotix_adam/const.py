"""Constants for IoTiX Adam integration."""
from typing import Final

DOMAIN: Final = "iotix_adam"
MANUFACTURER: Final = "IoTiX"
MODEL: Final = "Adam"

# Configuration
CONF_HOST: Final = "host"
CONF_MAC: Final = "mac"

# Update interval
UPDATE_INTERVAL: Final = 30  # seconds

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

# API endpoints
API_INFO: Final = "/api/info"
API_PINS_AVAILABLE: Final = "/api/pins/available"
API_PINS_CONFIG: Final = "/api/pins/config"
API_PIN_CONFIGURE: Final = "/api/pin/configure"
API_PIN_STATE: Final = "/api/pin/state"
API_PIN_CONTROL: Final = "/api/pin/control"