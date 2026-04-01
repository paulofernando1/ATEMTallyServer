# Repeater Mode Architecture

Tally Server Pro features a first-of-its-kind **Repeater Mode Protocol**. It allows for daisy-chaining multiple tally lights in large broadcast environments where direct WiFi coverage from the main server might be limited or where cable runs are preferred for reliability.

## 🌀 How it Works

In a standard setup, every tally light connects directly to the Tally Server (Star Topology). In **Repeater Mode**, one tally light acts as a "Master" for other sub-clients.

1.  **Direct Connection:** Tally A (Master) connects to the Tally Server Pro over WiFi or Ethernet.
2.  **Internal Hub:** Tally A creates a localized UDP bridge.
3.  **Sub-Clients:** Tally B and Tally C connect to Tally A instead of the main server.
4.  **Packet Forwarding:** Tally A receives Program/Preview data from the Tally Server and forwards the relevant indices to its sub-clients.

## 📊 Reporting Mechanism

To ensure the Tally Server Pro dashboard remains accurate, Repeaters follow a 5-second reporting cycle:

1.  Every 5 seconds, a Master Tally sends a specialized 8-byte **`Clnt`** (Client Report) packet to the Tally Server.
2.  This packet contains:
    -   **Sub-IP:** The IP of the connected sub-client.
    -   **Role:** The Cam ID assigned to that sub-IP.
3.  The Tally Server Pro UI will display these sub-clients under the **"Active Network Clients"** section with a special "via Repeater" tag.

## 🛠️ Configuration

To enable Repeater Mode on a Tally unit:
1.  Verify the unit has the latest `TallyServer` library installed.
2.  In the `ATEM_tally_light` firmware, set:
    ```cpp
    #define REPEATER_MODE true
    ```
3.  Flash the "Master" tally unit. Sub-clients can remain in standard mode but should point their `switcherIp` to the Master's IP address.

## ⚡ Benefits

-   **Extended Range:** Reach distant camera positions by jumping through intermediate tally units.
-   **Reduced Server Load:** The main Tally Server handles fewer direct UDP connections.
-   **Unified Dashboard:** Full visibility on all "invisible" sub-clients directly from the Tally Server Pro UI.

---

**Next:** [Web Tally Guide](Web-Tally.md)
