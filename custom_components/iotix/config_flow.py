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
    BUTTON_MODES,
    BUTTON_MODE_CLASSIC,
    BUTTON_MODE_PUSH,
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
        self._input_config: dict[str, Any] = {}  # Store partial config between steps

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

        # Build summary of all inputs with their triggers
        summary = "Current Input Configuration:\n\n"
        for i in range(16):
            pin_config = next((p for p in self._all_pins if p.get("pin") == i and p.get("type") == "binary_sensor"), None)
            if not pin_config:
                summary += f"Input {i+1}: Not configured\n"
                continue

            pin_name = pin_config.get("name", f"Input {i+1}")
            button_mode = pin_config.get("buttonMode", BUTTON_MODE_CLASSIC)
            
            if button_mode == BUTTON_MODE_CLASSIC:
                # Get trigger output info
                trigger_output = pin_config.get("triggerOutput", 255)
                if trigger_output != 255:
                    output_config = next((p for p in self._all_pins if p.get("pin") == trigger_output and p.get("type") in ["light", "switch", "cover"]), None)
                    if output_config:
                        output_name = output_config.get("name", f"Output {trigger_output+1}")
                        summary += f"Input {i+1}: {pin_name} is CLASSIC BUTTON\n"
                        summary += f"  └─ triggers OUTPUT {trigger_output+1} ({output_name})\n"
                    else:
                        summary += f"Input {i+1}: {pin_name} is CLASSIC BUTTON\n"
                        summary += f"  └─ triggers OUTPUT {trigger_output+1} (Not configured)\n"
                else:
                    summary += f"Input {i+1}: {pin_name} is CLASSIC BUTTON (no trigger output)\n"
            
            elif button_mode == BUTTON_MODE_PUSH:
                # Get push button trigger outputs
                short_output = pin_config.get("shortPressOutput", 255)
                long_output = pin_config.get("longPressOutput", 255)
                double_output = pin_config.get("doublePressOutput", 255)
                
                summary += f"Input {i+1}: {pin_name} is PUSH BUTTON\n"
                
                # Short press
                if short_output != 255:
                    output_config = next((p for p in self._all_pins if p.get("pin") == short_output and p.get("type") in ["light", "switch", "cover"]), None)
                    output_name = output_config.get("name", f"Output {short_output+1}") if output_config else f"Output {short_output+1}"
                    summary += f"  └─ Short Press → OUTPUT {short_output+1} ({output_name})\n"
                
                # Long press
                if long_output != 255:
                    output_config = next((p for p in self._all_pins if p.get("pin") == long_output and p.get("type") in ["light", "switch", "cover"]), None)
                    output_name = output_config.get("name", f"Output {long_output+1}") if output_config else f"Output {long_output+1}"
                    summary += f"  └─ Long Press → OUTPUT {long_output+1} ({output_name})\n"
                
                # Double press
                if double_output != 255:
                    output_config = next((p for p in self._all_pins if p.get("pin") == double_output and p.get("type") in ["light", "switch", "cover"]), None)
                    output_name = output_config.get("name", f"Output {double_output+1}") if output_config else f"Output {double_output+1}"
                    summary += f"  └─ Double Press → OUTPUT {double_output+1} ({output_name})\n"
                
                if short_output == 255 and long_output == 255 and double_output == 255:
                    summary += "  └─ (no triggers configured)\n"

        return self.async_show_form(
            step_id="configure_inputs",
            data_schema=vol.Schema({
                vol.Required("input"): vol.In(input_options),
            }),
            description_placeholders={"status": summary},
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

        # Build summary of all outputs
        summary = "Current Output Configuration:\n\n"
        for i in range(16):
            pin_config = next((p for p in self._all_pins if p.get("pin") == i and p.get("type") in ["light", "switch", "cover"]), None)
            if pin_config:
                pin_name = pin_config.get("name", f"Output {i+1}")
                pin_type = pin_config.get("type", "").upper()
                summary += f"Output {i+1}: {pin_name} is {pin_type}\n"
            else:
                summary += f"Output {i+1}: Not configured\n"

        return self.async_show_form(
            step_id="configure_outputs",
            data_schema=vol.Schema({
                vol.Required("output"): vol.In(output_options),
            }),
            description_placeholders={"status": summary},
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
        """Edit a specific input or output - Step 1: Name and Type."""
        pin_num = self._pin_to_configure
        is_input = self._is_input
        
        if user_input is not None:
            # Store config for next step
            self._input_config = {
                "pin": pin_num,
                "name": user_input["name"],
                "type": user_input["type"],
                "isInput": is_input,
            }
            
            # If unconfigured, save immediately
            if user_input["type"] == "unconfigured":
                # TODO: Add API call to remove/unconfigure pin
                if is_input:
                    return await self.async_step_configure_inputs()
                else:
                    return await self.async_step_configure_outputs()
            
            # For outputs, save immediately (no additional config needed)
            if not is_input:
                return await self._save_pin_config(self._input_config)
            
            # For inputs with type "button", go to button mode selection
            if user_input["type"] == "button":
                return await self.async_step_button_mode()
            
            # For binary_sensor inputs, save with classic mode default
            self._input_config["buttonMode"] = BUTTON_MODE_CLASSIC
            return await self._save_pin_config(self._input_config)

        # Get current configuration
        pin_config = next((p for p in self._all_pins if p.get("pin") == pin_num), None)
        current_name = pin_config.get("name", "") if pin_config else ""
        current_type = pin_config.get("type", "") if pin_config else ""
        current_button_mode = pin_config.get("buttonMode", BUTTON_MODE_CLASSIC) if pin_config else BUTTON_MODE_CLASSIC

        # Default names
        if not current_name:
            if is_input:
                current_name = f"Input {pin_num + 1}"
            else:
                current_name = f"Output {pin_num + 1}"

        # Type options
        if is_input:
            type_options = {
                "binary_sensor": "Binary Sensor (e.g. door/window sensor)",
                "button": "Button (e.g. physical button with triggers)",
                "unconfigured": "Not Configured",
            }
            # Map current config to new type system
            if current_type == "binary_sensor":
                if current_button_mode in [BUTTON_MODE_CLASSIC, BUTTON_MODE_PUSH]:
                    current_type = "button"
                else:
                    current_type = "binary_sensor"
            if not current_type:
                current_type = "button"  # Default to button
        else:
            type_options = {
                "light": "Light (e.g. on/off light)",
                "switch": "Switch (e.g. simple on/off switch)",
                "cover": "Cover (e.g. blinds, shades, garage door or gate)",
                "unconfigured": "Not Configured",
            }
            if not current_type:
                current_type = "light"

        pin_label = f"Input {pin_num + 1}" if is_input else f"Output {pin_num + 1}"
        
        # Build description
        if is_input:
            description = f"Configure {pin_label}\n\n"
            description += "Step 1: Set the name and type\n\n"
        else:
            description = f"Configure {pin_label}\n\n"
            description += "Step 1: Set the name and type\n\n"
        
        # Build schema
        schema_dict = {
            vol.Required("name", default=current_name): str,
            vol.Required("type", default=current_type): vol.In(type_options),
        }
        
        return self.async_show_form(
            step_id="edit_pin",
            data_schema=vol.Schema(schema_dict),
            description_placeholders={"info": description},
        )
    
    async def async_step_button_mode(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Configure button mode - Step 2 for button inputs."""
        if user_input is not None:
            button_mode = user_input["buttonMode"]
            self._input_config["buttonMode"] = button_mode
            
            # For classic mode, go to single trigger output selection
            if button_mode == BUTTON_MODE_CLASSIC:
                return await self.async_step_classic_trigger()
            
            # For push mode, go to push button triggers
            return await self.async_step_push_triggers()
        
        # Get current button mode
        pin_num = self._pin_to_configure
        pin_config = next((p for p in self._all_pins if p.get("pin") == pin_num), None)
        current_button_mode = pin_config.get("buttonMode", BUTTON_MODE_CLASSIC) if pin_config else BUTTON_MODE_CLASSIC
        
        button_mode_options = {
            BUTTON_MODE_CLASSIC: "Classic Button (Simple On/Off)",
            BUTTON_MODE_PUSH: "Push Button (Short/Long/Double Press)",
        }
        
        # Build context message
        pin_label = f"Input {pin_num + 1}"
        config_name = self._input_config.get("name", "")
        description = f"Configure {pin_label}: {config_name}\n\n"
        description += "Step 2 of 3: Select button mode\n\n"
        
        return self.async_show_form(
            step_id="button_mode",
            data_schema=vol.Schema({
                vol.Required("buttonMode", default=current_button_mode): vol.In(button_mode_options),
            }),
            description_placeholders={
                "info": description,
            },
        )
    
    async def async_step_classic_trigger(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Configure trigger output for classic button."""
        if user_input is not None:
            self._input_config["trigger_output"] = user_input["trigger_output"]
            return await self._save_pin_config(self._input_config)
        
        # Build list of ALL outputs (any can be selected)
        output_options = {255: "None (No trigger)"}
        for i in range(16):
            output_config = next((p for p in self._all_pins if p.get("pin") == i and not p.get("isInput", False)), None)
            if output_config:
                pin_type = output_config.get("type", "").capitalize()
                output_options[i] = f"Output {i+1}: {output_config.get('name', 'Unnamed')} ({pin_type})"
            else:
                output_options[i] = f"Output {i+1}: Not configured"
        
        # Get current trigger (default to same pin number)
        pin_num = self._pin_to_configure
        current_trigger = pin_num
        
        # Build context message
        pin_label = f"Input {pin_num + 1}"
        config_name = self._input_config.get("name", "")
        description = f"Configure {pin_label}: {config_name}\n\n"
        description += "Step 3 of 3: Select output to control\n\n"
        description += "Mode: Classic Button (On/Off Toggle)\n\n"
        description += "The button will directly toggle the selected output.\n"
        description += "Select 'None' if you only want to use this as a sensor."
        
        return self.async_show_form(
            step_id="classic_trigger",
            data_schema=vol.Schema({
                vol.Required("trigger_output", default=current_trigger): vol.In(output_options),
            }),
            description_placeholders={
                "info": description,
            },
        )
    
    async def async_step_push_triggers(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Configure trigger outputs for push button - all three press types."""
        if user_input is not None:
            self._input_config["short_press_output"] = user_input["short_press_output"]
            self._input_config["long_press_output"] = user_input["long_press_output"]
            self._input_config["double_press_output"] = user_input["double_press_output"]
            
            # Add default timing values
            self._input_config["longPressDuration"] = 500
            self._input_config["doublePressTimeframe"] = 300
            
            return await self._save_pin_config(self._input_config)
        
        # Build list of ALL outputs (any can be selected, even duplicates)
        output_options = {255: "None (No action)"}
        for i in range(16):
            output_config = next((p for p in self._all_pins if p.get("pin") == i and not p.get("isInput", False)), None)
            if output_config:
                pin_type = output_config.get("type", "").capitalize()
                output_options[i] = f"Output {i+1}: {output_config.get('name', 'Unnamed')} ({pin_type})"
            else:
                output_options[i] = f"Output {i+1}: Not configured"
        
        # Defaults (all can be different or the same)
        pin_num = self._pin_to_configure
        
        # Build context message
        pin_label = f"Input {pin_num + 1}"
        config_name = self._input_config.get("name", "")
        description = f"Configure {pin_label}: {config_name}\n\n"
        description += "Step 3 of 3: Assign actions for each press type\n\n"
        description += "Mode: Push Button (Multi-Action)\n\n"
        description += "Press Types:\n"
        description += "• Short Press - Quick tap (< 500ms)\n"
        description += "• Long Press - Hold button (≥ 500ms)\n"
        description += "• Double Press - Two quick taps (< 300ms apart)\n\n"
        description += "Each press type can toggle a different output.\n"
        description += "You can also use these in automations via events.\n\n"
        description += "Select 'None' for any press type you don't want to use."
        
        return self.async_show_form(
            step_id="push_triggers",
            data_schema=vol.Schema({
                vol.Required("short_press_output", default=255): vol.In(output_options),
                vol.Required("long_press_output", default=255): vol.In(output_options),
                vol.Required("double_press_output", default=255): vol.In(output_options),
            }),
            description_placeholders={
                "info": description,
            },
        )
    
    async def _save_pin_config(self, config_data: dict[str, Any]) -> FlowResult:
        """Save pin configuration to device."""
        host = self.config_entry.data[CONF_HOST]
        session = async_get_clientsession(self.hass)
        pin_num = config_data["pin"]
        is_input = config_data["isInput"]
        
        # Prepare payload for device
        payload = {
            "pin": pin_num,
            "type": "binary_sensor" if config_data.get("type") == "button" else config_data["type"],
            "name": config_data["name"],
            "isInput": is_input,
        }
        
        # Add button mode if present
        if "buttonMode" in config_data:
            payload["buttonMode"] = config_data["buttonMode"]
        
        # Add timing if present
        if "longPressDuration" in config_data:
            payload["longPressDuration"] = config_data["longPressDuration"]
        if "doublePressTimeframe" in config_data:
            payload["doublePressTimeframe"] = config_data["doublePressTimeframe"]
        
        try:
            async with session.post(
                f"http://{host}/api/pin/configure",
                json=payload,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status == 200:
                    # Set trigger outputs
                    if "trigger_output" in config_data and config_data["trigger_output"] != 255:
                        await self._set_trigger(pin_num, config_data["trigger_output"])
                    
                    # Handle push button triggers (short/long/double)
                    if ("short_press_output" in config_data or 
                        "long_press_output" in config_data or 
                        "double_press_output" in config_data):
                        await self._set_push_triggers(
                            pin_num,
                            config_data.get("short_press_output", 255),
                            config_data.get("long_press_output", 255),
                            config_data.get("double_press_output", 255)
                        )
                    
                    # Refresh and return
                    await self._fetch_pin_data()
                    await self.hass.config_entries.async_reload(self.config_entry.entry_id)
                    
                    if is_input:
                        return await self.async_step_configure_inputs()
                    else:
                        return await self.async_step_configure_outputs()
        except Exception as err:
            _LOGGER.error("Error configuring pin %s: %s", pin_num, err)
        
        # On error, return to list
        if is_input:
            return await self.async_step_configure_inputs()
        else:
            return await self.async_step_configure_outputs()
    
    async def _set_trigger(self, input_pin: int, output_pin: int) -> None:
        """Set trigger mapping for an input."""
        host = self.config_entry.data[CONF_HOST]
        session = async_get_clientsession(self.hass)
        
        trigger_data = {
            "inputPin": input_pin,
            "outputPin": output_pin,
        }
        
        try:
            async with session.post(
                f"http://{host}/api/input/trigger/set",
                json=trigger_data,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status != 200:
                    _LOGGER.warning("Failed to set input trigger")
        except Exception as err:
            _LOGGER.warning("Error setting input trigger: %s", err)
    
    async def _set_push_triggers(
        self, 
        input_pin: int, 
        short_press_output: int,
        long_press_output: int,
        double_press_output: int
    ) -> None:
        """Set push button trigger mappings for an input."""
        host = self.config_entry.data[CONF_HOST]
        session = async_get_clientsession(self.hass)
        
        trigger_data = {
            "inputPin": input_pin,
            "shortPressOutput": short_press_output,
            "longPressOutput": long_press_output,
            "doublePressOutput": double_press_output,
        }
        
        try:
            async with session.post(
                f"http://{host}/api/input/trigger/set",
                json=trigger_data,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status != 200:
                    _LOGGER.warning("Failed to set push button triggers")
        except Exception as err:
            _LOGGER.warning("Error setting push button triggers: %s", err)

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