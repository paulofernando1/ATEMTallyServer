# Web Tally Guide

The **Web Tally** feature converts any smartphone or tablet with a modern browser into a high-visibility tally light. It's the perfect solution for auxiliary camera positions or for mobile camera operators who can't use hardware-tethered tally lights.

## 🌟 Key Features

*   **Zero Install:** No app needed. Just scan a QR code or browse to the server's IP.
*   **Low Latency:** Uses optimized WebSockets (Socket.IO) for sub-100ms response times.
*   **Visual Feedback:**
    -   **Red:** Program (On Air)
    -   **Green:** Preview (Ready)
    -   **Blue:** Attention (Special)
    -   **Gray:** Idle
*   **Offline Native:** Includes localized dependencies. Works 100% offline on a local production network.

## 🚀 How to Launch

1.  **Server side:** Go to the **Settings** menu and find the **"Web Tally"** section.
2.  **Port:** Enter a port (default: `8080`).
3.  **Start:** Click **"Start Web Server"**. The status indicator will turn blue.
4.  **IP:** Find the server IP (e.g., `192.168.1.100`).

## 📱 Mobile Client Setup

1.  Open the browser (Chrome/Safari recommended) on your phone or tablet.
2.  Browse to `http://192.168.1.100:8080`.
3.  **Select Camera:** Choose the camera role (Cam 1 - Cam 41) from the dropdown at the bottom.
4.  **Confirm:** The screen will turn the color of your current role's tally state.

## 🛠️ Offline Support (Production Networks)

We understand that professional broadcast environments are often air-gapped (no internet access).

-   Tally Server Pro **hosts its own copies** of `socket.io.min.js`.
-   Mobile devices do not need an external internet connection to load the tally interface.
-   **Pro Tip:** If your mobile browser is struggling to connect, ensure "Mobile Data" is off and the device is strictly using the production WiFi network.

## ⚡ Troubleshooting

-   **"FAILED: Library not loaded":** If you see this on your phone, click **Force Re-Sync** or refresh the browser. Our v1.2 updates already include a cache-busting system to prevent this.
-   **No Color Update:** Ensure the server shows your client in the "Web Tally Clients" dashboard list. If not, refresh the browser on the mobile device.

---

**Next:** [Binary Protocol Specifications](Protocol-Specifications.md)
