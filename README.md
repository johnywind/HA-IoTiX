# IoTiX

<p align="center">
  <img src="./icon.png" alt="IoTiX Logo" width="512"/>
</p>

Home Assistant integration for IoTiX Adam controller (ESP32 + PCF8575).

## Features

### Hardware Support
- **16 configurable I/O pins** via PCF8575 (inputs and outputs)
- **XR8 relay extension modules** - Add up to 8 modules, 8 relays each (64 total relays)
- **Cover control** - 2 inputs + 2 outputs per cover with timers
- **Real-time updates** - 1-second polling for instant button detection

### Entity Types
- 💡 **Lights** - On/off with software brightness control
- 🔌 **Switches** - Simple on/off control
- 🚪 **Covers** - Curtains/blinds with timed movement and interlock
- 🔘 **Binary Sensors** - Button inputs with event detection
- 📢 **Events** - Short press, long press, double press detection
- 🔄 **Update** - Automatic firmware update notifications

### Smart Features
- **Input Triggers** - Buttons can directly control outputs
- **Button Modes**:
  - Classic: Button follows input state (on/off)
  - Push: Separate actions for short/long/double press
- **Automatic Discovery** - Zeroconf/mDNS auto-detection
- **Automatic Updates** - Firmware updates via Update entity
- **Persistent Config** - Device stores settings in flash memory

---

## Installation

### Method 1: HACS (Recommended)

1. **Install HACS** (if not already installed):
   - Follow instructions at https://hacs.xyz/docs/setup/download

2. **Add Custom Repository**:
   - Open HACS in Home Assistant
   - Click "Integrations" → "⋮" menu → "Custom repositories"
   - Add: `https://github.com/johnywind/HA-IoTiX`
   - Category: Integration
   - Click "Add"

3. **Install IoTiX**:
   - Search for "IoTiX" in HACS
   - Click "Download"
   - **Restart Home Assistant**

4. **Add Device**:
   - Go to Settings → Devices & Services
   - Click "Add Integration"
   - Search for "IoTiX"
   - Device should be auto-discovered, or enter IP manually

### Method 2: Manual Installation

1. Download the latest release from [GitHub](https://github.com/johnywind/HA-IoTiX/releases)
2. Copy the `custom_components/iotix` folder to your `config/custom_components/` directory
3. Restart Home Assistant
4. Go to Settings → Devices & Services → Add Integration → "IoTiX"

---

## Quick Start

### 1. Device Discovery
- Power on your Adam controller
- Home Assistant automatically detects it via mDNS
- Click notification to add the device

### 2. Configure Pins
- Go to device page → "Configure"
- Select "Configure Inputs" or "Configure Outputs"
- Choose a pin and set:
  - Name (e.g., "Living Room Light")
  - Type (light, switch, binary_sensor)
  - Button mode (for inputs)

### 3. Configure Covers (Optional)
- Select "Configure Covers"
- Choose 2 inputs (up/down buttons) and 2 outputs (motor control)
- Set timers for full open/close duration

### 4. Add XR8 Modules (Optional)
- Select "Configure XR8 Relay Modules"
- Add module with I2C address (0x20-0x27)
- Name your 8 relays
- Use XR8 relays in triggers and covers

### 5. Set Up Automations
- Use button events for complex automations
- Configure input triggers for direct button→relay control
- Create scenes with multiple outputs

---

## Configuration

### API Endpoints
The device exposes these endpoints:

- `GET /api/info` - Device information and firmware version
- `GET /api/pins/available` - Available I/O pins
- `GET /api/pins/config` - Current pin configuration
- `GET /api/pin/state?pin=NUM&isInput=0/1` - Pin state
- `POST /api/pin/configure` - Configure a pin
- `POST /api/pin/control` - Control output state
- `POST /api/device/name` - Set device name
- `POST /api/input/trigger/set` - Configure input trigger
- `GET /api/covers/config` - Cover configuration
- `POST /api/cover/configure` - Configure a cover
- `POST /api/cover/control` - Control cover movement
- `GET /api/xr8/list` - List XR8 modules
- `POST /api/xr8/configure` - Configure XR8 module
- `POST /api/xr8/relay/control` - Control XR8 relay
- `POST /api/update` - OTA firmware update
- `POST /api/reset` - Factory reset

### Advanced Configuration

#### Input Triggers
Configure buttons to directly control outputs without Home Assistant:

1. Configure input as binary_sensor
2. Select button mode:
   - **Classic**: Relay follows button (press=on, release=off)
   - **Push**: Toggle relay on short press, separate actions for long/double
3. Select output to control (physical or XR8 relay)

#### Cover Settings
- **Interlock**: Prevents up+down pressed simultaneously (safety)
- **Timers**: Time in seconds for full open/close
- **Stop**: Any button press during movement stops the cover

---

## Updates

### Integration Updates (via HACS)
- HACS checks daily for new integration versions
- Update notification appears in HACS
- Click "Update" → Restart Home Assistant
- See [INTEGRATION_UPDATE.md](INTEGRATION_UPDATE.md) for details

### Firmware Updates (via Home Assistant)
- Automatic check every 6 hours for new firmware
- Update notification on device page
- Click "Install" on Update entity
- Device downloads and flashes automatically
- See [FIRMWARE_UPDATE.md](FIRMWARE_UPDATE.md) for details

**Current Versions:**
- Integration: Check manifest.json or HACS
- Firmware: Check device info or `/api/info` endpoint

---

## Troubleshooting

### Discovery Not Working
- Ensure mDNS is enabled on your network
- Check device and Home Assistant are on same subnet
- Try adding manually with IP address
- Verify device SSID shows "Adam_XXXXXX" in WiFi

### No Entities After Adding
- Open device page → click "Configure"
- Configure at least one input or output
- Entities appear after configuration

### Button Not Responding
- Check polling interval (default 1 second)
- Verify input is configured as binary_sensor
- Check button mode matches your use case
- Review logs: Settings → System → Logs

### XR8 Relays Not Appearing
- Verify I2C address (0x20-0x27) is correct
- Check wiring: SDA=GPIO21, SCL=GPIO22
- Ensure module is configured (not just added)
- Only configured modules create entities

### Firmware Update Failed
- Check device is online: `ping DEVICE_IP`
- Verify firmware.bin is valid
- Ensure sufficient time for download (slow connection)
- Try manual update via curl
- See logs via Serial Monitor (115200 baud)

### Cover Not Moving
- Verify both outputs are assigned and configured
- Check timers are set (> 0 seconds)
- Ensure interlock isn't blocking movement
- Test outputs individually as switches first

---

## Technical Details

### Hardware Requirements
- ESP32 development board
- PCF8575 I2C I/O expander (address 0x26 outputs, 0x27 inputs)
- PCF8574 I2C I/O expander for XR8 modules (addresses 0x20-0x27)
- 5V power supply
- Relay modules for outputs

### Software Stack
- **Firmware**: Arduino framework for ESP32
- **Communication**: HTTP REST API
- **Discovery**: mDNS/Zeroconf
- **Storage**: NVS (Non-Volatile Storage)
- **OTA**: HTTP-based firmware updates

### Integration Details
- **Platform**: Home Assistant custom integration
- **Language**: Python 3
- **Update Method**: 1-second polling (fast for button detection)
- **Entity Types**: light, switch, cover, binary_sensor, event, update
- **Config Flow**: Full UI configuration, no YAML needed

### Performance
- Update interval: 1 second (configurable in const.py)
- Button event latency: < 1 second
- Cover movement: Timer-based, hardware-controlled
- Max devices: Unlimited (one integration per device)
