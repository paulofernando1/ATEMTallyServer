# ==============================================================================
# OBS Tally Client - WebSocket 5.x Bridge
# ==============================================================================
# Connects to OBS Studio via obsws-python (WebSocket 5.x protocol).
#
# Architecture:
#   - ONE ReqClient  → initial sync + periodic poll of visible inputs (3s).
#   - ONE EventClient → real-time scene-switch callbacks.
#   - Reconnection uses exponential backoff: 5 → 10 → 20 → 30s (max).
#
# Match Modes (selected via combo in OBS card):
#   Automatico  - Scene name OR visible source inside current scene.
#   Cenas       - Scene name only. Program=red, Preview=green.
#   Video Source- Visible source inputs only. Active=red LED.
# ==============================================================================

import threading
import time
from obsws_python import EventClient


class ObsTallyClient:
    def __init__(self, host, port, password, get_mapping_func, on_tally_update, get_match_type_func=None):
        self.host = host
        self.port = port
        self.password = password
        self.get_mapping      = get_mapping_func       # lambda → dict {idx: name}
        self.on_tally_update  = on_tally_update        # callback(flags[])
        self.get_match_type   = get_match_type_func    # lambda → str

        self.req_client   = None
        self.event_client = None
        self.running      = False
        self.thread       = None

        # Current scene state
        self.current_program = None
        self.current_preview = None
        self.prog_inputs = []   # visible source names in program scene
        self.prev_inputs = []   # visible source names in preview scene

    # ──────────────────────────────────────────────────────────────────────────
    # Lifecycle
    # ──────────────────────────────────────────────────────────────────────────

    def start(self):
        """Start the background connection thread (idempotent)."""
        if self.running:
            return
        self.running = True
        self.thread = threading.Thread(target=self._run_loop, daemon=True)
        self.thread.start()

    def stop(self):
        """Signal the loop to stop and wait for the thread to exit."""
        self.running = False
        self._teardown()
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=3.0)

    def _teardown(self):
        """Safely disconnect both clients and null their references."""
        for attr in ('event_client', 'req_client'):
            client = getattr(self, attr, None)
            if client is not None:
                try:
                    client.disconnect()
                except Exception:
                    pass
                setattr(self, attr, None)

    # ──────────────────────────────────────────────────────────────────────────
    # OBS Event Callbacks  (called from EventClient's internal thread)
    # ──────────────────────────────────────────────────────────────────────────

    def on_current_program_scene_changed(self, data):
        """Fires when OBS switches the live Program scene."""
        self.current_program = data.scene_name
        self.prog_inputs = self._get_visible_inputs(self.current_program)
        print(f"OBS EVENT: Program → '{self.current_program}' | visible: {self.prog_inputs}")
        self._update_tally()

    def on_current_preview_scene_changed(self, data):
        """Fires when OBS switches the Preview scene (Studio Mode only)."""
        self.current_preview = data.scene_name
        self.prev_inputs = self._get_visible_inputs(self.current_preview)
        print(f"OBS EVENT: Preview → '{self.current_preview}' | visible: {self.prev_inputs}")
        self._update_tally()

    def on_scene_item_enable_state_changed(self, data):
        """Fires when a source is shown/hidden (eye icon) inside a scene."""
        scene = getattr(data, 'scene_name', None)
        enabled = getattr(data, 'scene_item_enabled', '?')
        print(f"OBS EVENT: SceneItemEnableStateChanged scene='{scene}' enabled={enabled}")

        changed = False
        if scene and self.current_program and scene.lower() == self.current_program.lower():
            self.prog_inputs = self._get_visible_inputs(self.current_program)
            print(f"  → PGM visible inputs refreshed: {self.prog_inputs}")
            changed = True
        if scene and self.current_preview and scene.lower() == self.current_preview.lower():
            self.prev_inputs = self._get_visible_inputs(self.current_preview)
            print(f"  → PVW visible inputs refreshed: {self.prev_inputs}")
            changed = True

        if changed:
            self._update_tally()

    # ──────────────────────────────────────────────────────────────────────────
    # Scene Input Helpers
    # ──────────────────────────────────────────────────────────────────────────

    def _get_visible_inputs(self, scene_name, _depth=0):
        """
        Return source names that are VISIBLE (sceneItemEnabled=True) in the scene.
        Handles both camelCase and snake_case dict keys (obsws_python version variance).
        Recursively resolves groups and nested scenes up to a depth of 5.
        """
        if not self.req_client or not scene_name or _depth > 5:
            return []
        try:
            response = self.req_client.get_scene_item_list(scene_name)
            inputs = []
            items = getattr(response, 'scene_items', None)
            if items is None:
                return []
            for item in items:
                # obsws_python may return camelCase or snake_case keys
                enabled = item.get('sceneItemEnabled',
                          item.get('scene_item_enabled', True))
                name    = item.get('sourceName',
                          item.get('source_name', ''))
                is_group = item.get('isGroup',
                           item.get('is_group', False))
                stype   = item.get('sourceType',
                          item.get('source_type', ''))
                
                if not enabled or not name:
                    continue

                if is_group:
                    try:
                        grp = self.req_client.get_group_scene_item_list(name)
                        for gi in getattr(grp, 'scene_items', []):
                            g_enabled = gi.get('sceneItemEnabled',
                                        gi.get('scene_item_enabled', True))
                            g_name    = gi.get('sourceName',
                                        gi.get('source_name', ''))
                            if g_enabled and g_name:
                                inputs.append(g_name)
                    except Exception as ge:
                        print(f"OBS: Group fetch error for '{name}': {ge}")
                elif stype == 'OBS_SOURCE_TYPE_SCENE':
                    # Recurse nested scene
                    inputs.extend(self._get_visible_inputs(name, _depth + 1))
                else:
                    inputs.append(name)
            return inputs
        except Exception as e:
            print(f"OBS: _get_visible_inputs error for '{scene_name}': {e}")
            return []

    def _sync_scenes(self):
        """Fetch current program and preview scenes from OBS."""
        try:
            prog_resp = self.req_client.get_current_program_scene()
            if hasattr(prog_resp, 'current_program_scene_name'):
                self.current_program = prog_resp.current_program_scene_name
                self.prog_inputs = self._get_visible_inputs(self.current_program)
        except Exception as e:
            print(f"OBS: Could not get program scene: {e}")

        try:
            prev_resp = self.req_client.get_current_preview_scene()
            if hasattr(prev_resp, 'current_preview_scene_name'):
                self.current_preview = prev_resp.current_preview_scene_name
                self.prev_inputs = self._get_visible_inputs(self.current_preview)
        except Exception:
            pass  # Non-fatal: studio mode may be off

        print(f"OBS: Scene sync → PGM='{self.current_program}' visible={self.prog_inputs}")
        print(f"OBS: Scene sync → PVW='{self.current_preview}' visible={self.prev_inputs}")

    def _poll_inputs(self):
        """
        Poll current visible inputs and return True if anything changed.
        Called every 3s as a fallback in case SceneItemEnableStateChanged
        does not fire (e.g. subscription issue or OBS version quirk).
        """
        changed = False
        try:
            new_prog = self._get_visible_inputs(self.current_program)
            if new_prog != self.prog_inputs:
                print(f"OBS POLL: PGM visible changed: {self.prog_inputs} → {new_prog}")
                self.prog_inputs = new_prog
                changed = True
        except Exception:
            pass
        try:
            new_prev = self._get_visible_inputs(self.current_preview)
            if new_prev != self.prev_inputs:
                print(f"OBS POLL: PVW visible changed: {self.prev_inputs} → {new_prev}")
                self.prev_inputs = new_prev
                changed = True
        except Exception:
            pass
        return changed

    # ──────────────────────────────────────────────────────────────────────────
    # Tally Logic
    # ──────────────────────────────────────────────────────────────────────────

    def _update_tally(self):
        """
        Compute tally flags for all 41 cameras and fire the callback.
        flag 0=Off  1=Program/red  2=Preview/green
        """
        flags = [0] * 41
        mapping    = self.get_mapping()
        match_type = self.get_match_type() if self.get_match_type else "Automatico"

        prog_lower        = self.current_program.lower() if self.current_program else ""
        prev_lower        = self.current_preview.lower() if self.current_preview else ""
        prog_inputs_lower = [s.lower() for s in self.prog_inputs]
        prev_inputs_lower = [s.lower() for s in self.prev_inputs]

        for i in range(41):
            target = mapping.get(i, "").strip().lower()
            if not target:
                continue

            if match_type == "Cenas":
                # Match scene name only
                if target == prog_lower:
                    flags[i] = 1
                elif target == prev_lower:
                    flags[i] = 2

            elif match_type == "Video Source":
                # Source visible in program OR preview → red LED
                if target in prog_inputs_lower or target in prev_inputs_lower:
                    flags[i] = 1

            else:   # Automatico
                # Match scene name OR any visible source inside it
                if target == prog_lower or target in prog_inputs_lower:
                    flags[i] = 1
                elif target == prev_lower or target in prev_inputs_lower:
                    flags[i] = 2

        if self.on_tally_update:
            self.on_tally_update(flags)

    # ──────────────────────────────────────────────────────────────────────────
    # Connection Loop
    # ──────────────────────────────────────────────────────────────────────────

    def _run_loop(self):
        """
        Main connection loop with exponential backoff.
        1. Connect ReqClient → sync scenes → update tally.
        2. 1s pause, then connect EventClient with Subs.ALL for full events.
        3. Main loop: poll visible inputs every 3s + heartbeat every 30s.
        4. On failure, teardown + exponential backoff before retry.
        """
        from obsws_python import ReqClient, Subs

        retry_delay  = 5
        max_delay    = 30
        POLL_EVERY   = 3    # seconds between visible-input polls
        HB_EVERY     = 30   # seconds between heartbeat pings

        while self.running:
            try:
                # ── Step 1: Request Client ────────────────────────────────
                print(f"OBS: Connecting to {self.host}:{self.port}...")
                self.req_client = ReqClient(
                    host=self.host, port=self.port, password=self.password
                )
                if not self.running:
                    break

                self._sync_scenes()
                self._update_tally()

                # ── Step 2: Event Client (1s gap) ─────────────────────────
                time.sleep(1.0)
                if not self.running:
                    break

                print("OBS: Registering event listener (Subs.ALL)...")
                self.event_client = EventClient(
                    host=self.host, port=self.port, password=self.password,
                    subs=Subs.ALL      # ensure SceneItems events are included
                )
                self.event_client.callback.register([
                    self.on_current_program_scene_changed,
                    self.on_current_preview_scene_changed,
                    self.on_scene_item_enable_state_changed,
                ])

                print("OBS: Connected. Listening for events + polling every 3s.")
                retry_delay = 5   # reset backoff on successful connect

                # ── Step 3: Poll + Heartbeat loop ─────────────────────────
                last_poll = time.time()
                last_hb   = time.time()

                while self.running:
                    time.sleep(1)
                    now = time.time()

                    # Fast poll: refresh visible inputs every 3s
                    if now - last_poll >= POLL_EVERY:
                        last_poll = now
                        if self._poll_inputs():
                            self._update_tally()

                    # Slow heartbeat: verify connection every 30s
                    if now - last_hb >= HB_EVERY:
                        last_hb = now
                        try:
                            self.req_client.get_version()
                        except Exception as hb_err:
                            print(f"OBS: Heartbeat failed ({hb_err}). Reconnecting...")
                            break

            except Exception as conn_err:
                if self.running:
                    print(f"OBS: Connection error: {conn_err}. Retry in {retry_delay}s...")
                    time.sleep(retry_delay)
                    retry_delay = min(retry_delay * 2, max_delay)

            finally:
                self._teardown()
