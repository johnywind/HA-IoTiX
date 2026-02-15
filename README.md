# IoTiX

<p align="center">
  <img src="./icon.png" alt="IoTiX Logo" width="512"/>
</p>

Home Assistant integration for IoTiX Adam (ESP32 + PCF8575).

## Features
- Zeroconf discovery
- Pin configuration as light, switch, cover, binary sensor
- Persistent pin configuration and device name

## Installation (HACS)
1. Add this repository to HACS (Custom repositories).
2. Select category: Integration.
3. Install "IoTiX".
4. Restart Home Assistant.
5. Go to Settings -> Devices & Services and add the integration.

## Installation (Manual)
1. Copy the `iotix_adam` folder into `config/custom_components/`.
2. Restart Home Assistant.
3. Go to Settings -> Devices & Services and add the integration.

## Notes
- Firmware files are not installed by HACS.
- If you change the device name or pin configuration, the device stores settings persistently.

## API Endpoints
- GET /api/info
- GET /api/pins/available
- GET /api/pins/config
- GET /api/pin/state?pin=NUM
- POST /api/pin/configure
- POST /api/pin/control
- POST /api/device/name
- POST /api/reset

## Troubleshooting
- Discovery not working: ensure mDNS is allowed on the LAN and the device is on the same network.
- No entities after adding: open Options and configure pins.
- Device name not updating: confirm /api/device/name returns status ok and restart the integration.
