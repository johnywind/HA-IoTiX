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
                    
                    self._name = info.get("name", "IoTiX")
                    
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
                                title=user_input.get(CONF_NAME, info.get("name", "IoTiX")),
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
                    vol.Optional(CONF_NAME, default="IoTiX"): str,
                }
            ),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: config_entries.ConfigEntry) -> config_entries.OptionsFlow:
        """Get the options flow."""
        return AdamOptionsFlow()


class AdamOptionsFlow(config_entries.OptionsFlow):
    """Handle options flow for IoTiX Adam."""

    def __init__(self) -> None:
        """Initialize options flow."""
        super().__init__()
        self._all_pins: list[dict] = []
        self._inputs: list[dict] = []
        self._outputs: list[dict] = []
        self._pin_to_configure: int | None = None
        self._pin_type: str | None = None
        self._device_name: str | None = None
        self._is_input: bool = False

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Main configuration screen."""
        return await self.async_step_main_menu()

    async def _fetch_pin_data(self) -> None:
        """Fetch pin configuration from device."""
        host = self.config_entry.data[CONF_HOST]
        session = async_get_clientsession(self.hass)
        
        try:
            # Get device info
            async with session.get(
                f"http://{host}/api/info",
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status == 200:
                    info = await resp.json()
                    self._device_name = info.get("name", "IoTiX")
            
            # Get pin configuration
            async with session.get(
                f"http://{host}/api/pins/config",
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    self._all_pins = data.get("pins", [])
        except:
            pass

    async def async_step_main_menu(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Show main configuration menu."""
        await self._fetch_pin_data()
        
        if user_input is not None:
            action = user_input.get("action")
            
            if action == "device_name":
                return await self.async_step_device_name()
            elif action == "configure_inputs":
                return await self.async_step_configure_inputs()
            elif action == "configure_outputs":
                return await self.async_step_configure_outputs()
            elif action == "configure_triggers":
                return await self.async_step_configure_triggers()
            elif action == "done":
                return self.async_create_entry(title="", data={})

        # Count configured pins
        inputs = [p for p in self._all_pins if p.get("type") == "binary_sensor"]
        outputs = [p for p in self._all_pins if p.get("type") in ["light", "switch", "cover"]]
        
        description = f"Controller: {self._device_name}\n"
        description += f"Configured Inputs: {len(inputs)}/16\n"
        description += f"Configured Outputs: {len(outputs)}/16"

        return self.async_show_form(
            step_id="main_menu",
            data_schema=vol.Schema(
                {
                    vol.Required("action"): vol.In({
                        "device_name": "Set Controller Name",
                        "configure_inputs": "Configure Inputs (16)",
                        "configure_outputs": "Configure Outputs (16)",
                        "configure_triggers": "Configure Input Triggers",
                        "done": "Done",
                    }),
                }
            ),
            description_placeholders={"status": description},
        )

    async def async_step_configure_inputs(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Configure inputs screen - show all 16 inputs."""
        if user_input is not None:
            input_num = user_input["input"]
            self._pin_to_configure = input_num
            self._is_input = True
            return await self.async_step_edit_pin()

        # Build list of all 16 inputs
        input_options = {}
        for i in range(16):
            pin_config = next((p for p in self._all_pins if p.get("pin") == i and p.get("type") == "binary_sensor"), None)
            if pin_config:
                input_options[i] = f"Input {i+1}: {pin_config.get('name', 'Unnamed')} [✓]"
            else:
                input_options[i] = f"Input {i+1}: Not configured"

        return self.async_show_form(
            step_id="configure_inputs",
            data_schema=vol.Schema({
                vol.Required("input"): vol.In(input_options),
            }),
            description_placeholders={"info": "Select an input to configure"},
        )

    async def async_step_configure_outputs(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Configure outputs screen - show all 16 outputs."""
        if user_input is not None:
            output_num = user_input["output"]
            self._pin_to_configure = output_num
            self._is_input = False
            return await self.async_step_edit_pin()

        # Build list of all 16 outputs
        output_options = {}
        for i in range(16):
            pin_config = next((p for p in self._all_pins if p.get("pin") == i and p.get("type") in ["light", "switch", "cover"]), None)
            if pin_config:
                pin_type = pin_config.get("type", "").capitalize()
                output_options[i] = f"Output {i+1}: {pin_config.get('name', 'Unnamed')} ({pin_type}) [✓]"
            else:
                output_options[i] = f"Output {i+1}: Not configured"

        return self.async_show_form(
            step_id="configure_outputs",
            data_schema=vol.Schema({
                vol.Required("output"): vol.In(output_options),
            }),
            description_placeholders={"info": "Select an output to configure"},
        )

    async def async_step_configure_triggers(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Configure input-to-output triggers."""
        if user_input is not None:
            input_num = user_input["input"]
            self._pin_to_configure = input_num
            self._is_input = True
            return await self.async_step_select_trigger_output()

        # Build list of all configured inputs
        input_options = {}
        for i in range(16):
            pin_config = next((p for p in self._all_pins if p.get("pin") == i and p.get("type") == "binary_sensor"), None)
            if pin_config:
                input_options[i] = f"Input {i+1}: {pin_config.get('name', 'Unnamed')}"
            
        if not input_options:
            # No inputs configured
            return self.async_show_form(
                step_id="configure_triggers",
                data_schema=vol.Schema({}),
                description_placeholders={"info": "No inputs configured. Please configure inputs first."},
            )

        return self.async_show_form(
            step_id="configure_triggers",
            data_schema=vol.Schema({
                vol.Required("input"): vol.In(input_options),
            }),
            description_placeholders={"info": "Select an input to configure its trigger"},
        )

    async def async_step_select_trigger_output(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Select which output an input should trigger."""
        pin_num = self._pin_to_configure
        
        if user_input is not None:
            output_num = user_input["output"]
            host = self.config_entry.data[CONF_HOST]
            session = async_get_clientsession(self.hass)
            
            if output_num == 255:  # Special value for "None"
                # Don't set a trigger, just go back
                return await self.async_step_configure_triggers()
            
            config_data = {
                "inputPin": pin_num,
                "outputPin": output_num,
            }
            
            try:
                async with session.post(
                    f"http://{host}/api/input/trigger/set",
                    json=config_data,
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    if resp.status == 200:
                        await self.hass.config_entries.async_reload(self.config_entry.entry_id)
            except Exception as err:
                _LOGGER.error("Error setting input trigger: %s", err)
            
            return await self.async_step_configure_triggers()

        # Build list of outputs (only light and switch)
        output_options = {255: "None (No trigger)"}
        for i in range(16):
            pin_config = next((p for p in self._all_pins if p.get("pin") == i and p.get("type") in ["light", "switch"]), None)
            if pin_config:
                pin_type = pin_config.get("type", "").capitalize()
                output_options[i] = f"Output {i+1}: {pin_config.get('name', 'Unnamed')} ({pin_type})"
        
        input_config = next((p for p in self._all_pins if p.get("pin") == pin_num), None)
        input_name = input_config.get("name", f"Input {pin_num + 1}") if input_config else f"Input {pin_num + 1}"
        
        return self.async_show_form(
            step_id="select_trigger_output",
            data_schema=vol.Schema({
                vol.Required("output"): vol.In(output_options),
            }),
            description_placeholders={"input": input_name},
        )

    async def async_step_configure_all(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Configure all inputs and outputs - show all 32 pins."""
        if user_input is not None:
            pin_num = user_input["pin"]
            self._pin_to_configure = pin_num
            # Determine if it's an input (0-15) or output (16-31 displayed, but stored as 0-15)
            if pin_num < 100:  # Inputs are 0-15
                self._is_input = True
            else:  # Outputs are 100-115 (representing 0-15)
                self._is_input = False
                self._pin_to_configure = pin_num - 100
            return await self.async_step_edit_pin()

        # Build combined list of all inputs and outputs
        all_options = {}
        
        # Add all 16 inputs (pin numbers 0-15)
        for i in range(16):
            pin_config = next((p for p in self._all_pins if p.get("pin") == i and p.get("type") == "binary_sensor"), None)
            if pin_config:
                all_options[i] = f"Input {i+1}: {pin_config.get('name', 'Unnamed')} [✓]"
            else:
                all_options[i] = f"Input {i+1}: Not configured"
        
        # Add all 16 outputs (pin numbers 100-115 for display purposes)
        for i in range(16):
            pin_config = next((p for p in self._all_pins if p.get("pin") == i and p.get("type") in ["light", "switch", "cover"]), None)
            if pin_config:
                pin_type = pin_config.get("type", "").capitalize()
                all_options[i + 100] = f"Output {i+1}: {pin_config.get('name', 'Unnamed')} ({pin_type}) [✓]"
            else:
                all_options[i + 100] = f"Output {i+1}: Not configured"

        return self.async_show_form(
            step_id="configure_all",
            data_schema=vol.Schema({
                vol.Required("pin"): vol.In(all_options),
            }),
            description_placeholders={"info": "INPUTS (1-16) | OUTPUTS (1-16)\nSelect any input or output to configure"},
        )

    async def async_step_edit_pin(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Edit a specific input or output."""
        pin_num = self._pin_to_configure
        is_input = self._is_input
        
        if user_input is not None:
            host = self.config_entry.data[CONF_HOST]
            session = async_get_clientsession(self.hass)
            
            # Skip if user selected "unconfigured" with empty name
            if user_input["type"] == "unconfigured":
                # TODO: Add API call to remove/unconfigure pin
                # For now, just return to the list
                if is_input:
                    return await self.async_step_configure_inputs()
                else:
                    return await self.async_step_configure_outputs()

            config_data = {
                "pin": pin_num,
                "type": user_input["type"],
                "name": user_input["name"],
            }

            try:
                async with session.post(
                    f"http://{host}/api/pin/configure",
                    json=config_data,
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    if resp.status == 200:
                        # Refresh pin data before going back
                        await self._fetch_pin_data()
                        await self.hass.config_entries.async_reload(self.config_entry.entry_id)
                        if is_input:
                            return await self.async_step_configure_inputs()
                        else:
                            return await self.async_step_configure_outputs()
            except Exception as err:
                _LOGGER.error("Error configuring pin %s: %s", pin_num, err)
            
            # If we get here, there was an error, but continue anyway
            if is_input:
                return await self.async_step_configure_inputs()
            else:
                return await self.async_step_configure_outputs()

        # Get current configuration
        pin_config = next((p for p in self._all_pins if p.get("pin") == pin_num), None)
        current_name = pin_config.get("name", "") if pin_config else ""
        current_type = pin_config.get("type", "") if pin_config else ""

        # Default names
        if not current_name:
            if is_input:
                current_name = f"Input {pin_num + 1}"
            else:
                current_name = f"Output {pin_num + 1}"

        # Type options
        if is_input:
            type_options = {
                "binary_sensor": "Binary Sensor (Input)",
                "unconfigured": "Not Configured",
            }
            if not current_type:
                current_type = "binary_sensor"
        else:
            type_options = {
                "light": "Light",
                "switch": "Switch",
                "cover": "Cover",
                "unconfigured": "Not Configured",
            }
            if not current_type:
                current_type = "light"

        pin_label = f"Input {pin_num + 1}" if is_input else f"Output {pin_num + 1}"
        
        return self.async_show_form(
            step_id="edit_pin",
            data_schema=vol.Schema({
                vol.Required("name", default=current_name): str,
                vol.Required("type", default=current_type): vol.In(type_options),
            }),
            description_placeholders={"pin": pin_label},
        )

    async def async_step_device_name(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Configure controller name."""
        host = self.config_entry.data[CONF_HOST]
        session = async_get_clientsession(self.hass)

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
            except:
                pass
            
            return await self.async_step_main_menu()

        default_name = self._device_name or "IoTiX"
        return self.async_show_form(
            step_id="device_name",
            data_schema=vol.Schema({
                vol.Required("name", default=default_name): str,
            }),
        )