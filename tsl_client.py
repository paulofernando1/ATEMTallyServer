# ==============================================================================
# TSL UMD v3.1 Tally Client / Sender (UDP)
# ==============================================================================
# Implements the industry-standard TSL UMD (Under Monitor Display) Protocol v3.1.
# Used by Hollyland Wireless Tally Systems, Feelworld/Lilliput monitors,
# Multiviewers, TriCaster, Ross, Sony, and broadcast routers.
#
# Protocol Specification:
# - Transport: UDP (Unicast to specific device or Broadcast to LAN)
# - Default Port: 8900 (or 9800 depending on device)
# - Frame Size: 18 Bytes per Display/Camera
#   - Byte 0:    Header / Display Index: 0x80 | (cam_index & 0x7F)
#   - Byte 1-16: Display Label: 16 ASCII characters (space padded)
#   - Byte 17:   Control Byte:
#                - Bit 0: Tally 1 (RED / Program)
#                - Bit 1: Tally 2 (GREEN / Preview)
#                - Bit 2: Tally 3 (AMBER / Aux)
#                - Bit 3: Tally 4 (BLUE / Custom)
#                - Bits 4-5: Brightness (0-3)
# ==============================================================================

import socket
import threading
import time

class TslUmdSender:
    def __init__(self, host="255.255.255.255", port=8900):
        self.host = host
        self.port = port
        self.sock = None
        self.running = False
        self.lock = threading.Lock()

    def start(self):
        with self.lock:
            if self.running:
                return
            try:
                self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
                self.running = True
                print(f"TSL UMD 3.1 Sender active -> {self.host}:{self.port}")
            except Exception as e:
                print(f"TSL UMD Start Error: {e}")
                self.running = False

    def stop(self):
        with self.lock:
            self.running = False
            if self.sock:
                try:
                    self.sock.close()
                except Exception:
                    pass
                self.sock = None
            print("TSL UMD 3.1 Sender stopped")

    def create_tsl_record(self, cam_index, label="CAM", is_prog=False, is_prev=False, is_aux=False, is_blue=False):
        """Constructs an 18-byte TSL UMD v3.1 record."""
        # Byte 0: Address (0x80 + index, 0-126)
        header = 0x80 | (cam_index & 0x7F)
        
        # Bytes 1-16: 16-byte ASCII label (padded with spaces)
        clean_label = (label if label else f"CAM {cam_index + 1}").ljust(16)[:16]
        label_bytes = clean_label.encode("ascii", errors="replace")
        
        # Byte 17: Control Byte (Tally Bits + Brightness)
        ctrl = 0x30  # Default brightness: max (bits 4-5 = 11)
        if is_prog:
            ctrl |= 0x01  # Tally 1: Red / Program
        if is_prev:
            ctrl |= 0x02  # Tally 2: Green / Preview
        if is_aux:
            ctrl |= 0x04  # Tally 3: Amber
        if is_blue:
            ctrl |= 0x08  # Tally 4: Blue
            
        record = bytearray(18)
        record[0] = header
        record[1:17] = label_bytes
        record[17] = ctrl
        return bytes(record)

    def send_single_tally(self, cam_index, label, is_prog, is_prev, is_aux=False, is_blue=False):
        """Sends a single 18-byte TSL record via UDP."""
        if not self.running or not self.sock:
            return
        try:
            packet = self.create_tsl_record(cam_index, label, is_prog, is_prev, is_aux, is_blue)
            with self.lock:
                if self.sock:
                    self.sock.sendto(packet, (self.host, self.port))
        except Exception as e:
            print(f"TSL Send Error: {e}")

    def send_bulk_tally(self, tally_list):
        """
        Sends tally status for multiple cameras.
        tally_list is a list of tuples:
        (cam_index, label, is_prog, is_prev, is_aux, is_blue)
        """
        if not self.running or not self.sock or not tally_list:
            return
        try:
            buffer = bytearray()
            for item in tally_list:
                cam_index = item[0]
                label = item[1] if len(item) > 1 else f"CAM {cam_index + 1}"
                is_prog = bool(item[2]) if len(item) > 2 else False
                is_prev = bool(item[3]) if len(item) > 3 else False
                is_aux = bool(item[4]) if len(item) > 4 else False
                is_blue = bool(item[5]) if len(item) > 5 else False
                
                buffer.extend(self.create_tsl_record(cam_index, label, is_prog, is_prev, is_aux, is_blue))
            
            with self.lock:
                if self.sock:
                    self.sock.sendto(bytes(buffer), (self.host, self.port))
        except Exception as e:
            print(f"TSL Bulk Send Error: {e}")
