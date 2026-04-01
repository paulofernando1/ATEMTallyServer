# Welcome to the Tally Server Pro Wiki

Tally Server Pro is a professional-grade, multi-protocol tally server designed for broadcast environments. It emulates an ATEM Tally Server over UDP/9910, allowing DIY Tally Lights (ESP8266/ESP32) and mobile browsers to receive real-time status.

## 🗂️ Table of Contents

1.  **[Introduction](#)**
    *   [Introduction](Home.md)
    *   [Features](Home.md#-features)
2.  **[User Guide](#)**
    *   [Getting Started](Getting-Started.md)
    *   [Web Tally Guide](Web-Tally.md)
    *   [OBS & vMix Integration](vMix-and-OBS.md)
3.  **[Developer & Hardware Guide](#)**
    *   [Hardware & Firmware Setup](Hardware-Firmware.md)
    *   [Binary Protocol Specifications](Protocol-Specifications.md)
    *   [Repeater Mode Architecture](Repeater-Mode.md)
4.  **[Support](#)**
    *   [Troubleshooting](Troubleshooting.md)
    *   [Future Roadmap](Home.md#-roadmap)

---

## 🔥 Features

*   **Multi-Switcher Support:** Connect to vMix (TCP) and OBS Studio (WebSocket 5.5+) simultaneously.
*   **High Capacity:** Support for up to 41 simultaneous Tally lights (hardware or mobile).
*   **True Offline Operation:** All assets (including Socket.io) are hosted locally within the server. No internet access is required on the production network.
*   **Repeater Mode:** Built-in protocol support for hardware units to daisy-chain connections.
*   **Web Tally:** Convert any smartphone or tablet into a high-visibility tally light with a zero-install browser interface.
*   **Persistent Configuration:** Automatically saves and restores all window layouts, camera mappings, and port settings.

---

## 🛠️ Tech Stack

*   **Backend:** Python 3.10+, Flask, Flask-SocketIO.
*   **Frontend (GUI):** CustomTkinter (Modern Slate UI).
*   **Frontend (Web Tally):** HTML5, HSL-Dynamic CSS.
*   **Firmware:** C++ (Arduino/ESP8266/ESP32).

---

## 🗺️ Roadmap

- [ ] Neopixels Support Tests
- [ ] ESP32 Hardware Full Compatibility Validation
- [ ] ATEM Hardware Switchers Real-Link Tests
- [ ] Multi-Language UI Support
