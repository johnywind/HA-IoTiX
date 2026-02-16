"""Switch platform for IoTiX Adam."""
from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, PIN_TYPE_SWITCH
from .coordinator import AdamCoordinator
from .entity import AdamEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Adam switches from config entry."""
    coordinator: AdamCoordinator = hass.data[DOMAIN][entry.entry_id]

    switches = []
    for pin_config in coordinator.data.get("pins_config", []):
        if pin_config.get("type") == PIN_TYPE_SWITCH:
            switches.append(AdamSwitch(coordinator, pin_config["pin"], pin_config))

    async_add_entities(switches)


class AdamSwitch(AdamEntity, SwitchEntity):
    """Representation of an Adam Switch."""

    def __init__(
        self,
        coordinator: AdamCoordinator,
        pin: int,
        pin_config: dict,
    ) -> None:
        """Initialize the switch."""
        super().__init__(coordinator, pin, pin_config)
        self._attr_icon = "mdi:light-switch"

    @property
    def is_on(self) -> bool:
        """Return true if switch is on."""
        state = self._get_pin_state()
        return state.get("state", False)

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on the switch."""
        await self.coordinator.async_set_pin_state(self._pin, "on")

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off the switch."""
        await self.coordinator.async_set_pin_state(self._pin, "off")