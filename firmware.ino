// adam_controller.ino
#include <WiFi.h>
#include <ESPmDNS.h>
#include <WebServer.h>
#include <ArduinoJson.h>
#include <Wire.h>
#include <PCF8575.h>
#include <Preferences.h>
#include <WiFiManager.h>

// Configurare PCF8575
PCF8575 pcf8575(0x26);        // Outputs
PCF8575 pcf8575_inputs(0x27); // Inputs

WebServer server(80);
Preferences prefs;

static const char* NVS_NAMESPACE = "adam";
static const char* NVS_PINS_KEY = "pins_cfg";
static const char* NVS_CONF_KEY = "pin_conf";
static const char* NVS_TRIGGERS_KEY = "triggers";  // New key for input triggers

static const size_t MAX_TYPE_LEN = 16;
static const size_t MAX_NAME_LEN = 32;
static const size_t MAX_DEVICE_NAME_LEN = 48;

static const uint8_t RESET_PIN_A = 0;
static const uint8_t RESET_PIN_B = 15;
static const uint32_t RESET_HOLD_MS = 5000;
static const uint32_t RESET_POLL_MS = 50;
static const uint32_t RESET_WINDOW_MS = 30000;

static const char* NVS_DEVICE_NAME_KEY = "dev_name";

// Structură pentru configurarea pinilor
struct PinConfig {
  uint8_t pin;
  char type[MAX_TYPE_LEN]; // "light", "switch", "cover", "binary_sensor"
  char name[MAX_NAME_LEN];
  bool state;
  uint8_t brightness; // pentru PWM software
};

// Structură pentru input triggering (mapare input -> output)
struct InputTrigger {
  uint8_t inputPin;
  uint8_t outputPin; // Which output to trigger (0-15, or 255 = none)
  bool triggered;    // Flag to track if this input was already triggered
};

PinConfig pinConfigs[16]; // PCF8575 have 16 pins
bool pinConfigured[16] = {false};
InputTrigger inputTriggers[16]; // Max 16 inputs, each can trigger one output
uint32_t bootStartMs = 0;
char deviceName[MAX_DEVICE_NAME_LEN];

// Forward declaration for early helper functions
void initDefaultInputTriggers();

void savePinConfig() {
  prefs.begin(NVS_NAMESPACE, false);
  prefs.putBytes(NVS_PINS_KEY, pinConfigs, sizeof(pinConfigs));
  prefs.putBytes(NVS_CONF_KEY, pinConfigured, sizeof(pinConfigured));
  prefs.end();
}

void saveInputTriggers() {
  prefs.begin(NVS_NAMESPACE, false);
  prefs.putBytes(NVS_TRIGGERS_KEY, inputTriggers, sizeof(inputTriggers));
  prefs.end();
}

void loadInputTriggers() {
  prefs.begin(NVS_NAMESPACE, true);
  size_t triggersLen = prefs.getBytesLength(NVS_TRIGGERS_KEY);
  
  if (triggersLen == sizeof(inputTriggers)) {
    prefs.getBytes(NVS_TRIGGERS_KEY, inputTriggers, sizeof(inputTriggers));
  } else {
    // Initialize default triggers: input N triggers output N
    initDefaultInputTriggers();
  }
  prefs.end();
}

void initDefaultInputTriggers() {
  for (int i = 0; i < 16; i++) {
    inputTriggers[i].inputPin = i;
    // Map: input 0 -> output 8, input 1 -> output 9, ..., input 7 -> output 15
    if (i < 8) {
      inputTriggers[i].outputPin = i + 8;  // Inputs 0-7 trigger outputs 8-15
    } else {
      inputTriggers[i].outputPin = 255;  // Outputs don't trigger anything by default
    }
    inputTriggers[i].triggered = false;
  }
  saveInputTriggers();
}

void saveDeviceName() {
  prefs.begin(NVS_NAMESPACE, false);
  prefs.putString(NVS_DEVICE_NAME_KEY, deviceName);
  prefs.end();
}

void makeDefaultDeviceName() {
  String mac = WiFi.macAddress();
  String macNoSep = mac;
  macNoSep.replace(":", "");
  String suffix = macNoSep.substring(macNoSep.length() - 6);
  String defaultName = "Adam-" + suffix;
  defaultName.toCharArray(deviceName, MAX_DEVICE_NAME_LEN);
}

void loadDeviceName() {
  prefs.begin(NVS_NAMESPACE, true);
  String stored = prefs.getString(NVS_DEVICE_NAME_KEY, "");
  prefs.end();

  if (stored.length() == 0) {
    makeDefaultDeviceName();
    saveDeviceName();
  } else {
    stored.toCharArray(deviceName, MAX_DEVICE_NAME_LEN);
  }
}

void setDefaultPinName(uint8_t pin, const String& type, char* outName, size_t outLen) {
  String defaultName = "Output " + String(pin + 1);
  if (type == "binary_sensor") {
    defaultName = "Input " + String(pin + 1);
  }
  defaultName.toCharArray(outName, outLen);
}

void initDefaultConfig() {
  // Configure pins 0-15
  // Pins 0-7: binary_sensor (inputs)
  // Pins 8-15: light (outputs)
  for (int i = 0; i < 16; i++) {
    pinConfigs[i].pin = i;
    pinConfigs[i].state = false;
    pinConfigs[i].brightness = 255;
    memset(pinConfigs[i].type, 0, MAX_TYPE_LEN);
    memset(pinConfigs[i].name, 0, MAX_NAME_LEN);
    
    // Configure as input (binary_sensor) or output (light)
    if (i < 8) {
      // Inputs: pins 0-7
      strcpy(pinConfigs[i].type, "binary_sensor");
      String defaultName = "Input " + String(i + 1);
      defaultName.toCharArray(pinConfigs[i].name, MAX_NAME_LEN);
    } else {
      // Outputs: pins 8-15
      strcpy(pinConfigs[i].type, "light");
      String defaultName = "Output " + String(i - 7); // Output 1-8
      defaultName.toCharArray(pinConfigs[i].name, MAX_NAME_LEN);
    }
    pinConfigured[i] = true;
  }
  
  initDefaultInputTriggers();
}

void applyPinModes() {
  for (int i = 0; i < 16; i++) {
    if (!pinConfigured[i]) {
      continue;
    }
    String type = String(pinConfigs[i].type);
    if (type != "binary_sensor") {
      pcf8575.write(i, pinConfigs[i].state ? HIGH : LOW);
    }
  }
}

void loadPinConfig() {
  prefs.begin(NVS_NAMESPACE, true);
  size_t cfgLen = prefs.getBytesLength(NVS_PINS_KEY);
  size_t confLen = prefs.getBytesLength(NVS_CONF_KEY);

  if (cfgLen == sizeof(pinConfigs) && confLen == sizeof(pinConfigured)) {
    prefs.getBytes(NVS_PINS_KEY, pinConfigs, sizeof(pinConfigs));
    prefs.getBytes(NVS_CONF_KEY, pinConfigured, sizeof(pinConfigured));
  } else {
    initDefaultConfig();
    savePinConfig();  // Save the default configuration
  }
  prefs.end();
  
  // Load input triggers
  loadInputTriggers();
}

bool isOutputPin(uint8_t pin) {
  if (!pinConfigured[pin]) {
    return false;
  }
  return String(pinConfigs[pin].type) != "binary_sensor";
}

bool readResetBridge() {
  bool pinAWasOutput = isOutputPin(RESET_PIN_A);
  bool pinBWasOutput = isOutputPin(RESET_PIN_B);
  bool pinAState = false;
  bool pinBState = false;

  if (pinAWasOutput) {
    pinAState = pinConfigs[RESET_PIN_A].state;
  }
  if (pinBWasOutput) {
    pinBState = pinConfigs[RESET_PIN_B].state;
  }

  bool pinALow = pcf8575_inputs.read(RESET_PIN_A) == LOW;
  bool pinBLow = pcf8575_inputs.read(RESET_PIN_B) == LOW;

  if (pinAWasOutput) {
    pcf8575.write(RESET_PIN_A, pinAState ? HIGH : LOW);
  }
  if (pinBWasOutput) {
    pcf8575.write(RESET_PIN_B, pinBState ? HIGH : LOW);
  }

  return pinALow && pinBLow;
}

void factoryReset() {
  initDefaultConfig();
  for (int i = 0; i < 16; i++) {
    pcf8575.write(i, LOW);
  }
  savePinConfig();
  Serial.println("Factory reset complete, restarting...");
  delay(200);
  ESP.restart();
}

void checkFactoryReset() {
  static uint32_t lastPollMs = 0;
  static uint32_t holdStartMs = 0;

  uint32_t nowMs = millis();
  if (nowMs - bootStartMs > RESET_WINDOW_MS) {
    return;
  }
  if (nowMs - lastPollMs < RESET_POLL_MS) {
    return;
  }
  lastPollMs = nowMs;

  if (readResetBridge()) {
    if (holdStartMs == 0) {
      holdStartMs = nowMs;
    } else if (nowMs - holdStartMs >= RESET_HOLD_MS) {
      factoryReset();
    }
  } else {
    holdStartMs = 0;
  }
}

// Forward declarations
void handleInfo();
void handleDeviceName();
void handlePinsAvailable();
void handlePinsConfig();
void handlePinConfigure();
void handlePinState();
void handlePinControl();
void handleInputTriggers();
void handleSetInputTrigger();
void handleReset();
void processInputTriggers();
void initDefaultInputTriggers();

void setup() {
  Serial.begin(115200);
  delay(1000); // Wait for serial to stabilize
  Serial.println("\n\nAdam Controller Starting...");
  bootStartMs = millis();
  
  // Initialize I2C bus (GPIO 21 = SDA, GPIO 22 = SCL on ESP32)
  Wire.begin(21, 22);
  delay(100);
  
  // Initialize PCF8575 modules
  pcf8575.begin();        // Outputs at 0x26
  pcf8575_inputs.begin(); // Inputs at 0x27
  Serial.println("PCF8575 modules initialized");
  delay(100);
  
  // Load configuration from storage
  loadDeviceName();
  loadPinConfig();
  
  // WiFiManager - automatically handles AP and WiFi connection
  WiFiManager wm;
  
  // Uncomment to reset saved WiFi settings
  // wm.resetSettings();
  
  // Try to connect to saved WiFi, otherwise starts AP mode
  String apName = String(deviceName);
  bool res = wm.autoConnect(apName.c_str(), "12345678");
  
  if (res) {
    Serial.println("WiFi connected!");
    Serial.println("IP: " + WiFi.localIP().toString());
  } else {
    Serial.println("Failed to connect. AP mode active.");
    Serial.println("AP SSID: " + apName);
    Serial.println("AP IP: " + WiFi.softAPIP().toString());
  }
  
  applyPinModes();
  
  // mDNS for discovery
  MDNS.begin(String(deviceName).c_str());
  MDNS.addService("_iotix-adam", "_tcp", 80);
  MDNS.addServiceTxt("_iotix-adam", "_tcp", "version", "1.0");
  MDNS.addServiceTxt("_iotix-adam", "_tcp", "mac", WiFi.macAddress());
  MDNS.addServiceTxt("_iotix-adam", "_tcp", "model", "Adam");
  MDNS.addServiceTxt("_iotix-adam", "_tcp", "manufacturer", "IoTiX");
  
  // API endpoints
  server.on("/api/info", HTTP_GET, handleInfo);
  server.on("/api/device/name", HTTP_POST, handleDeviceName);
  server.on("/api/pins/available", HTTP_GET, handlePinsAvailable);
  server.on("/api/pins/config", HTTP_GET, handlePinsConfig);
  server.on("/api/pin/configure", HTTP_POST, handlePinConfigure);
  server.on("/api/pin/state", HTTP_GET, handlePinState);
  server.on("/api/pin/control", HTTP_POST, handlePinControl);
  server.on("/api/input/triggers", HTTP_GET, handleInputTriggers);
  server.on("/api/input/trigger/set", HTTP_POST, handleSetInputTrigger);
  server.on("/api/reset", HTTP_POST, handleReset);
  
  server.begin();
  
  Serial.println("IoTiX Adam Controller Ready");
  Serial.println("IP: " + WiFi.localIP().toString());
  
  // Debug: Show configured inputs and their trigger mappings
  Serial.println("\n=== Configured Inputs ===");
  for (int i = 0; i < 16; i++) {
    if (pinConfigured[i] && String(pinConfigs[i].type) == "binary_sensor") {
      Serial.print("Input ");
      Serial.print(i);
      Serial.print(" (");
      Serial.print(pinConfigs[i].name);
      Serial.print(") -> Output ");
      Serial.println(inputTriggers[i].outputPin);
    }
  }
  Serial.println("========================\n");
}

void loop() {
  checkFactoryReset();
  processInputTriggers();
  server.handleClient();
}

void processInputTriggers() {
  // Monitor all inputs for state changes and trigger outputs
  for (int i = 0; i < 16; i++) {
    // Check if this pin is configured as an input (binary_sensor)
    if (!pinConfigured[i]) {
      continue;
    }
    
    if (String(pinConfigs[i].type) != "binary_sensor") {
      continue;
    }
    
    // Read the current input state
    bool currentState = pcf8575_inputs.read(i) == HIGH;
    bool wasTriggered = inputTriggers[i].triggered;
    
    // Debug: Show input state changes
    static bool lastStates[16] = {false};
    if (currentState != lastStates[i]) {
      Serial.print("[INPUT] Pin ");
      Serial.print(i);
      Serial.print(" (");
      Serial.print(pinConfigs[i].name);
      Serial.print(") changed to: ");
      Serial.println(currentState ? "HIGH" : "LOW");
      lastStates[i] = currentState;
    }
    
    // If input became HIGH and wasn't triggered yet
    if (currentState && !wasTriggered) {
      Serial.print("[TRIGGER] Input ");
      Serial.print(i);
      Serial.println(" detected HIGH state");
      
      // Mark as triggered
      inputTriggers[i].triggered = true;
      
      // Get the output to trigger
      uint8_t outputPin = inputTriggers[i].outputPin;
      
      Serial.print("[TRIGGER] Attempting to trigger output ");
      Serial.println(outputPin);
      
      // Check if output pin is valid and configured
      if (outputPin >= 16) {
        Serial.println("[TRIGGER] ERROR: Output pin out of range");
      } else if (!pinConfigured[outputPin]) {
        Serial.print("[TRIGGER] ERROR: Output pin ");
        Serial.print(outputPin);
        Serial.println(" is not configured");
      } else if (String(pinConfigs[outputPin].type) == "binary_sensor") {
        Serial.print("[TRIGGER] ERROR: Output pin ");
        Serial.print(outputPin);
        Serial.println(" is configured as input, not output");
      } else if (outputPin < 16 && pinConfigured[outputPin] && String(pinConfigs[outputPin].type) != "binary_sensor") {
        // Trigger the output: toggle for switch, turn on for light/cover
        String type = String(pinConfigs[outputPin].type);
        
        if (type == "switch") {
          // Toggle switch
          pinConfigs[outputPin].state = !pinConfigs[outputPin].state;
        } else if (type == "light") {
          // Turn on light
          pinConfigs[outputPin].state = true;
          pinConfigs[outputPin].brightness = 255;
        } else if (type == "cover") {
          // Activate cover (open/close/stop)
          pinConfigs[outputPin].state = !pinConfigs[outputPin].state;
        }
        
        // Apply the state to the hardware
        pcf8575.write(outputPin, pinConfigs[outputPin].state ? HIGH : LOW);
        
        // Save the new state
        savePinConfig();
        
        Serial.print("[TRIGGER] SUCCESS: Input ");
        Serial.print(i);
        Serial.print(" (");
        Serial.print(pinConfigs[i].name);
        Serial.print(") triggered Output ");
        Serial.print(outputPin);
        Serial.print(" (");
        Serial.print(pinConfigs[outputPin].name);
        Serial.print(") to state: ");
        Serial.println(pinConfigs[outputPin].state ? "ON" : "OFF");
      }
    }
    // If input went back to LOW, reset the triggered flag
    else if (!currentState && wasTriggered) {
      Serial.print("[TRIGGER] Input ");
      Serial.print(i);
      Serial.println(" reset (went LOW)");
      inputTriggers[i].triggered = false;
    }
  }
}

void handleInfo() {
  JsonDocument doc;
  doc["manufacturer"] = "IoTiX";
  doc["model"] = "Adam";
  doc["name"] = String(deviceName);
  doc["mac"] = WiFi.macAddress();
  doc["ip"] = WiFi.localIP().toString();
  doc["firmware_version"] = "1.0.0";
  doc["chip"] = "PCF8575";
  doc["total_pins"] = 16;
  
  String response;
  serializeJson(doc, response);
  server.send(200, "application/json", response);
}

void handleDeviceName() {
  if (!server.hasArg("plain")) {
    server.send(400, "application/json", "{\"error\":\"No body\"}");
    return;
  }

  JsonDocument doc;
  DeserializationError error = deserializeJson(doc, server.arg("plain"));
  if (error) {
    server.send(400, "application/json", "{\"error\":\"Invalid JSON\"}");
    return;
  }

  String name = doc["name"].as<String>();
  name.trim();
  if (name.length() == 0) {
    server.send(400, "application/json", "{\"error\":\"Invalid name\"}");
    return;
  }

  name.toCharArray(deviceName, MAX_DEVICE_NAME_LEN);
  saveDeviceName();
  server.send(200, "application/json", "{\"status\":\"ok\"}");
}

void handlePinsAvailable() {
  JsonDocument doc;
  JsonArray pins = doc.createNestedArray("pins");
  
  for (int i = 0; i < 16; i++) {
    JsonObject pin = pins.createNestedObject();
    pin["pin"] = i;
    pin["name"] = "P" + String(i);
    pin["configured"] = pinConfigured[i];
    
    if (pinConfigured[i]) {
      pin["type"] = String(pinConfigs[i].type);
      pin["label"] = String(pinConfigs[i].name);
    } else {
      JsonArray capabilities = pin.createNestedArray("capabilities");
      capabilities.add("light");
      capabilities.add("switch");
      capabilities.add("cover");
      capabilities.add("binary_sensor");
    }
  }
  
  String response;
  serializeJson(doc, response);
  server.send(200, "application/json", response);
}

void handlePinsConfig() {
  JsonDocument doc;
  JsonArray configs = doc.createNestedArray("pins");
  
  for (int i = 0; i < 16; i++) {
    if (pinConfigured[i]) {
      JsonObject config = configs.createNestedObject();
      config["pin"] = i;
      config["type"] = String(pinConfigs[i].type);
      config["name"] = String(pinConfigs[i].name);
      config["state"] = pinConfigs[i].state;
      
      if (String(pinConfigs[i].type) == "light") {
        config["brightness"] = pinConfigs[i].brightness;
      }
    }
  }
  
  String response;
  serializeJson(doc, response);
  server.send(200, "application/json", response);
}

void handlePinConfigure() {
  if (!server.hasArg("plain")) {
    server.send(400, "application/json", "{\"error\":\"No body\"}");
    return;
  }
  
  JsonDocument doc;
  DeserializationError error = deserializeJson(doc, server.arg("plain"));
  
  if (error) {
    server.send(400, "application/json", "{\"error\":\"Invalid JSON\"}");
    return;
  }
  
  uint8_t pin = doc["pin"];
  String type = doc["type"].as<String>();
  String name = doc["name"].as<String>();
  
  if (pin >= 16) {
    server.send(400, "application/json", "{\"error\":\"Invalid pin\"}");
    return;
  }
  
  pinConfigs[pin].pin = pin;
  memset(pinConfigs[pin].type, 0, MAX_TYPE_LEN);
  type.toCharArray(pinConfigs[pin].type, MAX_TYPE_LEN);

  String finalName = name;
  if (finalName.length() == 0) {
    setDefaultPinName(pin, type, pinConfigs[pin].name, MAX_NAME_LEN);
  } else {
    memset(pinConfigs[pin].name, 0, MAX_NAME_LEN);
    finalName.toCharArray(pinConfigs[pin].name, MAX_NAME_LEN);
  }
  pinConfigs[pin].state = false;
  pinConfigs[pin].brightness = 255;
  pinConfigured[pin] = true;
  
  // Inițializare pin
  if (type != "binary_sensor") {
    pcf8575.write(pin, LOW);
  }

  savePinConfig();
  
  server.send(200, "application/json", "{\"status\":\"ok\"}");
}

void handlePinState() {
  if (!server.hasArg("pin")) {
    server.send(400, "application/json", "{\"error\":\"No pin specified\"}");
    return;
  }
  
  uint8_t pin = server.arg("pin").toInt();
  
  if (pin >= 16 || !pinConfigured[pin]) {
    server.send(400, "application/json", "{\"error\":\"Invalid or unconfigured pin\"}");
    return;
  }
  
  JsonDocument doc;
  doc["pin"] = pin;
  doc["state"] = pinConfigs[pin].state;
  
  if (String(pinConfigs[pin].type) == "light") {
    doc["brightness"] = pinConfigs[pin].brightness;
  }
  
  if (String(pinConfigs[pin].type) == "binary_sensor") {
    doc["state"] = pcf8575_inputs.read(pin) == HIGH;
  }
  
  String response;
  serializeJson(doc, response);
  server.send(200, "application/json", response);
}

void handlePinControl() {
  if (!server.hasArg("plain")) {
    server.send(400, "application/json", "{\"error\":\"No body\"}");
    return;
  }
  
  JsonDocument doc;
  DeserializationError error = deserializeJson(doc, server.arg("plain"));
  
  if (error) {
    server.send(400, "application/json", "{\"error\":\"Invalid JSON\"}");
    return;
  }
  
  uint8_t pin = doc["pin"];
  
  if (pin >= 16 || !pinConfigured[pin]) {
    server.send(400, "application/json", "{\"error\":\"Invalid or unconfigured pin\"}");
    return;
  }
  
  if (String(pinConfigs[pin].type) == "binary_sensor") {
    server.send(400, "application/json", "{\"error\":\"Cannot control input pin\"}");
    return;
  }
  
  String command = doc["command"].as<String>();
  
  if (command == "on") {
    pcf8575.write(pin, HIGH);
    pinConfigs[pin].state = true;
    
    if (doc.containsKey("brightness")) {
      pinConfigs[pin].brightness = doc["brightness"];
      // Pentru PWM software, ar trebui implementat separat
    }
  } else if (command == "off") {
    pcf8575.write(pin, LOW);
    pinConfigs[pin].state = false;
  }

  savePinConfig();
  
  server.send(200, "application/json", "{\"status\":\"ok\"}");
}

void handleReset() {
  for (int i = 0; i < 16; i++) {
    pinConfigured[i] = false;
    pcf8575.write(i, LOW);
  }
  initDefaultConfig();
  savePinConfig();
  server.send(200, "application/json", "{\"status\":\"reset complete\"}");
}
void handleInputTriggers() {
  JsonDocument doc;
  JsonArray triggers = doc.createNestedArray("triggers");
  
  for (int i = 0; i < 16; i++) {
    if (pinConfigured[i] && String(pinConfigs[i].type) == "binary_sensor") {
      JsonObject trigger = triggers.createNestedObject();
      trigger["inputPin"] = i;
      trigger["inputName"] = String(pinConfigs[i].name);
      trigger["outputPin"] = inputTriggers[i].outputPin;
      
      // Get the output name if it exists
      if (inputTriggers[i].outputPin < 16 && pinConfigured[inputTriggers[i].outputPin]) {
        trigger["outputName"] = String(pinConfigs[inputTriggers[i].outputPin].name);
      } else {
        trigger["outputName"] = "None";
      }
    }
  }
  
  String response;
  serializeJson(doc, response);
  server.send(200, "application/json", response);
}

void handleSetInputTrigger() {
  if (!server.hasArg("plain")) {
    server.send(400, "application/json", "{\"error\":\"No body\"}");
    return;
  }
  
  JsonDocument doc;
  DeserializationError error = deserializeJson(doc, server.arg("plain"));
  
  if (error) {
    server.send(400, "application/json", "{\"error\":\"Invalid JSON\"}");
    return;
  }
  
  uint8_t inputPin = doc["inputPin"];
  uint8_t outputPin = doc["outputPin"];
  
  // Validate input pin
  if (inputPin >= 16 || !pinConfigured[inputPin] || String(pinConfigs[inputPin].type) != "binary_sensor") {
    server.send(400, "application/json", "{\"error\":\"Invalid input pin\"}");
    return;
  }
  
  // Validate output pin
  if (outputPin >= 16 || !pinConfigured[outputPin] || String(pinConfigs[outputPin].type) == "binary_sensor") {
    server.send(400, "application/json", "{\"error\":\"Invalid output pin\"}");
    return;
  }
  
  // Set the trigger
  inputTriggers[inputPin].outputPin = outputPin;
  saveInputTriggers();
  
  server.send(200, "application/json", "{\"status\":\"ok\"}");
}