"""Light platform for IoTiX Adam."""
from __future__ import annotations

from typing import Any

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ColorMode,
    LightEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, PIN_TYPE_LIGHT
from .coordinator import AdamCoordinator
from .entity import AdamEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Adam lights from config entry."""
    coordinator: AdamCoordinator = hass.data[DOMAIN][entry.entry_id]

    lights = []
    for pin_config in coordinator.data.get("pins_config", []):
        if pin_config.get("type") == PIN_TYPE_LIGHT:
            lights.append(AdamLight(coordinator, pin_config["pin"], pin_config))

    async_add_entities(lights)


class AdamLight(AdamEntity, LightEntity):
    """Representation of an Adam Light."""

    _attr_color_mode = ColorMode.BRIGHTNESS
    _attr_supported_color_modes = {ColorMode.BRIGHTNESS}

    def __init__(
        self,
        coordinator: AdamCoordinator,
        pin: int,
        pin_config: dict,
    ) -> None:
        """Initialize the light."""
        super().__init__(coordinator, pin, pin_config)
        self._attr_icon = "mdi:lightbulb"

    @property
    def is_on(self) -> bool:
        """Return true if light is on."""
        state = self._get_pin_state()
        return state.get("state", False)

    @property
    def brightness(self) -> int | None:
        """Return the brightness of the light."""
        state = self._get_pin_state()
        return state.get("brightness", 255)

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on the light."""
        brightness = kwargs.get(ATTR_BRIGHTNESS, 255)
        
        await self.coordinator.async_set_pin_state(
            self._pin,
            "on",
            brightness=brightness,
        )

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off the light."""
        await self.coordinator.async_set_pin_state(self._pin, "off")