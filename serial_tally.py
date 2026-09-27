# ==============================================================================
# USB Serial & Hardware Relay Output Driver
# ==============================================================================
# Controls physical studio tally lights, USB Relays (LCUS-1, LCUS-2, 8-channel),
# Arduino serial shields, and FTDI/CH340 GPIO hardware interfaces.
#
# Protocols:
# - LCUS USB Relay Protocol: 0xA0 <channel> 0x01 <checksum> (ON) / 0x00 (OFF)
# - Arduino ASCII Protocol: TALLY:1,0,2,0...\n
# ==============================================================================

import threading
import time

try:
    import serial
    import serial.tools.list_ports
    HAS_SERIAL = True
except ImportError:
    HAS_SERIAL = False

class SerialTallyDriver:
    def __init__(self, port="COM3", baudrate=115200, protocol="Arduino"):
        self.port = port
        self.baudrate = int(baudrate)
        self.protocol = protocol # "Arduino" or "USB_Relay"
        self.ser = None
        self.running = False
        self.lock = threading.Lock()

    @staticmethod
    def get_available_ports():
        """Returns a list of available serial COM port names."""
        if not HAS_SERIAL:
            # Fallback simple list for Windows
            return ["COM1", "COM2", "COM3", "COM4", "COM5", "COM6", "COM7", "COM8"]
        try:
            ports = [p.device for p in serial.tools.list_ports.comports()]
            return ports if ports else ["No Ports Found"]
        except Exception:
            return ["COM1", "COM2", "COM3"]

    def start(self):
        if self.running:
            return
        if not HAS_SERIAL:
            print("PySerial not installed. Install with 'pip install pyserial' for USB Relay support.")
            return
        with self.lock:
            try:
                self.ser = serial.Serial(self.port, self.baudrate, timeout=0.5)
                self.running = True
                print(f"Serial Hardware Driver active on {self.port} @ {self.baudrate} bps")
            except Exception as e:
                print(f"Serial Connect Error on {self.port}: {e}")
                self.running = False

    def stop(self):
        with self.lock:
            self.running = False
            if self.ser:
                try:
                    self.ser.close()
                except Exception:
                    pass
                self.ser = None
            print("Serial Hardware Driver stopped")

    def send_tally_states(self, tally_list):
        """
        Sends tally states over Serial port.
        tally_list is a list of tuples: (cam_index, label, is_prog, is_prev, is_att)
        """
        if not self.running or not self.ser or not HAS_SERIAL:
            return
        with self.lock:
            try:
                if self.protocol == "USB_Relay":
                    # Send LCUS hex relay commands for first 8 channels
                    for item in tally_list[:8]:
                        ch = item[0] + 1
                        is_on = item[2] or item[3] # Active if Program or Preview
                        state_byte = 0x01 if is_on else 0x00
                        checksum = (0xA0 + ch + state_byte) & 0xFF
                        cmd = bytes([0xA0, ch, state_byte, checksum])
                        self.ser.write(cmd)
                else:
                    # Arduino ASCII Format: TALLY:1,0,2,0...\n
                    tokens = []
                    for item in tally_list:
                        val = 0
                        if len(item) > 2 and item[2]: val |= 1 # Program
                        if len(item) > 3 and item[3]: val |= 2 # Preview
                        tokens.append(str(val))
                    line = f"TALLY:{','.join(tokens)}\n"
                    self.ser.write(line.encode('ascii'))
            except Exception as e:
                print(f"Serial Write Error: {e}")
