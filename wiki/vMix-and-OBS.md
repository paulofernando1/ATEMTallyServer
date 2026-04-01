# OBS & vMix Integration

Tally Server Pro acts as a high-speed bridge between your professional production software and your Tally hardware. This page outlines the specific integration details for OBS Studio and vMix.

## 🔴 vMix Integration (TCP/8099)

vMix provides a dedicated Tally port (default `8099`) that reports input states in real-time via a custom TCP protocol.

### 1. Requirements
-   **vMix Version:** Any version (Pro, 4K, HD).
-   **Local Network:** The vMix computer must be reachable by IP from the Tally Server Pro machine.

### 2. Configuration
1.  In Tally Server Pro, enter the **vMix Host IP**. If vMix is on the same machine, use `127.0.0.1`.
2.  The default port is `8099`.
3.  Click **"Connect vMix"**.
4.  Once connected, Tally Server Pro will automatically subscribe to Tally updates. When a source is placed on Program or Preview in vMix, the server will broadcast this state to all 41 possible tally channels.

---

## 🔵 OBS Studio Integration (WebSocket 5.5+)

OBS uses a more modern WebSocket protocol for two-way communication. Tally Server Pro requires **OBS WebSocket 5.x** (which is standard in OBS Studio 28 and newer).

### 1. Requirements
-   **OBS Studio:** Version 28 or higher.
-   **WebSocket Plugin:** Ensure the server is enabled in OBS (**Tools** -> **WebSocket Server Settings**).

### 2. Configuration
1.  Enable **"Authenticate"** in OBS for security.
2.  In Tally Server Pro, enter the OBS Host, Port (default `4455`), and your WebSocket Password.
3.  Click **"Connect OBS"**.
4.  The server uses a **Scene-to-Input Mapping** logic. If the currently "Live" scene in OBS contains a source mapped to a Cam ID, that camera will receive the Program signal.

## 🔀 Merging Multi-Switcher Signals

One of the unique features of Tally Server Pro is its ability to merge signals from different sources:

-   **Priority:** If both vMix and OBS are connected, the server will **Logic OR** the tally results.
-   **Example:** If Camera 1 is Live in vMix but idling in OBS, Tally Server Pro will still send a **RED (Program)** signal to Camera 1 because at least one switcher reports it as active.
-   **Conflict Resolution:** If one source is Program in vMix and Preview in OBS, the server will prioritize **Program (Red)** to ensure the camera operator knows they are on-air.

---

*For more technical details on the underlying binary translation, visit the [Protocol Specifications](Protocol-Specifications.md).*
