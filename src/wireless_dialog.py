# DualCPY - Dual-screen scrcpy docking and control UI for Windows
# Copyright (C) 2026 the_swest
# Contact: Github issues
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

# src/wireless_dialog.py

import re
import ctypes
import logging
import customtkinter as ctk

from src.win32_darkmode import enable_dark_titlebar
from src.control_panel import (
    BG_COLOUR, PANEL_COLOUR, BORDER_COLOUR, TEXT_COLOUR,
    ACCENT_COLOUR, ACCENT2_COLOUR,
    SUCCESS_COLOUR, DANGER_COLOUR, WARNING_COLOUR,
    make_font, load_calsans, apply_window_icon,
)

try:
    _HAS_DARK_TITLEBAR = True
except Exception:
    _HAS_DARK_TITLEBAR = False

logger = logging.getLogger(__name__)

# Connection defaults
DEFAULT_CONNECT_PORT = "5555"

# Dialog window dimensions
DIALOG_WIDTH = 600
DIALOG_HEIGHT = 680
DIALOG_MIN_HEIGHT = 580


class WirelessConnectionDialog:
    """
    Dialog for managing wireless ADB connections.

    Allows users to:
    1) Pair with a device using a pairing code (for first-time setup)
    2) Connect to a device by IP address
    3) Disconnect wireless connections
    """

    def __init__(self, parent, scrcpy_manager, config=None):
        self.scrcpy_manager = scrcpy_manager
        self.config = config
        self.result = None

        load_calsans()

        # Create a CTkToplevel so it inherits the CTK appearance context
        self.dialog = ctk.CTkToplevel(parent) if parent else ctk.CTk()
        self.dialog.title("Wireless Connection Setup")
        self.dialog.configure(fg_color=BG_COLOUR)
        self.dialog.geometry(f"{DIALOG_WIDTH}x{DIALOG_HEIGHT}")
        self.dialog.resizable(False, True)
        self.dialog.minsize(DIALOG_WIDTH, DIALOG_MIN_HEIGHT)

        # Centre on screen
        self.dialog.update_idletasks()
        x = (self.dialog.winfo_screenwidth()  // 2) - (DIALOG_WIDTH  // 2)
        y = (self.dialog.winfo_screenheight() // 2) - (DIALOG_HEIGHT // 2)
        self.dialog.geometry(f"+{x}+{y}")

        apply_window_icon(self.dialog)

        if parent:
            self.dialog.transient(parent)

        self._create_widgets()
        self._load_inputs()

        self.dialog.protocol("WM_DELETE_WINDOW", self._on_close)
        self.dialog.deiconify()
        self.dialog.lift()
        self.dialog.focus_force()
        self.dialog.grab_set()

        # Dark titlebar
        try:
            self.dialog.update_idletasks()
            hwnd = ctypes.windll.user32.GetParent(self.dialog.winfo_id())
            if not hwnd:
                hwnd = self.dialog.winfo_id()
            if _HAS_DARK_TITLEBAR:
                enable_dark_titlebar(hwnd)
        except Exception:
            pass

        logger.info("Wireless connection dialog opened")

    # Widget construction
    def _create_widgets(self):
        """Build and lay out all dialog widgets."""
        scroll = ctk.CTkScrollableFrame(
            self.dialog,
            fg_color=BG_COLOUR,
            scrollbar_button_color=BORDER_COLOUR,
            scrollbar_button_hover_color=ACCENT_COLOUR,
        )
        scroll.pack(fill="both", expand=True)
        scroll.columnconfigure(0, weight=1)
        self._scroll = scroll

        # Header
        ctk.CTkLabel(
            scroll,
            text="Wireless Connection Setup",
            font=make_font(20, "bold"),
            text_color=TEXT_COLOUR,
            anchor="w",
        ).pack(fill="x", padx=20, pady=(20, 2))

        ctk.CTkLabel(
            scroll,
            text="Connect your AYN Thor wirelessly without a USB cable",
            font=make_font(12),
            text_color=BORDER_COLOUR,
            anchor="w",
        ).pack(fill="x", padx=20, pady=(0, 12))

        self._separator(scroll)

        # Status
        self._section(scroll, "Connection Status")

        self.status_label = ctk.CTkLabel(
            scroll,
            text="Checking...",
            font=make_font(12),
            text_color=TEXT_COLOUR,
            anchor="w",
            wraplength=540,
        )
        self.status_label.pack(fill="x", padx=20, pady=(0, 12))

        self._separator(scroll)

        # Quick Connect
        self._section(scroll, "Already Paired? Quick Connect")

        ctk.CTkLabel(
            scroll,
            text=(
                "If you've already paired your device, enter the IP and port shown in:\n"
                "Settings -> Developer Options -> Wireless Debugging"
            ),
            font=make_font(12),
            text_color=BORDER_COLOUR,
            anchor="w",
            wraplength=540,
            justify="left",
        ).pack(fill="x", padx=20, pady=(0, 10))

        connect_form = ctk.CTkFrame(scroll, fg_color="transparent")
        connect_form.pack(fill="x", padx=20, pady=(0, 4))
        connect_form.columnconfigure(1, weight=1)

        # IP address
        self._form_label(connect_form, "IP Address:", row=0)
        self.ip_entry = self._form_entry(connect_form, row=0, col=1, mono=True)
        self._hint_label(connect_form, "e.g. 192.168.1.100", row=0, col=2)

        # Port
        self._form_label(connect_form, "Port:", row=1)
        self.port_entry = self._form_entry(connect_form, row=1, col=1, width=120, mono=True)
        self._hint_label(connect_form, "From the MAIN wireless debugging page", row=1, col=2)

        self.connect_btn = ctk.CTkButton(
            scroll,
            text="Connect Now",
            command=self._on_connect,
            fg_color=ACCENT_COLOUR,
            hover_color=ACCENT2_COLOUR,
            text_color=TEXT_COLOUR,
            font=make_font(13),
        )
        self.connect_btn.pack(pady=(8, 12))

        self._separator(scroll)

        # First-time Pairing
        self._section(scroll, "First Time? Pair Your Device")

        ctk.CTkLabel(
            scroll,
            text=(
                "Follow these steps on your AYN Thor:\n\n"
                "1. Go to: Settings -> System -> Developer Options -> Wireless Debugging\n"
                "2. Tap on 'Pair device with pairing code'\n"
                "3. Enter the IP Address, Port, and 6-digit code shown below"
            ),
            font=make_font(12),
            text_color=BORDER_COLOUR,
            anchor="w",
            wraplength=540,
            justify="left",
        ).pack(fill="x", padx=20, pady=(0, 10))

        pair_form = ctk.CTkFrame(scroll, fg_color="transparent")
        pair_form.pack(fill="x", padx=20, pady=(0, 4))
        pair_form.columnconfigure(1, weight=1)

        # Pair IP
        self._form_label(pair_form, "IP Address:", row=0)
        self.pair_address_entry = self._form_entry(pair_form, row=0, col=1, mono=True)
        self._hint_label(pair_form, "From pairing screen", row=0, col=2)

        # Pair Port
        self._form_label(pair_form, "Port:", row=1)
        self.pair_port_entry = self._form_entry(pair_form, row=1, col=1, width=120, mono=True)
        self._hint_label(pair_form, "From pairing screen", row=1, col=2)

        # Pairing code
        self._form_label(pair_form, "Pairing Code:", row=2)
        self.pair_code_entry = self._form_entry(pair_form, row=2, col=1, width=120, mono=True)
        self._hint_label(pair_form, "6-digit code", row=2, col=2)

        self.pair_btn = ctk.CTkButton(
            scroll,
            text="Pair Device",
            command=self._on_pair,
            fg_color=PANEL_COLOUR,
            hover_color=BORDER_COLOUR,
            border_color=BORDER_COLOUR,
            border_width=1,
            text_color=TEXT_COLOUR,
            font=make_font(13),
        )
        self.pair_btn.pack(pady=(8, 12))

        self._separator(scroll)

        # Bottom actions
        bottom = ctk.CTkFrame(scroll, fg_color="transparent")
        bottom.pack(fill="x", padx=20, pady=(10, 20))

        self.disconnect_btn = ctk.CTkButton(
            bottom,
            text="Disconnect",
            command=self._on_disconnect,
            fg_color="#8b2020",
            hover_color="#c0392b",
            text_color=TEXT_COLOUR,
            font=make_font(13),
            state="disabled",
        )
        self.disconnect_btn.pack(side="left")

        ctk.CTkButton(
            bottom,
            text="Close",
            command=self._on_close,
            fg_color=PANEL_COLOUR,
            hover_color=BORDER_COLOUR,
            border_color=BORDER_COLOUR,
            border_width=1,
            text_color=TEXT_COLOUR,
            font=make_font(13),
        ).pack(side="right")

        self._update_status()

    # Layout helpers
    def _separator(self, parent):
        ctk.CTkFrame(parent, height=1, fg_color=BORDER_COLOUR).pack(
            fill="x", padx=16, pady=8
        )

    def _section(self, parent, title):
        ctk.CTkLabel(
            parent,
            text=title,
            font=make_font(14, "bold"),
            text_color=TEXT_COLOUR,
            anchor="w",
        ).pack(fill="x", padx=20, pady=(8, 4))

    def _form_label(self, parent, text, row):
        ctk.CTkLabel(
            parent,
            text=text,
            font=make_font(12),
            text_color=TEXT_COLOUR,
            anchor="w",
            width=110,
        ).grid(row=row, column=0, sticky="w", padx=(0, 8), pady=4)

    def _form_entry(self, parent, row, col, width=None, mono=False):
        kwargs = dict(
            fg_color=PANEL_COLOUR,
            border_color=BORDER_COLOUR,
            text_color=TEXT_COLOUR,
            font=ctk.CTkFont(family="Consolas", size=13) if mono else make_font(13),
        )
        if width:
            kwargs["width"] = width
        entry = ctk.CTkEntry(parent, **kwargs)
        sticky = "w" if width else "ew"
        entry.grid(row=row, column=col, sticky=sticky, padx=(0, 8), pady=4)
        return entry

    def _hint_label(self, parent, text, row, col):
        ctk.CTkLabel(
            parent,
            text=text,
            font=make_font(11),
            text_color=BORDER_COLOUR,
            anchor="w",
        ).grid(row=row, column=col, sticky="w", pady=4)

    # Entry helpers
    def _set_entry(self, entry, value):
        """Clear and set a CTkEntry's text."""
        entry.delete(0, "end")
        if value:
            entry.insert(0, value)

    # Data
    def _load_inputs(self):
        """
        Populate fields in priority order:
        1) Active wireless connection - autofill Connect IP + port from live serial
        2) Saved config values
        3) Default port 5555, everything else empty
        """
        serial = self.scrcpy_manager.serial
        mode   = self.scrcpy_manager.connection_mode

        if serial and mode == "wireless" and ":" in serial:
            connect_ip, connect_port = serial.rsplit(":", 1)
            logger.debug(f"Autofilling connect fields from live connection: {serial}")
        elif self.config:
            connect_ip   = self.config.get("wireless_connect_ip",   "")
            connect_port = self.config.get("wireless_connect_port", DEFAULT_CONNECT_PORT)
        else:
            connect_ip   = ""
            connect_port = DEFAULT_CONNECT_PORT

        self._set_entry(self.ip_entry,   connect_ip)
        self._set_entry(self.port_entry, connect_port)

        if self.config:
            pair_ip   = self.config.get("wireless_pair_ip",   "")
            pair_port = self.config.get("wireless_pair_port", "")
        else:
            pair_ip   = ""
            pair_port = ""

        self._set_entry(self.pair_address_entry, pair_ip)
        self._set_entry(self.pair_port_entry,    pair_port)

    def _save_inputs(self):
        """Persist user input to config, excluding the pairing code."""
        if not self.config:
            return
        try:
            cfg = self.config.load()
            cfg["wireless_connect_ip"]   = self.ip_entry.get().strip()
            cfg["wireless_connect_port"] = self.port_entry.get().strip()
            cfg["wireless_pair_ip"]      = self.pair_address_entry.get().strip()
            cfg["wireless_pair_port"]    = self.pair_port_entry.get().strip()
            self.config.save(cfg)
            logger.debug("Wireless dialog inputs saved")
        except Exception as e:
            logger.warning(f"Could not save wireless dialog inputs: {e}")

    def _update_status(self):
        """Refresh the status label and disconnect button."""
        if not self.scrcpy_manager.serial:
            text  = "No device connected"
            color = BORDER_COLOUR
            disc_state = "disabled"
        elif self.scrcpy_manager.connection_mode == "wireless":
            text  = f"Connected wirelessly to: {self.scrcpy_manager.serial}"
            color = SUCCESS_COLOUR
            disc_state = "normal"
        elif self.scrcpy_manager.connection_mode == "usb":
            text  = f"Connected via USB: {self.scrcpy_manager.serial}"
            color = WARNING_COLOUR
            disc_state = "disabled"
        else:
            text  = f"Connected: {self.scrcpy_manager.serial} (mode unknown)"
            color = ACCENT2_COLOUR
            disc_state = "disabled"

        self.status_label.configure(text=text, text_color=color)
        self.disconnect_btn.configure(state=disc_state)

    def _validate_ip(self, ip):
        """Check that a string is a well-formed IPv4 address."""
        if not re.match(r"^(\d{1,3}\.){3}\d{1,3}$", ip):
            return False
        return all(0 <= int(p) <= 255 for p in ip.split("."))

    # Button callbacks
    def _on_connect(self):
        """Validate fields and attempt a wireless ADB connection by IP."""
        ip   = self.ip_entry.get().strip()
        port = self.port_entry.get().strip()

        if not self._validate_ip(ip):
            self._msgbox_error(
                "Invalid IP Address",
                "Please enter a valid IP address.\n\n"
                "Example: 192.168.1.100\n\n"
                "Find this in: Settings -> Developer Options -> Wireless Debugging",
            )
            return

        try:
            port_num = int(port)
            if not (1 <= port_num <= 65535):
                raise ValueError()
        except ValueError:
            self._msgbox_error(
                "Invalid Port",
                "Please enter a valid port number between 1 and 65535.\n\n"
                "The default port is usually 5555.",
            )
            return

        logger.info(f"Attempting wireless connection to {ip}:{port}")

        self.connect_btn.configure(state="disabled", text="Connecting...")
        self.dialog.update()

        try:
            success = self.scrcpy_manager.connect_wireless(ip, port_num)
            if success:
                self._msgbox_info(
                    "Connection Successful",
                    f"Successfully connected to {ip}:{port}\n\n"
                    "You can now close the Wireless Connection Window and start using DualCPY wirelessly!\n"
                    "You may have to restart DualCPY for changes to take effect.\n"
                    "If the DualCPY main window doesn't open check it's not open in the background!",
                )
                self.result = "connected"
                self._update_status()
            else:
                self._msgbox_error(
                    "Connection Failed",
                    f"Could not connect to {ip}:{port}\n\n"
                    "Please check the following:\n\n"
                    "- Your device is powered on\n"
                    "- Both devices are on the same Wi-Fi network\n"
                    "- Wireless debugging is enabled on your Thor\n"
                    "- The IP address and port are correct\n"
                    "- You've successfully paired the device first (if first time)",
                )
        finally:
            self.connect_btn.configure(state="normal", text="Connect Now")

    def _on_pair(self):
        """Validate fields and attempt ADB wireless pairing using a 6-digit code."""
        ip           = self.pair_address_entry.get().strip()
        port_str     = self.pair_port_entry.get().strip()
        pairing_code = self.pair_code_entry.get().strip()

        if not self._validate_ip(ip):
            self._msgbox_error(
                "Invalid IP Address",
                "Please enter a valid IP address from the pairing screen.\n\n"
                "Example: 192.168.1.100",
            )
            return

        try:
            port_num = int(port_str)
            if not (1 <= port_num <= 65535):
                raise ValueError()
        except ValueError:
            self._msgbox_error(
                "Invalid Port",
                "Please enter the port number shown on the pairing screen.\n\n"
                "This is usually a 5-digit number like 37855.",
            )
            return

        if not pairing_code or not pairing_code.isdigit() or len(pairing_code) != 6:
            self._msgbox_error(
                "Invalid Pairing Code",
                "Please enter the 6-digit pairing code exactly as shown on your device.\n\n"
                "Find this in:\n"
                "Settings -> Developer Options -> Wireless Debugging -> Pair device with pairing code\n\n"
                "Note: The code expires after a short time. Generate a new one if needed.",
            )
            return

        address = f"{ip}:{port_str}"
        logger.info(f"Attempting to pair with {address}")

        self.pair_btn.configure(state="disabled", text="Pairing...")
        self.dialog.update()

        try:
            success = self.scrcpy_manager.pair_wireless(ip, port_num, pairing_code)
            if success:
                self._msgbox_info(
                    "Pairing Successful",
                    f"Successfully paired with {address}!\n\n"
                    "Next Step:\n"
                    "Use the 'Quick Connect' section above to connect.\n\n"
                    "Use the IP address and port shown in the main\n"
                    "'Wireless Debugging' settings (NOT the pairing screen).",
                )
                self._set_entry(self.ip_entry, ip)
                self._set_entry(self.pair_code_entry, "")
            else:
                self._msgbox_error(
                    "Pairing Failed",
                    f"Could not pair with {address}\n\n"
                    "Please check the following:\n\n"
                    "- Your device is powered on\n"
                    "- Both devices are on the same Wi-Fi network\n"
                    "- Wireless debugging is enabled\n"
                    "- The IP, port, and pairing code are entered correctly\n"
                    "- The pairing code hasn't expired\n\n"
                    "Tip: Try generating a new pairing code on your device.",
                )
        finally:
            self.pair_btn.configure(state="normal", text="Pair Device")

    def _on_disconnect(self):
        """Prompt the user to confirm, then disconnect the active wireless device."""
        if not self.scrcpy_manager.serial:
            return
        if self._msgbox_yesno(
            "Disconnect Device?",
            f"Are you sure you want to disconnect from:\n\n{self.scrcpy_manager.serial}\n\n"
            "You'll need to reconnect to use DualCPY wirelessly again.",
        ):
            logger.info("Disconnecting wireless device")
            success = self.scrcpy_manager.disconnect_wireless()
            if success:
                self._msgbox_info(
                    "Disconnected",
                    "Device disconnected successfully.\n\n"
                    "You can reconnect anytime using the 'Quick Connect' section.",
                )
                self.result = "disconnected"
                self._update_status()
            else:
                self._msgbox_error(
                    "Disconnection Failed",
                    "Failed to disconnect the device.\n\n"
                    "Try restarting DualCPY if the problem persists.",
                )

    def _on_close(self):
        """Save inputs, release modal grab, then destroy the dialog."""
        self._save_inputs()
        try:
            self.dialog.grab_release()
        except Exception as e:
            logger.warning(f"Error releasing dialog grab: {e}")
        try:
            self.dialog.destroy()
        except Exception as e:
            logger.warning(f"Error destroying dialog: {e}")

        # Bring the main DualCPY Control Panel window back to foreground
        try:
            user32 = ctypes.windll.user32
            hwnd = user32.FindWindowW(None, "DualCPY Control Panel")
            if hwnd:
                user32.ShowWindow(hwnd, 9)
                user32.SetForegroundWindow(hwnd)
                logger.debug("Main DualCPY window brought to foreground")
            else:
                logger.debug("Could not find DualCPY Control Panel window")
        except Exception as e:
            logger.warning(f"Error bringing main window to foreground: {e}")

        logger.info("Wireless connection dialog closed")

    # Message box helpers (CTK-native dialogs)
    def _msgbox_info(self, title, message):
        dlg = ctk.CTkInputDialog(text=message, title=title)
        # CTkInputDialog is the closest built-in; use CTkToplevel for a proper info box
        # We build a lightweight one so it matches the dark theme.
        dlg.destroy()
        self._simple_dialog(title, message, kind="info")

    def _msgbox_error(self, title, message):
        self._simple_dialog(title, message, kind="error")

    def _msgbox_yesno(self, title, message):
        return self._simple_dialog(title, message, kind="yesno")

    def _simple_dialog(self, title, message, kind="info"):
        """
        Simple themed message dialog
        """
        result_holder = [None]

        win = ctk.CTkToplevel(self.dialog)
        win.title(title)
        win.configure(fg_color=BG_COLOUR)
        win.resizable(False, False)
        win.grab_set()
        win.lift()
        win.focus_force()

        apply_window_icon(win)

        # Dark titlebar
        try:
            win.update_idletasks()
            hwnd = ctypes.windll.user32.GetParent(win.winfo_id())
            if not hwnd:
                hwnd = win.winfo_id()
            if _HAS_DARK_TITLEBAR:
                enable_dark_titlebar(hwnd)
        except Exception:
            pass

        # Icon colour strip at top
        accent = DANGER_COLOUR if kind == "error" else ACCENT_COLOUR
        ctk.CTkFrame(win, height=4, fg_color=accent).pack(fill="x")

        ctk.CTkLabel(
            win,
            text=message,
            font=make_font(12),
            text_color=TEXT_COLOUR,
            wraplength=380,
            justify="left",
        ).pack(padx=24, pady=(18, 12))

        btn_row = ctk.CTkFrame(win, fg_color="transparent")
        btn_row.pack(padx=24, pady=(0, 18))

        if kind == "yesno":
            ctk.CTkButton(
                btn_row, text="Yes",
                fg_color=ACCENT_COLOUR, hover_color=ACCENT2_COLOUR,
                text_color=TEXT_COLOUR, font=make_font(13), width=80,
                command=lambda: (result_holder.__setitem__(0, True), win.destroy()),
            ).pack(side="left", padx=(0, 8))
            ctk.CTkButton(
                btn_row, text="No",
                fg_color=PANEL_COLOUR, hover_color=BORDER_COLOUR,
                border_color=BORDER_COLOUR, border_width=1,
                text_color=TEXT_COLOUR, font=make_font(13), width=80,
                command=lambda: (result_holder.__setitem__(0, False), win.destroy()),
            ).pack(side="left")
        else:
            ctk.CTkButton(
                btn_row, text="OK",
                fg_color=ACCENT_COLOUR, hover_color=ACCENT2_COLOUR,
                text_color=TEXT_COLOUR, font=make_font(13), width=80,
                command=win.destroy,
            ).pack()

        # Centre over dialog
        win.update_idletasks()
        px = self.dialog.winfo_rootx() + (self.dialog.winfo_width()  - win.winfo_width())  // 2
        py = self.dialog.winfo_rooty() + (self.dialog.winfo_height() - win.winfo_height()) // 2
        win.geometry(f"+{px}+{py}")

        win.wait_window()
        return result_holder[0]

    # Public
    def show(self):
        """Block until the dialog is closed, then return the result."""
        self.dialog.wait_window()
        return self.result


def show_wireless_dialog(parent=None, scrcpy_manager=None, config=None):
    """
    Show the wireless connection dialog.
    """
    if not scrcpy_manager:
        logger.error("Cannot show wireless dialog: no scrcpy_manager provided")
        return None
    dialog = WirelessConnectionDialog(parent, scrcpy_manager, config=config)
    return dialog.show()