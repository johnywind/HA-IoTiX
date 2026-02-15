"""Binary sensor platform for IoTiX Adam."""
from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, PIN_TYPE_BINARY_SENSOR
from .coordinator import AdamCoordinator
from .entity import AdamEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Adam binary sensors from config entry."""
    coordinator: AdamCoordinator = hass.data[DOMAIN][entry.entry_id]

    sensors = []
    for pin_config in coordinator.data.get("pins_config", []):
        if pin_config.get("type") == PIN_TYPE_BINARY_SENSOR:
            sensors.append(AdamBinarySensor(coordinator, pin_config["pin"], pin_config))

    async_add_entities(sensors)


class AdamBinarySensor(AdamEntity, BinarySensorEntity):
    """Representation of an Adam Binary Sensor."""

    def __init__(
        self,
        coordinator: AdamCoordinator,
        pin: int,
        pin_config: dict,
    ) -> None:
        """Initialize the binary sensor."""
        super().__init__(coordinator, pin, pin_config)
        self._attr_icon = "mdi:electric-switch"

    @property
    def is_on(self) -> bool:
        """Return true if the binary sensor is on."""
        state = self._get_pin_state()
        return state.get("state", False)