# Getting Started

Tally Server Pro is designed to be a standalone, zero-config-needed solution for broadcast engineers. This page will guide you through the process of setting up your server for the first time.

## 🚀 Installation

1.  **Download:** Download the latest version of `TallyServerEmulator.exe` from the GitHub Releases page.
2.  **Location:** The application is portable. You can run it from any folder, including a USB stick.
3.  **Run:** Launch the application. If prompted by Windows Defender, select "Run anyway".

## 📡 Initial Server Setup

1.  **UDP Port:** By default, ATEM switchers and tallies use UDP port `9910`. Ensure this port is not blocked by your firewall.
2.  **Start Server:** Click the large **"Start Server"** button. The icon will turn green to indicate the UDP engine is active.
3.  **Local IP:** Note the IP displayed in the server settings. You will need this to configure your tally hardware and web clients.

## 🔗 Software Integration

Tally Server Pro acts as a bridge between your production software and your tally lights.

### vMix Integration
1.  Enter the IP of the computer running vMix (usually `127.0.0.1` if on the same machine).
2.  The default TCP port for vMix tally is `8099`.
3.  Click **"Connect vMix"**. The dashboard status indicators will light up as vMix changes states.

### OBS Studio Integration
1.  In OBS, go to **Tools** -> **WebSocket Server Settings**.
2.  Ensure "Enable WebSocket Server" is checked.
3.  Set a port (default: `4455`) and password.
4.  In Tally Server Pro, enter the OBS IP, port, and password.
5.  Click **"Connect OBS"**.

## 📱 Web Tally Setup

If you don't have enough hardware tally lights, you can use any smartphone or tablet.

1.  Enter a **Web Port** (default: `8080`).
2.  Click **"Start Web Tally"**.
3.  On the mobile device, browse to `http://<SERVER_IP>:8080`.
4.  Choose your camera role and you're done!

---

**Next:** [Hardware & Firmware Setup](Hardware-Firmware.md)
