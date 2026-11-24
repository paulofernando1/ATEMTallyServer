# ==============================================================================
# Open Sound Control (OSC) Universal Tally Bridge
# ==============================================================================
# Bidirectional OSC Bridge for Bitfocus Companion, TouchOSC, Digital Consoles
# (Behringer X32/Wing, Allen & Heath, Yamaha), QLab and GrandMA / Chamsys.
#
# Functions:
# - Transmits real-time OSC status: /tally/<cam_num>/program, /tally/<cam_num>/preview
# - Receives incoming OSC triggers from consoles or Companion buttons
# - Zero-dependency: Pure Python OSC packet encoder & decoder
# ==============================================================================

import socket
import struct
import threading
import time

def _pad4(data_bytes):
    """Pads byte array with null bytes to a multiple of 4."""
    padding = (4 - (len(data_bytes) % 4)) % 4
    return data_bytes + (b'\x00' * padding)

def encode_osc_message(address, *args):
    """Encodes an OSC address and arguments (int or float) into OSC binary bytes."""
    addr_bytes = _pad4(address.encode('ascii') + b'\x00')
    tags = ","
    payload = bytearray()
    
    for arg in args:
        if isinstance(arg, int):
            tags += "i"
            payload.extend(struct.pack(">i", arg))
        elif isinstance(arg, float):
            tags += "f"
            payload.extend(struct.pack(">f", arg))
        elif isinstance(arg, str):
            tags += "s"
            payload.extend(_pad4(arg.encode('ascii') + b'\x00'))
            
    type_tags_bytes = _pad4(tags.encode('ascii') + b'\x00')
    return addr_bytes + type_tags_bytes + bytes(payload)

def decode_osc_message(data):
    """Decodes a binary OSC message into (address, [args])."""
    try:
        # Address
        addr_end = data.find(b'\x00')
        if addr_end == -1: return None, []
        address = data[:addr_end].decode('ascii', errors='ignore')
        
        ptr = (addr_end + 4) & ~0x03
        if ptr >= len(data) or data[ptr:ptr+1] != b',':
            return address, []
        
        # Type tags
        tags_end = data.find(b'\x00', ptr)
        if tags_end == -1: return address, []
        tags = data[ptr:tags_end].decode('ascii', errors='ignore')[1:] # drop comma
        
        ptr = (tags_end + 4) & ~0x03
        args = []
        for tag in tags:
            if tag == 'i':
                if ptr + 4 <= len(data):
                    val = struct.unpack(">i", data[ptr:ptr+4])[0]
                    args.append(val)
                    ptr += 4
            elif tag == 'f':
                if ptr + 4 <= len(data):
                    val = struct.unpack(">f", data[ptr:ptr+4])[0]
                    args.append(val)
                    ptr += 4
            elif tag == 's':
                s_end = data.find(b'\x00', ptr)
                if s_end != -1:
                    args.append(data[ptr:s_end].decode('ascii', errors='ignore'))
                    ptr = (s_end + 4) & ~0x03
            elif tag == 'T':
                args.append(1)
            elif tag == 'F':
                args.append(0)
        return address, args
    except Exception:
        return None, []

class OscTallyBridge:
    def __init__(self, target_host="255.255.255.255", target_port=9000, listen_port=8000, on_osc_trigger=None):
        self.target_host = target_host
        self.target_port = int(target_port)
        self.listen_port = int(listen_port)
        self.on_osc_trigger = on_osc_trigger
        self.send_sock = None
        self.recv_sock = None
        self.running = False
        self.thread = None
        self.lock = threading.Lock()

    def start(self):
        if self.running:
            return
        self.running = True
        try:
            self.send_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.send_sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            
            self.recv_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.recv_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.recv_sock.bind(("", self.listen_port))
            self.recv_sock.settimeout(0.1)

            self.thread = threading.Thread(target=self._listen_loop, daemon=True)
            self.thread.start()
            print(f"OSC Bridge active -> Send: {self.target_host}:{self.target_port} | Listen: 0.0.0.0:{self.listen_port}")
        except Exception as e:
            self.running = False
            with self.lock:
                for s in (self.send_sock, self.recv_sock):
                    if s:
                        try:
                            s.close()
                        except Exception:
                            pass
                self.send_sock = None
                self.recv_sock = None
            print(f"OSC Start Error: {e}")

    def stop(self):
        self.running = False
        with self.lock:
            for s in (self.send_sock, self.recv_sock):
                if s:
                    try: s.close()
                    except Exception: pass
            self.send_sock = None
            self.recv_sock = None
        if self.thread:
            self.thread.join(timeout=1.0)
        print("OSC Bridge stopped")

    def send_tally(self, cam_index, is_prog, is_prev, is_att=False):
        """Sends OSC tally status for a single camera."""
        if not self.running or not self.send_sock:
            return
        try:
            p_val = 1 if is_prog else 0
            v_val = 1 if is_prev else 0
            msg_p = encode_osc_message(f"/tally/{cam_index + 1}/program", p_val)
            msg_v = encode_osc_message(f"/tally/{cam_index + 1}/preview", v_val)
            with self.lock:
                if self.send_sock:
                    self.send_sock.sendto(msg_p, (self.target_host, self.target_port))
                    self.send_sock.sendto(msg_v, (self.target_host, self.target_port))
        except Exception as e:
            print(f"OSC Send Error: {e}")

    def send_bulk_tally(self, tally_list):
        """Sends OSC tally messages for multiple cameras."""
        if not self.running or not self.send_sock:
            return
        for item in tally_list:
            cam_idx = item[0]
            is_p = bool(item[2]) if len(item) > 2 else False
            is_v = bool(item[3]) if len(item) > 3 else False
            is_att = bool(item[4]) if len(item) > 4 else False
            self.send_tally(cam_idx, is_p, is_v, is_att)

    def _listen_loop(self):
        while self.running:
            try:
                data, addr = self.recv_sock.recvfrom(2048)
                address, args = decode_osc_message(data)
                if address and self.on_osc_trigger:
                    self.on_osc_trigger(address, args)
            except (socket.timeout, BlockingIOError):
                pass
            except Exception:
                pass
