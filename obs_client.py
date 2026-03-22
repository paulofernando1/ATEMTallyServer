# ==============================================================================
# OBS Tally Client - WebSocket 5.x Bridge
# ==============================================================================
# This module connects to OBS Studio using the Websocket-python client.
# It monitors 'CurrentProgramSceneChanged' and 'CurrentPreviewSceneChanged'
# to automatically update hardware tally flags.
#
# Logic: 
# 1. Sync Program/Preview scenes.
# 2. Map those scenes (and their composite inputs) back to Cam IDs.
# ==============================================================================

import threading
import time
from obsws_python import EventClient

class ObsTallyClient:
    def __init__(self, host, port, password, get_mapping_func, on_tally_update):
        self.host = host
        self.port = port
        self.password = password
        self.get_mapping = get_mapping_func
        self.on_tally_update = on_tally_update
        
        self.req_client = None
        self.event_client = None
        self.running = False
        self.thread = None
        
        self.current_program = None
        self.current_preview = None
        self.prog_inputs = []
        self.prev_inputs = []

    def start(self):
        if self.running:
            return
        self.running = True
        self.thread = threading.Thread(target=self._run_loop, daemon=True)
        self.thread.start()

    def stop(self):
        self.running = False
        # Disconnect clients if they exist
        if self.event_client:
            try:
                self.event_client.disconnect()
            except:
                pass
        if self.req_client:
            try:
                self.req_client.disconnect()
            except:
                pass
                
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=2.0)

    def on_current_program_scene_changed(self, data):
        self.current_program = data.scene_name
        self.prog_inputs = self._get_scene_inputs(self.current_program)
        self._update_tally()

    def on_current_preview_scene_changed(self, data):
        self.current_preview = data.scene_name
        self.prev_inputs = self._get_scene_inputs(self.current_preview)
        self._update_tally()

    def on_scene_item_enable_state_changed(self, data):
        # Refresh inputs if an item is toggled
        if self.current_program and data.scene_name == self.current_program:
            self.prog_inputs = self._get_scene_inputs(self.current_program)
        if self.current_preview and data.scene_name == self.current_preview:
            self.prev_inputs = self._get_scene_inputs(self.current_preview)
        self._update_tally()

    def _get_scene_inputs(self, scene_name):
        """Helper to get all inputs currently active within a specific scene."""
        if not self.req_client or not scene_name:
            return []
            
        try:
            # Get the list of items in the scene
            response = self.req_client.get_scene_item_list(scene_name)
            inputs = []
            
            # Extract source names from the items
            if hasattr(response, 'scene_items'):
                for item in response.scene_items:
                    # 'sourceName' gives us the actual input name (e.g. "Webcam", "NDI Camera")
                    inputs.append(item.get('sourceName', ''))
            return inputs
        except Exception as e:
            # req_client might fail if disconnected momentarily
            return []

    def _update_tally(self):
        # Support up to 41 cameras as per the main dashboard
        flags = [0] * 41
        mapping = self.get_mapping() # dict of {index: input_name}
        
        for i in range(41):
            target = mapping.get(i, "").strip().lower()
            if not target:
                continue
            
            # 1. Check Program: Is it the scene name? OR is it an input in that scene?
            if (self.current_program and target == self.current_program.lower()) or \
               (target in [inp.lower() for inp in self.prog_inputs]):
                flags[i] = 1
            # 2. Check Preview: Similarly
            elif (self.current_preview and target == self.current_preview.lower()) or \
                 (target in [inp.lower() for inp in self.prev_inputs]):
                flags[i] = 2
                
        if self.on_tally_update:
            self.on_tally_update(flags)

    def _run_loop(self):
        from obsws_python import ReqClient
        while self.running:
            try:
                # 1. Establish the Event Client first
                print(f"OBS: Connecting Event Client to {self.host}:{self.port}...")
                self.event_client = EventClient(host=self.host, port=self.port, password=self.password)
                if not self.running: break
                
                self.event_client.callback.register([
                    self.on_current_program_scene_changed,
                    self.on_current_preview_scene_changed,
                    self.on_scene_item_enable_state_changed
                ])
                
                # Brief gap between client types to satisfy some OBS WebSocket versions
                time.sleep(1.0)
                if not self.running: break

                # 2. Establish the Request Client
                print(f"OBS: Connecting Request Client to {self.host}:{self.port}...")
                self.req_client = ReqClient(host=self.host, port=self.port, password=self.password)
                
                # Fetch initial scenes
                prog_resp = self.req_client.get_current_program_scene()
                if hasattr(prog_resp, 'current_program_scene_name'):
                    self.current_program = prog_resp.current_program_scene_name
                    self.prog_inputs = self._get_scene_inputs(self.current_program)

                prev_resp = self.req_client.get_current_preview_scene()
                if hasattr(prev_resp, 'current_preview_scene_name'):
                    self.current_preview = prev_resp.current_preview_scene_name
                    self.prev_inputs = self._get_scene_inputs(self.current_preview)

                print(f"OBS: Initial sync successful (PGM: {self.current_program})")
                self._update_tally()
                
                # Health Monitor: Low frequency heartbeat (15s)
                while self.running:
                    for _ in range(15): # 15s wait in 1s chunks to stay responsive to stop()
                        if not self.running: break
                        time.sleep(1)
                    if not self.running: break

                    try:
                        self.req_client.get_version()
                    except Exception as e:
                        print(f"OBS: Heartbeat lost ({e}). Reconnecting...")
                        break

            except Exception as e:
                print(f"OBS: Connection error ({e}). Retrying in 5s...")
                time.sleep(5)
            
            finally:
                # Clean teardown for next attempt
                if self.event_client:
                    try: self.event_client.disconnect()
                    except: pass
                if self.req_client:
                    try: self.req_client.disconnect()
                    except: pass
                self.event_client = None
                self.req_client = None
