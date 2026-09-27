# ==============================================================================
# ATEM Hardware Switcher Client (UDP 9910)
# ==============================================================================
# Connects to physical Blackmagic ATEM Switchers (ATEM Mini, SDI, Constellation,
# Television Studio, 1 M/E, 2 M/E, 4K) over UDP Port 9910.
#
# Functions:
# - Performs ATEM UDP binary handshake (HELLO / ACK / Keepalive).
# - Subscribes to Tally Input states ('TlIn') and M/E Program/Preview ('PrgI'/'PrvI').
# - Dispatches real-time tally flags to Tally Server Pro hub.
# ==============================================================================

import socket
import threading
import time

ATEM_FLAG_ACK            = 0b10000000
ATEM_FLAG_RESEND_REQ     = 0b01000000
ATEM_FLAG_RESENT_PKG     = 0b00100000
ATEM_FLAG_HELLO          = 0b00010000
ATEM_FLAG_ACK_REQ        = 0b00001000

class AtemHardwareClient:
    def __init__(self, host, port=9910, on_tally_update=None):
        self.host = host
        self.port = port
        self.on_tally_update = on_tally_update
        self.sock = None
        self.running = False
        self.is_connected = False
        self.thread = None
        self.session_id = 0
        self.local_packet_id = 0
        self.last_remote_packet_id = 0
        self.last_recv = 0
        self.last_send = 0
        self.last_flags = []

    def start(self):
        if self.running:
            return
        self.running = True
        self.thread = threading.Thread(target=self._run_loop, daemon=True)
        self.thread.start()
        print(f"ATEM Hardware Client starting for {self.host}:{self.port}")

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
        print("ATEM Hardware Client stopped")

    def _create_header(self, flags, length, remote_packet_id=0):
        header = bytearray(12)
        header[0] = flags | ((length >> 8) & 0b00000111)
        header[1] = length & 0xFF
        header[2] = (self.session_id >> 8) & 0xFF
        header[3] = self.session_id & 0xFF
        header[4] = (remote_packet_id >> 8) & 0xFF
        header[5] = remote_packet_id & 0xFF
        if (flags & ATEM_FLAG_ACK_REQ) and not (flags & ATEM_FLAG_HELLO):
            self.local_packet_id = (self.local_packet_id + 1) & 0xFFFF
            header[10] = (self.local_packet_id >> 8) & 0xFF
            header[11] = self.local_packet_id & 0xFF
        return header

    def _send_ack(self, remote_packet_id):
        if not self.sock or not self.running:
            return
        header = self._create_header(ATEM_FLAG_ACK, 12, remote_packet_id)
        try:
            self.sock.sendto(header, (self.host, self.port))
            self.last_send = time.time()
        except Exception:
            pass

    def _send_hello(self):
        if not self.sock or not self.running:
            return
        buf = bytearray(20)
        buf[0:12] = self._create_header(ATEM_FLAG_HELLO, 20)
        buf[12] = 0x01
        buf[13] = 0x00
        try:
            self.sock.sendto(buf, (self.host, self.port))
            self.last_send = time.time()
        except Exception:
            pass

    def _parse_commands(self, payload):
        ptr = 0
        total_len = len(payload)
        while ptr + 8 <= total_len:
            cmd_len = (payload[ptr] << 8) | payload[ptr + 1]
            if cmd_len < 8 or ptr + cmd_len > total_len:
                break
            try:
                cmd_name = payload[ptr + 4:ptr + 8].decode('ascii', errors='ignore')
                
                # --- TlIn: Tally by Index ---
                if cmd_name == 'TlIn':
                    if ptr + 10 <= total_len:
                        source_count = (payload[ptr + 8] << 8) | payload[ptr + 9]
                        flags = []
                        for i in range(source_count):
                            if ptr + 10 + i < ptr + cmd_len:
                                raw_flag = payload[ptr + 10 + i]
                                f = 0
                                if raw_flag & 0x01: f |= 1  # Program
                                if raw_flag & 0x02: f |= 2  # Preview
                                flags.append(f)
                        if flags and flags != self.last_flags:
                            self.last_flags = flags
                            if self.on_tally_update:
                                self.on_tally_update(flags)

                # --- PrgI: Program Input Video Source (M/E 1) ---
                elif cmd_name == 'PrgI':
                    me = payload[ptr + 8]
                    if me == 0 and ptr + 12 <= total_len:
                        pgm_source = (payload[ptr + 10] << 8) | payload[ptr + 11]
                        # Could be used for secondary fallback mapping if TlIn not sent
                        pass

            except Exception:
                pass
            ptr += cmd_len

    def _run_loop(self):
        while self.running:
            try:
                self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                self.sock.settimeout(0.1)
                self.session_id = 0
                self.local_packet_id = 0
                self.last_remote_packet_id = 0
                self.is_connected = False
                
                # Send HELLO Handshake
                self._send_hello()
                hello_start = time.time()
                self.last_recv = time.time()
                
                while self.running:
                    now = time.time()
                    try:
                        data, addr = self.sock.recvfrom(2048)
                        if addr[0] == self.host and len(data) >= 12:
                            self.last_recv = now
                            flags = data[0] & 0b11111000
                            packet_len = ((data[0] & 0b00000111) << 8) | data[1]
                            remote_session = (data[2] << 8) | data[3]
                            remote_packet_id = (data[10] << 8) | data[11]

                            # Handshake response
                            if flags & ATEM_FLAG_HELLO:
                                self.session_id = remote_session
                                self.is_connected = True
                                # Send ACK for Hello
                                self._send_ack(0)
                                print(f"ATEM Switcher Connected! Session ID: {self.session_id}")

                            elif self.is_connected:
                                if remote_packet_id > 0:
                                    self.last_remote_packet_id = remote_packet_id

                                # If switcher requested ACK, send it back immediately
                                if flags & ATEM_FLAG_ACK_REQ:
                                    self._send_ack(remote_packet_id)

                                # Process payload commands
                                if len(data) > 12:
                                    self._parse_commands(data[12:packet_len])

                    except (socket.timeout, BlockingIOError):
                        pass

                    # Connection timeout / Keepalive handling
                    if not self.is_connected and (now - hello_start > 2.0):
                        # Retry HELLO
                        self._send_hello()
                        hello_start = now

                    if self.is_connected:
                        # Send periodic Keepalive ACK every 1s
                        if (now - self.last_send >= 1.0):
                            self._send_ack(self.last_remote_packet_id)

                        # Timeout if no packet in 5s
                        if (now - self.last_recv > 5.0):
                            print("ATEM Switcher connection timeout, reconnecting...")
                            self.is_connected = False
                            break

            except Exception as e:
                print(f"ATEM Client Socket Exception: {e}")
            finally:
                if self.sock:
                    try:
                        self.sock.close()
                    except Exception:
                        pass
                    self.sock = None

            if self.running:
                time.sleep(2.0)
