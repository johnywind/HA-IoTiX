"""Update platform for IoTiX Adam."""
from __future__ import annotations

import logging
from typing import Any
from datetime import timedelta
import asyncio

import aiohttp

from homeassistant.components.update import (
    UpdateEntity,
    UpdateEntityFeature,
    UpdateDeviceClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.helpers.event import async_track_time_interval

from .const import DOMAIN, CONF_MAC, MANUFACTURER, MODEL
from .coordinator import AdamCoordinator

_LOGGER = logging.getLogger(__name__)

# GitHub repository for releases
GITHUB_REPO = "johnywind/adam-ha-firmware"
GITHUB_RELEASE_URL = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"

# Check for updates every 6 hours
UPDATE_CHECK_INTERVAL = timedelta(hours=6)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the IoTiX Adam update entity."""
    coordinator: AdamCoordinator = hass.data[DOMAIN][config_entry.entry_id]
    
    async_add_entities([AdamUpdateEntity(coordinator, config_entry)])


class AdamUpdateEntity(CoordinatorEntity[AdamCoordinator], UpdateEntity):
    """Representation of Adam firmware update entity."""

    _attr_device_class = UpdateDeviceClass.FIRMWARE
    _attr_supported_features = UpdateEntityFeature.INSTALL | UpdateEntityFeature.PROGRESS
    _attr_title = "Adam Controller"
    _attr_has_entity_name = True

    def __init__(self, coordinator: AdamCoordinator, config_entry: ConfigEntry) -> None:
        """Initialize the update entity."""
        super().__init__(coordinator)
        self._config_entry = config_entry
        self._attr_unique_id = f"{config_entry.data[CONF_MAC]}_update"
        self._latest_version: str | None = None
        self._release_url: str | None = None
        self._release_notes: str | None = None
        self._unsub_update_check = None
        
        # Device info
        device_info_data = coordinator.data.get("device_info", {})
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.mac)},
            name=device_info_data.get("name", "Adam Controller"),
            manufacturer=MANUFACTURER,
            model=MODEL,
            sw_version=device_info_data.get("firmware_version"),
            configuration_url=f"http://{coordinator.host}",
        )

    async def async_added_to_hass(self) -> None:
        """When entity is added to hass."""
        await super().async_added_to_hass()
        
        # Check for updates immediately
        await self.async_check_for_update()
        
        # Schedule periodic update checks
        self._unsub_update_check = async_track_time_interval(
            self.hass,
            self._async_check_update_interval,
            UPDATE_CHECK_INTERVAL,
        )

    async def async_will_remove_from_hass(self) -> None:
        """When entity will be removed from hass."""
        if self._unsub_update_check:
            self._unsub_update_check()
        await super().async_will_remove_from_hass()

    async def _async_check_update_interval(self, _=None) -> None:
        """Periodic update check callback."""
        await self.async_check_for_update()
        self.async_write_ha_state()

    @property
    def name(self) -> str:
        """Return the name of the entity."""
        return "Firmware"

    @property
    def installed_version(self) -> str | None:
        """Return the installed firmware version."""
        return self.coordinator.data.get("device_info", {}).get("firmware_version")

    @property
    def latest_version(self) -> str | None:
        """Return the latest available firmware version."""
        return self._latest_version or self.installed_version

    @property
    def release_url(self) -> str | None:
        """Return the URL for release notes."""
        return self._release_url

    @property
    def release_summary(self) -> str | None:
        """Return the release notes."""
        return self._release_notes

    async def async_check_for_update(self) -> None:
        """Check for latest firmware version from GitHub."""
        session = async_get_clientsession(self.hass)
        
        try:
            async with session.get(
                GITHUB_RELEASE_URL,
                timeout=aiohttp.ClientTimeout(total=10),
                headers={"Accept": "application/vnd.github.v3+json"}
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    
                    # Get version from tag_name (e.g., "v1.0.0" or "1.0.0")
                    tag_name = data.get("tag_name", "")
                    self._latest_version = tag_name.lstrip("v")
                    
                    # Get release URL and notes
                    self._release_url = data.get("html_url")
                    self._release_notes = data.get("body", "")
                    
                    # Find firmware.bin asset
                    assets = data.get("assets", [])
                    for asset in assets:
                        if asset.get("name") == "firmware.bin":
                            self._release_url = asset.get("browser_download_url")
                            break
                    
                    _LOGGER.debug(
                        "Latest firmware version: %s (installed: %s)",
                        self._latest_version,
                        self.installed_version
                    )
                else:
                    _LOGGER.debug("Failed to check for updates: HTTP %s", resp.status)
                    
        except Exception as err:
            _LOGGER.debug("Error checking for firmware updates: %s", err)

    async def async_update(self) -> None:
        """Update the entity - called periodically."""
        # Parent coordinator handles device data updates
        # We periodically check for new firmware versions
        pass

    async def async_install(
        self, version: str | None, backup: bool, **kwargs: Any
    ) -> None:
        """Install firmware update."""
        if not self._release_url:
            _LOGGER.error("No firmware download URL available")
            return

        session = async_get_clientsession(self.hass)
        host = self.coordinator.host
        
        try:
            # Download firmware from GitHub
            _LOGGER.info("Downloading firmware version %s from %s", version, self._release_url)
            self._attr_in_progress = True
            self.async_write_ha_state()
            
            async with session.get(
                self._release_url,
                timeout=aiohttp.ClientTimeout(total=60),
            ) as resp:
                if resp.status != 200:
                    _LOGGER.error("Failed to download firmware: HTTP %s", resp.status)
                    self._attr_in_progress = False
                    self.async_write_ha_state()
                    return
                
                firmware_data = await resp.read()
                _LOGGER.info("Downloaded %s bytes", len(firmware_data))
            
            # Upload to device
            _LOGGER.info("Uploading firmware to device at %s", host)
            data = aiohttp.FormData()
            data.add_field('file', firmware_data, filename='firmware.bin', content_type='application/octet-stream')
            
            async with session.post(
                f"http://{host}/api/update",
                data=data,
                timeout=aiohttp.ClientTimeout(total=120),
            ) as resp:
                if resp.status == 200:
                    _LOGGER.info("Firmware uploaded successfully, device rebooting")
                    self._attr_in_progress = False
                    self.async_write_ha_state()
                    
                    # Wait for device to reboot and stabilize
                    _LOGGER.info("Waiting 15 seconds for device to reboot...")
                    await asyncio.sleep(15)
                    
                    # Refresh coordinator to get new firmware version
                    _LOGGER.info("Refreshing device data to verify update")
                    await self.coordinator.async_request_refresh()
                    
                    # The installed_version will now reflect the new version
                    _LOGGER.info("Firmware update complete: %s", self.installed_version)
                else:
                    error_text = await resp.text()
                    _LOGGER.error("Firmware upload failed: %s", error_text)
                    self._attr_in_progress = False
                    self.async_write_ha_state()
                    
        except Exception as err:
            _LOGGER.error("Firmware update failed: %s", err)
            self._attr_in_progress = False
            self.async_write_ha_state()
