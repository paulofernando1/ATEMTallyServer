# 📡 Tally Server Pro - ATEM Emulator

Tally Server Pro is a professional-grade, multi-protocol tally server designed for broadcast environments. It emulates an ATEM Tally Server over UDP/9910, allowing DIY Tally Lights (ESP8266/ESP32) and mobile browsers to receive real-time status.

[![Version](https://img.shields.io/badge/Status-V1.0.1--Stable-green?style=for-the-badge)](https://github.com/paulofernando1/ATEMTallyServer/releases/download/v1.0.1/TallyServerEmulatorWindows.zip)
![Broadcasting](https://img.shields.io/badge/Protocol-HTTP/UDP/OBS_WebSocket-orange?style=for-the-badge)
[![Wiki](https://img.shields.io/badge/Docs-Wiki%20Manual-blue?style=for-the-badge)](https://github.com/paulofernando1/ATEMTallyServer/wiki)

[Windows V.1.0.1 Direct Download](https://github.com/paulofernando1/ATEMTallyServer/releases/download/v1.0.1/TallyServerEmulatorWindows.zip)

[Firmware BIN OTA Direct Download for ESP 8266 With 2 RGB LEDS](https://github.com/paulofernando1/ATEMTallyServer/releases/download/v1.0.1/ESP8266.I2C.Display.BIN.Firmware.v1.0.1.zip)

## 📖 How to Use

### 1. Initial Setup
1. Run `TallyServerEmulator.exe`.
2. Select your **UDP Port** (Default: `9910`).
3. Click **"Start Server"**. The button will turn green, indicating the UDP engine is active.

### 2. Integration (vMix / OBS)
- **vMix:** Enter the vMix computer IP and port (`8099`). Click **"Connect vMix"**. 
- **OBS Studio:** Enter the IP, port (`4455`), and password. Ensure "WebSocket Server" is enabled in OBS (Tools -> WebSocket Server Settings). Click **"Connect OBS"**.
- The dashboard will now automatically sync Program/Preview states based on your production software names.

### 3. Tally Lights Management
- **Hardware Tallies:** Flash your ESP8266/ESP32 with the provided firmware. Set the "Switcher IP" to your computer's IP.
- **Role Assignment:** In the "Active Network Clients" dashboard, assign a Cam ID to each IP.
- **Status Orbs:** Green orbits indicate the tally is connected and ready.

### 4. Web Tally (Mobile/Tablet)
1. In the "ATEM Tally Server" card, enter a **Web Port** (Default: `8080`).
2. Click **"Start Web Tally"**.
3. On your phone/tablet, browse to `http://<YOUR_COMPUTER_IP>:8080`.
4. **Offline Support:** The server now hosts all dependencies (Socket.IO) locally, allowing it to work on closed production networks without internet access.
5. **Force Re-Sync:** If a mobile client loses connection or fails to update, use the **"FORCE RE-SYNC"** button on the mobile screen to refresh states.
6. **Assign Role:** Select your camera role (Cam 1-41) directly from the mobile browser dropdown.

## 5. LED pins defined on default ESP firmware
**ESP32:**
 
 LED1
1. RED = PIN 32
2. GREEN = PIN 32
3. BLUE = PIN 25

 LED2
1. RED = PIN 26
2. GREEN = PIN 27
3. BLUE = PIN 14

4. **ESP8266:**
 
 LED1
1. RED = PIN 16
2. GREEN = PIN 5
3. BLUE = PIN 0

 LED2
1. RED = PIN 2
2. GREEN = PIN 13
3. BLUE = PIN 15

## 6. I2C Display pins defined on default ESP Firmware
**ESP32 / ESP82266 / NodeMCU**
 
OLED SCL = PIN 12
OLED SDA = PIN 14


---

## 🛠️ Technical Details

| Service | Port | Protocol | Usage |
| :--- | :--- | :--- | :--- |
| **ATEM Tally** | `9910` | UDP | Main tally communication (Binary Protocol) |
| **Web UI** | `8080` | TCP | Mobile tally clients (Flask/SocketIO) |
| **vMix API** | `8099` | TCP | Input state polling (TCP Bridge) |
| **OBS WS** | `4455` | TCP | Scene monitoring (WebSocket 5.5+) |

## 🔥 Key Features (v2.5)
- **High Capacity:** Supports up to 41 simultaneous Tally lights (hardware or web).
- **Repeater Mode:** Built-in support for hardware units acting as repeaters.
- **Smart Logic:** Automatic tally flag merging (Program + Preview + RGB Overrides).
- **RGB Support:** Experimental RGB LED2 support for specialized lighting requirements.
- **Persistent Memory:** All scene mappings and port configurations are auto-saved to `config.json`.

## 📦 Building from Source

To compile the application into a standalone portable `.exe`:
1. Use Python 3.14 (or 3.10+).
2. Install dependencies: `pip install customtkinter flask flask-socketio requests obsws-python websocket-client`.
3. Run the build script:
   ```powershell
   powershell -ExecutionPolicy Bypass -File build.ps1
   ```
## Pending Features (for v1.2.0)
- **Neopixels Tests** 
- **ATEM Hardware Switchers Tests** 
- **Other Compatible Hardware Switchers Tests**
- **ESP32 Hardware Compatibility Tests**  

---
Based on ATEM libraries for Arduino by [SKAARHOJ](https://www.skaarhoj.com/), available at Git repo: [SKAARHOJ-Open-Engineering](https://github.com/kasperskaarhoj/SKAARHOJ-Open-Engineering)

Ideas and some code based on: [ATEM_Wireless_Tally_Light](https://github.com/kalinchuk/ATEM_Wireless_Tally_Light) and [ATEM_tally_light_with_ESP8266](https://github.com/AronHetLam/ATEM_tally_light_with_ESP8266)

*Developed by Paulo Fernando de M. E. - Gandget S&P*
*Developed for professional live production workflows.*
