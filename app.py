# ==============================================================================
# Tally Server Pro - ATEM Emulator (Main GUI Application)
# ==============================================================================
# This application emulates an ATEM Tally Server over UDP/9910.
# It integrates with vMix, OBS Studio, and mobile web browsers.
#
# Author: Paulo Fernando
# Version: 1.0.2
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
from atem_client import AtemHardwareClient
from tsl_client import TslUmdSender
from roland_client import RolandTallyClient
from osc_client import OscTallyBridge
from serial_tally import SerialTallyDriver

# --- STYLING CONSTANTS (Adaptive Fluent/Zinc Light & Pro Dark Mode Tokens) ---
BG_COLOR = ("#f4f4f5", "#09090b")            # Zinc 100 / Zinc 950 (True Neutral Pro Dark Canvas)
PANEL_COLOR = ("#ffffff", "#18181b")         # Pure White / Zinc 900 (Elevated Surface)
HEADER_BG = ("#e4e4e7", "#121214")           # Zinc 200 / Deep Charcoal 
CARD_LEFT = ("#ffffff", "#1c1c1f")           # Left cards container surface
CARD_RIGHT = ("#ffffff", "#18181b")          # Right cards container surface
BORDER_COLOR = ("#cbd5e1", "#27272a")        # Zinc/Slate subtle border
BORDER_SUBTLE = ("#e2e8f0", "#202024")       # Extra subtle divider

# Typography Tokens
TEXT_PRIMARY = ("#09090b", "#f4f4f5")        # Zinc 950 / Zinc 50 (High contrast text)
TEXT_WHITE = TEXT_PRIMARY                    # Backward compatibility alias
SUBTEXT_COLOR = ("#52525b", "#a1a1aa")       # Zinc 600 / Zinc 400 (Readable muted)
TEXTBOX_BG = ("#f8fafc", "#121214")          # Textbox background
ROW_BG = ("#f8fafc", "#1f1f23")              # Dynamic table/list row background

# High-Contrast Monochrome Accent Tokens (Antigravity Dark/Light Style)
ACCENT_COLOR = ("#18181b", "#f4f4f5")        # Zinc 900 (Light) / Zinc 100 (Dark)
ACCENT_HOVER = ("#27272a", "#d4d4d8")        # Zinc 800 (Light) / Zinc 300 (Dark)
ACCENT_TEXT = ("#ffffff", "#09090b")         # Contrasting text on ACCENT_COLOR
HEADER_HOVER = ("#d4d4d8", "#27272a")        # Zinc 300 / Zinc 800

# Tally / Status Semantic Colors
COLOR_PROG = "#dc2626"                       # Red 600 (Program / On-Air)
COLOR_PROG_HOVER = "#b91c1c"                 # Red 700
COLOR_PREV = "#16a34a"                       # Green 600 (Preview)
COLOR_PREV_HOVER = "#15803d"                 # Green 700
COLOR_ATT = ("#1d4ed8", "#2563eb")           # Deep Blue 700/600 (Attention/Aux)
COLOR_ATT_HOVER = ("#1e40af", "#1d4ed8")

# Button State Tokens
BTN_INACTIVE_BG = ("#e4e4e7", "#27272a")     # Inactive button background
BTN_INACTIVE_TEXT = ("#3f3f46", "#a1a1aa")   # Inactive button text
BTN_INACTIVE_HOVER = ("#d4d4d8", "#3f3f46")  # Inactive button hover
BTN_OFF_ACTIVE = ("#cbd5e1", "#3f3f46")      # Active 'Off' button background
BTN_OFF_TEXT = ("#09090b", "#f4f4f5")        # Active 'Off' button text

COMBO_STYLE = {
    "fg_color": TEXTBOX_BG,
    "border_color": BORDER_COLOR,
    "button_color": BTN_INACTIVE_BG,
    "button_hover_color": BTN_INACTIVE_HOVER,
    "dropdown_fg_color": PANEL_COLOR,
    "dropdown_hover_color": HEADER_HOVER,
    "dropdown_text_color": TEXT_PRIMARY,
    "text_color": TEXT_PRIMARY,
}
CHECK_STYLE = {
    "fg_color": ACCENT_COLOR,
    "hover_color": ACCENT_HOVER,
    "border_color": BORDER_COLOR,
    "checkmark_color": ACCENT_TEXT,
    "text_color": TEXT_PRIMARY,
}

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

def apply_windows_titlebar_theme(window, dark_mode=True, bg_hex=None, text_hex=None, border_hex=None):
    """ Customizes the native Windows 10/11 system titlebar (DWM) """
    if sys.platform != "win32":
        return
    try:
        import ctypes
        window.update_idletasks()
        hwnd = ctypes.windll.user32.GetParent(window.winfo_id())
        if not hwnd:
            hwnd = window.winfo_id()

        # 1. Immersive Dark Mode for Windows 10 (1809+) & Windows 11
        DWMWA_USE_IMMERSIVE_DARK_MODE = 20
        DWMWA_USE_IMMERSIVE_DARK_MODE_OLD = 19
        val = ctypes.c_int(1 if dark_mode else 0)
        res = ctypes.windll.dwmapi.DwmSetWindowAttribute(
            hwnd, DWMWA_USE_IMMERSIVE_DARK_MODE, ctypes.byref(val), ctypes.sizeof(val)
        )
        if res != 0:
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd, DWMWA_USE_IMMERSIVE_DARK_MODE_OLD, ctypes.byref(val), ctypes.sizeof(val)
            )

        # 2. Windows 11 Custom Titlebar Colors
        def hex_to_dword(h):
            h = h.lstrip("#")
            if len(h) == 6:
                r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
                return (b << 16) | (g << 8) | r
            return 0

        if bg_hex:
            DWMWA_CAPTION_COLOR = 35
            c_bg = ctypes.c_uint(hex_to_dword(bg_hex))
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd, DWMWA_CAPTION_COLOR, ctypes.byref(c_bg), ctypes.sizeof(c_bg)
            )
        if text_hex:
            DWMWA_TEXT_COLOR = 36
            c_txt = ctypes.c_uint(hex_to_dword(text_hex))
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd, DWMWA_TEXT_COLOR, ctypes.byref(c_txt), ctypes.sizeof(c_txt)
            )
        if border_hex:
            DWMWA_BORDER_COLOR = 34
            c_brd = ctypes.c_uint(hex_to_dword(border_hex))
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd, DWMWA_BORDER_COLOR, ctypes.byref(c_brd), ctypes.sizeof(c_brd)
            )
    except Exception:
        pass

class TallyApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("Tally Server Pro")
        self.geometry("1150x700")
        self.configure(fg_color=BG_COLOR)
        try:
            self.iconbitmap(resource_path("Tally.ico"))
        except Exception:
            pass
        self.remotedisplay_radio_var = ctk.IntVar(self, value=0)
        self._auto_scrollbars = []

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
        self.atem_client = None
        self.tsl_sender = None
        self.roland_client = None
        self.osc_bridge = None
        self.serial_driver = None
        
        self.is_server_running = False
        self.is_vmix_connected = False
        self.is_obs_connected = False
        self.is_atem_connected = False
        self.is_tsl_active = False
        self.is_roland_connected = False
        self.is_osc_active = False
        self.is_serial_active = False
        
        # --- PERSISTENT VARS ---
        self.var_save_on_exit = ctk.BooleanVar(value=True)
        self.var_auto_server = ctk.BooleanVar(value=False)
        self.var_auto_vmix = ctk.BooleanVar(value=False)
        self.var_auto_obs = ctk.BooleanVar(value=False)
        self.var_auto_atem = ctk.BooleanVar(value=False)
        self.var_auto_tsl = ctk.BooleanVar(value=False)
        self.var_auto_roland = ctk.BooleanVar(value=False)
        self.var_auto_osc = ctk.BooleanVar(value=False)
        self.var_auto_serial = ctk.BooleanVar(value=False)
        self.var_touch_mode = ctk.BooleanVar(value=False)
        self.var_save_window = ctk.BooleanVar(value=True)
        self.var_remotedisplay_mode = ctk.BooleanVar(value=False)
        self.var_auto_web_tally = ctk.BooleanVar(value=False)
        self.var_obs_match_type = ctk.StringVar(value="Automatico")
        self.var_theme = ctk.StringVar(value="Dark")
        
        # --- WINDOW STATE PERSISTENCE ---
        self.last_w = 1150
        self.last_h = 700
        self.window_state = "normal"
        self.settings_w = 780
        self.settings_h = 560
        self.bind("<Configure>", self._on_configure)
        
        # --- WEB TALLY STATE ---
        # Initialize Flask with a static folder for local assets (Offline Support)
        # Use resource_path to find the bundled assets in PyInstaller EXE
        self.web_tally_app = Flask(__name__, static_folder=resource_path('static'))
        # Defer initialization to avoid crash at startup
        self.socketio = None
        self.is_web_server_active = False # New flag
        self.web_bind_error = False
        self.web_clients = {} # sid -> cam_index (0-7)
        self.active_cam_ids = set()
        self._settings_win = None
        self._help_win = None
        
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
        self.apply_titlebar()
        self.after(1000, self._poll_connection_statuses)
        
        # Mandatory UI refresh to prevent black screens on some systems
        self.update()


    def _on_configure(self, event):
        if event.widget == self:
            try:
                st = self.state()
                if st == "normal":
                    w = self.winfo_width()
                    h = self.winfo_height()
                    if w > 200 and h > 200:
                        self.last_w = w
                        self.last_h = h
            except Exception:
                pass

    def apply_titlebar(self):
        is_dark = ctk.get_appearance_mode() == "Dark"
        bg_hex = "#121214" if is_dark else "#e4e4e7"
        text_hex = "#f4f4f5" if is_dark else "#09090b"
        border_hex = "#27272a" if is_dark else "#cbd5e1"
        self.after(100, lambda: apply_windows_titlebar_theme(self, dark_mode=is_dark, bg_hex=bg_hex, text_hex=text_hex, border_hex=border_hex))


    def setup_ui(self):
        # 1. TOP HEADER
        self.header = ctk.CTkFrame(self, fg_color=HEADER_BG, height=60, corner_radius=0)
        self.header.pack(fill="x", side="top")
        
        self.lbl_header = ctk.CTkLabel(self.header, text="📡 Tally Server Pro", 
                                     font=ctk.CTkFont(size=20, weight="bold"), text_color=TEXT_PRIMARY)
        self.lbl_header.pack(side="left", padx=(20, 10), pady=10)
        self.broadcast_scheduled = False

        local_ip = self.get_local_ip()
        self.lbl_lan_ip = ctk.CTkLabel(
            self.header,
            text=f"🖧 LAN: {local_ip}",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=SUBTEXT_COLOR,
            fg_color=PANEL_COLOR,
            corner_radius=6,
            padx=10,
            pady=4,
        )
        self.lbl_lan_ip.pack(side="left", padx=6, pady=10)

        self.btn_settings = ctk.CTkButton(self.header, text="⚙️ Settings", width=100, 
                                        command=self.open_settings_menu,
                                        fg_color="transparent", hover_color=HEADER_HOVER, text_color=TEXT_PRIMARY)
        self.btn_settings.pack(side="right", padx=10)

        self.btn_theme_toggle = ctk.CTkButton(self.header, text="🌓 Theme", width=80,
                                             command=self.toggle_theme_mode,
                                             fg_color="transparent", hover_color=HEADER_HOVER, text_color=TEXT_PRIMARY)
        self.btn_theme_toggle.pack(side="right", padx=5)

        self.btn_help = ctk.CTkButton(self.header, text="❓ Help", width=80, 
                                     command=self.open_help_menu,
                                     fg_color="transparent", hover_color=HEADER_HOVER, text_color=TEXT_PRIMARY)
        self.btn_help.pack(side="right", padx=5)

        self.btn_qr_header = ctk.CTkButton(self.header, text="📱 QR Code", width=95,
                                          command=self.open_qr_window,
                                          fg_color="transparent", hover_color=HEADER_HOVER, text_color=TEXT_PRIMARY)
        self.btn_qr_header.pack(side="right", padx=5)

        # 1b. TOP COMPACT STATUS BAR (Frameless horizontal labels colored by live status)
        self.status_overview_rows = {}
        self.status_chips_order = []
        self.card_to_status_key = {}

        self.status_bar_frame = ctk.CTkFrame(
            self, fg_color=PANEL_COLOR, border_width=1, border_color=BORDER_COLOR, corner_radius=8
        )
        self.status_bar_frame.pack(fill="x", side="top", padx=20, pady=(8, 0))

        ctk.CTkLabel(
            self.status_bar_frame, text="⚡ Status:",
            font=ctk.CTkFont(size=11, weight="bold"), text_color=SUBTEXT_COLOR
        ).pack(side="left", padx=(10, 4), pady=4)

        self.status_chips_container = ctk.CTkFrame(self.status_bar_frame, fg_color="transparent")
        self.status_chips_container.pack(side="left", fill="x", expand=True, padx=(2, 8), pady=2)

        overview_defs = [
            ("server", "ATEM Server", "ATEM Tally Server"),
            ("web", "Web Tally", "ATEM Tally Server"),
            ("atem", "ATEM Switcher", "ATEM Switcher (Input)"),
            ("vmix", "vMix", "vMix Integration"),
            ("obs", "OBS", "OBS Integration"),
            ("roland", "Roland", "Roland Switcher (Input)"),
            ("tsl", "TSL", "Hollyland / TSL UMD (Output)"),
            ("osc", "OSC", "OSC Universal Bridge (In/Out)"),
            ("serial", "Serial", "USB Serial & Relays (Output)"),
            ("remotedisplay", "Remote I2C", "Remote Displays (I2C)"),
        ]
        for key, disp_name, target_module in overview_defs:
            lbl_name = ctk.CTkLabel(
                self.status_chips_container, text=f"● {disp_name}",
                font=ctk.CTkFont(size=11, weight="bold"),
                text_color=SUBTEXT_COLOR, cursor="hand2"
            )
            lbl_name.bind("<Button-1>", lambda _e, m=target_module: self.select_left_module(m))
            visible = (key != "remotedisplay")
            if visible:
                lbl_name.pack(side="left", padx=(5, 7), pady=3)
            self.status_overview_rows[key] = {
                "name_lbl": lbl_name,
                "target": target_module,
                "visible": visible,
            }
            self.status_chips_order.append(key)

        # 2. MAIN CONTAINER
        self.main_container = ctk.CTkFrame(self, fg_color="transparent")
        self.main_container.pack(fill="both", expand=True, padx=20, pady=10)
        
        self.main_container.grid_columnconfigure(0, weight=0, minsize=380)
        self.main_container.grid_columnconfigure(1, weight=1)
        self.main_container.grid_rowconfigure(0, weight=1)

        # --- LEFT COL: DROPDOWN SERVER CONFIG (WITH INLINE REMOTE DISPLAYS) + ACTIVE SERVER ---
        self.left_col = ctk.CTkScrollableFrame(self.main_container, fg_color="transparent")
        self.left_col.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        self.enable_auto_scrollbar(self.left_col)

        # 0. Module Filter + Individual Configuration Dropdown + Inline Remote Displays (I2C)
        self.selector_card = ctk.CTkFrame(
            self.left_col, fg_color=CARD_LEFT, border_width=1, border_color=BORDER_COLOR, corner_radius=8
        )
        self.selector_card.pack(fill="x", padx=10, pady=(4, 6))

        self.left_filter = ctk.CTkSegmentedButton(
            self.selector_card,
            values=["All", "Inputs", "Outputs"],
            command=self.filter_left_cards,
            fg_color=("#e4e4e7", "#121214"),
            selected_color=("#d4d4d8", "#3f3f46"),
            selected_hover_color=("#cbd5e1", "#52525b"),
            unselected_color=("#f4f4f5", "#18181b"),
            unselected_hover_color=HEADER_HOVER,
            text_color=TEXT_PRIMARY,
        )
        self.left_filter.set("All")
        self.left_filter.pack(fill="x", padx=10, pady=(8, 6))

        ctk.CTkLabel(
            self.selector_card, text="Configure Server / Function:",
            font=ctk.CTkFont(size=11, weight="bold"), text_color=SUBTEXT_COLOR, anchor="w"
        ).pack(fill="x", padx=10, pady=(0, 3))

        self.var_selected_left_module = ctk.StringVar(value="ATEM Tally Server")
        self.server_selector_dropdown = ctk.CTkOptionMenu(
            self.selector_card,
            values=["ATEM Tally Server"],
            variable=self.var_selected_left_module,
            command=self._show_selected_left_card,
            fg_color=ACCENT_COLOR,
            button_color=ACCENT_COLOR,
            button_hover_color=ACCENT_HOVER,
            text_color=ACCENT_TEXT,
            dropdown_fg_color=PANEL_COLOR,
            dropdown_hover_color=HEADER_HOVER,
            dropdown_text_color=TEXT_PRIMARY,
        )
        self.server_selector_dropdown.pack(fill="x", padx=10, pady=(0, 8))

        # Inline Remote Display (I2C) section directly inside selector_card below dropdown
        self.remotedisplay_card = ctk.CTkFrame(self.selector_card, fg_color="transparent")
        ctk.CTkFrame(self.remotedisplay_card, fg_color=BORDER_COLOR, height=1).pack(fill="x", padx=10, pady=(2, 6))

        rd_hdr = ctk.CTkFrame(self.remotedisplay_card, fg_color="transparent")
        rd_hdr.pack(pady=(2, 2), padx=10, fill="x")
        ctk.CTkLabel(
            rd_hdr, text="Remote Displays (I2C)",
            font=ctk.CTkFont(size=12, weight="bold"), text_color=ACCENT_COLOR
        ).pack(side="left")
        self.remotedisplay_card.status_lbl = ctk.CTkLabel(
            rd_hdr, text="● Idle",
            font=ctk.CTkFont(size=11, weight="bold"), text_color=SUBTEXT_COLOR
        )
        self.remotedisplay_card.status_lbl.pack(side="right")

        row_remotedisplay_sel = self.create_input_row(self.remotedisplay_card, "Target Cam:")
        self.combo_remotedisplay_target = ctk.CTkComboBox(row_remotedisplay_sel, values=["ALL"] + [f"Cam {i+1}" for i in range(41)], 
                                                         width=120, command=self.on_remotedisplay_target_changed, **COMBO_STYLE)
        self.combo_remotedisplay_target.pack(side="right")
        
        modes = [("OFF", 0), ("Show IP", 2), ("Tally Name", 3), ("WiFi", 4), ("SYS Info", 5), ("Message", 6)]
        radio_f = ctk.CTkFrame(self.remotedisplay_card, fg_color="transparent")
        radio_f.pack(pady=(4, 4), padx=10, fill="x")
        
        for i, (text, val) in enumerate(modes):
            r = ctk.CTkRadioButton(radio_f, text=text, variable=self.remotedisplay_radio_var, value=val, 
                                   font=ctk.CTkFont(size=10), command=self.send_remotedisplay_command,
                                   fg_color=ACCENT_COLOR, hover_color=ACCENT_HOVER, border_color=BORDER_COLOR, text_color=TEXT_PRIMARY)
            r.grid(row=i//3, column=i%3, sticky="w", pady=2, padx=5)
            
        msg_f = ctk.CTkFrame(self.remotedisplay_card, fg_color="transparent")
        msg_f.pack(pady=(4, 8), padx=10, fill="x")
        self.entry_remotedisplay_msg = ctk.CTkEntry(msg_f, placeholder_text="Enter Message...", height=35)
        self.entry_remotedisplay_msg.pack(side="left", expand=True, fill="x", padx=(0,5))
        self.btn_remotedisplay_send = ctk.CTkButton(msg_f, text="SEND ➤", width=80, height=35, 
                                          font=ctk.CTkFont(size=12, weight="bold"),
                                          fg_color="#10b981", hover_color="#059669", text_color="#ffffff",
                                          command=self.send_remotedisplay_command,
                                          state="disabled")
        self.btn_remotedisplay_send.pack(side="right")

        # 1. Dedicated slot for the active server/integration card selected in dropdown
        self.active_server_slot = ctk.CTkFrame(self.left_col, fg_color="transparent")
        self.active_server_slot.pack(fill="x")

        # 2. Tally Server
        self.server_card = self.create_card(self.active_server_slot, "ATEM Tally Server", show_status=True)
        row_server = self.create_input_row(self.server_card, "UDP SYS Port:")
        self.entry_port = ctk.CTkEntry(row_server, width=80)
        self.entry_port.insert(0, "9910")
        self.entry_port.pack(side="right")
        self.btn_toggle_server = ctk.CTkButton(self.server_card, text="Start Server", command=self.toggle_server, height=35,
                                              fg_color=ACCENT_COLOR, hover_color=ACCENT_HOVER, text_color=ACCENT_TEXT)
        self.btn_toggle_server.pack(pady=(10, 15), padx=10, fill="x")

        # Nested Web Tally Controls (No Title)
        row_web = self.create_input_row(self.server_card, "Web Port:")
        self.entry_web_port = ctk.CTkEntry(row_web, width=80)
        self.entry_web_port.insert(0, "8080")
        self.entry_web_port.pack(side="right")
        self.btn_toggle_web_server = ctk.CTkButton(self.server_card, text="Start Web Tally", command=self.toggle_web_server, height=35,
                                                  fg_color=ACCENT_COLOR, hover_color=ACCENT_HOVER, text_color=ACCENT_TEXT)
        self.btn_toggle_web_server.pack(pady=(10, 5), padx=10, fill="x")
        
        self.lbl_web_status = ctk.CTkLabel(self.server_card, text="● Web Tally: Stopped", font=ctk.CTkFont(size=11), text_color=SUBTEXT_COLOR)
        self.lbl_web_status.pack(pady=(0, 10))

        # 3. ATEM Switcher (Hardware Input)
        self.atem_card = self.create_card(self.active_server_slot, "ATEM Switcher (Input)", show_status=True)
        row_atem_ip = self.create_input_row(self.atem_card, "Switcher IP:")
        self.entry_atem_host = ctk.CTkEntry(row_atem_ip, width=140)
        self.entry_atem_host.pack(side="right")
        self.btn_atem_connect = ctk.CTkButton(self.atem_card, text="Connect ATEM", command=self.toggle_atem, height=35,
                                             fg_color=ACCENT_COLOR, hover_color=ACCENT_HOVER, text_color=ACCENT_TEXT)
        self.btn_atem_connect.pack(pady=(10, 15), padx=10, fill="x")

        # 4. vMix
        self.vmix_card = self.create_card(self.active_server_slot, "vMix Integration", show_status=True)
        row_vmix_ip = self.create_input_row(self.vmix_card, "Server IP:")
        self.entry_vmix_host = ctk.CTkEntry(row_vmix_ip, width=140)
        self.entry_vmix_host.pack(side="right")
        
        row_vmix_port = self.create_input_row(self.vmix_card, "Tally Port:")
        self.entry_vmix_port = ctk.CTkEntry(row_vmix_port, width=80)
        self.entry_vmix_port.insert(0, "8099")
        self.entry_vmix_port.pack(side="right")
        
        self.btn_vmix_connect = ctk.CTkButton(self.vmix_card, text="Connect vMix", command=self.toggle_vmix, height=35,
                                             fg_color=ACCENT_COLOR, hover_color=ACCENT_HOVER, text_color=ACCENT_TEXT)
        self.btn_vmix_connect.pack(pady=(10, 15), padx=10, fill="x")

        # 5. OBS
        self.obs_card = self.create_card(self.active_server_slot, "OBS Integration", show_status=True)
        row_obs_ip = self.create_input_row(self.obs_card, "Server IP:")
        self.entry_obs_host = ctk.CTkEntry(row_obs_ip, width=140)
        self.entry_obs_host.pack(side="right")
        
        row_obs_port = self.create_input_row(self.obs_card, "OBS WebSocket Port:")
        self.entry_obs_port = ctk.CTkEntry(row_obs_port, width=80)
        self.entry_obs_port.insert(0, "4455")
        self.entry_obs_port.pack(side="right")
        
        row_obs_pass = self.create_input_row(self.obs_card, "OBS WebSocket Pass:")
        self.entry_obs_pass = ctk.CTkEntry(row_obs_pass, placeholder_text="Password", show="*", width=140)
        self.entry_obs_pass.pack(side="right")
        
        row_obs_match = self.create_input_row(self.obs_card, "OBS Cam Type:")
        self.combo_obs_match = ctk.CTkComboBox(row_obs_match, values=["Auto", "Scenes", "Video Sources"], width=140, **COMBO_STYLE)
        self.combo_obs_match.set("Auto")
        self.combo_obs_match.pack(side="right")
        
        self.btn_obs_connect = ctk.CTkButton(self.obs_card, text="Connect OBS", command=self.toggle_obs, height=35,
                                            fg_color=ACCENT_COLOR, hover_color=ACCENT_HOVER, text_color=ACCENT_TEXT)
        self.btn_obs_connect.pack(pady=(15, 15), padx=10, fill="x")

        # 6. Roland Switcher (Hardware Input)
        self.roland_card = self.create_card(self.active_server_slot, "Roland Switcher (Input)", show_status=True)
        row_roland_ip = self.create_input_row(self.roland_card, "Switcher IP:")
        self.entry_roland_host = ctk.CTkEntry(row_roland_ip, width=140)
        self.entry_roland_host.pack(side="right")
        row_roland_port = self.create_input_row(self.roland_card, "TCP Port:")
        self.entry_roland_port = ctk.CTkEntry(row_roland_port, width=80)
        self.entry_roland_port.insert(0, "8023")
        self.entry_roland_port.pack(side="right")
        self.btn_roland_connect = ctk.CTkButton(self.roland_card, text="Connect Roland", command=self.toggle_roland, height=35,
                                               fg_color=ACCENT_COLOR, hover_color=ACCENT_HOVER, text_color=ACCENT_TEXT)
        self.btn_roland_connect.pack(pady=(10, 15), padx=10, fill="x")

        # 7. Hollyland / TSL UMD 3.1 (Output)
        self.tsl_card = self.create_card(self.active_server_slot, "Hollyland / TSL UMD (Output)", show_status=True)
        row_tsl_ip = self.create_input_row(self.tsl_card, "Target IP:")
        self.entry_tsl_host = ctk.CTkEntry(row_tsl_ip, width=140)
        self.entry_tsl_host.insert(0, "255.255.255.255")
        self.entry_tsl_host.pack(side="right")
        row_tsl_port = self.create_input_row(self.tsl_card, "TSL Port:")
        self.entry_tsl_port = ctk.CTkEntry(row_tsl_port, width=80)
        self.entry_tsl_port.insert(0, "8900")
        self.entry_tsl_port.pack(side="right")
        self.btn_tsl_toggle = ctk.CTkButton(self.tsl_card, text="Enable TSL 3.1 (Hollyland)", command=self.toggle_tsl, height=35,
                                           fg_color=ACCENT_COLOR, hover_color=ACCENT_HOVER, text_color=ACCENT_TEXT)
        self.btn_tsl_toggle.pack(pady=(10, 15), padx=10, fill="x")

        # 8. OSC Universal Bridge (In/Out)
        self.osc_card = self.create_card(self.active_server_slot, "OSC Universal Bridge (In/Out)", show_status=True)
        row_osc_ip = self.create_input_row(self.osc_card, "Target IP:")
        self.entry_osc_host = ctk.CTkEntry(row_osc_ip, width=140)
        self.entry_osc_host.insert(0, "255.255.255.255")
        self.entry_osc_host.pack(side="right")
        row_osc_send = self.create_input_row(self.osc_card, "Send Port:")
        self.entry_osc_port = ctk.CTkEntry(row_osc_send, width=80)
        self.entry_osc_port.insert(0, "9000")
        self.entry_osc_port.pack(side="right")
        row_osc_listen = self.create_input_row(self.osc_card, "Listen Port:")
        self.entry_osc_listen = ctk.CTkEntry(row_osc_listen, width=80)
        self.entry_osc_listen.insert(0, "8000")
        self.entry_osc_listen.pack(side="right")
        self.btn_osc_toggle = ctk.CTkButton(self.osc_card, text="Enable OSC Bridge", command=self.toggle_osc, height=35,
                                           fg_color=ACCENT_COLOR, hover_color=ACCENT_HOVER, text_color=ACCENT_TEXT)
        self.btn_osc_toggle.pack(pady=(10, 15), padx=10, fill="x")

        # 9. USB Serial / Relay (Output)
        self.serial_card = self.create_card(self.active_server_slot, "USB Serial & Relays (Output)", show_status=True)
        row_serial_port = self.create_input_row(self.serial_card, "COM Port:")
        avail_ports = SerialTallyDriver.get_available_ports()
        self.btn_refresh_serial = ctk.CTkButton(
            row_serial_port, text="🔄", width=30, height=28,
            fg_color=BTN_INACTIVE_BG, text_color=TEXT_PRIMARY, hover_color=BTN_INACTIVE_HOVER,
            command=self.refresh_serial_ports
        )
        self.btn_refresh_serial.pack(side="right", padx=(4, 0))
        self.combo_serial_port = ctk.CTkComboBox(row_serial_port, values=avail_ports, width=100, **COMBO_STYLE)
        self.combo_serial_port.set(avail_ports[0])
        self.combo_serial_port.pack(side="right")
        row_serial_proto = self.create_input_row(self.serial_card, "Protocol:")
        self.combo_serial_proto = ctk.CTkComboBox(row_serial_proto, values=["Arduino", "USB_Relay"], width=120, **COMBO_STYLE)
        self.combo_serial_proto.set("Arduino")
        self.combo_serial_proto.pack(side="right")
        self.btn_serial_toggle = ctk.CTkButton(self.serial_card, text="Enable USB Serial", command=self.toggle_serial, height=35,
                                              fg_color=ACCENT_COLOR, hover_color=ACCENT_HOVER, text_color=ACCENT_TEXT)
        self.btn_serial_toggle.pack(pady=(10, 15), padx=10, fill="x")

        self.left_cards_order = [
            ("ATEM Tally Server", self.server_card, "Outputs", "server"),
            ("ATEM Switcher (Input)", self.atem_card, "Inputs", "atem"),
            ("vMix Integration", self.vmix_card, "Inputs", "vmix"),
            ("OBS Integration", self.obs_card, "Inputs", "obs"),
            ("Roland Switcher (Input)", self.roland_card, "Inputs", "roland"),
            ("Hollyland / TSL UMD (Output)", self.tsl_card, "Outputs", "tsl"),
            ("OSC Universal Bridge (In/Out)", self.osc_card, "Outputs", "osc"),
            ("USB Serial & Relays (Output)", self.serial_card, "Outputs", "serial"),
        ]
        self.left_module_map = {name: card for name, card, _, _ in self.left_cards_order}
        self.card_to_status_key = {card: key for _, card, _, key in self.left_cards_order}
        self.card_to_status_key[self.remotedisplay_card] = "remotedisplay"
        self.filter_left_cards("All")

        # --- RIGHT COL: MONITORING ---
        self.right_col = ctk.CTkFrame(self.main_container, fg_color=PANEL_COLOR, border_width=1, border_color=BORDER_COLOR, corner_radius=8)
        self.right_col.grid(row=0, column=1, sticky="nsew")
        
        # Swap: Web Tally Clients Section Before Active Network Clients
        self.web_tally_card = self.create_card(self.right_col, "Web Tally Clients")
        self.web_tally_card.pack(fill="x", side="bottom", padx=20, pady=(0, 10))
        self.web_tally_list_f = ctk.CTkFrame(self.web_tally_card, fg_color="transparent")
        self.web_tally_list_f.pack(fill="x", padx=10, pady=5)
        self.lbl_no_web = ctk.CTkLabel(self.web_tally_list_f, text="No Web Clients Connected", font=ctk.CTkFont(size=11), text_color=SUBTEXT_COLOR)
        self.lbl_no_web.pack(pady=10)

        # Clients panel
        self.clients_card = self.create_card(self.right_col, "Active Network Clients")
        self.clients_card.pack(fill="x", side="bottom", padx=20, pady=(0, 20))
        self.txt_clients = ctk.CTkTextbox(self.clients_card, height=80, fg_color=TEXTBOX_BG, text_color=TEXT_PRIMARY, border_width=1, border_color=BORDER_COLOR, font=("Consolas", 12))
        self.txt_clients.pack(fill="both", expand=True, padx=5, pady=5)
        self.txt_clients.configure(state="disabled")
        
        # Header area for Right Col
        self.right_header_frame = ctk.CTkFrame(self.right_col, fg_color="transparent")
        self.right_header_frame.pack(fill="x", padx=20, pady=(15, 5))
        
        ctk.CTkLabel(self.right_header_frame, text="🎥 TALLY CONTROL PANEL", 
                   font=ctk.CTkFont(size=16, weight="bold"), text_color=ACCENT_COLOR).pack(side="left")

        # Add Tally Button relocated OUTSIDE the table and AFTER the title
        self.btn_add_tally = ctk.CTkButton(self.right_header_frame, text="➕ Add Tally Light Row", 
                                        fg_color="transparent", border_width=1, border_color=ACCENT_COLOR,
                                        hover_color=HEADER_HOVER, text_color=TEXT_PRIMARY, command=self.on_click_add_row)
        self.btn_add_tally.pack(side="right")

        self.btn_clear_tally = ctk.CTkButton(self.right_header_frame, text="🧹 Clear All", width=100,
                                          fg_color="transparent", border_width=1, border_color=BORDER_COLOR,
                                          hover_color=HEADER_HOVER, text_color=TEXT_PRIMARY, command=self.clear_all_tallies)
        self.btn_clear_tally.pack(side="right", padx=(0, 8))

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
        
        ctk.CTkLabel(self.header_row, text="#", font=ctk.CTkFont(weight="bold"), text_color=TEXT_PRIMARY).grid(row=0, column=0)
        ctk.CTkLabel(self.header_row, text="Scene Name", font=ctk.CTkFont(weight="bold"), text_color=TEXT_PRIMARY, anchor="w").grid(row=0, column=1, padx=10, sticky="w")
        ctk.CTkLabel(self.header_row, text="Main Tally (LED 1)", font=ctk.CTkFont(weight="bold"), text_color=TEXT_PRIMARY).grid(row=0, column=2, sticky="nsew")
        ctk.CTkLabel(self.header_row, text="LED 2 RGB", font=ctk.CTkFont(weight="bold"), text_color=TEXT_PRIMARY).grid(row=0, column=3, sticky="nsew")
        ctk.CTkLabel(self.header_row, text="Status", font=ctk.CTkFont(weight="bold"), text_color=TEXT_PRIMARY).grid(row=0, column=4, sticky="nsew")
        ctk.CTkLabel(self.header_row, text="", width=40).grid(row=0, column=5) # Placeholder for trash bin alignment

        ctk.CTkFrame(self.table_container, height=1, fg_color=BORDER_COLOR).pack(fill="x", pady=5)

        # Scrollable container for rows
        self.rows_scroll = ctk.CTkScrollableFrame(self.table_container, fg_color="transparent")
        self.rows_scroll.pack(fill="both", expand=True)
        self.enable_auto_scrollbar(self.rows_scroll)

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

        row = ctk.CTkFrame(self.rows_frame, fg_color="transparent", border_width=0, corner_radius=6, height=45)
        row.pack(fill="x", pady=2)
        row.grid_columnconfigure(0, minsize=40)
        row.grid_columnconfigure(1, weight=1)
        row.grid_columnconfigure(2, minsize=280)
        row.grid_columnconfigure(3, minsize=140)
        row.grid_columnconfigure(4, minsize=120)
        row.grid_columnconfigure(5, minsize=40)
        
        self.tally_rows_widgets.append(row)
        
        ctk.CTkLabel(row, text=str(i+1), font=ctk.CTkFont(weight="bold"), text_color=TEXT_PRIMARY).grid(row=0, column=0)
        ent = ctk.CTkEntry(row, textvariable=self.tally_scene_vars[i], height=30)
        ent.grid(row=0, column=1, padx=5, sticky="ew")
        
        # LED 1 Buttons
        f1 = ctk.CTkFrame(row, fg_color="transparent")
        f1.grid(row=0, column=2)
        
        o_btn = ctk.CTkButton(f1, text="Off", width=60, height=30, fg_color=BTN_INACTIVE_BG, text_color=BTN_INACTIVE_TEXT, hover_color=BTN_INACTIVE_HOVER, command=lambda idx=i: self.set_led1_state(idx, "Off"))
        o_btn.pack(side="left", padx=2)
        p_btn = ctk.CTkButton(f1, text="Prog", width=60, height=30, fg_color=BTN_INACTIVE_BG, text_color=BTN_INACTIVE_TEXT, hover_color=BTN_INACTIVE_HOVER, command=lambda idx=i: self.set_led1_state(idx, "Prog"))
        p_btn.pack(side="left", padx=2)
        v_btn = ctk.CTkButton(f1, text="Prev", width=60, height=30, fg_color=BTN_INACTIVE_BG, text_color=BTN_INACTIVE_TEXT, hover_color=BTN_INACTIVE_HOVER, command=lambda idx=i: self.set_led1_state(idx, "Prev"))
        v_btn.pack(side="left", padx=2)
        a_btn = ctk.CTkButton(f1, text="ATT", width=60, height=30, fg_color=BTN_INACTIVE_BG, text_color=BTN_INACTIVE_TEXT, hover_color=BTN_INACTIVE_HOVER, command=lambda idx=i: self.set_led1_state(idx, "ATT"))
        a_btn.pack(side="left", padx=2)

        self.tally_btn_led1_off.append(o_btn)
        self.tally_btn_led1_prog.append(p_btn)
        self.tally_btn_led1_prev.append(v_btn)
        self.tally_btn_led1_att.append(a_btn)
        
        f2 = ctk.CTkFrame(row, fg_color="transparent")
        f2.grid(row=0, column=3)
        
        r_btn = ctk.CTkButton(f2, text="R", width=30, height=30, fg_color=BTN_INACTIVE_BG, text_color=BTN_INACTIVE_TEXT, hover_color=BTN_INACTIVE_HOVER, command=lambda idx=i: self.toggle_led2_color(idx, "R"))
        r_btn.pack(side="left", padx=2)
        g_btn = ctk.CTkButton(f2, text="G", width=30, height=30, fg_color=BTN_INACTIVE_BG, text_color=BTN_INACTIVE_TEXT, hover_color=BTN_INACTIVE_HOVER, command=lambda idx=i: self.toggle_led2_color(idx, "G"))
        g_btn.pack(side="left", padx=2)
        b_btn = ctk.CTkButton(f2, text="B", width=30, height=30, fg_color=BTN_INACTIVE_BG, text_color=BTN_INACTIVE_TEXT, hover_color=BTN_INACTIVE_HOVER, command=lambda idx=i: self.toggle_led2_color(idx, "B"))
        b_btn.pack(side="left", padx=2)
        
        self.tally_btn_led2_r.append(r_btn)
        self.tally_btn_led2_g.append(g_btn)
        self.tally_btn_led2_b.append(b_btn)
        
        orb = ctk.CTkLabel(row, text="● Idle", text_color=SUBTEXT_COLOR, font=ctk.CTkFont(size=11))
        orb.grid(row=0, column=4)
        self.tally_status_orbs.append(orb)

        btn_del = ctk.CTkButton(row, text="✕", width=24, height=24, fg_color="#dc2626", 
                               hover_color="#991b1b", text_color="#ffffff", font=ctk.CTkFont(size=10, weight="bold"),
                               command=lambda idx=i: self.remove_tally_row(idx))
        btn_del.grid(row=0, column=5, padx=5, sticky="e")
        
        self.current_rows_count += 1
        
        # CRITICAL: Re-evaluate button colors for the newly rendered row
        self.update_led1_ui_buttons(i)
        self.update_led2_ui_buttons(i)
        self.check_scrollbar()

    def enable_auto_scrollbar(self, scroll_frame):
        """Show a CTkScrollableFrame scrollbar only when content overflows its viewport."""
        if scroll_frame is None:
            return
        registry = getattr(self, "_auto_scrollbars", None)
        if registry is None:
            registry = []
            self._auto_scrollbars = registry
        self._auto_scrollbars = [sf for sf in registry if sf.winfo_exists()]
        if scroll_frame not in self._auto_scrollbars:
            self._auto_scrollbars.append(scroll_frame)

        scroll_frame._auto_sb_after_id = None
        scroll_frame._syncing_scrollbar = False
        canvas = scroll_frame._parent_canvas
        sb = scroll_frame._scrollbar
        parent_frame = scroll_frame._parent_frame

        def _on_yscroll(first, last, sf=scroll_frame, bar=sb):
            bar.set(first, last)
            if getattr(sf, "_syncing_scrollbar", False):
                return
            try:
                f_val = float(first)
                l_val = float(last)
            except (TypeError, ValueError):
                return
            overflows = (f_val > 0.0001) or (l_val < 0.9999)
            if overflows != bool(bar.grid_info()):
                self._schedule_scrollbar_sync(sf, delay=20)

        canvas.configure(yscrollcommand=_on_yscroll)

        for widget in (scroll_frame, canvas, parent_frame):
            widget.bind("<Configure>", lambda _e, sf=scroll_frame: self._schedule_scrollbar_sync(sf, delay=20), add="+")
        parent_frame.bind("<Map>", lambda _e, sf=scroll_frame: self._schedule_scrollbar_sync(sf, delay=40), add="+")

        self._schedule_scrollbar_sync(scroll_frame, delay=60)

    def _schedule_scrollbar_sync(self, scroll_frame, delay=20):
        try:
            if scroll_frame is None or not scroll_frame.winfo_exists():
                return
            after_id = getattr(scroll_frame, "_auto_sb_after_id", None)
            if after_id is not None:
                try:
                    scroll_frame.after_cancel(after_id)
                except Exception:
                    pass
            scroll_frame._auto_sb_after_id = scroll_frame.after(
                delay, lambda sf=scroll_frame: self._sync_scrollbar(sf)
            )
        except Exception:
            pass

    def _sync_scrollbar(self, scroll_frame):
        try:
            if scroll_frame is None or not scroll_frame.winfo_exists():
                return
            scroll_frame._auto_sb_after_id = None
            canvas = scroll_frame._parent_canvas
            sb = scroll_frame._scrollbar
            if not canvas.winfo_exists() or not sb.winfo_exists():
                return

            canvas_h = canvas.winfo_height()
            if canvas_h <= 1:
                self._schedule_scrollbar_sync(scroll_frame, delay=60)
                return

            content_h = scroll_frame.winfo_reqheight()
            content_w = max(canvas.winfo_width(), scroll_frame.winfo_reqwidth(), 1)
            scroll_region = (0, 0, content_w, max(content_h, 1))

            scroll_frame._syncing_scrollbar = True
            try:
                if getattr(scroll_frame, "_last_scrollregion", None) != scroll_region:
                    canvas.configure(scrollregion=scroll_region)
                    scroll_frame._last_scrollregion = scroll_region

                needs_scroll = content_h > (canvas_h + 2)
                if needs_scroll:
                    if not sb.grid_info():
                        sb.grid()
                else:
                    if sb.grid_info():
                        sb.grid_remove()
                    try:
                        if canvas.yview()[0] > 0.0:
                            canvas.yview_moveto(0.0)
                    except Exception:
                        pass
            finally:
                scroll_frame._syncing_scrollbar = False
        except Exception:
            pass

    def _sync_all_scrollbars(self, delay=25):
        registry = getattr(self, "_auto_scrollbars", None)
        if not registry:
            return
        alive = []
        for sf in registry:
            try:
                if sf is not None and sf.winfo_exists():
                    alive.append(sf)
                    self._schedule_scrollbar_sync(sf, delay=delay)
            except Exception:
                pass
        self._auto_scrollbars = alive

    def check_scrollbar(self):
        if hasattr(self, "rows_scroll"):
            self._schedule_scrollbar_sync(self.rows_scroll, delay=20)

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
                self.update_led2_ui_buttons(i)

            self.btn_add_tally.configure(state="normal", text="➕ Add Tally Light Row")
            self.check_scrollbar()
            self.update_client_list()
            self.broadcast_all_tally()
            self.save_config()
        except Exception as e:
            print(f"REBUILD ERROR: {e}")

    def clear_all_tallies(self):
        for i in range(self.current_rows_count):
            self.tally_vars_led1[i].set("Off")
            self.tally_vars_led2_r[i].set(False)
            self.tally_vars_led2_g[i].set(False)
            self.tally_vars_led2_b[i].set(False)
            self.update_led1_ui_buttons(i)
            self.update_led2_ui_buttons(i)
        self.broadcast_all_tally()

    def create_card(self, parent, title, show_status=False):
        card_bg = CARD_LEFT if parent in (self.left_col, getattr(self, "active_server_slot", None)) else CARD_RIGHT
        card = ctk.CTkFrame(parent, fg_color=card_bg, border_width=1, border_color=BORDER_COLOR, corner_radius=8)
        card.pack(fill="x", padx=10, pady=8)
        if show_status:
            hdr = ctk.CTkFrame(card, fg_color="transparent")
            hdr.pack(pady=(8, 2), padx=12, fill="x")
            ctk.CTkLabel(hdr, text=title, font=ctk.CTkFont(size=12, weight="bold"), text_color=ACCENT_COLOR).pack(side="left")
            card.status_lbl = ctk.CTkLabel(hdr, text="● Idle", font=ctk.CTkFont(size=11, weight="bold"), text_color=SUBTEXT_COLOR)
            card.status_lbl.pack(side="right")
        else:
            ctk.CTkLabel(card, text=title, font=ctk.CTkFont(size=12, weight="bold"), text_color=ACCENT_COLOR).pack(pady=(8, 2), padx=12, anchor="w")
        return card

    def set_card_status(self, card, text, color):
        if hasattr(card, "status_lbl"):
            card.status_lbl.configure(text=text, text_color=color)
        key = getattr(self, "card_to_status_key", {}).get(card)
        if key and key in getattr(self, "status_overview_rows", {}):
            self.status_overview_rows[key]["name_lbl"].configure(text_color=color)

    def _set_web_status(self, full_text, color, short_text=None):
        if hasattr(self, "lbl_web_status"):
            self.lbl_web_status.configure(text=full_text, text_color=color)
        rows = getattr(self, "status_overview_rows", {})
        if "web" in rows:
            rows["web"]["name_lbl"].configure(text_color=color)

    def select_left_module(self, module_name):
        if not hasattr(self, "left_cards_order"):
            return
        if module_name == "Remote Displays (I2C)":
            if hasattr(self, "remotedisplay_card") and self.var_remotedisplay_mode.get():
                if self.remotedisplay_card.winfo_manager() != "pack":
                    self.remotedisplay_card.pack(fill="x", padx=0, pady=(0, 6))
            return
        cat = self.left_filter.get()
        visible_names = [
            name for name, _, grp, _ in self.left_cards_order
            if (cat == "All" or cat == grp)
        ]
        if module_name not in visible_names and cat != "All":
            self.left_filter.set("All")
            self.filter_left_cards("All")
        self.var_selected_left_module.set(module_name)
        self._show_selected_left_card(module_name)

    def _show_selected_left_card(self, selected_name=None):
        if not hasattr(self, "left_cards_order"):
            return
        name_to_show = selected_name or self.var_selected_left_module.get()
        target_card = getattr(self, "left_module_map", {}).get(name_to_show)
        for _, card, _, _ in self.left_cards_order:
            card.pack_forget()
        if target_card is not None:
            target_card.pack(fill="x", padx=10, pady=(2, 6))
        if hasattr(self, "left_col"):
            self._schedule_scrollbar_sync(self.left_col, delay=25)

    def filter_left_cards(self, category=None):
        if not hasattr(self, "left_cards_order"):
            return
        cat = category or self.left_filter.get()
        options = [
            name for name, _, grp, _ in self.left_cards_order
            if cat == "All" or cat == grp
        ]

        show_rd = bool(self.var_remotedisplay_mode.get())
        if hasattr(self, "remotedisplay_card"):
            if show_rd:
                if self.remotedisplay_card.winfo_manager() != "pack":
                    self.remotedisplay_card.pack(fill="x", padx=0, pady=(0, 6))
            else:
                self.remotedisplay_card.pack_forget()

        rd_chip = getattr(self, "status_overview_rows", {}).get("remotedisplay")
        if rd_chip:
            rd_chip["visible"] = show_rd
            if show_rd:
                if rd_chip["name_lbl"].winfo_manager() != "pack":
                    rd_chip["name_lbl"].pack(side="left", padx=(5, 7), pady=3)
            else:
                rd_chip["name_lbl"].pack_forget()

        if not options:
            options = ["ATEM Tally Server"]

        if hasattr(self, "server_selector_dropdown"):
            self.server_selector_dropdown.configure(values=options)
            current = self.var_selected_left_module.get()
            if current not in options:
                current = options[0]
                self.var_selected_left_module.set(current)
            self._show_selected_left_card(current)

    def refresh_serial_ports(self):
        avail_ports = SerialTallyDriver.get_available_ports()
        current = self.combo_serial_port.get()
        self.combo_serial_port.configure(values=avail_ports)
        if current in avail_ports:
            self.combo_serial_port.set(current)
        elif avail_ports:
            self.combo_serial_port.set(avail_ports[0])

    def create_input_row(self, parent, label):
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(pady=4, fill="x", padx=10)
        ctk.CTkLabel(row, text=label, text_color=SUBTEXT_COLOR).pack(side="left")
        return row

    def open_settings_menu(self):
        try:
            if getattr(self, "_settings_win", None) is not None and self._settings_win.winfo_exists():
                self._settings_win.lift()
                self._settings_win.focus_force()
                return
            import tkinter as tk
            win = tk.Toplevel(self) # Use standard Toplevel for stability
            self._settings_win = win
            win.title("Preferences & Tally Management")
            
            # Center and ensure positive coordinates
            off_x = max(0, self.winfo_x() + 50)
            off_y = max(0, self.winfo_y() + 50)
            
            settings_w = getattr(self, "settings_w", 780)
            settings_h = getattr(self, "settings_h", 560)
            win.geometry(f"{settings_w}x{settings_h}+{off_x}+{off_y}")
            win.minsize(780, 560)
            
            win.resizable(True, True)
            current_mode = ctk.get_appearance_mode()
            is_dark = current_mode == "Dark"
            win.configure(bg="#09090b" if is_dark else "#f4f4f5")
            try:
                win.iconbitmap(resource_path("Config.ico"))
            except Exception:
                pass
            win.transient(self)
            bg_hex = "#121214" if is_dark else "#e4e4e7"
            text_hex = "#f4f4f5" if is_dark else "#09090b"
            border_hex = "#27272a" if is_dark else "#cbd5e1"
            win.after(100, lambda: apply_windows_titlebar_theme(win, dark_mode=is_dark, bg_hex=bg_hex, text_hex=text_hex, border_hex=border_hex))
            
            # Use one big ctk frame as container
            main_container_f = ctk.CTkFrame(win, fg_color=BG_COLOR, corner_radius=0)
            main_container_f.pack(fill="both", expand=True)
            
            def on_settings_close():
                # Save geometry
                try:
                    self.settings_w = win.winfo_width()
                    self.settings_h = win.winfo_height()
                except Exception:
                    pass
                self._settings_win = None
                win.destroy()
                
            win.protocol("WM_DELETE_WINDOW", on_settings_close)
            
            # Pack Close button first at the bottom so it never gets squeezed
            close_btn = ctk.CTkButton(main_container_f, text="Close", fg_color=ACCENT_COLOR, hover_color=ACCENT_HOVER, text_color=ACCENT_TEXT, command=on_settings_close)
            close_btn.pack(side="bottom", pady=10)
            
            main_f = ctk.CTkFrame(main_container_f, fg_color="transparent")
            main_f.pack(side="top", fill="both", expand=True, padx=20, pady=10)
            
            # --- LEFT COL: PREFERENCES ---
            left_f = ctk.CTkFrame(main_f, fg_color=PANEL_COLOR, border_width=1, border_color=BORDER_COLOR, corner_radius=8)
            left_f.pack(side="left", fill="both", expand=True, padx=(0, 10))
            left_inner = ctk.CTkScrollableFrame(left_f, fg_color="transparent")
            left_inner.pack(fill="both", expand=True, padx=10, pady=10)
            self.enable_auto_scrollbar(left_inner)
            
            ctk.CTkLabel(left_inner, text="⚙️ Preferences", font=ctk.CTkFont(size=18, weight="bold"), text_color=TEXT_PRIMARY).pack(pady=10)
            ctk.CTkCheckBox(left_inner, text="Save Config on Exit", variable=self.var_save_on_exit, **CHECK_STYLE).pack(pady=5, padx=10, anchor="w")
            ctk.CTkCheckBox(left_inner, text="Save Window Sizes", variable=self.var_save_window, **CHECK_STYLE).pack(pady=5, padx=10, anchor="w")
            ctk.CTkCheckBox(left_inner, text="Enable Remote Displays", variable=self.var_remotedisplay_mode, command=self.toggle_remotedisplay_ui, **CHECK_STYLE).pack(pady=5, padx=10, anchor="w")
            ctk.CTkCheckBox(left_inner, text="Enable Touchscreen Mode", variable=self.var_touch_mode, command=self.apply_touch_scale, **CHECK_STYLE).pack(pady=5, padx=10, anchor="w")
            ctk.CTkCheckBox(left_inner, text="AutoStart Server", variable=self.var_auto_server, **CHECK_STYLE).pack(pady=5, padx=10, anchor="w")
            ctk.CTkCheckBox(left_inner, text="AutoStart WebTallys Server", variable=self.var_auto_web_tally, **CHECK_STYLE).pack(pady=5, padx=10, anchor="w")
            ctk.CTkCheckBox(left_inner, text="Auto Connect OBS", variable=self.var_auto_obs, **CHECK_STYLE).pack(pady=5, padx=10, anchor="w")
            ctk.CTkCheckBox(left_inner, text="Auto Connect vMix", variable=self.var_auto_vmix, **CHECK_STYLE).pack(pady=5, padx=10, anchor="w")
            ctk.CTkCheckBox(left_inner, text="Auto Connect ATEM Switcher", variable=self.var_auto_atem, **CHECK_STYLE).pack(pady=5, padx=10, anchor="w")
            ctk.CTkCheckBox(left_inner, text="Auto Connect Roland Switcher", variable=self.var_auto_roland, **CHECK_STYLE).pack(pady=5, padx=10, anchor="w")
            ctk.CTkCheckBox(left_inner, text="Auto Enable TSL 3.1 (Hollyland)", variable=self.var_auto_tsl, **CHECK_STYLE).pack(pady=5, padx=10, anchor="w")
            ctk.CTkCheckBox(left_inner, text="Auto Enable OSC Bridge", variable=self.var_auto_osc, **CHECK_STYLE).pack(pady=5, padx=10, anchor="w")
            ctk.CTkCheckBox(left_inner, text="Auto Enable USB Serial", variable=self.var_auto_serial, **CHECK_STYLE).pack(pady=5, padx=10, anchor="w")
            
            row_theme = ctk.CTkFrame(left_inner, fg_color="transparent")
            row_theme.pack(pady=8, padx=10, fill="x")
            ctk.CTkLabel(row_theme, text="UI Theme Mode:", text_color=TEXT_PRIMARY).pack(side="left")
            self.combo_theme = ctk.CTkComboBox(row_theme, values=["Dark", "Light", "System"], width=110, command=self.set_theme_mode, **COMBO_STYLE)
            self.combo_theme.set(self.var_theme.get())
            self.combo_theme.pack(side="right")
            
            ctk.CTkFrame(left_inner, fg_color=BORDER_COLOR, height=1).pack(fill="x", padx=10, pady=(10, 5))

            ctk.CTkLabel(left_inner, text="Version: V 1.0.2 Stable\nMax Capacity: up to 41 Tally Lights\n\nDeveloped by: Paulo Fernando", 
                          font=ctk.CTkFont(size=11), text_color=SUBTEXT_COLOR).pack(pady=20)
            # Qrcode button
            ctk.CTkButton(
                left_inner,
                text="📱 Web QR Code",
                height=35,
                fg_color=ACCENT_COLOR,
                hover_color=ACCENT_HOVER,
                text_color=ACCENT_TEXT,
                command=self.open_qr_window
            ).pack(pady=5, padx=10, fill="x")

            # --- RIGHT COL: TALLY MANAGEMENT ---
            right_f = ctk.CTkFrame(main_f, fg_color=PANEL_COLOR, border_width=1, border_color=BORDER_COLOR, corner_radius=8)
            right_f.pack(side="right", fill="both", expand=True)
            right_inner = ctk.CTkFrame(right_f, fg_color="transparent")
            right_inner.pack(fill="both", expand=True, padx=15, pady=15)
            
            ctk.CTkLabel(right_inner, text="📡 Tally Management", font=ctk.CTkFont(size=18, weight="bold"), text_color=TEXT_PRIMARY).pack(pady=10)
            
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
            
            self.combo_tally_selector = ctk.CTkComboBox(right_inner, values=self.tally_ips, width=200, command=self.on_tally_device_selected, **COMBO_STYLE)
            self.combo_tally_selector.pack(pady=10)
            
            self.info_tally_card = ctk.CTkFrame(right_inner, fg_color=TEXTBOX_BG, border_width=1, border_color=BORDER_COLOR, corner_radius=8)
            self.info_tally_card.pack(fill="both", expand=True, pady=10)
            
            self.lbl_tally_info = ctk.CTkLabel(self.info_tally_card, text="Select a Tally Light\nto view details", 
                                              font=ctk.CTkFont(size=12), justify="left", text_color=SUBTEXT_COLOR)
            self.lbl_tally_info.pack(padx=10, pady=20)
            
            btn_f = ctk.CTkFrame(right_inner, fg_color="transparent")
            btn_f.pack(fill="x", pady=10)
            
            # Centralize and swap buttons: Update Info Left, Firmware Update Right
            self.btn_refresh_tally = ctk.CTkButton(btn_f, text="Update Info", width=140, height=35, 
                                                   fg_color=PANEL_COLOR, text_color=TEXT_PRIMARY, border_width=1, border_color=BORDER_COLOR,
                                                   hover_color=HEADER_HOVER,
                                                   command=lambda: self.on_tally_device_selected(self.combo_tally_selector.get()))
            self.btn_refresh_tally.pack(side="left", expand=True, padx=5)

            self.btn_ota_update = ctk.CTkButton(btn_f, text="🚀 Firmware Update", fg_color="#10b981", hover_color="#059669", text_color="#ffffff", state="disabled",
                                               height=35, width=140, command=self.open_tally_ota_page)
            self.btn_ota_update.pack(side="left", expand=True, padx=5)
            
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
                        self.lbl_tally_info.configure(text=info, text_color=TEXT_PRIMARY, justify="left"),
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

    def open_qr_window(self):
        """Abre janela com QR Code do endereço Web Tally."""
        import tkinter as tk
        try:
            import qrcode
            # pyrefly: ignore [missing-import]
            from PIL import ImageTk
        except ImportError:
            import tkinter.messagebox as mb
            mb.showerror("Dependência ausente", 
                        "Instale 'qrcode[pil]' para usar esta função.\n\npip install qrcode[pil]")
            return

        local_ip = self.get_local_ip()
        web_port = self.entry_web_port.get() or "8080"
        url = f"http://{local_ip}:{web_port}"

        # --- Gera QR Code ---
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_M,
            box_size=8,
            border=4,
        )
        qr.add_data(url)
        qr.make(fit=True)
        img = qr.make_image(fill_color="#09090b", back_color="#ffffff")

        # --- Janela ---
        qr_win = tk.Toplevel(self)
        qr_win.title("Web Tally QR Code")
        current_mode = ctk.get_appearance_mode()
        is_dark = current_mode == "Dark"
        qr_win.configure(bg="#09090b" if is_dark else "#f4f4f5")
        qr_win.resizable(False, False)
        try:
            qr_win.iconbitmap(resource_path("Tally.ico"))
        except Exception:
            pass
        focused = self.focus_get()
        parent_win = focused.winfo_toplevel() if focused else self
        qr_win.transient(parent_win)
        bg_hex = "#121214" if is_dark else "#e4e4e7"
        text_hex = "#f4f4f5" if is_dark else "#09090b"
        border_hex = "#27272a" if is_dark else "#cbd5e1"
        qr_win.after(80, lambda: apply_windows_titlebar_theme(qr_win, dark_mode=is_dark, bg_hex=bg_hex, text_hex=text_hex, border_hex=border_hex))

        if parent_win is not self:
            try:
                parent_win.grab_release()
            except Exception:
                pass
        qr_win.grab_set()
        qr_win.lift()
        qr_win.focus_force()

        tk_img = ImageTk.PhotoImage(img)
        # Mantém referência para evitar garbage collection
        qr_win._qr_img_ref = tk_img

        frame = ctk.CTkFrame(qr_win, fg_color=PANEL_COLOR, border_width=1, border_color=BORDER_COLOR, corner_radius=12)
        frame.pack(padx=20, pady=20)

        ctk.CTkLabel(frame, text="Scan to connect",
                    font=ctk.CTkFont(size=14, weight="bold"),
                    text_color=TEXT_PRIMARY).pack(pady=(15, 5))

        lbl_url = ctk.CTkLabel(frame, text=url,
                                font=ctk.CTkFont(size=12),
                                text_color=ACCENT_COLOR)
        lbl_url.pack(pady=(0, 10))

        img_bg = "#18181b" if is_dark else "#ffffff"
        img_label = tk.Label(frame, image=tk_img, bg=img_bg, bd=0)
        img_label.pack(padx=20, pady=10)

        if not self.is_web_server_active:
            ctk.CTkLabel(frame, text="Web Tally is stopped",
                        font=ctk.CTkFont(size=11),
                        text_color="#f59e0b").pack(pady=(0, 5))
        
        def on_qr_close():
            try:
                qr_win.grab_release()
            except Exception:
                pass
            qr_win.destroy()
            # Devolve o foco ao parent se for Settings
            if parent_win is not self and parent_win.winfo_exists():
                try:
                    parent_win.lift()
                    parent_win.grab_set()
                    parent_win.focus_force()
                except Exception:
                    pass
        qr_win.protocol("WM_DELETE_WINDOW", on_qr_close)
        ctk.CTkButton(frame, text="Close", width=120, fg_color=ACCENT_COLOR, hover_color=ACCENT_HOVER, text_color=ACCENT_TEXT, command=on_qr_close).pack(pady=(5, 15))
            

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
                scene_names = [v.get() for v in self.tally_scene_vars]
                return render_template_string('''
                <!DOCTYPE html>
                <html>
                <head>
                    <title>Web Tally Light</title>
                    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no, viewport-fit=cover">
                    <!-- Local Socket.IO Library (True Offline Production Support) -->
                    <script src="/static/socket.io.min.js?v=4.7.2"></script>
                    <style>
                        body { margin: 0; padding: 0; background: #000; color: #fff; font-family: 'Segoe UI', sans-serif; overflow: hidden; height: 100vh; width: 100vw; }
                        #tally { width: 100%; height: 100%; display: flex; flex-direction: column; align-items: center; justify-content: center; transition: background 0.2s cubic-bezier(0.4, 0, 0.2, 1); position: relative; }
                        #cam-badge {
                            position: absolute;
                            top: calc(18px + env(safe-area-inset-top, 0px));
                            padding: 8px 18px;
                            border-radius: 999px;
                            background: rgba(0, 0, 0, 0.45);
                            backdrop-filter: blur(8px);
                            border: 1px solid rgba(255, 255, 255, 0.2);
                            font-size: 16px;
                            font-weight: 800;
                            letter-spacing: 1px;
                            text-transform: uppercase;
                            pointer-events: none;
                            max-width: 85vw;
                            white-space: nowrap;
                            overflow: hidden;
                            text-overflow: ellipsis;
                        }
                        #status { font-size: 15vw; font-weight: 900; text-transform: uppercase; letter-spacing: 5px; text-shadow: 0 5px 25px rgba(0,0,0,0.8); pointer-events: none; }
                        .prog { background: #dc2626 !important; box-shadow: inset 0 0 100px rgba(0,0,0,0.5); }
                        .prev { background: #16a34a !important; color: #fff !important; box-shadow: inset 0 0 100px rgba(0,0,0,0.5); }
                        .att { background: #1d4ed8 !important; box-shadow: inset 0 0 100px rgba(0,0,0,0.5); }
                        .off { background: #09090b !important; }
                        
                        /* Floating Action Button */
                        #toggle-config-btn {
                            position: absolute;
                            bottom: calc(20px + env(safe-area-inset-bottom, 0px));
                            right: 20px;
                            width: 56px;
                            height: 56px;
                            border-radius: 50%;
                            background: rgba(255, 255, 255, 0.15);
                            backdrop-filter: blur(10px);
                            border: 1px solid rgba(255, 255, 255, 0.25);
                            color: white;
                            font-size: 24px;
                            cursor: pointer;
                            display: flex;
                            align-items: center;
                            justify-content: center;
                            z-index: 100;
                            box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3);
                            transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
                            outline: none;
                        }
                        #toggle-config-btn:hover {
                            transform: scale(1.1);
                            background: rgba(255, 255, 255, 0.25);
                            box-shadow: 0 12px 40px rgba(0, 0, 0, 0.4);
                        }
                        #toggle-config-btn.open {
                            transform: scale(1.1) rotate(90deg);
                            background: rgba(255, 255, 255, 0.3);
                        }
                        #toggle-config-btn:active {
                            transform: scale(0.95);
                        }

                        /* Condensed Configuration Panel */
                        #config-panel {
                            position: absolute;
                            bottom: calc(90px + env(safe-area-inset-bottom, 0px));
                            right: 20px;
                            background: rgba(18, 18, 20, 0.95);
                            backdrop-filter: blur(15px);
                            border: 1px solid rgba(255, 255, 255, 0.12);
                            padding: 24px;
                            border-radius: 24px;
                            display: flex;
                            flex-direction: column;
                            align-items: center;
                            gap: 12px;
                            box-shadow: 0 20px 40px rgba(0, 0, 0, 0.5);
                            z-index: 99;
                            opacity: 0;
                            pointer-events: none;
                            transform: scale(0.9) translateY(20px);
                            transform-origin: bottom right;
                            transition: all 0.3s cubic-bezier(0.34, 1.56, 0.64, 1);
                            width: 290px;
                            box-sizing: border-box;
                        }
                        #config-panel.visible {
                            opacity: 1;
                            pointer-events: auto;
                            transform: scale(1) translateY(0);
                        }
                        #cam-info {
                            font-size: 20px;
                            font-weight: 800;
                            color: #f1f5f9;
                            letter-spacing: 0.5px;
                            text-align: center;
                        }
                        #socket-status {
                            font-size: 11px;
                            opacity: 0.9;
                            font-weight: bold;
                            font-family: monospace;
                            text-align: center;
                        }
                        #wakelock-status {
                            font-size: 10px;
                            color: #94a3b8;
                            font-family: monospace;
                        }
                        .divider {
                            width: 100%;
                            height: 1px;
                            background: rgba(255, 255, 255, 0.1);
                            margin: 4px 0;
                        }
                        select {
                            background: #18181b;
                            color: white;
                            border: 1px solid #3f3f46;
                            padding: 12px 15px;
                            font-size: 15px;
                            border-radius: 12px;
                            outline: none;
                            cursor: pointer;
                            width: 100%;
                            text-align-last: center;
                            box-sizing: border-box;
                        }
                        .btn-sync {
                            background: #f4f4f5;
                            color: #09090b;
                            border: none;
                            padding: 12px 15px;
                            border-radius: 12px;
                            font-size: 13px;
                            font-weight: 700;
                            cursor: pointer;
                            transition: 0.2s;
                            width: 100%;
                            box-sizing: border-box;
                        }
                        .btn-sync:active {
                            transform: scale(0.98);
                            background: #d4d4d8;
                        }
                        .btn-fs {
                            background: #27272a;
                            color: #e4e4e7;
                            border: 1px solid #3f3f46;
                            padding: 10px 15px;
                            border-radius: 12px;
                            font-size: 12px;
                            font-weight: 600;
                            cursor: pointer;
                            transition: 0.2s;
                            width: 100%;
                            box-sizing: border-box;
                        }
                        .btn-fs:active {
                            transform: scale(0.98);
                            background: #3f3f46;
                        }
                        .hint {
                            font-size: 10px;
                            color: #71717a;
                            text-transform: uppercase;
                            letter-spacing: 1px;
                            margin-top: 2px;
                        }

                        /* Responsive Design for Mobile Screen Center */
                        @media (max-width: 480px) {
                            #config-panel {
                                right: 15px;
                                left: 15px;
                                width: auto;
                                bottom: calc(130px + env(safe-area-inset-bottom, 0px));
                                transform-origin: bottom center;
                            }
                            #toggle-config-btn {
                                left: 50%;
                                right: auto;
                                margin-left: -28px;
                                bottom: calc(90px + env(safe-area-inset-bottom, 0px));
                            }
                        }
                    </style>
                </head>
                <body>
                    <div id="tally" class="off">
                        <div id="cam-badge">CAM 1</div>
                        <div id="status">OFF</div>
                        
                        <!-- Floating configuration toggle button -->
                        <button id="toggle-config-btn" onclick="toggleConfig()">⚙️</button>
                        
                        <!-- Floating Glassmorphic config overlay panel -->
                        <div id="config-panel">
                            <div id="cam-info">CAM 1</div>
                            <div id="socket-status">CONNECTING...</div>
                            <div id="wakelock-status">WAKE LOCK: PENDING</div>
                            <div class="divider"></div>
                            <select id="cam-num" onchange="updateCam()">
                                {% for i in range(1, 42) %}<option value="{{ i-1 }}">CAM {{ i }} — {{ scene_names[i-1] if i-1 < scene_names|length else ('Cam ' ~ i) }}</option>{% endfor %}
                            </select>
                            <button class="btn-sync" onclick="forceSync()">FORCE RE-SYNC</button>
                            <button class="btn-fs" onclick="toggleFullscreen()">⛶ FULLSCREEN</button>
                            <div class="hint">Tally Client</div>
                        </div>
                    </div>
                    <script>
                        var sceneNames = {{ scene_names | tojson }};
                        var wakeLock = null;

                        async function requestWakeLock() {
                            var wlEl = document.getElementById("wakelock-status");
                            if (!('wakeLock' in navigator)) {
                                wlEl.innerText = "WAKE LOCK: UNSUPPORTED";
                                return;
                            }
                            try {
                                wakeLock = await navigator.wakeLock.request('screen');
                                wlEl.innerText = "WAKE LOCK: ACTIVE";
                                wlEl.style.color = "#4ade80";
                                wakeLock.addEventListener('release', function() {
                                    wlEl.innerText = "WAKE LOCK: RELEASED";
                                    wlEl.style.color = "#fbbf24";
                                });
                            } catch (err) {
                                wlEl.innerText = "WAKE LOCK: TAP SCREEN";
                                wlEl.style.color = "#94a3b8";
                            }
                        }

                        document.addEventListener('visibilitychange', function() {
                            if (document.visibilityState === 'visible') {
                                requestWakeLock();
                            }
                        });
                        document.addEventListener('click', function() {
                            if (!wakeLock) requestWakeLock();
                        }, { passive: true });
                        requestWakeLock();

                        function toggleFullscreen() {
                            var doc = document.documentElement;
                            if (!document.fullscreenElement && !document.webkitFullscreenElement) {
                                if (doc.requestFullscreen) doc.requestFullscreen().catch(function(){});
                                else if (doc.webkitRequestFullscreen) doc.webkitRequestFullscreen();
                            } else {
                                if (document.exitFullscreen) document.exitFullscreen().catch(function(){});
                                else if (document.webkitExitFullscreen) document.webkitExitFullscreen();
                            }
                        }

                        // Toggle configuration panel visibility
                        function toggleConfig() {
                            var panel = document.getElementById("config-panel");
                            var btn = document.getElementById("toggle-config-btn");
                            var isOpen = panel.classList.toggle("visible");
                            btn.classList.toggle("open", isOpen);
                            btn.innerText = isOpen ? "✕" : "⚙️";
                        }

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
                        if (isNaN(camIdx) || camIdx < 0 || camIdx > 40) camIdx = 0;

                        function refreshCamLabels() {
                            var lbl = (sceneNames && sceneNames[camIdx]) ? sceneNames[camIdx] : ("Cam " + (camIdx + 1));
                            var txt = "CAM " + (camIdx + 1) + " • " + lbl;
                            document.getElementById("cam-info").innerText = txt;
                            document.getElementById("cam-badge").innerText = txt;
                        }

                        document.getElementById("cam-num").value = camIdx;
                        refreshCamLabels();

                        function updateCam() {
                            camIdx = parseInt(document.getElementById("cam-num").value);
                            refreshCamLabels();
                            document.getElementById("socket-status").innerText = "UPDATING CAM " + (camIdx + 1);
                            socket.emit('set_cam', {index: camIdx});
                            localStorage.setItem('web_tally_cam', camIdx);
                        }

                        function forceSync() {
                            document.getElementById("socket-status").innerText = "FORCE SYNCING...";
                            socket.emit('set_cam', {index: camIdx});
                            requestWakeLock();
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
                            if (data && typeof data.index === 'number' && data.label) {
                                sceneNames[data.index] = data.label;
                            }
                            if(data.index == camIdx) {
                                refreshCamLabels();
                                applyUpdate(data.flag);
                            }
                        });
                        socket.on('tally_bulk_update', function(data) {
                            if(!data || !data.updates) return;
                            data.updates.forEach(function(item) {
                                if (typeof item.index === 'number' && item.label) {
                                    sceneNames[item.index] = item.label;
                                    var opt = document.querySelector('#cam-num option[value="' + item.index + '"]');
                                    if (opt) opt.text = "CAM " + (item.index + 1) + " — " + item.label;
                                }
                                if(item.index == camIdx) {
                                    refreshCamLabels();
                                    applyUpdate(item.flag);
                                }
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
                            camIdx = parseInt(data.index);
                            document.getElementById("cam-num").value = camIdx;
                            localStorage.setItem('web_tally_cam', camIdx);
                            refreshCamLabels();
                        });
                    </script>
                </body>
                </html>
                ''', scene_names=scene_names)

            self.socketio.on_event('connect', self.handle_web_connect)
            self.socketio.on_event('disconnect', self.handle_web_disconnect)
            self.socketio.on_event('set_cam', self.handle_web_set_cam)
            self.socketio.on_event('heartbeat', self.handle_web_heartbeat)

    def start_web_server(self):
        self.web_bind_error = False
        try:
            raw_port = self.entry_web_port.get().strip()
            port = int(raw_port if raw_port else 8080)
            self.after(0, lambda p=port: self._set_web_status(f"● Web Tally: Starting (:{p})...", "#fbbf24", f"● Starting (:{p})..."))
            self.is_web_server_active = True
            self.socketio.run(self.web_tally_app, host='0.0.0.0', port=port, allow_unsafe_werkzeug=True)
        except Exception as e:
            self.web_bind_error = True
            self.is_web_server_active = False
            print(f"WEB TALLY ERROR: {e}")
            self.after(0, lambda: [
                self._set_web_status("● Web Tally: Bind Error", "#ef4444", "● Bind Error"),
                self.btn_toggle_web_server.configure(text="Start Web Tally", fg_color=ACCENT_COLOR, hover_color=ACCENT_HOVER, text_color=ACCENT_TEXT)
            ])
        finally:
            self.is_web_server_active = False
            if not self.web_bind_error:
                self.after(0, lambda: [
                    self._set_web_status("● Web Tally: Stopped", SUBTEXT_COLOR, "● Stopped"),
                    self.btn_toggle_web_server.configure(text="Start Web Tally", fg_color=ACCENT_COLOR, hover_color=ACCENT_HOVER, text_color=ACCENT_TEXT)
                ])

    def check_web_server_active(self):
        if self.is_web_server_active:
            port = self.entry_web_port.get().strip() or "8080"
            self._set_web_status(f"● Web Tally: Online (:{port})", "#10b981", f"● Online (:{port})")
        elif not self.web_bind_error:
            self._set_web_status("● Web Tally: Error/Stopped", "#ef4444", "● Error/Stopped")

    def get_local_ip(self):
        import socket
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception:
            return "127.0.0.1"

    def open_help_menu(self):
        if getattr(self, "_help_win", None) is not None and self._help_win.winfo_exists():
            self._help_win.lift()
            self._help_win.focus_force()
            return

        win = ctk.CTkToplevel(self)
        self._help_win = win
        win.title("Help & Information")
        win.geometry("560x600")
        win.minsize(480, 460)
        win.configure(fg_color=BG_COLOR)
        win.transient(self)
        try:
            win.after(200, lambda: win.iconbitmap(resource_path("Help.ico")))
        except Exception:
            pass
        is_dark = ctk.get_appearance_mode() == "Dark"
        bg_hex = "#121214" if is_dark else "#e4e4e7"
        text_hex = "#f4f4f5" if is_dark else "#09090b"
        border_hex = "#27272a" if is_dark else "#cbd5e1"
        win.after(100, lambda: apply_windows_titlebar_theme(win, dark_mode=is_dark, bg_hex=bg_hex, text_hex=text_hex, border_hex=border_hex))

        def on_help_close():
            self._help_win = None
            win.destroy()

        win.protocol("WM_DELETE_WINDOW", on_help_close)

        ctk.CTkLabel(win, text="❓ Help & Information", font=ctk.CTkFont(size=22, weight="bold"), text_color=TEXT_PRIMARY).pack(pady=(16, 8))

        ctk.CTkButton(win, text="Got it!", fg_color=ACCENT_COLOR, hover_color=ACCENT_HOVER, text_color=ACCENT_TEXT, command=on_help_close).pack(side="bottom", pady=14)

        scroll_body = ctk.CTkScrollableFrame(win, fg_color=PANEL_COLOR, border_width=1, border_color=BORDER_COLOR, corner_radius=8)
        scroll_body.pack(fill="both", expand=True, padx=20, pady=6)
        self.enable_auto_scrollbar(scroll_body)

        info_txt = (
            "🚀 Scene Matching (OBS / vMix):\n"
            "Ensure the 'Scene Name' in the table matches your OBS Scene or\n"
            "Source name (or select 'Auto', 'Scenes', or 'Video Sources').\n\n"
            "📡 Supported Protocols & Default Ports:\n"
            "• ATEM Tally Server (UDP Out - ESP8266/ESP32): 9910\n"
            "• Web Tally Server (TCP/HTTP/Socket.IO): 8080\n"
            "• Blackmagic ATEM Hardware Switcher (UDP In): 9910\n"
            "• OBS Studio WebSocket 5.x (TCP In): 4455\n"
            "• vMix Tally Bridge (TCP In): 8099\n"
            "• Roland Video Switcher (TCP In): 8023\n"
            "• Hollyland / TSL UMD v3.1 (UDP Out): 8900\n"
            "• OSC Universal Bridge (UDP Out / In): 9000 / 8000\n"
            "• USB Serial & Hardware Relays (COM Port): Arduino / USB_Relay\n\n"
            "🛡️ Firewall & Network Note:\n"
            "Allow TCP 8080 (Web Tally) and UDP 9910 / 8900 / 9000 / 8000\n"
            "in Windows Firewall for external devices on your LAN.\n\n"
            "📱 Mobile Web Tally Tips:\n"
            "Click '📱 QR Code' in the top bar to connect smartphones quickly.\n"
            "The mobile client keeps Screen Wake Lock active automatically.\n\n"
            "📝 Credits & Open Source Libraries:\n"
            "ATEM libraries for Arduino by SKAARHOJ:\n"
            "https://github.com/kasperskaarhoj/SKAARHOJ-Open-Engineering\n"
            "Based on ideas from ATEM_Wireless_Tally_Light & ATEM_tally_light_with_ESP8266:\n"
            "https://github.com/kalinchuk/ATEM_Wireless_Tally_Light\n"
            "https://github.com/AronHetLam/ATEM_tally_light_with_ESP8266"
        )

        lbl = ctk.CTkLabel(scroll_body, text=info_txt, font=ctk.CTkFont(size=13), justify="left", text_color=TEXT_PRIMARY, wraplength=470)
        lbl.pack(pady=14, padx=16, anchor="w")

    def toggle_remotedisplay_ui(self):
        self.filter_left_cards()

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
        self.update_idletasks()
        self._sync_all_scrollbars(delay=40)

    def on_repeater_detected(self, repeater_ip):
        # Immediate feedback for user when a repeater reports clients
        self.after(0, self.update_client_list)

    def toggle_server(self):
        if not self.is_server_running:
            try:
                self.server.port = int(self.entry_port.get().strip() or 9910)
                self.server.start()
                if not self.server.running:
                    self.is_server_running = False
                    self.set_card_status(self.server_card, "● Port Error", "#ef4444")
                    return
                self.is_server_running = True
                self.set_card_status(self.server_card, "● Online", "#10b981")
                self.btn_toggle_server.configure(text="Stop Server", fg_color="#dc2626", hover_color="#991b1b", text_color="#ffffff")
            except Exception as e:
                self.is_server_running = False
                self.set_card_status(self.server_card, "● Port Error", "#ef4444")
                print(f"SERVER START ERROR: {e}")
        else:
            self.server.stop()
            self.is_server_running = False
            self.set_card_status(self.server_card, "● Idle", SUBTEXT_COLOR)
            self.btn_toggle_server.configure(text="Start Server", fg_color=ACCENT_COLOR, hover_color=ACCENT_HOVER, text_color=ACCENT_TEXT)
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
                    self.after(0, lambda m=err_msg: self._set_web_status(f"● Web Tally: Init Error\n({m[:40]})", "#ef4444", "● Init Error"))
                    return
            
            if self.socketio:
                self.btn_toggle_web_server.configure(text="Stop Web Tally", fg_color="#dc2626", hover_color="#991b1b", text_color="#ffffff")
                t = threading.Thread(target=self.start_web_server, daemon=True)
                t.start()
                # Verify status after a short delay
                self.after(1500, self.check_web_server_active)
        else:
            self.is_web_server_active = False 
            self.btn_toggle_web_server.configure(text="Start Web Tally", fg_color=ACCENT_COLOR, hover_color=ACCENT_HOVER, text_color=ACCENT_TEXT)
            self._set_web_status("● Web Tally: Stopped", SUBTEXT_COLOR, "● Stopped")
            self.update_client_list()

    def toggle_vmix(self):
        if not self.is_vmix_connected:
            try:
                h = self.entry_vmix_host.get().strip()
                if not h:
                    self.set_card_status(self.vmix_card, "● Invalid IP", "#ef4444")
                    return
                p = int(self.entry_vmix_port.get().strip() or 8099)
                self.vmix_client = VmixTallyClient(h, p, self.on_external_update)
                self.vmix_client.start()
                self.is_vmix_connected = True
                self.set_card_status(self.vmix_card, "● Connecting...", "#f59e0b")
                self.btn_vmix_connect.configure(text="Disconnect vMix", fg_color="#dc2626", hover_color="#991b1b", text_color="#ffffff")
            except Exception as e:
                self.is_vmix_connected = False
                self.set_card_status(self.vmix_card, "● Error", "#ef4444")
                print(f"VMIX CONNECT ERROR: {e}")
        else:
            if self.vmix_client: self.vmix_client.stop()
            self.vmix_client = None
            self.is_vmix_connected = False
            self.set_card_status(self.vmix_card, "● Idle", SUBTEXT_COLOR)
            self.btn_vmix_connect.configure(text="Connect vMix", fg_color=ACCENT_COLOR, hover_color=ACCENT_HOVER, text_color=ACCENT_TEXT)

    def toggle_obs(self):
        if not self.is_obs_connected:
            try:
                h = self.entry_obs_host.get().strip()
                if not h:
                    self.set_card_status(self.obs_card, "● Invalid IP", "#ef4444")
                    return
                p = int(self.entry_obs_port.get().strip() or 4455)
                pw = self.entry_obs_pass.get()
                self.obs_client = ObsTallyClient(h, p, pw, 
                                               lambda: {i: v.get() for i, v in enumerate(self.tally_scene_vars)}, 
                                               self.on_external_update,
                                               lambda: self.combo_obs_match.get())
                self.obs_client.start()
                self.is_obs_connected = True
                self.set_card_status(self.obs_card, "● Connecting...", "#f59e0b")
                self.btn_obs_connect.configure(text="Disconnect OBS", fg_color="#dc2626", hover_color="#991b1b", text_color="#ffffff")
            except Exception as e:
                self.is_obs_connected = False
                self.set_card_status(self.obs_card, "● Error", "#ef4444")
                print(f"OBS CONNECT ERROR: {e}")
        else:
            if self.obs_client: self.obs_client.stop()
            self.obs_client = None
            self.is_obs_connected = False
            self.set_card_status(self.obs_card, "● Idle", SUBTEXT_COLOR)
            self.btn_obs_connect.configure(text="Connect OBS", fg_color=ACCENT_COLOR, hover_color=ACCENT_HOVER, text_color=ACCENT_TEXT)

    def toggle_atem(self):
        if not self.is_atem_connected:
            try:
                h = self.entry_atem_host.get().strip()
                if not h:
                    self.set_card_status(self.atem_card, "● Invalid IP", "#ef4444")
                    return
                self.atem_client = AtemHardwareClient(h, 9910, self.on_external_update)
                self.atem_client.start()
                self.is_atem_connected = True
                self.set_card_status(self.atem_card, "● Connecting...", "#f59e0b")
                self.btn_atem_connect.configure(text="Disconnect ATEM", fg_color="#dc2626", hover_color="#991b1b", text_color="#ffffff")
            except Exception as e:
                self.is_atem_connected = False
                self.set_card_status(self.atem_card, "● Error", "#ef4444")
                print(f"ATEM CONNECT ERROR: {e}")
        else:
            if self.atem_client: self.atem_client.stop()
            self.atem_client = None
            self.is_atem_connected = False
            self.set_card_status(self.atem_card, "● Idle", SUBTEXT_COLOR)
            self.btn_atem_connect.configure(text="Connect ATEM", fg_color=ACCENT_COLOR, hover_color=ACCENT_HOVER, text_color=ACCENT_TEXT)

    def toggle_tsl(self):
        if not self.is_tsl_active:
            try:
                h = self.entry_tsl_host.get().strip() or "255.255.255.255"
                p = int(self.entry_tsl_port.get().strip() or 8900)
                self.tsl_sender = TslUmdSender(h, p)
                self.tsl_sender.start()
                if not self.tsl_sender.running:
                    self.is_tsl_active = False
                    self.tsl_sender = None
                    self.set_card_status(self.tsl_card, "● Error", "#ef4444")
                    return
                self.is_tsl_active = True
                self.set_card_status(self.tsl_card, "● Online", "#10b981")
                self.btn_tsl_toggle.configure(text="Disable TSL 3.1", fg_color="#dc2626", hover_color="#991b1b", text_color="#ffffff")
                self.broadcast_all_tally()
            except Exception as e:
                self.is_tsl_active = False
                self.tsl_sender = None
                self.set_card_status(self.tsl_card, "● Error", "#ef4444")
                print(f"TSL START ERROR: {e}")
        else:
            if self.tsl_sender: self.tsl_sender.stop()
            self.tsl_sender = None
            self.is_tsl_active = False
            self.set_card_status(self.tsl_card, "● Idle", SUBTEXT_COLOR)
            self.btn_tsl_toggle.configure(text="Enable TSL 3.1 (Hollyland)", fg_color=ACCENT_COLOR, hover_color=ACCENT_HOVER, text_color=ACCENT_TEXT)

    def toggle_roland(self):
        if not self.is_roland_connected:
            try:
                h = self.entry_roland_host.get().strip()
                if not h:
                    self.set_card_status(self.roland_card, "● Invalid IP", "#ef4444")
                    return
                p = int(self.entry_roland_port.get().strip() or 8023)
                self.roland_client = RolandTallyClient(h, p, self.on_external_update)
                self.roland_client.start()
                self.is_roland_connected = True
                self.set_card_status(self.roland_card, "● Connecting...", "#f59e0b")
                self.btn_roland_connect.configure(text="Disconnect Roland", fg_color="#dc2626", hover_color="#991b1b", text_color="#ffffff")
            except Exception as e:
                self.is_roland_connected = False
                self.set_card_status(self.roland_card, "● Error", "#ef4444")
                print(f"ROLAND CONNECT ERROR: {e}")
        else:
            if self.roland_client: self.roland_client.stop()
            self.roland_client = None
            self.is_roland_connected = False
            self.set_card_status(self.roland_card, "● Idle", SUBTEXT_COLOR)
            self.btn_roland_connect.configure(text="Connect Roland", fg_color=ACCENT_COLOR, hover_color=ACCENT_HOVER, text_color=ACCENT_TEXT)

    def toggle_osc(self):
        if not self.is_osc_active:
            try:
                th = self.entry_osc_host.get().strip() or "255.255.255.255"
                tp = int(self.entry_osc_port.get().strip() or 9000)
                lp = int(self.entry_osc_listen.get().strip() or 8000)
                self.osc_bridge = OscTallyBridge(th, tp, lp, self.on_osc_trigger)
                self.osc_bridge.start()
                if not self.osc_bridge.running:
                    self.is_osc_active = False
                    self.osc_bridge = None
                    self.set_card_status(self.osc_card, "● Port Error", "#ef4444")
                    return
                self.is_osc_active = True
                self.set_card_status(self.osc_card, "● Online", "#10b981")
                self.btn_osc_toggle.configure(text="Disable OSC", fg_color="#dc2626", hover_color="#991b1b", text_color="#ffffff")
                self.broadcast_all_tally()
            except Exception as e:
                self.is_osc_active = False
                self.osc_bridge = None
                self.set_card_status(self.osc_card, "● Port Error", "#ef4444")
                print(f"OSC START ERROR: {e}")
        else:
            if self.osc_bridge: self.osc_bridge.stop()
            self.osc_bridge = None
            self.is_osc_active = False
            self.set_card_status(self.osc_card, "● Idle", SUBTEXT_COLOR)
            self.btn_osc_toggle.configure(text="Enable OSC Bridge", fg_color=ACCENT_COLOR, hover_color=ACCENT_HOVER, text_color=ACCENT_TEXT)

    def on_osc_trigger(self, address, args):
        try:
            self.after(0, lambda a=address, g=list(args): self._apply_osc_trigger(a, g))
        except Exception:
            pass

    def _apply_osc_trigger(self, address, args):
        try:
            parts = address.strip("/").split("/")
            if len(parts) >= 3 and parts[0].lower() == "tally":
                cam_idx = int(parts[1]) - 1
                cmd = parts[2].lower()
                val = int(args[0]) if args else 1
                if 0 <= cam_idx < self.current_rows_count:
                    if cmd in ("program", "prog", "pgm"):
                        self.set_led1_state(cam_idx, "Prog" if val else "Off")
                    elif cmd in ("preview", "prev", "pvw"):
                        self.set_led1_state(cam_idx, "Prev" if val else "Off")
                    elif cmd in ("off", "clear"):
                        self.set_led1_state(cam_idx, "Off")
        except Exception as e:
            print(f"OSC TRIGGER ERROR: {e}")

    def toggle_serial(self):
        if not self.is_serial_active:
            try:
                p = self.combo_serial_port.get().strip()
                proto = self.combo_serial_proto.get().strip()
                if not p or p == "No Ports Found":
                    self.set_card_status(self.serial_card, "● Port Error", "#ef4444")
                    return
                self.serial_driver = SerialTallyDriver(port=p, protocol=proto)
                self.serial_driver.start()
                if not self.serial_driver.running:
                    self.is_serial_active = False
                    self.serial_driver = None
                    self.set_card_status(self.serial_card, "● Port Error", "#ef4444")
                    return
                self.is_serial_active = True
                self.set_card_status(self.serial_card, "● Online", "#10b981")
                self.btn_serial_toggle.configure(text="Disable USB Serial", fg_color="#dc2626", hover_color="#991b1b", text_color="#ffffff")
                self.broadcast_all_tally()
            except Exception as e:
                self.is_serial_active = False
                self.serial_driver = None
                self.set_card_status(self.serial_card, "● Port Error", "#ef4444")
                print(f"SERIAL START ERROR: {e}")
        else:
            if self.serial_driver: self.serial_driver.stop()
            self.serial_driver = None
            self.is_serial_active = False
            self.set_card_status(self.serial_card, "● Idle", SUBTEXT_COLOR)
            self.btn_serial_toggle.configure(text="Enable USB Serial", fg_color=ACCENT_COLOR, hover_color=ACCENT_HOVER, text_color=ACCENT_TEXT)

    def toggle_theme_mode(self):
        current = ctk.get_appearance_mode()
        new_mode = "Light" if current == "Dark" else "Dark"
        self.set_theme_mode(new_mode)

    def set_theme_mode(self, mode):
        ctk.set_appearance_mode(mode)
        self.var_theme.set(mode)
        if hasattr(self, 'btn_theme_toggle'):
            self.btn_theme_toggle.configure(text="☀️ Light" if mode == "Dark" else "🌙 Dark")
        if hasattr(self, 'combo_theme'):
            self.combo_theme.set(mode)
        for i in range(self.current_rows_count):
            self.update_led1_ui_buttons(i)
            self.update_led2_ui_buttons(i)
        self.apply_titlebar()
        is_dark = ctk.get_appearance_mode() == "Dark"
        bg_hex = "#121214" if is_dark else "#e4e4e7"
        text_hex = "#f4f4f5" if is_dark else "#09090b"
        border_hex = "#27272a" if is_dark else "#cbd5e1"
        for sub_win in (getattr(self, "_settings_win", None), getattr(self, "_help_win", None)):
            if sub_win is not None and sub_win.winfo_exists():
                apply_windows_titlebar_theme(sub_win, dark_mode=is_dark, bg_hex=bg_hex, text_hex=text_hex, border_hex=border_hex)
        self.save_config()

    def on_external_update(self, flags):
        try:
            self.after(0, lambda f=list(flags): self._apply_external_update(f))
        except Exception:
            pass

    def _apply_external_update(self, flags):
        for i, f in enumerate(flags):
            if i < self.current_rows_count:
                v = "Off"
                if f == 1 or (f & 0x01): v = "Prog"
                elif f == 2 or (f & 0x02): v = "Prev"
                elif f == 32 or (f & 0x20): v = "ATT" # 0x20
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

    def _refresh_row_status_orb(self, idx):
        if idx >= len(self.tally_status_orbs):
            return
        is_online = (self.is_server_running or self.is_web_server_active) and (idx in self.active_cam_ids)
        base = "● Online" if is_online else "● Idle"
        state = self.tally_vars_led1[idx].get() if idx < len(self.tally_vars_led1) else "Off"
        if state == "Prog":
            self.tally_status_orbs[idx].configure(text=f"{base} [PGM]", text_color=COLOR_PROG)
        elif state == "Prev":
            self.tally_status_orbs[idx].configure(text=f"{base} [PVW]", text_color=COLOR_PREV)
        elif state == "ATT":
            self.tally_status_orbs[idx].configure(text=f"{base} [ATT]", text_color=COLOR_ATT)
        elif is_online:
            self.tally_status_orbs[idx].configure(text="● Online", text_color="#10b981")
        else:
            self.tally_status_orbs[idx].configure(text="● Idle", text_color=SUBTEXT_COLOR)

    def update_led1_ui_buttons(self, idx):
        if idx >= len(self.tally_btn_led1_off): return
        
        state = self.tally_vars_led1[idx].get()
        
        # Configure Off button
        if state == "Off":
            self.tally_btn_led1_off[idx].configure(fg_color=BTN_OFF_ACTIVE, text_color=BTN_OFF_TEXT, hover_color=BTN_INACTIVE_HOVER)
        else:
            self.tally_btn_led1_off[idx].configure(fg_color=BTN_INACTIVE_BG, text_color=BTN_INACTIVE_TEXT, hover_color=BTN_INACTIVE_HOVER)

        # Configure Prog button
        if state == "Prog":
            self.tally_btn_led1_prog[idx].configure(fg_color=COLOR_PROG, text_color="#ffffff", hover_color=COLOR_PROG_HOVER)
        else:
            self.tally_btn_led1_prog[idx].configure(fg_color=BTN_INACTIVE_BG, text_color=BTN_INACTIVE_TEXT, hover_color=BTN_INACTIVE_HOVER)

        # Configure Prev button
        if state == "Prev":
            self.tally_btn_led1_prev[idx].configure(fg_color=COLOR_PREV, text_color="#ffffff", hover_color=COLOR_PREV_HOVER)
        else:
            self.tally_btn_led1_prev[idx].configure(fg_color=BTN_INACTIVE_BG, text_color=BTN_INACTIVE_TEXT, hover_color=BTN_INACTIVE_HOVER)

        # Configure ATT button
        if state == "ATT":
            self.tally_btn_led1_att[idx].configure(fg_color=COLOR_ATT, text_color="#ffffff", hover_color=COLOR_ATT_HOVER)
        else:
            self.tally_btn_led1_att[idx].configure(fg_color=BTN_INACTIVE_BG, text_color=BTN_INACTIVE_TEXT, hover_color=BTN_INACTIVE_HOVER)

        # Semantic row highlight for high-contrast studio readability
        if idx < len(self.tally_rows_widgets):
            row_w = self.tally_rows_widgets[idx]
            if state == "Prog":
                row_w.configure(fg_color=("#fee2e2", "#3b1219"), border_width=1, border_color=("#fca5a5", "#7f1d1d"))
            elif state == "Prev":
                row_w.configure(fg_color=("#dcfce7", "#0f2e1f"), border_width=1, border_color=("#86efac", "#14532d"))
            elif state == "ATT":
                row_w.configure(fg_color=("#dbeafe", "#13233d"), border_width=1, border_color=("#93c5fd", "#1e3a8a"))
            else:
                row_w.configure(fg_color="transparent", border_width=0)

        self._refresh_row_status_orb(idx)

    def update_led2_ui_buttons(self, idx):
        if idx >= len(self.tally_btn_led2_r):
            return
        mapping = [
            (self.tally_vars_led2_r, self.tally_btn_led2_r, COLOR_PROG, COLOR_PROG_HOVER),
            (self.tally_vars_led2_g, self.tally_btn_led2_g, COLOR_PREV, COLOR_PREV_HOVER),
            (self.tally_vars_led2_b, self.tally_btn_led2_b, COLOR_ATT, COLOR_ATT_HOVER),
        ]
        for vars_list, btns_list, act_col, act_hov in mapping:
            if vars_list[idx].get():
                btns_list[idx].configure(fg_color=act_col, text_color="#ffffff", hover_color=act_hov)
            else:
                btns_list[idx].configure(fg_color=BTN_INACTIVE_BG, text_color=BTN_INACTIVE_TEXT, hover_color=BTN_INACTIVE_HOVER)

    def toggle_led2_color(self, idx, color):
        var = {"R": self.tally_vars_led2_r, "G": self.tally_vars_led2_g, "B": self.tally_vars_led2_b}[color][idx]
        var.set(not var.get())
        self.update_led2_ui_buttons(idx)
        self.broadcast_all_tally()

    def broadcast_all_tally(self):
        # 120 sources to cover all tallies + Remote Display (41+) + Message buffer (82-106)
        self.server.set_tally_sources(120)
        
        batch_data = []
        tsl_data = []
        # We broadcast all 41 possible camera indices
        for i in range(41):
            f = 0
            lbl = self.tally_scene_vars[i].get() if i < len(self.tally_scene_vars) else f"Cam {i+1}"
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
                
                tsl_data.append((i, lbl, (l1 == "Prog"), (l1 == "Prev"), (l1 == "ATT")))
            
            self.server.set_tally_flag(i, f)
            
            # Prepare batch data for Web Tally
            if self.is_web_server_active:
                batch_data.append({'index': i, 'flag': f, 'label': lbl})
            
            # Remote Display Modes (Stored per Camera Slot)
            if i < len(self.remotedisplay_display_modes):
                self.server.set_tally_flag(41 + i, self.remotedisplay_display_modes[i])
                
        # Emit TSL UMD 3.1 to Hollyland / Monitors
        if self.tsl_sender and self.is_tsl_active and tsl_data:
            self.tsl_sender.send_bulk_tally(tsl_data)

        # Emit OSC Bridge to Companion / Digital Consoles
        if self.osc_bridge and self.is_osc_active and tsl_data:
            self.osc_bridge.send_bulk_tally(tsl_data)

        # Emit USB Serial / Hardware Relays
        if self.serial_driver and self.is_serial_active and tsl_data:
            self.serial_driver.send_tally_states(tsl_data)

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
        print(f"Web Tally Connected: {sid}")
        self.web_clients[sid] = 0
        self.after(0, self.update_web_tally_ui)
        self.after(0, self.update_client_list)
        self.after(50, lambda s=sid: self._sync_web_client_cam(s, 0))

    def handle_web_disconnect(self, *args, **kwargs):
        sid = request.sid
        print(f"Web Tally Disconnected: {sid}")
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
        lbl = self.tally_scene_vars[idx].get() if idx < len(self.tally_scene_vars) else f"Cam {idx+1}"
        # Emit using socketio.emit to the specific SID
        if self.socketio:
            try:
                self.socketio.emit('tally_update', {'index': idx, 'flag': f, 'label': lbl}, to=sid)
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
                row = ctk.CTkFrame(self.web_tally_list_f, fg_color=ROW_BG, border_width=1, border_color=BORDER_COLOR, corner_radius=6)
                row.pack(fill="x", pady=2)
                
                # Show first 8 chars of SID for better identification
                short_id = sid[:6] if sid else "????"
                name_lbl = ctk.CTkLabel(row, text=f"🌐 Tally SID: {short_id}", font=ctk.CTkFont(size=12, weight="bold"), text_color=TEXT_PRIMARY)
                name_lbl.pack(side="left", padx=10, pady=5)
                
                combo = ctk.CTkComboBox(row, values=[f"Cam {i+1}" for i in range(41)], width=100, height=24, **COMBO_STYLE)
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
                text_lines.append(f"🌐 Web Tally: Cam {cam_id + 1} (SID: {sid[:6]})")

        if self.is_server_running:
            for c in self.server.clients:
                if c.is_connected:
                    s = "Active" if c.is_initialized else "Sync"
                    text_lines.append(f"🚨 Tally [{c.ip}]: Cam {c.tally_id + 1 if c.tally_id >= 0 else '?'} ({s})")
                    if c.is_initialized and c.tally_id >= 0:
                        active_ids.add(c.tally_id)
            
            # Add Sub-clients reported via Repeaters
            for parent_ip, sub_data in getattr(self.server, 'repeater_clients', {}).items():
                for sub_item in sub_data:
                    # sub_item is (ip, role)
                    sub_ip, sub_role = sub_item
                    role_str = f"SubTally: Cam {sub_role + 1}" if sub_role >= 0 else "Role: ?"
                    text_lines.append(f"  └─ [{sub_ip}] {role_str} via Repeater ({parent_ip})")
                    if sub_role >= 0:
                        active_ids.add(sub_role)

        if not text_lines and (self.is_server_running or self.is_web_server_active):
            text_lines.append("No active clients detected.")
        
        output_text = "\n".join(text_lines)
        self.txt_clients.insert("end", output_text if output_text else "Waiting for connections...")
        self.txt_clients.configure(state="disabled")
        
        self.active_cam_ids = active_ids
        for i in range(self.current_rows_count):
            self._refresh_row_status_orb(i)
        
        # Force UI refresh
        self.update_idletasks()

    def _poll_connection_statuses(self):
        try:
            if self.is_server_running:
                if self.server.running:
                    self.set_card_status(self.server_card, "● Online", "#10b981")
                else:
                    self.set_card_status(self.server_card, "● Error", "#ef4444")

            if self.is_atem_connected and self.atem_client:
                if self.atem_client.is_connected:
                    self.set_card_status(self.atem_card, "● Connected", "#10b981")
                else:
                    self.set_card_status(self.atem_card, "● Connecting...", "#f59e0b")

            if self.is_vmix_connected and self.vmix_client:
                if self.vmix_client.is_connected:
                    self.set_card_status(self.vmix_card, "● Connected", "#10b981")
                else:
                    self.set_card_status(self.vmix_card, "● Connecting...", "#f59e0b")

            if self.is_obs_connected and self.obs_client:
                if self.obs_client.is_connected:
                    self.set_card_status(self.obs_card, "● Connected", "#10b981")
                else:
                    self.set_card_status(self.obs_card, "● Connecting...", "#f59e0b")

            if self.is_roland_connected and self.roland_client:
                if self.roland_client.is_connected:
                    self.set_card_status(self.roland_card, "● Connected", "#10b981")
                else:
                    self.set_card_status(self.roland_card, "● Connecting...", "#f59e0b")

            if self.is_tsl_active and self.tsl_sender:
                if self.tsl_sender.running:
                    self.set_card_status(self.tsl_card, "● Online", "#10b981")
                else:
                    self.set_card_status(self.tsl_card, "● Error", "#ef4444")

            if self.is_osc_active and self.osc_bridge:
                if self.osc_bridge.running:
                    self.set_card_status(self.osc_card, "● Online", "#10b981")
                else:
                    self.set_card_status(self.osc_card, "● Error", "#ef4444")

            if self.is_serial_active and self.serial_driver:
                if self.serial_driver.running:
                    self.set_card_status(self.serial_card, "● Online", "#10b981")
                else:
                    self.set_card_status(self.serial_card, "● Error", "#ef4444")

            if self.is_web_server_active:
                port = self.entry_web_port.get().strip() or "8080"
                self._set_web_status(f"● Web Tally: Online (:{port})", "#10b981", f"● Online (:{port})")

            if self.var_remotedisplay_mode.get():
                if self.is_server_running and self.server.running:
                    self.set_card_status(self.remotedisplay_card, "● Ready", "#10b981")
                else:
                    self.set_card_status(self.remotedisplay_card, "● Needs Server", "#f59e0b")
            else:
                self.set_card_status(self.remotedisplay_card, "● Idle", SUBTEXT_COLOR)
        except Exception as e:
            print(f"STATUS POLL ERROR: {e}")
        finally:
            if self.winfo_exists():
                self.after(1000, self._poll_connection_statuses)

    def load_config(self):
        if not os.path.exists(self.config_file): return
        try:
            with open(self.config_file, "r") as f:
                c = json.load(f)
                self.entry_port.delete(0, "end")
                self.entry_port.insert(0, c.get("server_port", "9910"))
                self.entry_atem_host.delete(0, "end")
                self.entry_atem_host.insert(0, c.get("atem_host", "192.168.10.240"))
                self.entry_roland_host.delete(0, "end")
                self.entry_roland_host.insert(0, c.get("roland_host", "192.168.1.100"))
                self.entry_roland_port.delete(0, "end")
                self.entry_roland_port.insert(0, str(c.get("roland_port", "8023")))
                self.entry_tsl_host.delete(0, "end")
                self.entry_tsl_host.insert(0, c.get("tsl_host", "255.255.255.255"))
                self.entry_tsl_port.delete(0, "end")
                self.entry_tsl_port.insert(0, str(c.get("tsl_port", "8900")))
                self.entry_osc_host.delete(0, "end")
                self.entry_osc_host.insert(0, c.get("osc_host", "255.255.255.255"))
                self.entry_osc_port.delete(0, "end")
                self.entry_osc_port.insert(0, str(c.get("osc_port", "9000")))
                self.entry_osc_listen.delete(0, "end")
                self.entry_osc_listen.insert(0, str(c.get("osc_listen", "8000")))
                if "serial_port" in c:
                    self.combo_serial_port.set(c.get("serial_port"))
                if "serial_proto" in c:
                    self.combo_serial_proto.set(c.get("serial_proto"))
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
                self.var_auto_atem.set(c.get("auto_atem", False))
                self.var_auto_tsl.set(c.get("auto_tsl", False))
                self.var_auto_roland.set(c.get("auto_roland", False))
                self.var_auto_osc.set(c.get("auto_osc", False))
                self.var_auto_serial.set(c.get("auto_serial", False))
                self.var_touch_mode.set(c.get("touch_mode", False))
                self.var_save_window.set(c.get("save_window", True))
                self.var_remotedisplay_mode.set(c.get("remotedisplay_mode", False))
                self.var_auto_web_tally.set(c.get("auto_web_tally", False))
                raw_match = c.get("obs_match_type", "Auto")
                match_map = {
                    "Automatico": "Auto",
                    "Cenas": "Scenes",
                    "Video Source": "Video Sources",
                }
                norm_match = match_map.get(raw_match, raw_match)
                if norm_match not in ("Auto", "Scenes", "Video Sources"):
                    norm_match = "Auto"
                self.var_obs_match_type.set(norm_match)
                self.combo_obs_match.set(norm_match)
                self.var_theme.set(c.get("theme_mode", "Dark"))
                ctk.set_appearance_mode(self.var_theme.get())
                if hasattr(self, 'btn_theme_toggle'):
                    self.btn_theme_toggle.configure(text="☀️ Light" if self.var_theme.get() == "Dark" else "🌙 Dark")
                self.toggle_remotedisplay_ui()
                
                if self.var_save_window.get():
                    w = c.get("window_w", 1150)
                    h = c.get("window_h", 700)
                    self.last_w = w
                    self.last_h = h
                    self.geometry(f"{w}x{h}")
                    st = c.get("window_state", "normal")
                    self.window_state = st
                    if st in ("maximized", "zoomed"):
                        self.after(50, lambda: self.state("zoomed"))
                    elif st in ("minimized", "iconic"):
                        self.after(50, lambda: self.iconify())
                self.settings_w = c.get("settings_w", 780)
                self.settings_h = c.get("settings_h", 560)

                # Restore Remote Display UI State
                self.combo_remotedisplay_target.set(c.get("remotedisplay_target", "ALL"))
                self.remotedisplay_radio_var.set(c.get("remotedisplay_mode_val", 0))
                self.entry_remotedisplay_msg.delete(0, "end")
                self.entry_remotedisplay_msg.insert(0, c.get("remotedisplay_msg", ""))
                
                # Load or construct remotedisplay_display_modes
                target = c.get("remotedisplay_target", "ALL")
                mode_val = c.get("remotedisplay_mode_val", 0)
                if "remotedisplay_display_modes" in c:
                    self.remotedisplay_display_modes = c.get("remotedisplay_display_modes")
                else:
                    self.remotedisplay_display_modes = [0] * 41
                    if target == "ALL":
                        self.remotedisplay_display_modes = [mode_val] * 41
                    else:
                        try:
                            cam_idx = int(target.split(" ")[1]) - 1
                            if 0 <= cam_idx < 41:
                                self.remotedisplay_display_modes[cam_idx] = mode_val
                        except: pass
                if len(self.remotedisplay_display_modes) < 41:
                    self.remotedisplay_display_modes += [0] * (41 - len(self.remotedisplay_display_modes))
                elif len(self.remotedisplay_display_modes) > 41:
                    self.remotedisplay_display_modes = self.remotedisplay_display_modes[:41]
                
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
                for i in range(row_count):
                    self.update_led1_ui_buttons(i)
                    self.update_led2_ui_buttons(i)

                names = c.get("scenes", [])
                for i, name in enumerate(names):
                    if i < len(self.tally_scene_vars): self.tally_scene_vars[i].set(name)
                if self.var_touch_mode.get(): ctk.set_widget_scaling(1.2)
                self.after(600, self._auto_run)
        except Exception as e:
            print(f"Error loading config: {e}")

    def _auto_run(self):
        if self.var_auto_server.get(): 
            self.toggle_server()
            # After server starts, broadcast current Remote Display state
            self.after(1000, self.send_remotedisplay_command)
        if self.var_auto_vmix.get(): self.toggle_vmix()
        if self.var_auto_obs.get(): self.toggle_obs()
        if self.var_auto_atem.get(): self.toggle_atem()
        if self.var_auto_roland.get(): self.toggle_roland()
        if self.var_auto_tsl.get(): self.toggle_tsl()
        if self.var_auto_osc.get(): self.toggle_osc()
        if self.var_auto_serial.get(): self.toggle_serial()
        if self.var_auto_web_tally.get(): self.toggle_web_server()

    def save_config(self):
        if not self.var_save_on_exit.get(): return
        st = "normal"
        try:
            s = self.state()
            if s == "zoomed":
                st = "maximized"
            elif s == "iconic":
                st = "minimized"
            else:
                st = "normal"
                w = self.winfo_width()
                h = self.winfo_height()
                if w > 200 and h > 200:
                    self.last_w = w
                    self.last_h = h
        except Exception:
            pass
        self.window_state = st
        cfg = {
            "server_port": self.entry_port.get(),
            "atem_host": self.entry_atem_host.get(),
            "roland_host": self.entry_roland_host.get(),
            "roland_port": self.entry_roland_port.get(),
            "tsl_host": self.entry_tsl_host.get(),
            "tsl_port": self.entry_tsl_port.get(),
            "osc_host": self.entry_osc_host.get(),
            "osc_port": self.entry_osc_port.get(),
            "osc_listen": self.entry_osc_listen.get(),
            "serial_port": self.combo_serial_port.get(),
            "serial_proto": self.combo_serial_proto.get(),
            "vmix_host": self.entry_vmix_host.get(), "vmix_port": self.entry_vmix_port.get(),
            "obs_host": self.entry_obs_host.get(), "obs_port": self.entry_obs_port.get(), "obs_pass": self.entry_obs_pass.get(),
            "web_port": self.entry_web_port.get(),
            "theme_mode": self.var_theme.get(),
            "save_on_exit": self.var_save_on_exit.get(), "auto_server": self.var_auto_server.get(),
            "auto_vmix": self.var_auto_vmix.get(), "auto_obs": self.var_auto_obs.get(),
            "auto_atem": self.var_auto_atem.get(), "auto_roland": self.var_auto_roland.get(),
            "auto_tsl": self.var_auto_tsl.get(), "auto_osc": self.var_auto_osc.get(),
            "auto_serial": self.var_auto_serial.get(),
            "auto_web_tally": self.var_auto_web_tally.get(),
            "obs_match_type": self.combo_obs_match.get(),
            "touch_mode": self.var_touch_mode.get(), 
            "remotedisplay_mode": self.var_remotedisplay_mode.get(),
            "remotedisplay_target": self.combo_remotedisplay_target.get(),
            "remotedisplay_mode_val": self.remotedisplay_radio_var.get(),
            "remotedisplay_display_modes": self.remotedisplay_display_modes,
            "remotedisplay_msg": self.entry_remotedisplay_msg.get(),
            "save_window": self.var_save_window.get(),
            "window_state": self.window_state,
            "window_w": self.last_w,
            "window_h": self.last_h,
            "settings_w": getattr(self, "settings_w", 780),
            "settings_h": getattr(self, "settings_h", 560),
            "row_count": self.current_rows_count,
            "scenes": [v.get() for v in self.tally_scene_vars]
        }
        temp_config = f"{self.config_file}.{os.getpid()}.tmp"
        try:
            with open(temp_config, "w", encoding="utf-8") as f:
                json.dump(cfg, f, indent=4)
            os.replace(temp_config, self.config_file)
        except Exception as e:
            print(f"Erro ao salvar configuração: {e}")
            if os.path.exists(temp_config):
                try:
                    os.remove(temp_config)
                except Exception:
                    pass

    def on_closing(self):
        try:
            self.save_config()
        except Exception as e:
            print(f"Error saving config on exit: {e}")

        self.is_web_server_active = False
        for service in (
            self.vmix_client,
            self.obs_client,
            self.atem_client,
            self.roland_client,
            self.tsl_sender,
            self.osc_bridge,
            self.serial_driver,
            self.server,
        ):
            if service is not None:
                try:
                    service.stop()
                except Exception as e:
                    print(f"Error stopping service on exit: {e}")
        self.destroy()

if __name__ == "__main__":
    app = TallyApp()
    app.protocol("WM_DELETE_WINDOW", app.on_closing)
    app.mainloop()
