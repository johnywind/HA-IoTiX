"""Cover platform for IoTiX Adam."""
from __future__ import annotations

from typing import Any

from homeassistant.components.cover import (
    CoverEntity,
    CoverEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, PIN_TYPE_COVER
from .coordinator import AdamCoordinator
from .entity import AdamEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Adam covers from config entry."""
    coordinator: AdamCoordinator = hass.data[DOMAIN][entry.entry_id]

    covers = []
    for pin_config in coordinator.data.get("pins_config", []):
        if pin_config.get("type") == PIN_TYPE_COVER:
            covers.append(AdamCover(coordinator, pin_config["pin"], pin_config))

    async_add_entities(covers)


class AdamCover(AdamEntity, CoverEntity):
    """Representation of an Adam Cover."""

    _attr_supported_features = CoverEntityFeature.OPEN | CoverEntityFeature.CLOSE

    def __init__(
        self,
        coordinator: AdamCoordinator,
        pin: int,
        pin_config: dict,
    ) -> None:
        """Initialize the cover."""
        super().__init__(coordinator, pin, pin_config)
        self._attr_icon = "mdi:window-shutter"

    @property
    def is_closed(self) -> bool:
        """Return if the cover is closed."""
        state = self._get_pin_state()
        return not state.get("state", False)

    async def async_open_cover(self, **kwargs: Any) -> None:
        """Open the cover."""
        await self.coordinator.async_set_pin_state(self._pin, "on")

    async def async_close_cover(self, **kwargs: Any) -> None:
        """Close the cover."""
        await self.coordinator.async_set_pin_state(self._pin, "off")