"""Switch platform for IoTiX Adam."""
from __future__ import annotations

from typing import Any

import aiohttp

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, PIN_TYPE_SWITCH, MANUFACTURER, MODEL
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

    # XR8 relay switches - only create for configured modules
    for module in coordinator.data.get("xr8_modules", []):
        if not module.get("configured", False):
            continue
        module_id = module.get("id")
        address = module.get("address")
        for relay in module.get("relays", []):
            relay_id = relay.get("id")
            relay_name = relay.get("name")
            switches.append(XR8RelaySwitch(coordinator, module_id, relay_id, relay_name, address))

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


class XR8RelaySwitch(CoordinatorEntity[AdamCoordinator], SwitchEntity):
    """Representation of an XR8 relay switch."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: AdamCoordinator, module_id: int, relay_id: int, name: str, address: int):
        """Initialize the XR8 relay switch."""
        super().__init__(coordinator)
        self._module_id = module_id
        self._relay_id = relay_id
        self._address = address
        self._initial_name = name  # Store initial name as fallback
        self._attr_unique_id = f"{coordinator.mac}_xr8_{module_id}_{relay_id}"
        self._attr_icon = "mdi:electric-switch"
        
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
    def name(self) -> str:
        """Return the name of the relay - dynamically updated from coordinator."""
        for module in self.coordinator.data.get("xr8_modules", []):
            if module.get("id") == self._module_id:
                for relay in module.get("relays", []):
                    if relay.get("id") == self._relay_id:
                        return relay.get("name", self._initial_name)
        return self._initial_name

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        if not super().available:
            return False
        
        # Check if module exists and is configured
        for module in self.coordinator.data.get("xr8_modules", []):
            if module.get("id") == self._module_id and module.get("configured", False):
                return True
        return False

    @property
    def is_on(self) -> bool:
        """Return true if relay is on."""
        for module in self.coordinator.data.get("xr8_modules", []):
            if module.get("id") == self._module_id:
                for relay in module.get("relays", []):
                    if relay.get("id") == self._relay_id:
                        return relay.get("state", False)
        return False

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on the relay."""
        await self._set_relay_state(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off the relay."""
        await self._set_relay_state(False)

    async def _set_relay_state(self, state: bool) -> None:
        """Set relay state on the device."""
        payload = {
            "moduleId": self._module_id,
            "relayId": self._relay_id,
            "state": state,
        }
        try:
            async with self.coordinator.session.post(
                f"{self.coordinator.base_url}/api/xr8/relay/control",
                json=payload,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status == 200:
                    await self.coordinator.async_request_refresh()
        except (aiohttp.ClientError, TimeoutError):
            pass