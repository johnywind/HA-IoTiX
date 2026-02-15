"""Base entity for IoTiX Adam."""
from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER, MODEL
from .coordinator import AdamCoordinator


class AdamEntity(CoordinatorEntity[AdamCoordinator]):
    """Base entity for IoTiX Adam."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: AdamCoordinator,
        pin: int,
        pin_config: dict,
    ) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)
        
        self._pin = pin
        self._pin_config = pin_config
        self._attr_name = pin_config.get("name", f"P{pin}")
        
        # Unique ID based on MAC and pin
        self._attr_unique_id = f"{coordinator.mac}_pin_{pin}"
        
        # Device info
        device_info = coordinator.data.get("device_info", {})
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.mac)},
            name=device_info.get("name", "Adam Controller"),
            manufacturer=MANUFACTURER,
            model=MODEL,
            sw_version=device_info.get("firmware_version"),
            configuration_url=f"http://{coordinator.host}",
        )

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return (
            super().available
            and self._pin in self.coordinator.data.get("pin_states", {})
        )

    def _get_pin_state(self):
        """Get current pin state from coordinator."""
        return self.coordinator.data.get("pin_states", {}).get(self._pin, {})