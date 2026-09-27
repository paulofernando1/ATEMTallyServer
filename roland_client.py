# ==============================================================================
# Roland Video Switcher Client (TCP/IP)
# ==============================================================================
# Connects to Roland Video Switchers (V-1HD, V-1HD+, V-8HD, V-60HD, V-160HD, VR-50HD)
# over TCP/IP (Default Port: 8023).
#
# Protocol Details:
# - Transport: TCP Socket
# - Framing: STX (0x02) ... ETX (0x03) or ASCII with CRLF
# - Queries: QPL (Query Program/Preset Live), QST (Query Status)
# - Responses: QPL:pgm,pvw or TLY:flags
# ==============================================================================

import socket
import threading
import time

class RolandTallyClient:
    def __init__(self, host, port=8023, on_tally_update=None):
        self.host = host
        self.port = int(port)
        self.on_tally_update = on_tally_update
        self.sock = None
        self.running = False
        self.is_connected = False
        self.thread = None

    def start(self):
        if self.running:
            return
        self.running = True
        self.thread = threading.Thread(target=self._run_loop, daemon=True)
        self.thread.start()
        print(f"Roland Switcher Client starting for {self.host}:{self.port}")

    def stop(self):
        self.running = False
        self.is_connected = False
        if self.sock:
            try:
                self.sock.close()
            except Exception:
                pass
            self.sock = None
        if self.thread:
            self.thread.join(timeout=2.0)
        print("Roland Switcher Client stopped")

    def _parse_roland_message(self, msg):
        clean = msg.strip().strip("\x02\x03")
        flags = [0] * 41

        # Format 1: QPL:pgm,pvw (e.g. QPL:1,2 or QPL:0,1)
        if "QPL:" in clean or "QST:0," in clean:
            parts = clean.split(":")[-1].split(",")
            if len(parts) >= 2:
                try:
                    pgm_idx = int(parts[0]) - 1
                    pvw_idx = int(parts[1]) - 1
                    if 0 <= pgm_idx < 41:
                        flags[pgm_idx] |= 1
                    if 0 <= pvw_idx < 41:
                        flags[pvw_idx] |= 2
                    if self.on_tally_update:
                        self.on_tally_update(flags)
                except ValueError:
                    pass

        # Format 2: TLY:1,0,2,0... (Explicit tally array)
        elif "TLY:" in clean:
            parts = clean.split("TLY:")[-1].split(",")
            for i, val in enumerate(parts):
                if i < 41:
                    try:
                        v = int(val.strip())
                        flags[i] = v
                    except ValueError:
                        pass
            if self.on_tally_update:
                self.on_tally_update(flags)

    def _run_loop(self):
        while self.running:
            try:
                self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self.sock.settimeout(3.0)
                self.sock.connect((self.host, self.port))
                self.is_connected = True
                print(f"Connected to Roland Switcher at {self.host}:{self.port}")

                # Subscribe / Query Initial Status
                query_cmds = [b"\x02QPL\x03\r\n", b"\x02QST:0\x03\r\n", b"QPL\r\n"]
                for cmd in query_cmds:
                    try:
                        self.sock.sendall(cmd)
                    except Exception:
                        pass

                buffer = ""
                last_poll = time.time()

                while self.running:
                    now = time.time()
                    try:
                        data = self.sock.recv(1024)
                        if not data:
                            break
                        buffer += data.decode("ascii", errors="ignore")
                        
                        while "\x03" in buffer or "\r\n" in buffer:
                            if "\x03" in buffer:
                                msg, buffer = buffer.split("\x03", 1)
                            else:
                                msg, buffer = buffer.split("\r\n", 1)
                            self._parse_roland_message(msg)

                    except socket.timeout:
                        pass

                    # Periodic polling query every 500ms
                    if now - last_poll >= 0.5:
                        try:
                            self.sock.sendall(b"\x02QPL\x03\r\n")
                            last_poll = now
                        except Exception:
                            break

            except (socket.error, ConnectionRefusedError, socket.timeout):
                self.is_connected = False
            except Exception as e:
                print(f"Roland Client Exception: {e}")
                self.is_connected = False
            finally:
                if self.sock:
                    try:
                        self.sock.close()
                    except Exception:
                        pass
                    self.sock = None

            if self.running:
                time.sleep(2.0)
