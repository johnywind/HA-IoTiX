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
    API_INPUT_TRIGGERS,
    API_BUTTON_EVENTS,
    API_COVERS_CONFIG,
    API_COVERS_STATE,
    API_COVER_CONTROL,
    API_COVER_CONFIGURE,
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
        self._button_event_listeners: dict[int, list] = {}  # pin -> list of callbacks
        
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=UPDATE_INTERVAL),
        )
    
    def register_button_event_listener(self, pin: int, callback) -> None:
        """Register a callback for button events on a specific pin."""
        if pin not in self._button_event_listeners:
            self._button_event_listeners[pin] = []
        self._button_event_listeners[pin].append(callback)
    
    def _trigger_button_events(self, button_events: list) -> None:
        """Trigger callbacks for any detected button events."""
        for event in button_events:
            pin = event.get("inputPin")
            event_type = event.get("eventType")
            
            if pin in self._button_event_listeners:
                for callback in self._button_event_listeners[pin]:
                    try:
                        callback(event_type)
                    except Exception as err:
                        _LOGGER.error(
                            "Error calling button event callback for pin %s: %s",
                            pin,
                            err
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

            raw_pins_config = pins_config.get("pins", [])

            # Get configured covers and merge as virtual cover entities (pin = 100 + coverId)
            covers_config: list[dict[str, Any]] = []
            try:
                async with self.session.get(
                    f"{self.base_url}{API_COVERS_CONFIG}",
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    if resp.status == 200:
                        covers_data = await resp.json()
                        covers_config = covers_data.get("covers", [])
            except (aiohttp.ClientError, TimeoutError) as err:
                _LOGGER.debug("Error fetching covers config: %s", err)

            existing_cover_ids = {
                pin_config.get("coverId", max(pin_config.get("pin", 100) - 100, 0))
                for pin_config in raw_pins_config
                if pin_config.get("type") == "cover"
            }

            merged_pins_config = list(raw_pins_config)
            for cover in covers_config:
                cover_id = cover.get("coverId")
                if cover_id is None or cover_id in existing_cover_ids:
                    continue

                merged_pins_config.append(
                    {
                        "pin": 100 + int(cover_id),
                        "type": "cover",
                        "name": cover.get("name", f"Cover {int(cover_id) + 1}"),
                        "isInput": False,
                        "coverId": int(cover_id),
                        "inputUpPin": cover.get("inputUpPin"),
                        "inputDownPin": cover.get("inputDownPin"),
                        "outputUpPin": cover.get("outputUpPin"),
                        "outputDownPin": cover.get("outputDownPin"),
                        "upTimeSec": cover.get("upTimeSec"),
                        "downTimeSec": cover.get("downTimeSec"),
                        "interlock": cover.get("interlock", True),
                        "moving": cover.get("moving", False),
                        "direction": cover.get("direction", "stopped"),
                    }
                )

            # Get state for each configured pin
            pin_states = {}
            for pin_config in merged_pins_config:
                pin = pin_config["pin"]
                if pin_config.get("type") == "cover" or pin >= 100:
                    continue
                is_input = pin_config.get("isInput", pin_config.get("type") == "binary_sensor")
                state_key = f"{'in' if is_input else 'out'}_{pin}"
                try:
                    async with self.session.get(
                        f"{self.base_url}{API_PIN_STATE}?pin={pin}&isInput={1 if is_input else 0}",
                        timeout=aiohttp.ClientTimeout(total=5),
                    ) as resp:
                        if resp.status == 200:
                            state_data = await resp.json()
                            pin_states[state_key] = state_data
                except (aiohttp.ClientError, TimeoutError) as err:
                    _LOGGER.warning("Error fetching state for pin %s: %s", pin, err)
                    continue

            covers_state: dict[int, dict[str, Any]] = {}
            try:
                async with self.session.get(
                    f"{self.base_url}{API_COVERS_STATE}",
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    if resp.status == 200:
                        covers_data = await resp.json()
                        for cover_state in covers_data.get("covers", []):
                            cover_id = cover_state.get("coverId")
                            if cover_id is not None:
                                covers_state[cover_id] = cover_state
            except (aiohttp.ClientError, TimeoutError) as err:
                _LOGGER.debug("Error fetching cover state: %s", err)

            # Get input trigger mappings
            triggers = {}
            try:
                async with self.session.get(
                    f"{self.base_url}{API_INPUT_TRIGGERS}",
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    if resp.status == 200:
                        triggers_data = await resp.json()
                        triggers = triggers_data.get("triggers", [])
            except (aiohttp.ClientError, TimeoutError) as err:
                _LOGGER.warning("Error fetching input triggers: %s", err)

            # Get button events for push buttons
            button_events = []
            try:
                async with self.session.get(
                    f"{self.base_url}{API_BUTTON_EVENTS}",
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    if resp.status == 200:
                        events_data = await resp.json()
                        button_events = events_data.get("events", [])
            except (aiohttp.ClientError, TimeoutError) as err:
                _LOGGER.debug("Error fetching button events: %s", err)
            
            # Trigger button event callbacks
            self._trigger_button_events(button_events)

            # Fetch XR8 relay modules
            xr8_modules = []
            try:
                async with self.session.get(
                    f"{self.base_url}/api/xr8/list",
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    if resp.status == 200:
                        xr8_data = await resp.json()
                        xr8_modules = xr8_data.get("modules", [])
            except (aiohttp.ClientError, TimeoutError) as err:
                _LOGGER.debug("Error fetching XR8 modules: %s", err)

            return {
                "device_info": device_info,
                "pins_config": merged_pins_config,
                "pin_states": pin_states,
                "triggers": triggers,
                "button_events": button_events,
                "covers_state": covers_state,
                "covers_config": covers_config,
                "xr8_modules": xr8_modules,
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

    async def async_cover_command(self, cover_id: int, command: str) -> bool:
        """Send a command to a cover."""
        payload = {
            "coverId": cover_id,
            "command": command,
        }

        try:
            async with self.session.post(
                f"{self.base_url}{API_COVER_CONTROL}",
                json=payload,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status == 200:
                    await self.async_request_refresh()
                    return True
                return False
        except (aiohttp.ClientError, TimeoutError) as err:
            _LOGGER.error("Error sending cover command %s for cover %s: %s", command, cover_id, err)
            return False

    async def async_configure_cover(
        self,
        cover_id: int,
        name: str,
        input_up_pin: int,
        input_down_pin: int,
        output_up_pin: int,
        output_down_pin: int,
        up_time_sec: int,
        down_time_sec: int,
        interlock: bool,
    ) -> bool:
        """Configure a cover on the device."""
        payload = {
            "coverId": cover_id,
            "name": name,
            "inputUpPin": input_up_pin,
            "inputDownPin": input_down_pin,
            "outputUpPin": output_up_pin,
            "outputDownPin": output_down_pin,
            "upTimeSec": up_time_sec,
            "downTimeSec": down_time_sec,
            "interlock": interlock,
        }

        try:
            async with self.session.post(
                f"{self.base_url}{API_COVER_CONFIGURE}",
                json=payload,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status == 200:
                    await self.async_request_refresh()
                    return True
                return False
        except (aiohttp.ClientError, TimeoutError) as err:
            _LOGGER.error("Error configuring cover %s: %s", cover_id, err)
            return False

    async def async_configure_xr8_module(
        self,
        module_id: int,
        address: int,
        configured: bool,
        relay_names: list[str] | None = None,
    ) -> bool:
        """Configure an XR8 module on the device."""
        payload = {
            "moduleId": module_id,
            "address": address,
            "configured": configured,
        }

        if relay_names and len(relay_names) == 8:
            payload["relays"] = [{"name": name} for name in relay_names]

        try:
            async with self.session.post(
                f"{self.base_url}/api/xr8/configure",
                json=payload,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status == 200:
                    await self.async_request_refresh()
                    return True
                return False
        except (aiohttp.ClientError, TimeoutError) as err:
            _LOGGER.error("Error configuring XR8 module %s: %s", module_id, err)
            return False