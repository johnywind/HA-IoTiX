"""Data coordinator for IoTiX Adam."""
from __future__ import annotations

from datetime import timedelta
import logging
from typing import Any

import aiohttp

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)

from .const import (
    DOMAIN,
    UPDATE_INTERVAL,
    API_INFO,
    API_PINS_CONFIG,
    API_PIN_STATE,
)

_LOGGER = logging.getLogger(__name__)


class AdamCoordinator(DataUpdateCoordinator):
    """Class to manage fetching Adam data."""

    def __init__(self, hass: HomeAssistant, host: str, mac: str) -> None:
        """Initialize coordinator."""
        self.host = host
        self.mac = mac
        self.base_url = f"http://{host}"
        self.session = async_get_clientsession(hass)
        
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=UPDATE_INTERVAL),
        )

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from Adam controller."""
        try:
            # Get device info
            async with self.session.get(
                f"{self.base_url}{API_INFO}",
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status != 200:
                    raise UpdateFailed(f"Error communicating with API: {resp.status}")
                device_info = await resp.json()

            # Get pin configurations
            async with self.session.get(
                f"{self.base_url}{API_PINS_CONFIG}",
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status != 200:
                    raise UpdateFailed(f"Error fetching pin config: {resp.status}")
                pins_config = await resp.json()

            # Get state for each configured pin
            pin_states = {}
            for pin_config in pins_config.get("pins", []):
                pin = pin_config["pin"]
                try:
                    async with self.session.get(
                        f"{self.base_url}{API_PIN_STATE}?pin={pin}",
                        timeout=aiohttp.ClientTimeout(total=5),
                    ) as resp:
                        if resp.status == 200:
                            state_data = await resp.json()
                            pin_states[pin] = state_data
                except (aiohttp.ClientError, TimeoutError) as err:
                    _LOGGER.warning("Error fetching state for pin %s: %s", pin, err)
                    continue

            return {
                "device_info": device_info,
                "pins_config": pins_config.get("pins", []),
                "pin_states": pin_states,
            }

        except (aiohttp.ClientError, TimeoutError) as err:
            raise UpdateFailed(f"Error communicating with Adam: {err}") from err

    async def async_set_pin_state(
        self, pin: int, command: str, **kwargs
    ) -> bool:
        """Send command to a pin."""
        payload = {
            "pin": pin,
            "command": command,
        }
        
        # Add optional parameters
        if "brightness" in kwargs:
            payload["brightness"] = kwargs["brightness"]
        
        try:
            async with self.session.post(
                f"{self.base_url}/api/pin/control",
                json=payload,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status == 200:
                    # Request immediate refresh
                    await self.async_request_refresh()
                    return True
                return False
        except (aiohttp.ClientError, TimeoutError) as err:
            _LOGGER.error("Error controlling pin %s: %s", pin, err)
            return False

    async def async_configure_pin(
        self, pin: int, pin_type: str, name: str
    ) -> bool:
        """Configure a pin."""
        payload = {
            "pin": pin,
            "type": pin_type,
            "name": name,
        }
        
        try:
            async with self.session.post(
                f"{self.base_url}/api/pin/configure",
                json=payload,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status == 200:
                    await self.async_request_refresh()
                    return True
                return False
        except (aiohttp.ClientError, TimeoutError) as err:
            _LOGGER.error("Error configuring pin %s: %s", pin, err)
            return False