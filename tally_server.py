# ==============================================================================
# Tally Server Pro - Core UDP Protocol Engine
# ==============================================================================
# This module implements the binary UDP protocol for ATEM Tally communication.
# Protocol Features:
# - HELLO Handshake for session initialization.
# - ACK/RESEND mechanisms for reliable UDP delivery.
# - Paging/Padding for 4-byte architecture alignment (ESP8266/ESP32).
# - Role-Aware Repeater Reporting (8-byte Clnt records).
# ==============================================================================

import socket
import threading
import time

# --- PROTOCOL FLAGS ---
TALLY_SERVER_FLAG_ACK               = 0b10000000
TALLY_SERVER_FLAG_RESEND_REQUEST    = 0b01000000
TALLY_SERVER_FLAG_RESENT_PACKAGE    = 0b00100000
TALLY_SERVER_FLAG_HELLO             = 0b00010000
TALLY_SERVER_FLAG_ACK_REQUEST       = 0b00001000

# --- CONNECTION STATES ---
TALLY_SERVER_CONNECTION_REQUEST     = 1
TALLY_SERVER_CONNECTION_ACCEPTED    = 2
TALLY_SERVER_CONNECTION_REJECTED    = 3
TALLY_SERVER_CONNECTION_LOST        = 4

TALLY_SERVER_MAX_TALLY_FLAGS        = 128
TALLY_SERVER_BUFFER_LENGTH          = 256
TALLY_SERVER_KEEP_ALIVE_MSG_INTERVAL= 1.5 # seconds

# ------------------------------------------------------------------------------
# TallyClient: Tracks the network state and session of a single UDP hardware unit
# ------------------------------------------------------------------------------
class TallyClient:
    def __init__(self, ip, port):
        self.ip = ip
        self.port = port
        self.is_connected = False
        self.is_initialized = False
        self.session_id = 0
        self.local_packet_id_counter = 0
        self.last_recv = time.time()
        self.last_send = time.time()
        self.last_acked_id = 0
        self.last_remote_packet_id = 0
        self.tally_id = -1

class TallyServer:
    def __init__(self, port=9910, max_clients=100, on_client_update=None, on_repeater_detected=None):
        self.port = port
        self.max_clients = max_clients
        self.on_client_update = on_client_update
        self.on_repeater_detected = on_repeater_detected
        self.sock = None
        self.clients = []
        self.atem_tally_sources = 120 # Support up to 120 sources (Tallies + Display + Message)
        self.atem_tally_flags = bytearray(256) 
        self.run_thread = None
        self.repeater_clients = {} # Parent IP -> List of Child IPs
        self.tally_flags_changed = False
        self.running = False
        self.thread = None

    def start(self):
        if self.running:
            return
        self.clients = []
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(("", self.port))
        self.sock.settimeout(0.01)
        self.running = True
        self.thread = threading.Thread(target=self._run_loop, daemon=True)
        self.thread.start()
        print(f"TallyServer started on port {self.port}")

    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join()
        if self.sock:
            self.sock.close()
            self.sock = None
        print("TallyServer stopped")

    def set_tally_sources(self, num_sources):
        if num_sources <= TALLY_SERVER_MAX_TALLY_FLAGS:
            self.atem_tally_sources = num_sources

    def set_tally_flag(self, tally_index, tally_flag):
        if tally_index < TALLY_SERVER_MAX_TALLY_FLAGS and self.atem_tally_flags[tally_index] != tally_flag:
            self.atem_tally_flags[tally_index] = tally_flag
            self.tally_flags_changed = True

    def _reset_client(self, client):
        client.is_connected = False
        client.is_initialized = False
        client.last_recv = 0
        client.local_packet_id_counter = 0
        client.last_remote_packet_id = 0
        client.session_id = 0
        if self.on_client_update:
            self.on_client_update()

    def _get_client(self, ip, port):
        # First look for an existing client by IP+port (regardless of connection state)
        for c in self.clients:
            if c.ip == ip and c.port == port:
                return c

        # Then look for a free slot
        for c in self.clients:
            if not c.is_connected and not c.is_initialized:
                c.ip = ip
                c.port = port
                return c

        # Allocate a new slot
        if len(self.clients) < self.max_clients:
            c = TallyClient(ip, port)
            self.clients.append(c)
            return c

        return None

    def _create_header(self, client, flags, length, remote_packet_id=0, resend_packet_id=None):
        header = bytearray(12)
        header[0] = flags | ((length >> 8) & 0b00000111)
        header[1] = length & 0xFF
        header[2] = (client.session_id >> 8) & 0xFF
        header[3] = client.session_id & 0xFF
        header[4] = (remote_packet_id >> 8) & 0xFF
        header[5] = remote_packet_id & 0xFF
        
        # Local packet ID only on ACK_REQUEST and without specific flags
        if (flags & TALLY_SERVER_FLAG_ACK_REQUEST) and not (flags & (TALLY_SERVER_FLAG_RESENT_PACKAGE | TALLY_SERVER_FLAG_RESEND_REQUEST | TALLY_SERVER_FLAG_HELLO)):
            client.local_packet_id_counter = (client.local_packet_id_counter + 1) & 0xFFFF
            header[10] = (client.local_packet_id_counter >> 8) & 0xFF
            header[11] = client.local_packet_id_counter & 0xFF

        if resend_packet_id is not None:
            header[10] = (resend_packet_id >> 8) & 0xFF
            header[11] = resend_packet_id & 0xFF

        return header

    def _create_tally_data_cmd(self, buffer):
        # Header(8) + Sources(2) + Flags
        cmd_only_len = 10 + self.atem_tally_sources
        
        # ATEM commands must be 4-byte aligned
        padding = (4 - (cmd_only_len % 4)) % 4
        total_cmd_len = cmd_only_len + padding
        
        buffer[12] = (total_cmd_len >> 8) & 0xFF
        buffer[13] = total_cmd_len & 0xFF
        # 14, 15 unknown/padding
        buffer[16:20] = b'TlIn'
        buffer[20] = (self.atem_tally_sources >> 8) & 0xFF
        buffer[21] = self.atem_tally_sources & 0xFF
        for i in range(self.atem_tally_sources):
            buffer[22+i] = self.atem_tally_flags[i]
            
        # Ensure padding bytes are 0
        for p in range(padding):
            buffer[22 + self.atem_tally_sources + p] = 0
            
        return total_cmd_len

    def _send_buffer(self, client, data):
        try:
            self.sock.sendto(data, (client.ip, client.port))
            client.last_send = time.time()
        except:
            pass

    def _run_loop(self):
        while self.running:
            try:
                data, addr = self.sock.recvfrom(2048)
                ip, port = addr
                packet_size = len(data)
                
                if packet_size >= 12:
                    flags = data[0] & 0b11111000
                    packet_len = ((data[0] & 0b00000111) << 8) + data[1]
                    
                    if packet_size >= packet_len:
                        client = self._get_client(ip, port)
                        if client:
                            client.session_id = (data[2] << 8) + data[3]
                            remote_packet_id = (data[10] << 8) + data[11]
                            if remote_packet_id > 0:
                                client.last_remote_packet_id = remote_packet_id
                            client.last_recv = time.time()

                            # Custom: Parse Repeater Client List (Clnt command)
                            if len(data) >= 20:
                                ptr = 12
                                while ptr + 8 <= len(data):
                                    cmd_len = (data[ptr] << 8) | data[ptr+1]
                                    if cmd_len < 8 or ptr + cmd_len > len(data): break
                                    try:
                                        cmd_name = data[ptr+4:ptr+8].decode('ascii', errors='ignore')
                                        if cmd_name == 'Clnt':
                                            count = data[ptr+9]
                                            ips_with_roles = []
                                            # New Format: 8 bytes per client [IP:4, Role:1, PAD:3]
                                            for i in range(count):
                                                s = ptr + 10 + (i * 8)
                                                if s + 5 <= ptr + cmd_len:
                                                    ip_str = f"{data[s]}.{data[s+1]}.{data[s+2]}.{data[s+3]}"
                                                    role = int(data[s+4])
                                                    ips_with_roles.append((ip_str, role))
                                            self.repeater_clients[client.ip] = ips_with_roles
                                            if self.on_repeater_detected: self.on_repeater_detected(client.ip)
                                            if self.on_client_update: self.on_client_update()
                                    except: pass
                                    ptr += cmd_len

                            if flags & TALLY_SERVER_FLAG_HELLO:
                                import random
                                client.session_id = random.randint(1, 32767)
                                buf = bytearray(20)
                                buf[0:12] = self._create_header(client, TALLY_SERVER_FLAG_HELLO, 20)
                                buf[12] = TALLY_SERVER_CONNECTION_ACCEPTED
                                self._send_buffer(client, buf)
                                client.is_connected = True
                                if len(data) >= 14:
                                    client.tally_id = data[13]

                            elif client.is_initialized:
                                if flags & TALLY_SERVER_FLAG_ACK:
                                    client.last_acked_id = (data[4] << 8) + data[5]
                                
                                if flags & TALLY_SERVER_FLAG_ACK_REQUEST:
                                    buf = bytearray(12)
                                    buf[0:12] = self._create_header(client, TALLY_SERVER_FLAG_ACK, 12, remote_packet_id)
                                    self._send_buffer(client, buf)

                                if flags & TALLY_SERVER_FLAG_RESEND_REQUEST:
                                    resend_packet_id = ((data[6] << 8) + data[7] + 1) & 0xFFFF
                                    buf = bytearray(TALLY_SERVER_BUFFER_LENGTH)
                                    cmd_len = 12 + self._create_tally_data_cmd(buf)
                                    header = self._create_header(client, TALLY_SERVER_FLAG_RESENT_PACKAGE | TALLY_SERVER_FLAG_ACK | TALLY_SERVER_FLAG_ACK_REQUEST, cmd_len, 0, resend_packet_id)
                                    buf[0:12] = header
                                    self._send_buffer(client, buf[:cmd_len])

                            elif client.is_connected:
                                if flags & TALLY_SERVER_FLAG_ACK:
                                    # Initialize and send state
                                    buf = bytearray(TALLY_SERVER_BUFFER_LENGTH)
                                    cmd_len = 12 + self._create_tally_data_cmd(buf)
                                    buf[0:12] = self._create_header(client, TALLY_SERVER_FLAG_ACK_REQUEST, cmd_len)
                                    self._send_buffer(client, buf[:cmd_len])
                                    
                                    buf2 = bytearray(12)
                                    buf2[0:12] = self._create_header(client, TALLY_SERVER_FLAG_ACK_REQUEST, 12)
                                    self._send_buffer(client, buf2)

                                    client.is_initialized = True
                                    if self.on_client_update: self.on_client_update()
                                else:
                                    self._reset_client(client)

                        else:
                            # connection rejected
                            if flags & TALLY_SERVER_FLAG_HELLO:
                                dummy = TallyClient(ip, port)
                                buf = bytearray(20)
                                buf[0:12] = self._create_header(dummy, TALLY_SERVER_FLAG_HELLO, 20)
                                buf[12] = TALLY_SERVER_CONNECTION_REJECTED
                                try:
                                    self.sock.sendto(buf, (ip, port))
                                except:
                                    pass

            except BlockingIOError:
                pass
            except socket.timeout:
                pass
            except Exception as e:
                print("Server loop exception:", e)

            # --- TALLY FLAGS CHANGE --- 
            if self.tally_flags_changed:
                buf = bytearray(TALLY_SERVER_BUFFER_LENGTH)
                cmd_len = 12 + self._create_tally_data_cmd(buf)
                for client in self.clients:
                    if client.is_initialized:
                        buf[0:12] = self._create_header(client, TALLY_SERVER_FLAG_ACK_REQUEST, cmd_len)
                        self._send_buffer(client, buf[:cmd_len])
                self.tally_flags_changed = False

            # --- KEEP ALIVE THREAD ---
            current_time = time.time()
            for client in self.clients:
                if client.is_initialized:
                    # Handle 16-bit wrap around for packet IDs
                    diff = (client.local_packet_id_counter - client.last_acked_id) & 0xFFFF
                    unacked = (diff > 0 and diff < 32768)
                    
                    if unacked and (current_time - client.last_send >= 0.25):
                        # Retransmit the tally state properly to demand an ACK
                        buf = bytearray(TALLY_SERVER_BUFFER_LENGTH)
                        cmd_len = 12 + self._create_tally_data_cmd(buf)
                        buf[0:12] = self._create_header(client, TALLY_SERVER_FLAG_ACK_REQUEST, cmd_len)
                        
                        self._send_buffer(client, buf[:cmd_len])
                        
                    elif (current_time - client.last_recv >= TALLY_SERVER_KEEP_ALIVE_MSG_INTERVAL) and \
                         (current_time - client.last_send >= TALLY_SERVER_KEEP_ALIVE_MSG_INTERVAL):
                        buf = bytearray(12)
                        buf[0:12] = self._create_header(client, TALLY_SERVER_FLAG_ACK_REQUEST, 12)
                        self._send_buffer(client, buf)
                        
                    elif (current_time - client.last_recv >= 4.0):
                        self._reset_client(client)
                        
                elif client.is_connected:
                    if (current_time - client.last_send >= TALLY_SERVER_KEEP_ALIVE_MSG_INTERVAL):
                        buf = bytearray(20)
                        buf[0:12] = self._create_header(client, TALLY_SERVER_FLAG_HELLO, 20)
                        buf[12] = TALLY_SERVER_CONNECTION_ACCEPTED
                        self._send_buffer(client, buf)
                        
                    elif (current_time - client.last_recv >= 4.0):
                        self._reset_client(client)

            time.sleep(0.01)
