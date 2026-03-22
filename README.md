# 📖 Tally Server Pro - User Guide

This guide provides everything you need to know to operate the **Tally Server Pro Controller** and sync it with your hardware.

---

# Hardware Setup
1. Esp32 or ESP8266 boards prefferable with an OLED screen.
    **OLED screen:**
    Pin for SCL = 12    
    Pin for SDA = 14     

2. Pins for LED 1 and LED 2 conections are in the tallys main arduino code
    ### Esp8266:
    #### LED1 color pins
    PIN_RED1   = 16     //D0 
    PIN_GREEN1 = 5    //D1 
    PIN_BLUE1  = 0     //D3 
    #### LED2 color pins
    PIN_RED2   = 2      //D4 
    PIN_GREEN2 = 13   //D7 
    PIN_BLUE2  = 15    //D8 
    ### Esp32:
    #### LED1 color pins
    PIN_RED1   = 32      
    PIN_GREEN1 = 33   
    PIN_BLUE1  = 25     
    #### LED2 color pins
    PIN_RED2   = 26     
    PIN_GREEN2 = 27   
    PIN_BLUE2  = 14    

## 🚀 Getting Started

1. **Launch the Server**: Run `TallyServerEmulator.exe`.
2. **Start Communication**: Click the **"Start Server"** button. By default, it uses UDP Port `9910`.
3. **Connect Hardware**: Turn on your Tally Lights. They should automatically connect to the server IP and start showing "● ONLINE" in the monitoring panel.

---

## 📽️ Integrations

### 🔴 vMix
1. Enter the IP address of your vMix computer.
2. Default port is `8099`.
3. Click **"Connect vMix"**. The server will now read Tally states directly from vMix.

### 🎥 OBS Studio
1. Enter your OBS IP and WebSocket port (default `4455`).
2. Enter your WebSocket password if set.
3. Click **"Connect OBS"**.
4. **Mapping**: In the main table, ensure the names in the **"Scene/Input Name"** column match your OBS source names exactly.

---

## 📺 Remote Display (I2C)

The **Remote Display** feature allows you to send custom information and messages to the OLED screens on your Tally Lights.

### How to use:
1. **Enable**: Go to **Settings (⚙️)** and check **"Enable Remote Display"**.
2. **Select Target**: Choose the **Camera (1-8)** you want to control.
3. **Select Mode**:
    - **OFF**: Turns off the display.
    - **ON**: Shows the "READY" status screen.
    - **Show IP**: Displays the Tally Light's current IP address.
    - **Tally Name**: Shows the custom name of the device.
    - **WiFi**: Displays the signal strength (RSSI).
    - **ALL**: Shows a summary of Name, IP, and RSSI.
    - **MESSAGE**: Enables the large-text mode for custom messages.
4. **Direct Control**: Clicking any mode (except MESSAGE) sends the command **instantly** to the Tally Light.
5. **Custom Messages**: Select **"MESSAGE"**, type your text, and click **"SEND ➤"**. Long messages will **auto-scroll** smoothly across the screen.

---

## ⚙️ Global Preferences

- **Save Config on Exit**: Remembers your IP addresses, ports, and scene mappings for the next session.
- **Auto-start**: Automatically starts the server or connects to vMix/OBS when the app opens.
- **Touchscreen Mode**: Increases button and text size for use with tablets or touch monitors.

---

## 🛠️ Troubleshooting

- **Latencies?** Ensure your ESP8266/ESP32 has `WIFI_NONE_SLEEP` enabled in the code to avoid 6s delay spikes.
- **No Connection?** Check if Windows Firewall is blocking UDP Port `9910`.
- **Text Not Scrolling?** Ensure you have selected the **"MESSAGE"** mode before sending long texts.

---
Based on ATEM libraries for Arduino by [SKAARHOJ](https://www.skaarhoj.com/), available at Git repo: [SKAARHOJ-Open-Engineering](https://github.com/kasperskaarhoj/SKAARHOJ-Open-Engineering)

Ideas and some code based on: [ATEM_Wireless_Tally_Light](https://github.com/kalinchuk/ATEM_Wireless_Tally_Light) and [ATEM_tally_light_with_ESP8266](https://github.com/AronHetLam/ATEM_tally_light_with_ESP8266)

*Developed by Paulo Fernando de M. E. - Gandget S&P*
