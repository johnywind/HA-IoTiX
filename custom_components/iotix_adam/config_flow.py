"""Config flow for IoTiX Adam."""
from __future__ import annotations

import logging
from typing import Any

import aiohttp
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.components import zeroconf
from homeassistant.const import CONF_HOST, CONF_NAME
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    DOMAIN,
    CONF_MAC,
    PIN_TYPES,
)

_LOGGER = logging.getLogger(__name__)


class AdamConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for IoTiX Adam."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._discovered_devices: dict[str, dict[str, Any]] = {}
        self._host: str | None = None
        self._mac: str | None = None
        self._name: str | None = None

    async def async_step_zeroconf(
        self, discovery_info: zeroconf.ZeroconfServiceInfo
    ) -> FlowResult:
        """Handle zeroconf discovery."""
        mac = discovery_info.properties.get("mac")
        if not mac:
            return self.async_abort(reason="no_mac")

        await self.async_set_unique_id(mac)
        self._abort_if_unique_id_configured()

        host = discovery_info.host
        self._host = host
        self._mac = mac

        # Verify device is reachable
        session = async_get_clientsession(self.hass)
        
        try:
            async with session.get(
                f"http://{host}/api/info", timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                if resp.status == 200:
                    info = await resp.json()
                    
                    # Verify it's an Adam controller
                    if info.get("model") != "Adam" or info.get("manufacturer") != "IoTiX":
                        return self.async_abort(reason="not_adam_controller")
                    
                    self._name = info.get("name", "Adam Controller")
                    
                    self.context["title_placeholders"] = {
                        "name": self._name,
                        "host": host,
                    }
                    
                    return await self.async_step_discovery_confirm()
        except (aiohttp.ClientError, TimeoutError):
            return self.async_abort(reason="cannot_connect")

    async def async_step_discovery_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Confirm discovery."""
        if user_input is not None:
            return self.async_create_entry(
                title=self._name,
                data={
                    CONF_HOST: self._host,
                    CONF_MAC: self._mac,
                    CONF_NAME: self._name,
                },
            )

        return self.async_show_form(
            step_id="discovery_confirm",
            description_placeholders={
                "name": self._name,
                "host": self._host,
            },
        )

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle manual setup."""
        errors = {}

        if user_input is not None:
            host = user_input[CONF_HOST]
            session = async_get_clientsession(self.hass)

            try:
                async with session.get(
                    f"http://{host}/api/info",
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    if resp.status == 200:
                        info = await resp.json()
                        
                        if info.get("model") != "Adam" or info.get("manufacturer") != "IoTiX":
                            errors["base"] = "not_adam_controller"
                        else:
                            mac = info.get("mac")
                            await self.async_set_unique_id(mac)
                            self._abort_if_unique_id_configured()

                            return self.async_create_entry(
                                title=user_input.get(CONF_NAME, info.get("name", "Adam Controller")),
                                data={
                                    CONF_HOST: host,
                                    CONF_MAC: mac,
                                    CONF_NAME: user_input.get(CONF_NAME, info.get("name")),
                                },
                            )
                    else:
                        errors["base"] = "cannot_connect"
            except (aiohttp.ClientError, TimeoutError):
                errors["base"] = "cannot_connect"

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_HOST): str,
                    vol.Optional(CONF_NAME, default="Adam Controller"): str,
                }
            ),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: config_entries.ConfigEntry) -> config_entries.OptionsFlow:
        """Get the options flow."""
        return AdamOptionsFlow(config_entry)


class AdamOptionsFlow(config_entries.OptionsFlow):
    """Handle options flow for IoTiX Adam."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self.config_entry = config_entry
        self._available_pins: list[dict] = []
        self._pin_to_configure: int | None = None
        self._pin_type: str | None = None
        self._device_name: str | None = None

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage pin configuration."""
        return await self.async_step_pin_list()

    async def async_step_pin_list(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Show list of pins and configuration options."""
        if user_input is not None:
            action = user_input.get("action")
            
            if action == "configure_pin":
                return await self.async_step_select_pin()
            elif action == "set_device_name":
                return await self.async_step_device_name()
            elif action == "done":
                return self.async_create_entry(title="", data={})

        # Get current pin configuration
        host = self.config_entry.data[CONF_HOST]
        session = async_get_clientsession(self.hass)
        
        try:
            async with session.get(
                f"http://{host}/api/pins/available",
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    self._available_pins = data.get("pins", [])
        except:
            pass

        # Build description of current config
        configured_pins = [p for p in self._available_pins if p.get("configured")]
        unconfigured_pins = [p for p in self._available_pins if not p.get("configured")]
        
        description = f"Configured pins: {len(configured_pins)}\n"
        description += f"Available pins: {len(unconfigured_pins)}"

        return self.async_show_form(
            step_id="pin_list",
            data_schema=vol.Schema(
                {
                    vol.Required("action"): vol.In({
                        "configure_pin": "Configure a pin",
                        "set_device_name": "Set device name",
                        "done": "Finish configuration",
                    }),
                }
            ),
            description_placeholders={"pin_info": description},
        )

    async def async_step_select_pin(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Select which pin to configure."""
        if user_input is not None:
            self._pin_to_configure = user_input["pin"]
            return await self.async_step_configure_pin_type()

        # Get available pins
        unconfigured = [p for p in self._available_pins if not p.get("configured")]
        
        if not unconfigured:
            return await self.async_step_pin_list()

        pin_options = {p["pin"]: f"P{p['pin']} ({p['name']})" for p in unconfigured}

        return self.async_show_form(
            step_id="select_pin",
            data_schema=vol.Schema({
                vol.Required("pin"): vol.In(pin_options),
            }),
        )

    async def async_step_configure_pin_type(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Select pin type."""
        if user_input is not None:
            self._pin_type = user_input["type"]
            return await self.async_step_configure_pin_name()

        return self.async_show_form(
            step_id="configure_pin_type",
            data_schema=vol.Schema({
                vol.Required("type"): vol.In({
                    "light": "Light",
                    "switch": "Switch",
                    "cover": "Cover",
                    "binary_sensor": "Binary Sensor",
                }),
            }),
            description_placeholders={"pin": f"P{self._pin_to_configure}"},
        )

    async def async_step_configure_pin_name(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Configure pin name and send config."""
        if user_input is not None:
            host = self.config_entry.data[CONF_HOST]
            session = async_get_clientsession(self.hass)

            config_data = {
                "pin": self._pin_to_configure,
                "type": self._pin_type,
                "name": user_input["name"],
            }

            try:
                async with session.post(
                    f"http://{host}/api/pin/configure",
                    json=config_data,
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    if resp.status == 200:
                        await self.hass.config_entries.async_reload(self.config_entry.entry_id)
                        return await self.async_step_pin_list()
            except:
                pass

        default_name = "Output {pin}".format(pin=(self._pin_to_configure or 0) + 1)
        if self._pin_type == "binary_sensor":
            default_name = "Input {pin}".format(pin=(self._pin_to_configure or 0) + 1)

        return self.async_show_form(
            step_id="configure_pin_name",
            data_schema=vol.Schema({
                vol.Required("name", default=default_name): str,
            }),
            description_placeholders={
                "pin": f"P{self._pin_to_configure}",
                "type": self._pin_type,
            },
        )

    async def async_step_device_name(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Configure device name."""
        host = self.config_entry.data[CONF_HOST]
        session = async_get_clientsession(self.hass)

        if self._device_name is None:
            try:
                async with session.get(
                    f"http://{host}/api/info",
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    if resp.status == 200:
                        info = await resp.json()
                        self._device_name = info.get("name")
            except:
                pass

        if user_input is not None:
            name = user_input["name"]
            try:
                async with session.post(
                    f"http://{host}/api/device/name",
                    json={"name": name},
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    if resp.status == 200:
                        await self.hass.config_entries.async_reload(self.config_entry.entry_id)
                        return await self.async_step_pin_list()
            except:
                pass

        default_name = self._device_name or "Adam Controller"
        return self.async_show_form(
            step_id="device_name",
            data_schema=vol.Schema({
                vol.Required("name", default=default_name): str,
            }),
        )