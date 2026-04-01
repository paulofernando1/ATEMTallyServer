# Protocol Specifications

Tally Server Pro uses the **ATEM Tally Protocol** (UDP/9910) by Blackmagic Design. This binary protocol is highly optimized for real-time broadcast signaling.

## 📦 Binary UDP Packet Format

Every packet starts with a **12-byte header** used for session management and acknowledgement.

### 1. Packet Header (12 Bytes)
| Offset | Type | Description |
| :--- | :--- | :--- |
| `0-1` | `uint16_t` | **Flags & Length:** Packet length (first 11 bits) + flags (last 5 bits). |
| `2-3` | `uint16_t` | **Session ID:** Unique identification for the connection. |
| `4-7` | `uint32_t` | **Acknowledgement Number:** Used for reliable delivery tracking. |
| `8-11` | `uint32_t` | **Packet ID:** Sequence number for the packet. |

### 2. Tally Command (TlIn)
Sent from the server to tally lights to update state.
*   **Command ID:** `TlIn`
*   **Payload:** Array of bytes. Each byte represents one camera source.
    -   `0x00`: Off
    -   `0x01`: Program (Red)
    -   `0x02`: Preview (Green)
    -   `0x03`: Program + Preview

### 3. Sub-Client Reporting (Clnt)
A custom extension implemented for Tally Server Pro's **Repeater Mode**.
*   **Command ID:** `Clnt`
*   **Length:** 8 Bytes.
*   **Structure:**
    -   `0-3`: Sub-Client IP (Binary IPv4)
    -   `4-7`: Assigned Cam ID (uint32_t)

## 🔄 The Connection Handshake

1.  **Client Init:** Tally client sends a `0x10` (Connect) packet to the server.
2.  **Server Ack:** Server responds with a `0x10` (Connect) and a `SessionID`.
3.  **Client Final:** Client sends a `0x80` (Acknowledge) to complete the session.
4.  **Tally Stream:** Server begins sending `TlIn` command packets every time a source changes or as a keep-alive (every 1 second).

## 🛡️ Reliability Features

-   **UDP/9910:** Fast, connectionless initial signaling.
-   **Session Tracking:** The server maintains a `SessionID` for each unique IP. If a client goes quiet, the server automatically times out the session after 30 seconds.
-   **ACK/Resend:** Critical state changes (like switching to Program) are resent until the client acknowledges the packet.

---

**Next:** [vMix and OBS Integration](vMix-and-OBS.md)
