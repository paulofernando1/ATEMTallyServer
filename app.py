# ==============================================================================
# Tally Server Pro - ATEM Emulator (Main GUI Application)
# ==============================================================================
# This application emulates an ATEM Tally Server over UDP/9910.
# It integrates with vMix, OBS Studio, and mobile web browsers.
#
# Author: Paulo Fernando
# Version: 1.0.1
# ==============================================================================

import customtkinter as ctk
import json
import os
import threading
import requests
import webbrowser
from flask import Flask, render_template_string, request, send_from_directory
from flask_socketio import SocketIO, emit
import engineio.async_drivers.threading # Force PyInstaller to bundle the threading async driver
from tally_server import TallyServer
from vmix_client import VmixTallyClient
from obs_client import ObsTallyClient

# --- STYLING CONSTANTS ---
BG_COLOR = "#0f172a"          # Slate 900
PANEL_COLOR = "#1e293b"       # Slate 800
ACCENT_COLOR = "#3b82f6"      # Blue 500
HEADER_BG = "#1e293b"         # Slate 800
SUBTEXT_COLOR = "#94a3b8"     # Slate 400
TEXT_WHITE = "#f8fafc"        # Slate 50

# --- SILENCE STDOUT/STDERR FOR WINDOWED MODE (CRITICAL FOR FLASK) ---
import sys
import os
# sys.stdout = open(os.devnull, 'w') # Commented out for debugging
# sys.stderr = open(os.devnull, 'w')

def resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

class TallyApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("Tally Server Pro Controller")
        self.geometry("1150x700")
        self.configure(fg_color=BG_COLOR)
        self.remotedisplay_radio_var = ctk.IntVar(self, value=0)
        
        # --- STATE ---
        self.config_file = "config.json"
        # Initialize Tally Server on port 9910 with 41 sources (required for display)
        # Note: server_ip is not used by TallyServer, it binds to all interfaces.
        # The port is set later in toggle_server from entry_port.
        self.server = TallyServer(on_client_update=self.on_client_update, 
                                 on_repeater_detected=self.on_repeater_detected)
        self.server.set_tally_sources(120) # Support many tallies + display/message indices
        self.vmix_client = None
        self.obs_client = None
        
        self.is_server_running = False
        self.is_vmix_connected = False
        self.is_obs_connected = False
        
        # --- PERSISTENT VARS ---
        self.var_save_on_exit = ctk.BooleanVar(value=True)
        self.var_auto_server = ctk.BooleanVar(value=False)
        self.var_auto_vmix = ctk.BooleanVar(value=False)
        self.var_auto_obs = ctk.BooleanVar(value=False)
        self.var_touch_mode = ctk.BooleanVar(value=False)
        self.var_save_window = ctk.BooleanVar(value=True)
        self.var_remotedisplay_mode = ctk.BooleanVar(value=False)
        self.var_auto_web_tally = ctk.BooleanVar(value=False)
        
        # --- WINDOW STATE PERSISTENCE ---
        self.last_w = 1150
        self.last_h = 700
        self.bind("<Configure>", self.on_window_resize)
        
        # --- WEB TALLY STATE ---
        # Initialize Flask with a static folder for local assets (Offline Support)
        # Use resource_path to find the bundled assets in PyInstaller EXE
        self.web_tally_app = Flask(__name__, static_folder=resource_path('static'))
        # Defer initialization to avoid crash at startup
        self.socketio = None
        self.is_web_server_active = False # New flag
        self.web_clients = {} # sid -> cam_index (0-7)
        
        # --- TALLY VARS ---
        self.tally_vars_led1 = []
        self.tally_vars_led2_r = []
        self.tally_vars_led2_g = []
        self.tally_vars_led2_b = []
        self.tally_scene_vars = []
        self.tally_status_orbs = []
        self.tally_btn_led2_r = []
        self.tally_btn_led2_g = []
        self.tally_btn_led2_b = []
        self.tally_btn_led1_off = []
        self.tally_btn_led1_prog = []
        self.tally_btn_led1_prev = []
        self.tally_btn_led1_att = []
        self.tally_rows_widgets = [] # Frame references for deletion
        
        for i in range(41): # Pre-initialize variables for up to 41 tallys
            self.tally_vars_led1.append(ctk.StringVar(value="Off"))
            self.tally_vars_led2_r.append(ctk.BooleanVar(value=False))
            self.tally_vars_led2_g.append(ctk.BooleanVar(value=False))
            self.tally_vars_led2_b.append(ctk.BooleanVar(value=False))
            self.tally_scene_vars.append(ctk.StringVar(value=f"Cam {i+1}"))
        
        self.remotedisplay_display_modes = [0] * 41 # Support all possible tally slots
        self.remotedisplay_last_msg = ""
        self.current_rows_count = 0

        self.setup_ui()
        self.load_config()
        
        # Mandatory UI refresh to prevent black screens on some systems
        self.update()

    def on_window_resize(self, event):
        # Only track if it's the main window resize and not a child widget
        if event.widget == self:
            self.last_w = self.winfo_width()
            self.last_h = self.winfo_height()

    def setup_ui(self):
        # 1. TOP HEADER
        self.header = ctk.CTkFrame(self, fg_color=HEADER_BG, height=60, corner_radius=0)
        self.header.pack(fill="x", side="top")
        
        self.lbl_header = ctk.CTkLabel(self.header, text="📡 Tally Server Pro Controller", 
                                     font=ctk.CTkFont(size=20, weight="bold"), text_color=TEXT_WHITE)
        self.lbl_header.pack(side="left", padx=20, pady=10)
        self.broadcast_scheduled = False

        self.btn_settings = ctk.CTkButton(self.header, text="⚙️ Settings", width=100, 
                                        command=self.open_settings_menu,
                                        fg_color="transparent", hover_color="#334155")
        self.btn_settings.pack(side="right", padx=10)

        self.btn_help = ctk.CTkButton(self.header, text="❓ Help", width=80, 
                                     command=self.open_help_menu,
                                     fg_color="transparent", hover_color="#334155")
        self.btn_help.pack(side="right", padx=10)

        # 2. MAIN CONTAINER
        self.main_container = ctk.CTkFrame(self, fg_color="transparent")
        self.main_container.pack(fill="both", expand=True, padx=20, pady=10)
        
        self.main_container.grid_columnconfigure(0, weight=0, minsize=380)
        self.main_container.grid_columnconfigure(1, weight=1)
        self.main_container.grid_rowconfigure(0, weight=1)

        # --- LEFT COL: CONNECTIVITY ---
        self.left_col = ctk.CTkScrollableFrame(self.main_container, fg_color="transparent")
        self.left_col.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        # 1. Remote Display Panel
        self.remotedisplay_card = self.create_card(self.left_col, "📺 Remote Display (I2C)")
        self.remotedisplay_card.pack(fill="x", padx=10, pady=10) # Pack immediately
        if not self.var_remotedisplay_mode.get():
            self.remotedisplay_card.pack_forget() # Hide if not enabled
        
        row_remotedisplay_sel = self.create_input_row(self.remotedisplay_card, "Target Cam:")
        self.combo_remotedisplay_target = ctk.CTkComboBox(row_remotedisplay_sel, values=["ALL"] + [f"Cam {i+1}" for i in range(41)], 
                                                         width=120, command=self.on_remotedisplay_target_changed)
        self.combo_remotedisplay_target.pack(side="right")
        
        modes = [("OFF", 0), ("Show IP", 2), ("Tally Name", 3), ("WiFi", 4), ("SYS Info", 5), ("MESSAGE", 6)]
        radio_f = ctk.CTkFrame(self.remotedisplay_card, fg_color="transparent")
        radio_f.pack(pady=5, padx=10, fill="x")
        
        for i, (text, val) in enumerate(modes):
            r = ctk.CTkRadioButton(radio_f, text=text, variable=self.remotedisplay_radio_var, value=val, 
                                   font=ctk.CTkFont(size=10), command=self.send_remotedisplay_command)
            r.grid(row=i//3, column=i%3, sticky="w", pady=2, padx=5)
            
        msg_f = ctk.CTkFrame(self.remotedisplay_card, fg_color="transparent")
        msg_f.pack(pady=10, padx=10, fill="x")
        self.entry_remotedisplay_msg = ctk.CTkEntry(msg_f, placeholder_text="Enter message display...", height=35)
        self.entry_remotedisplay_msg.pack(side="left", expand=True, fill="x", padx=(0,5))
        self.btn_remotedisplay_send = ctk.CTkButton(msg_f, text="SEND ➤", width=80, height=35, 
                                          font=ctk.CTkFont(size=12, weight="bold"),
                                          fg_color="#10b981", hover_color="#059669", 
                                          command=self.send_remotedisplay_command,
                                          state="disabled")
        self.btn_remotedisplay_send.pack(side="right")

        # 2. Tally Server
        self.server_card = self.create_card(self.left_col, "ATEM Tally Server")
        row_server = self.create_input_row(self.server_card, "UDP Port:")
        self.entry_port = ctk.CTkEntry(row_server, width=80)
        self.entry_port.insert(0, "9910")
        self.entry_port.pack(side="right")
        self.btn_toggle_server = ctk.CTkButton(self.server_card, text="Start Server", command=self.toggle_server, height=35)
        self.btn_toggle_server.pack(pady=(10, 15), padx=10, fill="x")

        # Nested Web Tally Controls (No Title)
        row_web = self.create_input_row(self.server_card, "Web Port:")
        self.entry_web_port = ctk.CTkEntry(row_web, width=80)
        self.entry_web_port.insert(0, "8080")
        self.entry_web_port.pack(side="right")
        self.btn_toggle_web_server = ctk.CTkButton(self.server_card, text="Start Web Tally", command=self.toggle_web_server, height=35)
        self.btn_toggle_web_server.pack(pady=(10, 5), padx=10, fill="x")
        
        self.lbl_web_status = ctk.CTkLabel(self.server_card, text="● Web Tally: Stopped", font=ctk.CTkFont(size=11), text_color=SUBTEXT_COLOR)
        self.lbl_web_status.pack(pady=(0, 10))

        # 3. vMix
        self.vmix_card = self.create_card(self.left_col, "vMix Integration")
        row_vmix_ip = self.create_input_row(self.vmix_card, "Host IP:")
        self.entry_vmix_host = ctk.CTkEntry(row_vmix_ip, width=140)
        self.entry_vmix_host.pack(side="right")
        
        row_vmix_port = self.create_input_row(self.vmix_card, "Tally Port:")
        self.entry_vmix_port = ctk.CTkEntry(row_vmix_port, width=80)
        self.entry_vmix_port.insert(0, "8099")
        self.entry_vmix_port.pack(side="right")
        
        self.btn_vmix_connect = ctk.CTkButton(self.vmix_card, text="Connect vMix", command=self.toggle_vmix, height=35)
        self.btn_vmix_connect.pack(pady=(10, 15), padx=10, fill="x")

        # 4. OBS
        self.obs_card = self.create_card(self.left_col, "OBS integration")
        row_obs_ip = self.create_input_row(self.obs_card, "Host IP:")
        self.entry_obs_host = ctk.CTkEntry(row_obs_ip, width=140)
        self.entry_obs_host.pack(side="right")
        
        row_obs_port = self.create_input_row(self.obs_card, "WS Port:")
        self.entry_obs_port = ctk.CTkEntry(row_obs_port, width=80)
        self.entry_obs_port.insert(0, "4455")
        self.entry_obs_port.pack(side="right")
        
        row_obs_pass = self.create_input_row(self.obs_card, "WS Password:")
        self.entry_obs_pass = ctk.CTkEntry(row_obs_pass, placeholder_text="Password", show="*", width=140)
        self.entry_obs_pass.pack(side="right")
        
        self.btn_obs_connect = ctk.CTkButton(self.obs_card, text="Connect OBS", command=self.toggle_obs, height=35)
        self.btn_obs_connect.pack(pady=(5, 15), padx=10, fill="x")

        # --- RIGHT COL: MONITORING ---
        self.right_col = ctk.CTkFrame(self.main_container, fg_color=PANEL_COLOR)
        self.right_col.grid(row=0, column=1, sticky="nsew")
        
        # Swap: Web Tally Clients Section Before Active Network Clients
        self.web_tally_card = self.create_card(self.right_col, "🌐 Web Tally Clients")
        self.web_tally_card.pack(fill="x", side="bottom", padx=20, pady=(0, 10))
        self.web_tally_list_f = ctk.CTkFrame(self.web_tally_card, fg_color="transparent")
        self.web_tally_list_f.pack(fill="x", padx=10, pady=5)
        self.lbl_no_web = ctk.CTkLabel(self.web_tally_list_f, text="No Web Clients Connected", font=ctk.CTkFont(size=11), text_color=SUBTEXT_COLOR)
        self.lbl_no_web.pack(pady=10)

        # Clients panel
        self.clients_card = self.create_card(self.right_col, "▶ Active Network Clients")
        self.clients_card.pack(fill="x", side="bottom", padx=20, pady=(0, 20))
        self.txt_clients = ctk.CTkTextbox(self.clients_card, height=80, fg_color="#0f172a", border_width=0, font=("Consolas", 12))
        self.txt_clients.pack(fill="both", expand=True, padx=5, pady=5)
        self.txt_clients.configure(state="disabled")
        
        # Header area for Right Col
        self.right_header_frame = ctk.CTkFrame(self.right_col, fg_color="transparent")
        self.right_header_frame.pack(fill="x", padx=20, pady=(15, 5))
        
        ctk.CTkLabel(self.right_header_frame, text="🎥 CAMERA STATUS & TALLY CONTROL", 
                   font=ctk.CTkFont(size=16, weight="bold"), text_color=ACCENT_COLOR).pack(side="left")

        # Add Tally Button relocated OUTSIDE the table and AFTER the title
        self.btn_add_tally = ctk.CTkButton(self.right_header_frame, text="➕ Add Tally Light Row", 
                                        fg_color="transparent", border_width=1, border_color=ACCENT_COLOR,
                                        hover_color="#1d4ed8", command=self.on_click_add_row)
        self.btn_add_tally.pack(side="right")

        # Table with Grid for perfect alignment
        self.table_container = ctk.CTkFrame(self.right_col, fg_color="transparent")
        self.table_container.pack(fill="both", expand=True, padx=20, pady=5)
        
        # Header Row
        self.header_row = ctk.CTkFrame(self.table_container, fg_color="transparent", height=40)
        self.header_row.pack(fill="x")
        
        # Define grid weights for alignment
        self.header_row.grid_columnconfigure(0, minsize=40)  # #
        self.header_row.grid_columnconfigure(1, weight=1)    # Scene Name
        self.header_row.grid_columnconfigure(2, minsize=280) # LED 1 (Increased space for 4 buttons)
        self.header_row.grid_columnconfigure(3, minsize=140) # LED 2
        self.header_row.grid_columnconfigure(4, minsize=120) # Status
        self.header_row.grid_columnconfigure(5, minsize=40)  # Action (Delete)
        
        ctk.CTkLabel(self.header_row, text="#", font=ctk.CTkFont(weight="bold")).grid(row=0, column=0)
        ctk.CTkLabel(self.header_row, text="Scene Name", font=ctk.CTkFont(weight="bold"), anchor="w").grid(row=0, column=1, padx=10, sticky="w")
        ctk.CTkLabel(self.header_row, text="Main Tally (LED 1)", font=ctk.CTkFont(weight="bold")).grid(row=0, column=2, sticky="nsew")
        ctk.CTkLabel(self.header_row, text="LED 2 RGB", font=ctk.CTkFont(weight="bold")).grid(row=0, column=3, sticky="nsew")
        ctk.CTkLabel(self.header_row, text="Status", font=ctk.CTkFont(weight="bold")).grid(row=0, column=4, sticky="nsew")
        ctk.CTkLabel(self.header_row, text="", width=40).grid(row=0, column=5) # Placeholder for trash bin alignment

        ctk.CTkFrame(self.table_container, height=2, fg_color=BG_COLOR).pack(fill="x", pady=5)

        # Scrollable container for rows
        self.rows_scroll = ctk.CTkScrollableFrame(self.table_container, fg_color="transparent")
        self.rows_scroll.pack(fill="both", expand=True)

        self.rows_frame = ctk.CTkFrame(self.rows_scroll, fg_color="transparent")
        self.rows_frame.pack(fill="both", expand=True)

        for i in range(8):
            self.add_tally_row()
            if i < len(self.tally_scene_vars): self.tally_scene_vars[i].set(f"Cam {i+1}")
            self.update_led1_ui_buttons(i)
            


    def on_click_add_row(self):
        if self.current_rows_count < 41:
            self.add_tally_row(self.current_rows_count)
        else:
            self.btn_add_tally.configure(state="disabled", text="Max Rows Reached")

    def add_tally_row(self, index=None):
        i = index if index is not None else self.current_rows_count
        if i >= 41: return
        
        # FAIL-SAFE: Ensure underlying data structures exist for this index
        while len(self.tally_scene_vars) <= i:
            self.tally_scene_vars.append(ctk.StringVar(value=f"Cam {len(self.tally_scene_vars)+1}"))
        while len(self.tally_vars_led1) <= i:
            self.tally_vars_led1.append(ctk.StringVar(value="Off"))
        while len(self.tally_vars_led2_r) <= i:
            self.tally_vars_led2_r.append(ctk.BooleanVar(value=False))
            self.tally_vars_led2_g.append(ctk.BooleanVar(value=False))
            self.tally_vars_led2_b.append(ctk.BooleanVar(value=False))

        row = ctk.CTkFrame(self.rows_frame, fg_color="transparent", height=45)
        row.pack(fill="x", pady=2)
        row.grid_columnconfigure(0, minsize=40)
        row.grid_columnconfigure(1, weight=1)
        row.grid_columnconfigure(2, minsize=280)
        row.grid_columnconfigure(3, minsize=140)
        row.grid_columnconfigure(4, minsize=120)
        row.grid_columnconfigure(5, minsize=40)
        
        self.tally_rows_widgets.append(row)
        
        ctk.CTkLabel(row, text=str(i+1), font=ctk.CTkFont(weight="bold")).grid(row=0, column=0)
        ent = ctk.CTkEntry(row, textvariable=self.tally_scene_vars[i], height=30)
        ent.grid(row=0, column=1, padx=5, sticky="ew")
        
        # LED 1 Buttons
        f1 = ctk.CTkFrame(row, fg_color="transparent")
        f1.grid(row=0, column=2)
        
        o_btn = ctk.CTkButton(f1, text="Off", width=60, height=30, fg_color="#334155", command=lambda idx=i: self.set_led1_state(idx, "Off"))
        o_btn.pack(side="left", padx=2)
        p_btn = ctk.CTkButton(f1, text="Prog", width=60, height=30, fg_color="#334155", command=lambda idx=i: self.set_led1_state(idx, "Prog"))
        p_btn.pack(side="left", padx=2)
        v_btn = ctk.CTkButton(f1, text="Prev", width=60, height=30, fg_color="#334155", command=lambda idx=i: self.set_led1_state(idx, "Prev"))
        v_btn.pack(side="left", padx=2)
        a_btn = ctk.CTkButton(f1, text="ATT", width=60, height=30, fg_color="#334155", command=lambda idx=i: self.set_led1_state(idx, "ATT"))
        a_btn.pack(side="left", padx=2)

        self.tally_btn_led1_off.append(o_btn)
        self.tally_btn_led1_prog.append(p_btn)
        self.tally_btn_led1_prev.append(v_btn)
        self.tally_btn_led1_att.append(a_btn)
        
        f2 = ctk.CTkFrame(row, fg_color="transparent")
        f2.grid(row=0, column=3)
        
        r_btn = ctk.CTkButton(f2, text="R", width=30, height=30, fg_color="#334155", command=lambda idx=i: self.toggle_led2_color(idx, "R"))
        r_btn.pack(side="left", padx=2)
        g_btn = ctk.CTkButton(f2, text="G", width=30, height=30, fg_color="#334155", command=lambda idx=i: self.toggle_led2_color(idx, "G"))
        g_btn.pack(side="left", padx=2)
        b_btn = ctk.CTkButton(f2, text="B", width=30, height=30, fg_color="#334155", command=lambda idx=i: self.toggle_led2_color(idx, "B"))
        b_btn.pack(side="left", padx=2)
        
        self.tally_btn_led2_r.append(r_btn)
        self.tally_btn_led2_g.append(g_btn)
        self.tally_btn_led2_b.append(b_btn)
        
        orb = ctk.CTkLabel(row, text="● Idle", text_color="#64748b", font=ctk.CTkFont(size=11))
        orb.grid(row=0, column=4)
        self.tally_status_orbs.append(orb)

        btn_del = ctk.CTkButton(row, text="X", width=24, height=24, fg_color="#ef4444", 
                               hover_color="#991b1b", font=ctk.CTkFont(size=10, weight="bold"),
                               command=lambda idx=i: self.remove_tally_row(idx))
        btn_del.grid(row=0, column=5, padx=5, sticky="e")
        
        self.current_rows_count += 1
        
        # CRITICAL: Re-evaluate button colors for the newly rendered row
        self.update_led1_ui_buttons(i)
        self.check_scrollbar()

    def check_scrollbar(self):
        try:
            if self.current_rows_count <= 8:
                self.rows_scroll._scrollbar.grid_remove()
            else:
                self.rows_scroll._scrollbar.grid()
        except: pass

    def remove_tally_row(self, idx):
        try:
            if idx < 0 or idx >= self.current_rows_count: return
            
            # --- SNAPSHOT CURRENT DATA ---
            scenes = [v.get() for v in self.tally_scene_vars[:self.current_rows_count]]
            led1s = [v.get() for v in self.tally_vars_led1[:self.current_rows_count]]
            led2r = [v.get() for v in self.tally_vars_led2_r[:self.current_rows_count]]
            led2g = [v.get() for v in self.tally_vars_led2_g[:self.current_rows_count]]
            led2b = [v.get() for v in self.tally_vars_led2_b[:self.current_rows_count]]

            # --- POP INDEX ---
            scenes.pop(idx)
            led1s.pop(idx)
            led2r.pop(idx)
            led2g.pop(idx)
            led2b.pop(idx)

            # --- TOTAL UI REBUILD ---
            self.current_rows_count = 0
            for w in self.rows_frame.winfo_children(): w.destroy()
            
            self.tally_rows_widgets = []
            self.tally_status_orbs = []
            self.tally_btn_led1_off = []; self.tally_btn_led1_prog = []; self.tally_btn_led1_prev = []; self.tally_btn_led1_att = []
            self.tally_btn_led2_r = []; self.tally_btn_led2_g = []; self.tally_btn_led2_b = []
            
            for i in range(41): self.server.set_tally_flag(i, 0)
            
            for i in range(len(scenes)):
                self.add_tally_row(i)
                self.tally_scene_vars[i].set(scenes[i])
                self.tally_vars_led1[i].set(led1s[i])
                self.tally_vars_led2_r[i].set(led2r[i])
                self.tally_vars_led2_g[i].set(led2g[i])
                self.tally_vars_led2_b[i].set(led2b[i])
                self.update_led1_ui_buttons(i)

            self.btn_add_tally.configure(state="normal", text="➕ Add Tally Light Row")
            self.broadcast_all_tally()
            self.save_config()
        except Exception as e:
            print(f"REBUILD ERROR: {e}")
    def create_card(self, parent, title):
        card = ctk.CTkFrame(parent, fg_color="#334155" if parent == self.left_col else "#0f172a")
        card.pack(fill="x", padx=10, pady=10)
        ctk.CTkLabel(card, text=title, font=ctk.CTkFont(size=12, weight="bold"), text_color=ACCENT_COLOR).pack(pady=(5, 0), padx=10, anchor="w")
        return card

    def create_input_row(self, parent, label):
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(pady=5, fill="x", padx=10)
        ctk.CTkLabel(row, text=label, text_color=SUBTEXT_COLOR).pack(side="left")
        return row

    def open_settings_menu(self):
        try:
            import tkinter as tk
            win = tk.Toplevel(self) # Use standard Toplevel for stability
            win.title("Global Preferences & Tally Management")
            
            # Center and ensure positive coordinates
            off_x = max(0, self.winfo_x() + 50)
            off_y = max(0, self.winfo_y() + 50)
            win.geometry(f"780x500+100+100") # Start safe
            win.geometry(f"780x500+{off_x}+{off_y}")
            
            win.resizable(True, True)
            win.configure(bg=BG_COLOR)
            win.transient(self)
            
            # Use one big ctk frame as container
            main_container_f = ctk.CTkFrame(win, fg_color=BG_COLOR, corner_radius=0)
            main_container_f.pack(fill="both", expand=True)
            
            main_f = ctk.CTkFrame(main_container_f, fg_color="transparent")
            main_f.pack(fill="both", expand=True, padx=20, pady=10)
            
            # --- LEFT COL: PREFERENCES ---
            left_f = ctk.CTkFrame(main_f, fg_color=PANEL_COLOR)
            left_f.pack(side="left", fill="both", expand=True, padx=(0, 10))
            # Use inner frame for padding if needed, or just pack with padx/pady
            left_inner = ctk.CTkFrame(left_f, fg_color="transparent")
            left_inner.pack(fill="both", expand=True, padx=15, pady=15)
            
            ctk.CTkLabel(left_inner, text="⚙️ Preferences", font=ctk.CTkFont(size=18, weight="bold")).pack(pady=10)
            ctk.CTkCheckBox(left_inner, text="Save Config on Exit", variable=self.var_save_on_exit).pack(pady=5, padx=10, anchor="w")
            ctk.CTkCheckBox(left_inner, text="Save Window Sizes", variable=self.var_save_window).pack(pady=5, padx=10, anchor="w")
            ctk.CTkCheckBox(left_inner, text="Enable Remote Displays", variable=self.var_remotedisplay_mode, command=self.toggle_remotedisplay_ui).pack(pady=5, padx=10, anchor="w")
            ctk.CTkCheckBox(left_inner, text="Enable Touchscreen Mode", variable=self.var_touch_mode, command=self.apply_touch_scale).pack(pady=5, padx=10, anchor="w")
            ctk.CTkCheckBox(left_inner, text="AutoStart Server", variable=self.var_auto_server).pack(pady=5, padx=10, anchor="w")
            ctk.CTkCheckBox(left_inner, text="AutoStart WebTallys Server", variable=self.var_auto_web_tally).pack(pady=5, padx=10, anchor="w")
            ctk.CTkCheckBox(left_inner, text="Auto Connect OBS", variable=self.var_auto_obs).pack(pady=5, padx=10, anchor="w")
            ctk.CTkCheckBox(left_inner, text="Auto Connect vMix", variable=self.var_auto_vmix).pack(pady=5, padx=10, anchor="w")
            
            ctk.CTkLabel(left_inner, text="Version: V 1.0.1 Stable\nMax Capacity: up to 41 Tally Lights\n\nDeveloped by Paulo Fernando", 
                          font=ctk.CTkFont(size=11), text_color=SUBTEXT_COLOR).pack(pady=20)

            # --- RIGHT COL: TALLY MANAGEMENT ---
            right_f = ctk.CTkFrame(main_f, fg_color=PANEL_COLOR)
            right_f.pack(side="right", fill="both", expand=True)
            right_inner = ctk.CTkFrame(right_f, fg_color="transparent")
            right_inner.pack(fill="both", expand=True, padx=15, pady=15)
            
            ctk.CTkLabel(right_inner, text="📡 Tally Management", font=ctk.CTkFont(size=18, weight="bold")).pack(pady=10)
            
            # Thread-safe client list access - include direct and repeater clients
            try:
                clients_snapshot = list(self.server.clients)
                self.tally_ips = [c.ip for c in clients_snapshot if c.is_connected]
                
                # Also include clients reported via repeaters
                for parent_ip, sub_data in getattr(self.server, 'repeater_clients', {}).items():
                    for sub_item in sub_data:
                        # sub_item is (ip, role) tuple
                        sub_ip = sub_item[0]
                        if sub_ip not in self.tally_ips:
                            self.tally_ips.append(sub_ip)
            except Exception as e:
                print(f"IP SCAN ERROR: {e}")
                self.tally_ips = []
                
            if not self.tally_ips: self.tally_ips = ["No Tally Connected"]
            
            self.combo_tally_selector = ctk.CTkComboBox(right_inner, values=self.tally_ips, width=200, command=self.on_tally_device_selected)
            self.combo_tally_selector.pack(pady=10)
            
            self.info_tally_card = ctk.CTkFrame(right_inner, fg_color=BG_COLOR, corner_radius=8)
            self.info_tally_card.pack(fill="both", expand=True, pady=10)
            
            self.lbl_tally_info = ctk.CTkLabel(self.info_tally_card, text="Select a Tally Light\nto view details", 
                                              font=ctk.CTkFont(size=12), justify="left", text_color=SUBTEXT_COLOR)
            self.lbl_tally_info.pack(padx=10, pady=20)
            
            btn_f = ctk.CTkFrame(right_inner, fg_color="transparent")
            btn_f.pack(fill="x", pady=10)
            
            # Centralize and swap buttons: Update Info Left, Firmware Update Right
            self.btn_refresh_tally = ctk.CTkButton(btn_f, text="Update Info", width=140, height=35, 
                                                   fg_color=PANEL_COLOR, border_width=1, border_color="#475569",
                                                   command=lambda: self.on_tally_device_selected(self.combo_tally_selector.get()))
            self.btn_refresh_tally.pack(side="left", expand=True, padx=5)

            self.btn_ota_update = ctk.CTkButton(btn_f, text="🚀 Firmware Update", fg_color="#10b981", state="disabled",
                                               height=35, width=140, command=self.open_tally_ota_page)
            self.btn_ota_update.pack(side="left", expand=True, padx=5)

            ctk.CTkButton(main_container_f, text="Close", command=win.destroy).pack(pady=10)
            
            # Final focus call
            def final_focus():
                if win.winfo_exists():
                    win.lift(); win.update(); win.grab_set(); win.focus_force()
            win.after(200, final_focus)

        except Exception as e:
            print(f"SETTINGS ERROR: {e}")

    def on_tally_device_selected(self, ip):
        if not ip or ip == "No Tally Connected": return
        
        self.lbl_tally_info.configure(text="Fetching detailed diagnostics...", text_color=SUBTEXT_COLOR)
        self.btn_ota_update.configure(state="disabled")
        
        def fetch():
            try:
                r = requests.get(f"http://{ip}/", timeout=3)
                if r.status_code == 200:
                    text = r.text
                    
                    def get_val(key):
                        if key in text:
                            # Parse structured <div><strong>Key:</strong> Value</div>
                            try:
                                return text.split(key)[1].split("</div>")[0].strip()
                            except: return "N/A"
                        return "Unknown"

                    name = get_val("Device Name:</strong>")
                    status_raw = "Connected" if "status-on" in text else "Disconnected"
                    sig = get_val("Signal:</strong>")
                    vbat = get_val("Battery Voltage:</strong>")
                    static = get_val("Static IP:</strong>")
                    firmware = get_val("Firmware Version:</strong>")
                    mask = get_val("Subnet Mask:</strong>")
                    gate = get_val("Gateway:</strong>")

                    info = (
                        f"Device Name: {name}\n"
                        f"IP: {ip}\n"
                        f"Subnet Mask: {mask}\n"
                        f"Gateway: {gate}\n"
                        f"Signal: {sig}\n"
                        f"Battery Voltage: {vbat}\n"
                        f"Static IP: {static}\n"
                        f"Firmware Version: {firmware}\n"
                        f"Status: {status_raw}"
                    )
                    
                    self.after(0, lambda: [
                        self.lbl_tally_info.configure(text=info, text_color=TEXT_WHITE, justify="left"),
                        self.btn_ota_update.configure(state="normal")
                    ])
                else:
                    self.after(0, lambda: self.lbl_tally_info.configure(text="Tally Offline\n(No Web Server Response)", text_color="#ef4444"))
            except Exception as e:
                self.after(0, lambda: self.lbl_tally_info.configure(text=f"Connection Error:\n{str(e)[:50]}", text_color="#ef4444"))
        
        threading.Thread(target=fetch, daemon=True).start()

    def open_tally_ota_page(self):
        ip = self.combo_tally_selector.get()
        if ip and ip != "No Tally Connected":
            webbrowser.open(f"http://{ip}/update")

    def handle_web_set_cam(self, data):
        sid = request.sid
        if not isinstance(data, dict):
            return 
        idx = int(data.get('index', 0))
        self.web_clients[sid] = idx
        self.after(0, self.update_web_tally_ui)
        self.after(0, self.update_client_list)
        # Send the client its current tally state immediately
        self.after(50, lambda s=sid, i=idx: self._sync_web_client_cam(s, i))

    def handle_web_heartbeat(self, data):
        # Simply acknowledges the client is alive
        pass



    def set_web_client_cam(self, sid, combo):
        try:
            val = combo.get()
            cam_idx = int(val.split(" ")[1]) - 1
            if sid in self.web_clients:
                self.web_clients[sid] = cam_idx
                if self.socketio:
                    # Explicitly tell the web client to switch camera
                    self.socketio.emit('force_cam', {'index': cam_idx}, room=sid)
                    self.broadcast_all_tally()
        except Exception as e:
            print(f"WEB TALLY SET CAM ERROR: {e}")

    def setup_web_tally_routes(self):
        if self.socketio:
            @self.web_tally_app.route('/static/socket.io.min.js')
            def serve_socketio():
                # Explicitly serve with correct MIME type to avoid mobile browser security blocks
                # Use resource_path for PyInstaller bundle compatibility
                static_dir = resource_path('static')
                return send_from_directory(static_dir, 'socket.io.min.js', mimetype='application/javascript')

            @self.web_tally_app.route('/')
            def index():
                return render_template_string('''
                <!DOCTYPE html>
                <html>
                <head>
                    <title>Web Tally Light Simulation</title>
                    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no, viewport-fit=cover">
                    <!-- Local Socket.IO Library (True Offline Production Support) -->
                    <script src="/static/socket.io.min.js?v=4.7.2"></script>
                    <style>
                        body { margin: 0; padding: 0; background: #000; color: #fff; font-family: 'Segoe UI', sans-serif; overflow: hidden; height: 100vh; width: 100vw; }
                        #tally { width: 100%; height: 100%; display: flex; flex-direction: column; align-items: center; justify-content: center; transition: background 0.2s cubic-bezier(0.4, 0, 0.2, 1); }
                        #cam-info { position: absolute; top: 10vh; font-size: 38px; font-weight: 800; background: rgba(0,0,0,0.7); padding: 10px 40px; border-radius: 50px; border: 1px solid rgba(255,255,255,0.3); backdrop-filter: blur(10px); }
                        #status { font-size: 15vw; font-weight: 900; text-transform: uppercase; letter-spacing: 5px; text-shadow: 0 5px 25px rgba(0,0,0,0.8); pointer-events: none; }
                        .prog { background: #dc2626 !important; box-shadow: inset 0 0 100px rgba(0,0,0,0.5); }
                        .prev { background: #16a34a !important; color: #fff !important; box-shadow: inset 0 0 100px rgba(0,0,0,0.5); }
                        .att { background: #2563eb !important; box-shadow: inset 0 0 100px rgba(0,0,0,0.5); }
                        .off { background: #0f172a !important; }
                        #settings-panel { position: absolute; bottom: 8vh; background: rgba(0,0,0,0.8); padding: 20px 30px; border-radius: 20px; border: 1px solid rgba(255,255,255,0.15); backdrop-filter: blur(15px); display: flex; flex-direction: column; align-items: center; gap: 10px; }
                        select { background: #1e293b; color: white; border: 1px solid #475569; padding: 12px 20px; font-size: 20px; border-radius: 12px; outline: none; cursor: pointer; width: 220px; text-align: center; }
                        .btn-sync { background: #475569; color: white; border: none; padding: 8px 15px; border-radius: 8px; font-size: 11px; cursor: pointer; transition: 0.2s; }
                        .btn-sync:active { transform: scale(0.9); background: #64748b; }
                        .hint { font-size: 11px; color: #94a3b8; text-transform: uppercase; letter-spacing: 1px; }
                    </style>
                </head>
                <body>
                    <div id="tally" class="off">
                        <div id="cam-info">CAM 1</div>
                        <div id="status">OFF</div>
                        <div id="socket-status" style="font-size: 11px; opacity: 0.7; margin-top: 15px; font-weight: bold; font-family: monospace;">CONNECTING...</div>
                        <div id="settings-panel">
                            <select id="cam-num" onchange="updateCam()">
                                {% for i in range(1, 42) %}<option value="{{ i-1 }}">ASSIGN CAM {{ i }}</option>{% endfor %}
                            </select>
                            <button class="btn-sync" onclick="forceSync()">FORCE RE-SYNC</button>
                            <div class="hint">Digital Tally Client</div>
                        </div>
                    </div>
                    <script>
                        // Diagnostic: Check if library loaded
                        if (typeof io === 'undefined') {
                            document.getElementById("socket-status").innerText = "FAILED: Library not loaded. Check Internet.";
                            document.getElementById("socket-status").style.color = "red";
                        }

                        // Use explicit host to avoid guessing if the relative path fails on some mobile browsers
                        var socket = io(window.location.protocol + "//" + window.location.host, {
                            transports: ['websocket', 'polling'],
                            upgrade: true
                        });
                        
                        var camIdx = parseInt(localStorage.getItem('web_tally_cam') || 0);
                        document.getElementById("cam-num").value = camIdx;
                        document.getElementById("cam-info").innerText = "CAM " + (camIdx + 1);

                        function updateCam() {
                            camIdx = parseInt(document.getElementById("cam-num").value);
                            document.getElementById("cam-info").innerText = "CAM " + (camIdx + 1);
                            document.getElementById("socket-status").innerText = "UPDATING CAM " + (camIdx + 1);
                            socket.emit('set_cam', {index: camIdx});
                            localStorage.setItem('web_tally_cam', camIdx);
                        }

                        function forceSync() {
                            document.getElementById("socket-status").innerText = "FORCE SYNCING...";
                            socket.emit('set_cam', {index: camIdx});
                        }

                        socket.on('connect', function() {
                            console.log("Web Tally Connected");
                            document.getElementById("socket-status").innerText = "ONLINE (SID: " + socket.id.substring(0,6) + ")";
                            document.getElementById("socket-status").style.color = "#4ade80";
                            socket.emit('set_cam', {index: camIdx});
                        });
                        
                        socket.on('disconnect', function() {
                            document.getElementById("socket-status").innerText = "RECONNECTING...";
                            document.getElementById("socket-status").style.color = "#fbbf24";
                        });

                        socket.on('connect_error', function(err) {
                            document.getElementById("socket-status").innerText = "CONNECTION ERROR: " + err.message;
                            document.getElementById("socket-status").style.color = "#f87171";
                        });

                        setInterval(function() {
                            if (socket.connected) socket.emit('heartbeat', {sid: socket.id});
                        }, 5000);
                        socket.on('tally_update', function(data) {
                            if(data.index == camIdx) applyUpdate(data.flag);
                        });
                        socket.on('tally_bulk_update', function(data) {
                            if(!data || !data.updates) return;
                            data.updates.forEach(function(item) {
                                if(item.index == camIdx) applyUpdate(item.flag);
                            });
                        });
                        function applyUpdate(flag) {
                            var el = document.getElementById("tally");
                            var st = document.getElementById("status");
                            el.className = "";
                            el.style.background = ""; 

                            if (flag & 0x40) {
                                var r = (flag & 0x04) ? 255 : 0;
                                var g = (flag & 0x08) ? 255 : 0;
                                var b = (flag & 0x10) ? 255 : 0;
                                if(r || g || b) {
                                    el.style.background = "rgb("+r+","+g+","+b+")";
                                    st.innerText = (r?"R":"") + (g?"G":"") + (b?"B":"");
                                    return;
                                }
                            }
                            if(flag & 0x01) { el.classList.add("prog"); st.innerText = "PROGRAM"; }
                            else if(flag & 0x02) { el.classList.add("prev"); st.innerText = "PREVIEW"; }
                            else if(flag & 0x20) { el.classList.add("att"); st.innerText = "ATTENTION"; }
                            else { el.classList.add("off"); st.innerText = "OFF"; }
                        }
                        socket.on('force_cam', function(data) {
                            camIdx = data.index;
                            document.getElementById("cam-num").value = camIdx;
                            document.getElementById("cam-info").innerText = "CAM " + (parseInt(camIdx) + 1);
                        });
                    </script>
                </body>
                </html>
                ''')

            self.socketio.on_event('connect', self.handle_web_connect)
            self.socketio.on_event('disconnect', self.handle_web_disconnect)
            self.socketio.on_event('set_cam', self.handle_web_set_cam)
            self.socketio.on_event('heartbeat', self.handle_web_heartbeat)

    def start_web_server(self):
        try:
            raw_port = self.entry_web_port.get().strip()
            port = int(raw_port if raw_port else 8080)
            self.after(0, lambda: self.lbl_web_status.configure(text=f"● Web Tally: Starting ({port})...", text_color="#fbbf24"))
            self.is_web_server_active = True
            self.socketio.run(self.web_tally_app, host='0.0.0.0', port=port, allow_unsafe_werkzeug=True)
        except Exception as e:
            self.is_web_server_active = False
            self.after(0, lambda: self.lbl_web_status.configure(text=f"● Web Tally: Bind Error", text_color="#ef4444"))
            print(f"WEB TALLY ERROR: {e}")
            self.btn_toggle_web_server.configure(text="Start Web Tally", fg_color=ACCENT_COLOR)
        finally:
            self.is_web_server_active = False
            self.after(0, lambda: self.lbl_web_status.configure(text="● Web Tally: Stopped", text_color=SUBTEXT_COLOR))

    def check_web_server_active(self):
        if self.is_web_server_active:
            self.lbl_web_status.configure(text="● Web Tally: ONLINE", text_color="#10b981")
        else:
            self.lbl_web_status.configure(text="● Web Tally: Error/Stopped", text_color="#ef4444")

    def get_local_ip(self):
        import socket
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except: return "127.0.0.1"

    def open_help_menu(self):
        win = ctk.CTkToplevel(self)
        win.title("Help & Information")
        win.geometry("500x550")
        win.attributes("-topmost", True)
        
        ctk.CTkLabel(win, text="❓ Help & Information", font=ctk.CTkFont(size=22, weight="bold")).pack(pady=20)
        
        info_txt = (
            "🚀 Scene Matching:\n"
            "Ensure the 'Scene Name' in the table exactly matches your\n"
            "OBS Scene name or Source (Input) name for tally to work.\n\n"
            "📡 Default Network Ports:\n"
            "• Tally Server (UDP): 9910\n"
            "• Web Tally (TCP): 8080\n"
            "• vMix (TCP): 8099\n"
            "• OBS (Websocket): 4455\n\n"
            "🛡️ Firewall Note:\n"
            "Allow Port 8080 (TCP) and 9910 (UDP) in Windows Firewall\n"
            "for external browsers and tally lights to connect."
        )
        
        lbl = ctk.CTkLabel(win, text=info_txt, font=ctk.CTkFont(size=13), justify="left")
        lbl.pack(pady=10, padx=30)
        
        ctk.CTkButton(win, text="Got it!", command=win.destroy).pack(pady=30)

    def toggle_remotedisplay_ui(self):
        if self.var_remotedisplay_mode.get():
            self.remotedisplay_card.pack(fill="x", padx=10, pady=10, before=self.server_card)
        else:
            self.remotedisplay_card.pack_forget()

    def on_remotedisplay_target_changed(self, choice):
        # Synchronize UI buttons when changing the target cam
        try:
            if choice == "ALL":
                mode = self.remotedisplay_radio_var.get()
            else:
                cam_idx = int(choice.split(" ")[1]) - 1
                mode = self.remotedisplay_display_modes[cam_idx]
                self.remotedisplay_radio_var.set(mode)
            # Enable Send button only if MESSAGE mode (6) is selected
            self.btn_remotedisplay_send.configure(state="normal" if mode == 6 else "disabled")
        except: pass

    def send_remotedisplay_command(self):
        # This function is triggered both by radio clicks (auto-send) and the green SEND button
        msg = self.entry_remotedisplay_msg.get().strip()
        cam_str = self.combo_remotedisplay_target.get() # "Cam X" or "ALL"
            
        mode = self.remotedisplay_radio_var.get()
        if cam_str == "ALL":
            for i in range(len(self.remotedisplay_display_modes)):
                self.remotedisplay_display_modes[i] = mode
        else:
            try:
                cam_idx = int(cam_str.split(" ")[1]) - 1
                self.remotedisplay_display_modes[cam_idx] = mode
            except: pass
        
        # Update UI button state
        self.btn_remotedisplay_send.configure(state="normal" if mode == 6 else "disabled")

        # 41-Source Support, 4-byte Padding, Expanded Buffers
        if msg:
            self.remotedisplay_last_msg = msg
            print(f"REMOTE DISPLAY: Sending message '{msg}' to {cam_str}")
        
        print(f"REMOTE DISPLAY: Setting mode {mode} for {cam_str}")
        self.broadcast_all_tally()

    def apply_touch_scale(self):
        ctk.set_widget_scaling(1.2 if self.var_touch_mode.get() else 1.0)
        # Auto-resize window to content
        self.update_idletasks()
        self.geometry("")

    def on_repeater_detected(self, repeater_ip):
        # Immediate feedback for user when a repeater reports clients
        self.after(0, self.update_client_list)

    def toggle_server(self):
        if not self.is_server_running:
            try:
                self.server.port = int(self.entry_port.get())
                self.server.start(); self.is_server_running = True
                self.btn_toggle_server.configure(text="Stop Server", fg_color="#ef4444")
            except Exception as e:
                print(f"SERVER START ERROR: {e}")
        else:
            self.server.stop(); self.is_server_running = False
            self.btn_toggle_server.configure(text="Start Server", fg_color=ACCENT_COLOR)
            # RESET ALL STATUS TO IDLE IMMEDIATELY
            self.update_client_list()

    def toggle_web_server(self):
        if not self.is_web_server_active:
            if self.socketio is None:
                try:
                    # 'threading' mode explicitly enabled and driver imported at top of file
                    self.socketio = SocketIO(self.web_tally_app, 
                                            cors_allowed_origins="*", 
                                            async_mode='threading',
                                            engineio_logger=False)
                    self.setup_web_tally_routes()
                except Exception as e:
                    err_msg = str(e)
                    self.after(0, lambda m=err_msg: self.lbl_web_status.configure(text=f"● Web Tally: Init Error\n({m[:40]})", text_color="#ef4444"))
                    return
            
            if self.socketio:
                self.btn_toggle_web_server.configure(text="Stop Web Tally", fg_color="#ef4444")
                t = threading.Thread(target=self.start_web_server, daemon=True)
                t.start()
                # Verify status after a short delay
                self.after(3000, self.check_web_server_active)
        else:
            self.is_web_server_active = False 
            self.btn_toggle_web_server.configure(text="Start Web Tally", fg_color=ACCENT_COLOR)
            self.lbl_web_status.configure(text="● Web Tally: Stopped", text_color=SUBTEXT_COLOR)

    def toggle_vmix(self):
        if not self.is_vmix_connected:
            try:
                h = self.entry_vmix_host.get(); p = int(self.entry_vmix_port.get() or 8099)
                self.vmix_client = VmixTallyClient(h, p, self.on_external_update)
                self.vmix_client.start(); self.is_vmix_connected = True
                self.btn_vmix_connect.configure(text="Disconnect vMix", fg_color="#ef4444")
            except: pass
        else:
            if self.vmix_client: self.vmix_client.stop()
            self.is_vmix_connected = False; self.btn_vmix_connect.configure(text="Connect vMix", fg_color=ACCENT_COLOR)

    def toggle_obs(self):
        if not self.is_obs_connected:
            try:
                h = self.entry_obs_host.get(); p = int(self.entry_obs_port.get() or 4455); pw = self.entry_obs_pass.get()
                self.obs_client = ObsTallyClient(h, p, pw, 
                                               lambda: {i: v.get() for i, v in enumerate(self.tally_scene_vars)}, 
                                               self.on_external_update)
                self.obs_client.start(); self.is_obs_connected = True
                self.btn_obs_connect.configure(text="Disconnect OBS", fg_color="#ef4444")
            except: pass
        else:
            if self.obs_client: self.obs_client.stop()
            self.is_obs_connected = False; self.btn_obs_connect.configure(text="Connect OBS", fg_color=ACCENT_COLOR)


    def on_external_update(self, flags):
        for i, f in enumerate(flags):
            if i < self.current_rows_count:
                v = "Off"
                if f == 1: v = "Prog"
                elif f == 2: v = "Prev"
                elif f == 32: v = "ATT" # 0x20
                self.tally_vars_led1[i].set(v)
                self.update_led1_ui_buttons(i)
        self.trigger_broadcast()

    def set_led1_state(self, idx, state):
        self.tally_vars_led1[idx].set(state)
        self.update_led1_ui_buttons(idx)
        self.trigger_broadcast()

    def trigger_broadcast(self):
        # Throttle broadcasts to 50ms to prevent network/socket congestion
        if not self.broadcast_scheduled:
            self.broadcast_scheduled = True
            self.after(50, self._do_broadcast)

    def _do_broadcast(self):
        self.broadcast_scheduled = False
        self.broadcast_all_tally()

    def update_led1_ui_buttons(self, idx):
        if idx >= len(self.tally_btn_led1_off): return
        
        state = self.tally_vars_led1[idx].get()
        # High-visibility colors for LED states
        cols = {"Off": "#334155", "Prog": "#ef4444", "Prev": "#10b981", "ATT": "#3b82f6"}
        
        self.tally_btn_led1_off[idx].configure(fg_color=cols["Off"] if state == "Off" else "#1e293b")
        self.tally_btn_led1_prog[idx].configure(fg_color=cols["Prog"] if state == "Prog" else "#1e293b")
        self.tally_btn_led1_prev[idx].configure(fg_color=cols["Prev"] if state == "Prev" else "#1e293b")
        self.tally_btn_led1_att[idx].configure(fg_color=cols["ATT"] if state == "ATT" else "#1e293b")

    def toggle_led2_color(self, idx, color):
        var = {"R": self.tally_vars_led2_r, "G": self.tally_vars_led2_g, "B": self.tally_vars_led2_b}[color][idx]
        var.set(not var.get())
        btn = {"R": self.tally_btn_led2_r, "G": self.tally_btn_led2_g, "B": self.tally_btn_led2_b}[color][idx]
        col = {"R": "#ef4444", "G": "#10b981", "B": "#3b82f6"}[color]
        btn.configure(fg_color=col if var.get() else "#334155")
        self.broadcast_all_tally()

    def broadcast_all_tally(self):
        # 120 sources to cover all tallies + Remote Display (41+) + Message buffer (82-106)
        self.server.set_tally_sources(120)
        
        batch_data = []
        # We broadcast all 41 possible camera indices
        for i in range(41):
            f = 0
            if i < self.current_rows_count:
                l1 = self.tally_vars_led1[i].get()
                if l1 == "Prog": f |= 0x01
                elif l1 == "Prev": f |= 0x02
                elif l1 == "ATT": f |= 0x20
                
                # LED 2 RGB
                if self.tally_vars_led2_r[i].get(): f |= 0x04
                if self.tally_vars_led2_g[i].get(): f |= 0x08
                if self.tally_vars_led2_b[i].get(): f |= 0x10
                
                # FORCE LED2 AUX OVERRIDE (Bit 6 / 0x40)
                if f & 0x1C: f |= 0x40
            
            self.server.set_tally_flag(i, f)
            
            # Prepare batch data for Web Tally
            if self.is_web_server_active:
                batch_data.append({'index': i, 'flag': f})
            
            # Remote Display Modes (Stored per Camera Slot)
            if i < len(self.remotedisplay_display_modes):
                self.server.set_tally_flag(41 + i, self.remotedisplay_display_modes[i])
                
        # Emit Batch to Web Tally Clients  
        if self.socketio and self.is_web_server_active and batch_data:
            try:
                self.socketio.emit('tally_bulk_update', {'updates': batch_data})
            except Exception:
                pass
            
        # Message Buffer: Re-mapped to start at index 82
        msg_bytes = list(self.remotedisplay_last_msg.encode('ascii', 'ignore')[:24])
        for i in range(24):
            val = msg_bytes[i] if i < len(msg_bytes) else 0
            self.server.set_tally_flag(82 + i, val)
            
        # Message Length Trigger: Re-mapped to index 106
        self.server.set_tally_flag(106, len(msg_bytes))

    def handle_web_connect(self, *args, **kwargs):
        sid = request.sid
        print(f"WEB TALLY CONNECTED: {sid}")
        self.web_clients[sid] = 0
        self.after(0, self.update_web_tally_ui)
        self.after(0, self.update_client_list)
        self.after(50, lambda s=sid: self._sync_web_client_cam(s, 0))

    def handle_web_disconnect(self, *args, **kwargs):
        sid = request.sid
        print(f"WEB TALLY DISCONNECTED: {sid}")
        self.web_clients.pop(sid, None)
        self.after(0, self.update_web_tally_ui)
        self.after(0, self.update_client_list)

    def _sync_web_client_cam(self, sid, idx):
        self.update_web_tally_ui()
        if idx >= self.current_rows_count: return
        f = 0
        if self.tally_vars_led1[idx].get() == "Prog": f |= 0x01
        elif self.tally_vars_led1[idx].get() == "Prev": f |= 0x02
        elif self.tally_vars_led1[idx].get() == "ATT": f |= 0x20
        
        if self.tally_vars_led2_r[idx].get(): f |= 0x04
        if self.tally_vars_led2_g[idx].get(): f |= 0x08
        if self.tally_vars_led2_b[idx].get(): f |= 0x10
        
        if f & 0x1C: f |= 0x40 # Override bit if RGB
        # Emit using socketio.emit to the specific SID
        if self.socketio:
            try:
                self.socketio.emit('tally_update', {'index': idx, 'flag': f}, to=sid)
            except Exception:
                pass



    def update_web_tally_ui(self):
        try:
            # Clear old items except the 'No clients' label if empty
            if not getattr(self, 'web_clients', None):
                for w in self.web_tally_list_f.winfo_children():
                    if w != self.lbl_no_web: w.destroy()
                self.lbl_no_web.pack(pady=10)
                return
                
            self.lbl_no_web.pack_forget()
            for w in self.web_tally_list_f.winfo_children():
                if w != self.lbl_no_web: w.destroy()
            
            # Rebuild the list of web clients
            for sid, target_cam in list(self.web_clients.items()):
                row = ctk.CTkFrame(self.web_tally_list_f, fg_color="#1e293b", corner_radius=6)
                row.pack(fill="x", pady=2)
                
                # Show first 8 chars of SID for better identification
                short_id = sid[:8] if sid else "????"
                name_lbl = ctk.CTkLabel(row, text=f"📱 Client {short_id}...", font=ctk.CTkFont(size=12, weight="bold"))
                name_lbl.pack(side="left", padx=10, pady=5)
                
                combo = ctk.CTkComboBox(row, values=[f"Cam {i+1}" for i in range(41)], width=100, height=24)
                combo.set(f"Cam {target_cam+1}")
                combo.pack(side="right", padx=10, pady=5)
                
                def on_change(choice, s=sid):
                    try:
                        idx = int(choice.split(" ")[1]) - 1
                        if s in self.web_clients:
                            self.web_clients[s] = idx
                            if self.socketio:
                                self.socketio.emit('force_cam', {'index': idx}, to=s)
                            self.broadcast_all_tally()
                    except: pass
                    
                combo.configure(command=on_change)
        except Exception as e:
            print(f"WEB UI UPDATE ERROR: {e}")


    def on_client_update(self):
        self.after(0, self.update_client_list)

    def update_client_list(self):
        self.txt_clients.configure(state="normal")
        self.txt_clients.delete("1.0", "end")
        
        text_lines = []
        active_ids = set()
        
        if getattr(self, 'web_clients', None):
            for sid, cam_id in self.web_clients.items():
                active_ids.add(cam_id)
                text_lines.append(f"🌐 [Web Tally] Role: Cam {cam_id + 1} (SID: {sid[:4]}...)")

        if self.is_server_running:
            for c in self.server.clients:
                if c.is_connected:
                    s = "Active" if c.is_initialized else "Sync"
                    text_lines.append(f"▶ [{c.ip}] Role: Cam {c.tally_id + 1 if c.tally_id >= 0 else '?'} ({s})")
                    if c.is_initialized and c.tally_id >= 0:
                        active_ids.add(c.tally_id)
            
            # Add Sub-clients reported via Repeaters
            for parent_ip, sub_data in getattr(self.server, 'repeater_clients', {}).items():
                for sub_item in sub_data:
                    # sub_item is (ip, role)
                    sub_ip, sub_role = sub_item
                    role_str = f"Role: Cam {sub_role + 1}" if sub_role >= 0 else "Role: ?"
                    text_lines.append(f"  └─ [{sub_ip}] {role_str} via Repeater ({parent_ip})")
                    if sub_role >= 0:
                        active_ids.add(sub_role)
            
            # Show if current dashboard tally rows are active via ANY connection
            active_repeater_sub_ips = []
            for sub_data in self.server.repeater_clients.values():
                for sub_item in sub_data:
                    active_repeater_sub_ips.append(sub_item[0])
            
            # Final footer summary (optional)
            if not text_lines: 
                text_lines.append("No active clients detected.")
        
        output_text = "\n".join(text_lines)
        self.txt_clients.insert("end", output_text if output_text else "Waiting for connections...")
        self.txt_clients.configure(state="disabled")
        
        # Final dashboard footer logic
        pass
        
        # Row Status Orbs - high-reliability lighting logic
        for i in range(self.current_rows_count):
            is_active = (i in active_ids)
            
            # Additional check: If row role is mentioned by an online repeater
            # We don't have direct role matching for repeater clients, but if the repeater
            # is connected and reporting sub-IPs, we show status for the repeater itself.
            # However, if a sub-tally connects eventually, c.tally_id will handle it.
            
            if self.is_server_running and is_active:
                self.tally_status_orbs[i].configure(text="● ONLINE", text_color="#10b981")
            else:
                self.tally_status_orbs[i].configure(text="● Idle", text_color=SUBTEXT_COLOR)
        
        # Force UI refresh
        self.update_idletasks()

    def load_config(self):
        if not os.path.exists(self.config_file): return
        try:
            with open(self.config_file, "r") as f:
                c = json.load(f)
                self.entry_port.delete(0, "end")
                self.entry_port.insert(0, c.get("server_port", "9910"))
                self.entry_vmix_host.delete(0, "end")
                self.entry_vmix_host.insert(0, c.get("vmix_host", ""))
                self.entry_vmix_port.delete(0, "end")
                self.entry_vmix_port.insert(0, str(c.get("vmix_port", "8099")))
                self.entry_obs_host.delete(0, "end")
                self.entry_obs_host.insert(0, c.get("obs_host", ""))
                self.entry_obs_port.delete(0, "end")
                self.entry_obs_port.insert(0, str(c.get("obs_port", "4455")))
                self.entry_obs_pass.delete(0, "end")
                self.entry_obs_pass.insert(0, c.get("obs_pass", ""))
                self.entry_web_port.delete(0, "end")
                self.entry_web_port.insert(0, str(c.get("web_port", "8080")))
                self.var_save_on_exit.set(c.get("save_on_exit", True))
                self.var_auto_server.set(c.get("auto_server", False))
                self.var_auto_vmix.set(c.get("auto_vmix", False))
                self.var_auto_obs.set(c.get("auto_obs", False))
                self.var_touch_mode.set(c.get("touch_mode", False))
                self.var_save_window.set(c.get("save_window", True))
                self.var_remotedisplay_mode.set(c.get("remotedisplay_mode", False))
                self.var_auto_web_tally.set(c.get("auto_web_tally", False))
                self.toggle_remotedisplay_ui()
                
                if self.var_save_window.get():
                    w = c.get("window_w", 1150)
                    h = c.get("window_h", 700)
                    self.geometry(f"{w}x{h}")

                # Restore Remote Display UI State
                self.combo_remotedisplay_target.set(c.get("remotedisplay_target", "ALL"))
                self.remotedisplay_radio_var.set(c.get("remotedisplay_mode_val", 0))
                self.entry_remotedisplay_msg.delete(0, "end")
                self.entry_remotedisplay_msg.insert(0, c.get("remotedisplay_msg", ""))
                self.on_remotedisplay_target_changed(self.combo_remotedisplay_target.get())

                row_count = c.get("row_count", 8)
                # Clear initial rows first
                for widget in self.rows_frame.winfo_children(): widget.destroy()
                self.current_rows_count = 0
                self.tally_rows_widgets = []
                self.tally_status_orbs = []
                self.tally_btn_led1_off = []; self.tally_btn_led1_prog = []; self.tally_btn_led1_prev = []; self.tally_btn_led1_att = []
                self.tally_btn_led2_r = []; self.tally_btn_led2_g = []; self.tally_btn_led2_b = []
                
                for i in range(row_count): self.add_tally_row(i)
                # Re-highlight LED buttons after loading config
                for i in range(row_count): self.update_led1_ui_buttons(i)

                names = c.get("scenes", [])
                for i, name in enumerate(names):
                    if i < len(self.tally_scene_vars): self.tally_scene_vars[i].set(name)
                if self.var_touch_mode.get(): ctk.set_widget_scaling(1.2)
                self.after(600, self._auto_run)
        except: pass

    def _auto_run(self):
        if self.var_auto_server.get(): 
            self.toggle_server()
            # After server starts, broadcast current Remote Display state
            self.root.after(1000, lambda: self.on_remotedisplay_target_changed(self.combo_remotedisplay_target.get()))
        if self.var_auto_vmix.get(): self.toggle_vmix()
        if self.var_auto_obs.get(): self.toggle_obs()
        if self.var_auto_web_tally.get(): self.toggle_web_server()

    def save_config(self):
        if not self.var_save_on_exit.get(): return
        cfg = {
            "server_port": self.entry_port.get(),
            "vmix_host": self.entry_vmix_host.get(), "vmix_port": self.entry_vmix_port.get(),
            "obs_host": self.entry_obs_host.get(), "obs_port": self.entry_obs_port.get(), "obs_pass": self.entry_obs_pass.get(),
            "web_port": self.entry_web_port.get(),
            "save_on_exit": self.var_save_on_exit.get(), "auto_server": self.var_auto_server.get(),
            "auto_vmix": self.var_auto_vmix.get(), "auto_obs": self.var_auto_obs.get(),
            "auto_web_tally": self.var_auto_web_tally.get(),
            "touch_mode": self.var_touch_mode.get(), 
            "remotedisplay_mode": self.var_remotedisplay_mode.get(),
            "remotedisplay_target": self.combo_remotedisplay_target.get(),
            "remotedisplay_mode_val": self.remotedisplay_radio_var.get(),
            "remotedisplay_msg": self.entry_remotedisplay_msg.get(),
            "save_window": self.var_save_window.get(),
            "window_w": self.last_w,
            "window_h": self.last_h,
            "row_count": self.current_rows_count,
            "scenes": [v.get() for v in self.tally_scene_vars]
        }
        with open(self.config_file, "w") as f: json.dump(cfg, f, indent=4)

if __name__ == "__main__":
    app = TallyApp()
    app.protocol("WM_DELETE_WINDOW", lambda: (app.save_config(), app.destroy()))
    app.mainloop()
