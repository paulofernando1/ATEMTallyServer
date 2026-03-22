import socket
import time
import struct
import threading

from tally_server import TallyServer

def hex_dump(data):
    return " ".join(f"{b:02X}" for b in data)

# Wrap the send and recv to print
class DebugTallyServer(TallyServer):
    def _send_buffer(self, client, data):
        print(f"[{time.time():.3f}] SEND to {client.ip}:{client.port} ({len(data)} bytes): {hex_dump(data)}")
        super()._send_buffer(client, data)

    def _run_loop(self):
        print("Debug run loop started...")
        while self.running:
            try:
                data, addr = self.sock.recvfrom(2048)
                ip, port = addr
                print(f"[{time.time():.3f}] RECV from {ip}:{port} ({len(data)} bytes): {hex_dump(data)}")
                
                packet_size = len(data)
                
                if packet_size >= 12:
                    flags = data[0] & 0b11111000
                    packet_len = ((data[0] & 0b00000111) << 8) + data[1]
                    
                    if packet_size == packet_len:
                        client = self._get_client(ip, port)
                        if client:
                            client.session_id = (data[2] << 8) + data[3]
                            remote_packet_id = (data[10] << 8) + data[11]
                            if remote_packet_id > 0:
                                client.last_remote_packet_id = remote_packet_id
                            client.last_recv = time.time()

                            if client.is_initialized:
                                if flags & 0b10000000: # ACK
                                    client.last_acked_id = (data[4] << 8) + data[5]
                                    print(f"  -> ACK received for ID {client.last_acked_id}")
                                
                                if flags & 0b00001000: # ACK_REQUEST
                                    print(f"  -> ACK_REQUEST received, sending ACK for {remote_packet_id}")
                                    buf = bytearray(12)
                                    buf[0:12] = self._create_header(client, 0b10000000, 12, remote_packet_id)
                                    self._send_buffer(client, buf)

                                if flags & 0b01000000: # RESEND_REQUEST
                                    resend_packet_id = ((data[6] << 8) + data[7] + 1) & 0xFFFF
                                    print(f"  -> RESEND_REQUEST received for ID {resend_packet_id}")
                                    buf = bytearray(62)
                                    cmd_len = 12 + self._create_tally_data_cmd(buf)
                                    header = self._create_header(client, 0b10000000 | 0b00100000 | 0b00001000, cmd_len, 0, resend_packet_id)
                                    buf[0:12] = header
                                    self._send_buffer(client, buf[:cmd_len])

                            elif client.is_connected:
                                if flags & 0b10000000: # ACK
                                    print("  -> First ACK received. Initializing client and sending state.")
                                    buf = bytearray(62)
                                    cmd_len = 12 + self._create_tally_data_cmd(buf)
                                    buf[0:12] = self._create_header(client, 0b00001000, cmd_len) # ACK_REQUEST
                                    self._send_buffer(client, buf[:cmd_len])
                                    
                                    buf2 = bytearray(12)
                                    buf2[0:12] = self._create_header(client, 0b00001000, 12) # ACK_REQUEST
                                    self._send_buffer(client, buf2)

                                    client.is_initialized = True
                                    if self.on_client_update: self.on_client_update()
                            else:
                                if flags & 0b00010000: # HELLO
                                    print("  -> HELLO received. Accepting.")
                                    buf = bytearray(20)
                                    buf[0:12] = self._create_header(client, 0b00010000, 20)
                                    buf[12] = 2 # ACCEPTED
                                    self._send_buffer(client, buf)
                                    client.is_connected = True
                                    if self.on_client_update: self.on_client_update()
                                else:
                                    print("  -> Expected HELLO but got something else. Dropping.")
                                    self._reset_client(client)
                        else:
                            if flags & 0b00010000:
                                print("  -> REJECTING connection (full)")
                                dummy = type('Dummy', (), {'session_id': 0, 'local_packet_id_counter': 0})()
                                buf = bytearray(20)
                                buf[0:12] = self._create_header(dummy, 0b00010000, 20)
                                buf[12] = 3 # REJECTED
                                try:
                                    self.sock.sendto(buf, (ip, port))
                                except: pass
            except BlockingIOError: pass
            except socket.timeout: pass
            except Exception as e: print("Exception:", e)

            if self.tally_flags_changed:
                buf = bytearray(62)
                cmd_len = 12 + self._create_tally_data_cmd(buf)
                for client in self.clients:
                    if client.is_initialized:
                        buf[0:12] = self._create_header(client, 0b00001000, cmd_len)
                        self._send_buffer(client, buf[:cmd_len])
                self.tally_flags_changed = False

            current_time = time.time()
            for client in self.clients:
                if client.is_initialized:
                    if client.last_acked_id < client.local_packet_id_counter and (current_time - client.last_send >= 0.25):
                        print(f"[{current_time:.3f}] TIMEOUT on ACK for packet {client.local_packet_id_counter}, resending")
                        buf = bytearray(62)
                        cmd_len = 12 + self._create_tally_data_cmd(buf)
                        buf[0:12] = self._create_header(client, 0b00001000, cmd_len)
                        # We must decrease the local packet id counter because _create_header increases it 
                        client.local_packet_id_counter = (client.local_packet_id_counter - 1) & 0xFFFF
                        buf[10] = (client.local_packet_id_counter >> 8) & 0xFF
                        buf[11] = client.local_packet_id_counter & 0xFF
                        self._send_buffer(client, buf[:cmd_len])
                    elif (current_time - client.last_recv >= 1.5) and (current_time - client.last_send >= 1.5):
                        print(f"[{current_time:.3f}] Sending Keep-Alive ACK_REQUEST")
                        buf = bytearray(12)
                        buf[0:12] = self._create_header(client, 0b00001000, 12)
                        self._send_buffer(client, buf)
                    elif (current_time - client.last_recv >= 10.0):
                        print(f"[{current_time:.3f}] DISCONNECT: 10.0s timeout reached for {client.ip}")
                        self._reset_client(client)
                elif client.is_connected:
                    if (current_time - client.last_send >= 1.5):
                        print(f"[{current_time:.3f}] Resending HELLO ACCEPTED")
                        buf = bytearray(20)
                        buf[0:12] = self._create_header(client, 0b00010000, 20)
                        buf[12] = 2
                        self._send_buffer(client, buf)
                    elif (current_time - client.last_recv >= 10.0):
                        print(f"[{current_time:.3f}] DISCONNECT (uninitialized): 10.0s timeout")
                        self._reset_client(client)
            time.sleep(0.01)

server = DebugTallyServer(port=9910)
server.start()
try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    server.stop()
