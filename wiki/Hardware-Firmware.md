# Hardware & Firmware Setup

Tally Server Pro is compatible with any hardware unit that implements the **ATEM Tally Protocol** over UDP (9910). This includes the popular ESP8266 and ESP32 platforms.

## 🛠️ Required Hardware

1.  **Microcontroller:** ESP8266 (NodeMCU, Wemos D1 Mini) or ESP32.
2.  **Display (Recommended):** I2C OLED (SSD1306/U8g2 compatible). 128x32 or 128x64.
3.  **Light Indicator:** RGB LED or Single Program/Preview LEDs.

## 💾 Firmware Installation

We provide a specialized firmware designed for this server. It includes **Repeater Mode** support and **Enhanced Role Reporting**.

### 1. Prerequisites
- [Arduino IDE](https://www.arduino.cc/en/software) or [PlatformIO](https://platformio.org/).
- **Libraries Required:**
  - `ATEMmin` (Provided in the `ATEM_Tally_Light/libraries` folder)
  - `TallyServer` (Provided in the `ATEM_Tally_Light/libraries` folder)
  - `U8g2` (For OLED Display)
  - `FastLED` (For RGB Indicators)

### 2. Configuration
Open the `ATEM_tally_light.ino` (or `.cpp`) file and modify the following:
```cpp
// Your Wi-Fi credentials
const char* ssid = "YOUR_WIFI_NAME";
const char* password = "YOUR_WIFI_PASSWORD";

// Tally Server Pro IP (The computer running the Emulator)
IPAddress switcherIp(192, 168, 1, 10);
```

### 3. Flashing
1.  Connect your ESP8266/ESP32 via USB.
2.  Select the correct board and port in your IDE.
3.  Click **Upload**.

## 📊 Connection Diagnostics

Once flashed, the OLED display will show:
- **WiFi Status:** Searching... -> Connected.
- **Switcher IP:** The target Tally Server IP.
- **Role:** The assigned Cam ID (Assigned via the Server Dashboard).
- **Signal:** Red (Program), Green (Preview), Blue (Attention).

## 🔌 Pin Mapping (Default)

| Component | ESP8266 Pin (D-Pin) | ESP32 Pin |
| :--- | :--- | :--- |
| **I2C SDA** | `D2` | `21` |
| **I2C SCL** | `D1` | `22` |
| **LED RED** | `D5` | `32` |
| **LED GREEN** | `D6` | `33` |
| **LED BLUE** | `D7` | `25` |

---

**Next:** [Repeater Mode Architecture](Repeater-Mode.md)
