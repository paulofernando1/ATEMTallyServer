import socket
import threading
import time

class VmixTallyClient:
    def __init__(self, host, port, on_tally_update):
        self.host = host
        self.port = port
        self.on_tally_update = on_tally_update
        self.sock = None
        self.running = False
        self.thread = None

    def start(self):
        if self.running:
            return
        self.running = True
        self.thread = threading.Thread(target=self._run_loop, daemon=True)
        self.thread.start()

    def stop(self):
        self.running = False
        if self.sock:
            try:
                self.sock.close()
            except:
                pass
        if self.thread:
            self.thread.join()

    def _run_loop(self):
        while self.running:
            try:
                self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self.sock.settimeout(2.0)
                self.sock.connect((self.host, self.port))
                
                # Subscribe to TALLY events (standard vMix TCP API)
                self.sock.sendall(b"SUBSCRIBE TALLY\r\n")
                
                buffer = ""
                while self.running:
                    data = self.sock.recv(4096)
                    if not data:
                        break
                    
                    buffer += data.decode('utf-8', errors='ignore')
                    while "\r\n" in buffer:
                        line, buffer = buffer.split("\r\n", 1)
                        self._process_line(line)
                        
            except (socket.timeout, socket.error, ConnectionRefusedError):
                pass
            except Exception as e:
                print(f"vMix connection error: {e}")
            finally:
                if self.sock:
                    try:
                        self.sock.close()
                    except:
                        pass
            
            if self.running:
                time.sleep(2)  # Reconnect delay

    def _process_line(self, line):
        if line.startswith("TALLY OK"):
            # Format: 'TALLY OK 12000...'
            tally_data = line.replace("TALLY OK ", "").strip()
            
            flags = []
            for i in range(min(8, len(tally_data))):
                state = tally_data[i]
                if state == '1': # Program
                    flags.append(1)
                elif state == '2': # Preview
                    flags.append(2)
                else: # Off
                    flags.append(0)
            
            if self.on_tally_update:
                self.on_tally_update(flags)
