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
    seen_cover_ids: set[int] = set()

    for pin_config in coordinator.data.get("pins_config", []):
        if pin_config.get("type") == PIN_TYPE_COVER and pin_config.get("pin", -1) >= 100:
            cover_id = pin_config.get("coverId", max(pin_config.get("pin", 100) - 100, 0))
            seen_cover_ids.add(cover_id)
            covers.append(AdamCover(coordinator, pin_config["pin"], pin_config))

    # Fallback: build covers from dedicated covers_config endpoint data
    for cover_config in coordinator.data.get("covers_config", []):
        cover_id = cover_config.get("coverId")
        if cover_id is None or cover_id in seen_cover_ids:
            continue

        pin_config = {
            "pin": 100 + int(cover_id),
            "type": PIN_TYPE_COVER,
            "name": cover_config.get("name", f"Cover {int(cover_id) + 1}"),
            "coverId": int(cover_id),
            "isInput": False,
            "inputUpPin": cover_config.get("inputUpPin"),
            "inputDownPin": cover_config.get("inputDownPin"),
            "outputUpPin": cover_config.get("outputUpPin"),
            "outputDownPin": cover_config.get("outputDownPin"),
            "upTimeSec": cover_config.get("upTimeSec"),
            "downTimeSec": cover_config.get("downTimeSec"),
            "interlock": cover_config.get("interlock", True),
        }
        covers.append(AdamCover(coordinator, pin_config["pin"], pin_config))
        seen_cover_ids.add(int(cover_id))

    async_add_entities(covers)


class AdamCover(AdamEntity, CoverEntity):
    """Representation of an Adam Cover."""

    _attr_supported_features = (
        CoverEntityFeature.OPEN | CoverEntityFeature.CLOSE | CoverEntityFeature.STOP
    )
    _attr_assumed_state = True

    def __init__(
        self,
        coordinator: AdamCoordinator,
        pin: int,
        pin_config: dict,
    ) -> None:
        """Initialize the cover."""
        super().__init__(coordinator, pin, pin_config)
        self._attr_icon = "mdi:window-shutter"
        self._cover_id = pin_config.get("coverId", max(pin - 100, 0))
        self._attr_unique_id = f"{coordinator.mac}_cover_{self._cover_id}"

    @property
    def is_opening(self) -> bool | None:
        """Return if the cover is opening."""
        state = self.coordinator.data.get("covers_state", {}).get(self._cover_id, {})
        return state.get("moving", False) and state.get("direction") == "up"

    @property
    def is_closing(self) -> bool | None:
        """Return if the cover is closing."""
        state = self.coordinator.data.get("covers_state", {}).get(self._cover_id, {})
        return state.get("moving", False) and state.get("direction") == "down"

    @property
    def is_closed(self) -> bool | None:
        """Return if the cover is closed.

        Position feedback is not available from firmware yet, so return unknown.
        """
        return None

    @property
    def available(self) -> bool:
        """Return if cover is available."""
        if not self.coordinator.last_update_success:
            return False

        # Covers are virtual entities (pin >= 100), so they are not present in pin_states.
        has_cover_in_pins = any(
            pin_config.get("type") == PIN_TYPE_COVER
            and pin_config.get("coverId", max(pin_config.get("pin", 100) - 100, 0)) == self._cover_id
            for pin_config in self.coordinator.data.get("pins_config", [])
        )

        if has_cover_in_pins:
            return True

        return any(
            cover_config.get("coverId") == self._cover_id
            for cover_config in self.coordinator.data.get("covers_config", [])
        )

    async def async_open_cover(self, **kwargs: Any) -> None:
        """Open the cover."""
        await self.coordinator.async_cover_command(self._cover_id, "open")

    async def async_close_cover(self, **kwargs: Any) -> None:
        """Close the cover."""
        await self.coordinator.async_cover_command(self._cover_id, "close")

    async def async_stop_cover(self, **kwargs: Any) -> None:
        """Stop the cover."""
        await self.coordinator.async_cover_command(self._cover_id, "stop")