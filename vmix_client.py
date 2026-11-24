# ==============================================================================
# vMix Tally Client - TCP Interface
# ==============================================================================
# This module connects to vMix via the TCP Protocol on Port 8099.
# It subscribes to "TALLY" updates and parses them into Program/Preview states.
# ==============================================================================

import socket
import threading
import time

class VmixTallyClient:
    def __init__(self, host, port, on_tally_update):
        # ...
        self.host = host
        self.port = port
        self.on_tally_update = on_tally_update
        self.sock = None
        self.running = False
        self.is_connected = False
        self.thread = None
        self._stop_event = threading.Event()
        self._last_flags = None

    def start(self):
        if self.running:
            return
        self.running = True
        self._stop_event.clear()
        self._last_flags = None
        self.thread = threading.Thread(target=self._run_loop, daemon=True)
        self.thread.start()

    def stop(self):
        self.running = False
        self.is_connected = False
        self._stop_event.set()
        if self.sock:
            try:
                self.sock.close()
            except Exception:
                pass
            self.sock = None
        if self.thread:
            self.thread.join(timeout=1.5)

    def _run_loop(self):
        while self.running and not self._stop_event.is_set():
            try:
                self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self.sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                self.sock.settimeout(2.0)
                self.sock.connect((self.host, self.port))
                self.sock.settimeout(1.0)
                self.is_connected = True
                self._last_flags = None

                # Subscribe to TALLY events (standard vMix TCP API)
                self.sock.sendall(b"SUBSCRIBE TALLY\r\n")
                last_activity = time.monotonic()
                last_keepalive = last_activity

                buffer = ""
                while self.running and not self._stop_event.is_set():
                    try:
                        data = self.sock.recv(4096)
                        if not data:
                            break
                        last_activity = time.monotonic()
                        buffer += data.decode('utf-8', errors='ignore')
                        while "\r\n" in buffer:
                            line, buffer = buffer.split("\r\n", 1)
                            self._process_line(line)
                    except socket.timeout:
                        now = time.monotonic()
                        if now - last_activity >= 20.0:
                            break
                        if now - last_keepalive >= 10.0:
                            self.sock.sendall(b"TALLY\r\n")
                            last_keepalive = now

            except (socket.timeout, socket.error, ConnectionRefusedError):
                self.is_connected = False
            except Exception as e:
                self.is_connected = False
                print(f"vMix connection error: {e}")
            finally:
                self.is_connected = False
                if self.sock:
                    try:
                        self.sock.close()
                    except Exception:
                        pass
                    self.sock = None

            if self.running and not self._stop_event.is_set():
                self._stop_event.wait(2.0)  # Reconnect delay

    def _process_line(self, line):
        if line.startswith("TALLY OK"):
            # Format: 'TALLY OK 12000...'
            tally_data = line.replace("TALLY OK ", "").strip()

            flags = [0] * 41
            for i in range(min(41, len(tally_data))):
                state = tally_data[i]
                if state == '1':  # Program
                    flags[i] = 1
                elif state == '2':  # Preview
                    flags[i] = 2

            if flags != self._last_flags:
                self._last_flags = flags
                if self.on_tally_update:
                    self.on_tally_update(flags)
