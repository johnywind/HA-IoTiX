"""Event platform for IoTiX Adam."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.event import EventEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    DOMAIN,
    BUTTON_MODE_PUSH,
    BUTTON_PRESS_SHORT,
    BUTTON_PRESS_LONG,
    BUTTON_PRESS_DOUBLE,
)
from .coordinator import AdamCoordinator
from .entity import AdamEntity

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Adam events from config entry."""
    coordinator: AdamCoordinator = hass.data[DOMAIN][entry.entry_id]

    events = []
    for pin_config in coordinator.data.get("pins_config", []):
        if pin_config.get("isInput") and pin_config.get("buttonMode") == BUTTON_MODE_PUSH:
            events.append(AdamButtonEvent(coordinator, pin_config["pin"], pin_config))

    async_add_entities(events)


class AdamButtonEvent(AdamEntity, EventEntity):
    """Representation of an Adam Button Event."""

    _attr_event_types = [
        BUTTON_PRESS_SHORT,
        BUTTON_PRESS_LONG,
        BUTTON_PRESS_DOUBLE,
    ]

    def __init__(
        self,
        coordinator: AdamCoordinator,
        pin: int,
        pin_config: dict,
    ) -> None:
        """Initialize the button event."""
        super().__init__(coordinator, pin, pin_config)
        self._attr_icon = "mdi:gesture-tap-button"
        self._pin = pin
        
        # Register with coordinator to receive button events
        coordinator.register_button_event_listener(pin, self._handle_button_event)
    
    def _handle_button_event(self, event_type: str) -> None:
        """Handle button event from coordinator."""
        _LOGGER.debug(
            "Button event received on %s: %s",
            self.name,
            event_type
        )
        self.async_trigger_event(event_type)
        self.async_write_ha_state()
    
    @property
    def available(self) -> bool:
        """Return if entity is available."""
        # Check if this is a push button input
        pin_config = self._get_pin_config()
        if not pin_config:
            return False
        return (
            pin_config.get("isInput", False)
            and pin_config.get("buttonMode") == BUTTON_MODE_PUSH
        )
