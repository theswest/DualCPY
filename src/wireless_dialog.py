# ThorCPY – Dual-screen scrcpy docking and control UI for Windows
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

import tkinter as tk
from tkinter import ttk, messagebox, font as tkfont
import logging
import re
import os
import sys

logger = logging.getLogger(__name__)

# Connection defaults
DEFAULT_CONNECT_PORT = "5555"

# Dialog window dimensions
DIALOG_WIDTH = 600
DIALOG_HEIGHT = 680
DIALOG_MIN_HEIGHT = 600
DIALOG_PADDING = 20

# Color scheme
COLOR_SUCCESS = "#28a745"
COLOR_WARNING = "#ffc107"
COLOR_ERROR = "#dc3545"
COLOR_INFO = "#17a2b8"
COLOR_LIGHT_BG = "#f8f9fa"

# Font configuration
FONT_FAMILY = "CalSans"
FONT_FAMILY_FALLBACK = "Arial"


def resource_path(rel):
    """
    Get absolute path to resource, works for python files and for PyInstaller
    """
    try:
        if hasattr(sys, "_MEIPASS"):
            path = os.path.join(sys._MEIPASS, rel)
            return path
        path = os.path.join(os.path.abspath("."), rel)
        return path
    except Exception as PathResolutionError:
        logger.error(f"Failed to resolve resource path for '{rel}': {PathResolutionError}")
        return rel


def load_custom_font():
    """
    Load the CalSans font for the dialog.
    Returns the font family name to use.
    """
    try:
        font_path = resource_path("assets/fonts/CalSans-Regular.ttf")
        if os.path.exists(font_path):
            # Register the font with tkinter
            # This doesn't always work reliably across all systems so we'll still use a fallback
            logger.debug(f"Found CalSans font at: {font_path}")
            return FONT_FAMILY
        else:
            logger.debug(f"CalSans font not found at {font_path}, using fallback")
            return FONT_FAMILY_FALLBACK
    except Exception as FontLoadError:
        logger.warning(f"Error loading CalSans font: {FontLoadError}, using fallback")
        return FONT_FAMILY_FALLBACK


class WirelessConnectionDialog:
    """
    Dialog for managing wireless ADB connections.

    Allows users to:
    1) Pair with a device using a pairing code (for first-time setup)
    2) Connect to a device by IP address
    3) Disconnect wireless connections
    """

    def __init__(self, parent, scrcpy_manager, config=None):
        """
        Initialize the wireless connection dialog.
        """
        self.scrcpy_manager = scrcpy_manager
        self.config = config
        self.result = None

        # Create dialog window
        self.dialog = tk.Toplevel(parent) if parent else tk.Tk()
        self.dialog.title("Wireless Connection Setup")
        self.dialog.geometry(f"{DIALOG_WIDTH}x{DIALOG_HEIGHT}")
        self.dialog.resizable(False, True)
        self.dialog.minsize(DIALOG_WIDTH, DIALOG_MIN_HEIGHT)

        # Load font family
        self.font_family = load_custom_font()

        # Create font objects
        self.font_title = (self.font_family, 16, "bold")
        self.font_header = (self.font_family, 11, "bold")
        self.font_normal = (self.font_family, 9)
        self.font_small = (self.font_family, 8)
        self.font_mono = ("Consolas", 10)
        self.font_code = ("Consolas", 14, "bold")

        # Centre dialog on screen
        self.dialog.update_idletasks()
        x = (self.dialog.winfo_screenwidth() // 2) - (DIALOG_WIDTH // 2)
        y = (self.dialog.winfo_screenheight() // 2) - (DIALOG_HEIGHT // 2)
        self.dialog.geometry(f"+{x}+{y}")

        if parent:
            self.dialog.transient(parent)

        self._create_widgets()
        self._load_inputs()

        # Grab and focus
        self.dialog.protocol("WM_DELETE_WINDOW", self._on_close)
        self.dialog.deiconify()
        self.dialog.lift()
        self.dialog.focus_force()
        self.dialog.grab_set()

        logger.info("Wireless connection dialog opened")

    def _create_widgets(self):
        """
        Build and lay out all dialog widgets with improved UX.
        Uses a scrollable canvas to handle smaller screen heights.
        """
        # Scrollable canvas setup
        canvas = tk.Canvas(self.dialog, borderwidth=0, highlightthickness=0)
        scrollbar = ttk.Scrollbar(self.dialog, orient=tk.VERTICAL, command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        main_frame = ttk.Frame(canvas, padding=DIALOG_PADDING)
        canvas_window = canvas.create_window((0, 0), window=main_frame, anchor="nw")

        # Keep scroll region in sync with content size
        main_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda e: canvas.itemconfig(canvas_window, width=e.width))
        self.dialog.bind("<MouseWheel>", lambda e: canvas.yview_scroll(int(-1 * (e.delta / 120)), "units"))

        # ==================== HEADER ====================
        header_frame = ttk.Frame(main_frame)
        header_frame.pack(fill=tk.X, pady=(0, 15))

        ttk.Label(
            header_frame,
            text="Wireless Connection Setup",
            font=self.font_title
        ).pack(anchor=tk.W)

        ttk.Label(
            header_frame,
            text="Connect your AYN Thor wirelessly without a USB cable",
            font=self.font_normal,
            foreground="gray"
        ).pack(anchor=tk.W, pady=(2, 0))

        # Add separator
        ttk.Separator(main_frame, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=(0, 15))

        # ==================== STATUS ====================
        status_frame = ttk.Frame(main_frame)
        status_frame.pack(fill=tk.X, pady=(0, 15))

        status_header = ttk.Frame(status_frame)
        status_header.pack(fill=tk.X)
        ttk.Label(
            status_header,
            text="Connection Status",
            font=self.font_header
        ).pack(side=tk.LEFT)

        self.status_label = ttk.Label(
            status_frame,
            text="Checking...",
            font=self.font_normal,
            wraplength=540
        )
        self.status_label.pack(anchor=tk.W, pady=(8, 0))

        # Add separator
        ttk.Separator(main_frame, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=(15, 15))

        # ==================== QUICK CONNECT SECTION ====================
        # This section is shown when already paired
        connect_section = ttk.Frame(main_frame)
        connect_section.pack(fill=tk.X, pady=(0, 15))

        connect_header = ttk.Frame(connect_section)
        connect_header.pack(fill=tk.X, pady=(0, 10))

        ttk.Label(
            connect_header,
            text="Already Paired? Quick Connect",
            font=self.font_header
        ).pack(side=tk.LEFT)

        # Instructions for already paired devices
        instructions_text = (
            "If you've already paired your device, enter the IP and port shown in:\n"
            "Settings → Developer Options → Wireless Debugging"
        )
        instructions_label = ttk.Label(
            connect_section,
            text=instructions_text,
            font=self.font_normal,
            foreground="gray",
            wraplength=540,
            justify=tk.LEFT
        )
        instructions_label.pack(anchor=tk.W, pady=(0, 10))

        # Connect form with improved layout
        connect_form = ttk.Frame(connect_section)
        connect_form.pack(fill=tk.X, pady=(0, 5))

        # IP Address row
        ip_row = ttk.Frame(connect_form)
        ip_row.pack(fill=tk.X, pady=(0, 8))
        ttk.Label(ip_row, text="IP Address:", width=12, anchor=tk.W, font=self.font_normal).pack(side=tk.LEFT,
                                                                                                 padx=(0, 5))
        self.ip_entry = ttk.Entry(ip_row, font=self.font_mono)
        self.ip_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10))
        ttk.Label(ip_row, text="e.g., 192.168.1.100", foreground="gray", font=self.font_small).pack(side=tk.LEFT)

        # Port row
        port_row = ttk.Frame(connect_form)
        port_row.pack(fill=tk.X, pady=(0, 10))
        ttk.Label(port_row, text="Port:", width=12, anchor=tk.W, font=self.font_normal).pack(side=tk.LEFT, padx=(0, 5))
        self.port_entry = ttk.Entry(port_row, width=15, font=self.font_mono)
        self.port_entry.pack(side=tk.LEFT, padx=(0, 10))
        ttk.Label(port_row, text="The port from the MAIN wireless debugging page", foreground="gray",
                  font=self.font_small).pack(side=tk.LEFT)

        # Connect button - prominent
        self.connect_btn = ttk.Button(
            connect_section,
            text="Connect Now",
            command=self._on_connect
        )
        self.connect_btn.pack(pady=(5, 0))

        # Add separator
        ttk.Separator(main_frame, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=(15, 15))

        # ==================== FIRST TIME PAIRING SECTION ====================
        pairing_section = ttk.Frame(main_frame)
        pairing_section.pack(fill=tk.X, pady=(0, 15))

        pairing_header = ttk.Frame(pairing_section)
        pairing_header.pack(fill=tk.X, pady=(0, 10))

        ttk.Label(
            pairing_header,
            text="First Time? Pair Your Device",
            font=self.font_header
        ).pack(side=tk.LEFT)

        # Step-by-step instructions
        steps_text = (
            "Follow these steps on your AYN Thor:\n\n"
            "1. Go to: Settings → System → Developer Options → Wireless Debugging\n"
            "2. Tap on 'Pair device with pairing code'\n"
            "3. Enter the IP Address, Port, and 6-digit code shown below"
        )
        steps_label = ttk.Label(
            pairing_section,
            text=steps_text,
            font=self.font_normal,
            foreground="gray",
            wraplength=540,
            justify=tk.LEFT
        )
        steps_label.pack(anchor=tk.W, pady=(0, 10))

        # Pairing form with improved layout
        pair_form = ttk.Frame(pairing_section)
        pair_form.pack(fill=tk.X, pady=(0, 5))

        # IP Address row
        pair_ip_row = ttk.Frame(pair_form)
        pair_ip_row.pack(fill=tk.X, pady=(0, 8))
        ttk.Label(pair_ip_row, text="IP Address:", width=12, anchor=tk.W, font=self.font_normal).pack(side=tk.LEFT,
                                                                                                      padx=(0, 5))
        self.pair_address_entry = ttk.Entry(pair_ip_row, font=self.font_mono)
        self.pair_address_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10))
        ttk.Label(pair_ip_row, text="From pairing screen", foreground="gray", font=self.font_small).pack(side=tk.LEFT)

        # Port row
        pair_port_row = ttk.Frame(pair_form)
        pair_port_row.pack(fill=tk.X, pady=(0, 8))
        ttk.Label(pair_port_row, text="Port:", width=12, anchor=tk.W, font=self.font_normal).pack(side=tk.LEFT,
                                                                                                  padx=(0, 5))
        self.pair_port_entry = ttk.Entry(pair_port_row, width=15, font=self.font_mono)
        self.pair_port_entry.pack(side=tk.LEFT, padx=(0, 10))
        ttk.Label(pair_port_row, text="From pairing screen", foreground="gray", font=self.font_small).pack(side=tk.LEFT)

        # Pairing code row
        pair_code_row = ttk.Frame(pair_form)
        pair_code_row.pack(fill=tk.X, pady=(0, 10))
        ttk.Label(pair_code_row, text="Pairing Code:", width=12, anchor=tk.W, font=self.font_normal).pack(side=tk.LEFT,
                                                                                                          padx=(0, 5))
        self.pair_code_entry = ttk.Entry(pair_code_row, width=15, font=self.font_code)
        self.pair_code_entry.pack(side=tk.LEFT, padx=(0, 10))
        ttk.Label(pair_code_row, text="6-digit code", foreground="gray", font=self.font_small).pack(side=tk.LEFT)

        # Pair button - prominent
        self.pair_btn = ttk.Button(
            pairing_section,
            text="Pair Device",
            command=self._on_pair
        )
        self.pair_btn.pack(pady=(5, 0))

        # Add separator
        ttk.Separator(main_frame, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=(15, 10))

        # ==================== BOTTOM ACTIONS ====================
        bottom_frame = ttk.Frame(main_frame)
        bottom_frame.pack(fill=tk.X, pady=(10, 0))

        # Left side - disconnect button
        left_actions = ttk.Frame(bottom_frame)
        left_actions.pack(side=tk.LEFT)
        self.disconnect_btn = ttk.Button(
            left_actions,
            text="Disconnect",
            command=self._on_disconnect,
            state=tk.DISABLED
        )
        self.disconnect_btn.pack(side=tk.LEFT)

        # Right side - close button
        right_actions = ttk.Frame(bottom_frame)
        right_actions.pack(side=tk.RIGHT)
        ttk.Button(
            right_actions,
            text="Close",
            command=self._on_close
        ).pack(side=tk.RIGHT)

        self._update_status()

    def _set_entry(self, entry, value):
        """Clear and set an entry widget's text."""
        entry.delete(0, tk.END)
        if value:
            entry.insert(0, value)

    def _load_inputs(self):
        """
        Populate fields in priority order:
          1. Active wireless connection — autofill Connect IP + port from live serial
          2. Saved config values
          3. Default port 5555, everything else empty
        Pairing code is never saved or pre-filled.
        """
        serial = self.scrcpy_manager.serial
        mode = self.scrcpy_manager.connection_mode

        # Connect by IP. prefer live connection, fall back to saved, then defaults
        if serial and mode == 'wireless' and ':' in serial:
            connect_ip, connect_port = serial.rsplit(':', 1)
            logger.debug(f"Autofilling connect fields from live connection: {serial}")
        elif self.config:
            connect_ip = self.config.get("wireless_connect_ip", "")
            connect_port = self.config.get("wireless_connect_port", DEFAULT_CONNECT_PORT)
        else:
            connect_ip = ""
            connect_port = DEFAULT_CONNECT_PORT

        self._set_entry(self.ip_entry, connect_ip)
        self._set_entry(self.port_entry, connect_port)

        # Pair fields: prefer saved values, pairing code always empty
        if self.config:
            pair_ip = self.config.get("wireless_pair_ip", "")
            pair_port = self.config.get("wireless_pair_port", "")
        else:
            pair_ip = ""
            pair_port = ""

        self._set_entry(self.pair_address_entry, pair_ip)
        self._set_entry(self.pair_port_entry, pair_port)

    def _save_inputs(self):
        """Persist user input to config, excluding the pairing code."""
        if not self.config:
            return
        try:
            cfg = self.config.load()
            cfg["wireless_connect_ip"] = self.ip_entry.get().strip()
            cfg["wireless_connect_port"] = self.port_entry.get().strip()
            cfg["wireless_pair_ip"] = self.pair_address_entry.get().strip()
            cfg["wireless_pair_port"] = self.pair_port_entry.get().strip()
            self.config.save(cfg)
            logger.debug("Wireless dialog inputs saved")
        except Exception as ConfigSaveError:
            logger.warning(f"Could not save wireless dialog inputs: {ConfigSaveError}")

    def _update_status(self):
        """Refresh the status label and disconnect button to reflect current connection state."""
        if not self.scrcpy_manager.serial:
            status_text = "No device connected"
            status_color = "gray"
            self.disconnect_btn.config(state=tk.DISABLED)
        elif self.scrcpy_manager.connection_mode == 'wireless':
            status_text = f"Connected wirelessly to: {self.scrcpy_manager.serial}"
            status_color = COLOR_SUCCESS
            self.disconnect_btn.config(state=tk.NORMAL)
        elif self.scrcpy_manager.connection_mode == 'usb':
            status_text = f"Connected via USB: {self.scrcpy_manager.serial}"
            status_color = COLOR_WARNING
            self.disconnect_btn.config(state=tk.DISABLED)
        else:
            status_text = f"Connected: {self.scrcpy_manager.serial} (mode unknown)"
            status_color = COLOR_INFO
            self.disconnect_btn.config(state=tk.DISABLED)

        self.status_label.config(text=status_text, foreground=status_color)

    def _validate_ip(self, ip):
        """Check that a string is a well-formed IPv4 address."""
        if not re.match(r'^(\d{1,3}\.){3}\d{1,3}$', ip):
            return False
        return all(0 <= int(p) <= 255 for p in ip.split('.'))

    def _on_connect(self):
        """
        Validate fields and attempt a wireless ADB connection by IP.
        Disables the connect button during the attempt to prevent double-clicks.
        """
        ip = self.ip_entry.get().strip()
        port = self.port_entry.get().strip()

        if not self._validate_ip(ip):
            messagebox.showerror(
                "Invalid IP Address",
                "Please enter a valid IP address.\n\n"
                "Example: 192.168.1.100\n\n"
                "Find this in: Settings → Developer Options → Wireless Debugging"
            )
            return

        try:
            port_num = int(port)
            if port_num < 1 or port_num > 65535:
                raise ValueError()
        except ValueError:
            messagebox.showerror(
                "Invalid Port",
                "Please enter a valid port number between 1 and 65535.\n\n"
                "The default port is usually 5555."
            )
            return

        logger.info(f"Attempting wireless connection to {ip}:{port}")

        # Disable button to prevent double-clicks during connection attempt
        self.connect_btn.config(state=tk.DISABLED, text="Connecting...")
        self.dialog.update()

        try:
            success = self.scrcpy_manager.connect_wireless(ip, port_num)
            if success:
                messagebox.showinfo(
                    "Connection Successful",
                    f"Successfully connected to {ip}:{port}\n\n"
                    "You can now close the Wireless Connection Window and start using ThorCPY wirelessly!\n"
                    "You may have to restart ThorCPY for changes to take effect.\n"
                    "If the ThorCPY main window doesn't open check it's not open in the background!"
                )
                self.result = 'connected'
                self._update_status()
            else:
                messagebox.showerror(
                    "Connection Failed",
                    f"Could not connect to {ip}:{port}\n\n"
                    "Please check the following:\n\n"
                    "• Your device is powered on\n"
                    "• Both devices are on the same Wi-Fi network\n"
                    "• Wireless debugging is enabled on your Thor\n"
                    "• The IP address and port are correct\n"
                    "• You've successfully paired the device first (if first time)"
                )
        finally:
            self.connect_btn.config(state=tk.NORMAL, text="Connect Now")

    def _on_pair(self):
        """
        Validate fields and attempt ADB wireless pairing using a 6-digit code.
        On success, autofills the Connect IP field to streamline the follow-up connection step.
        """
        ip = self.pair_address_entry.get().strip()
        port_str = self.pair_port_entry.get().strip()
        pairing_code = self.pair_code_entry.get().strip()

        if not self._validate_ip(ip):
            messagebox.showerror(
                "Invalid IP Address",
                "Please enter a valid IP address from the pairing screen.\n\n"
                "Example: 192.168.1.100"
            )
            return

        try:
            port_num = int(port_str)
            if port_num < 1 or port_num > 65535:
                raise ValueError()
        except ValueError:
            messagebox.showerror(
                "Invalid Port",
                "Please enter the port number shown on the pairing screen.\n\n"
                "This is usually a 5-digit number like 37855."
            )
            return

        if not pairing_code or not pairing_code.isdigit() or len(pairing_code) != 6:
            messagebox.showerror(
                "Invalid Pairing Code",
                "Please enter the 6-digit pairing code exactly as shown on your device.\n\n"
                "Find this in:\n"
                "Settings → Developer Options → Wireless Debugging → Pair device with pairing code\n\n"
                "Note: The code expires after a short time. Generate a new one if needed."
            )
            return

        address = f"{ip}:{port_str}"
        logger.info(f"Attempting to pair with {address}")

        # Disable button to prevent double-clicks during pairing attempt
        self.pair_btn.config(state=tk.DISABLED, text="Pairing...")
        self.dialog.update()

        try:
            success = self.scrcpy_manager.pair_wireless(ip, port_num, pairing_code)
            if success:
                messagebox.showinfo(
                    "Pairing Successful",
                    f"Successfully paired with {address}!\n\n"
                    "Next Step:\n"
                    "Use the 'Quick Connect' section above to connect.\n\n"
                    "Use the IP address and port shown in the main\n"
                    "'Wireless Debugging' settings (NOT the pairing screen)."
                )
                # Autofill connect IP to reduce friction for the follow-up step
                self._set_entry(self.ip_entry, ip)
                # Clear pairing code for security
                self._set_entry(self.pair_code_entry, "")
            else:
                messagebox.showerror(
                    "Pairing Failed",
                    f"Could not pair with {address}\n\n"
                    "Please check the following:\n\n"
                    "• Your device is powered on\n"
                    "• Both devices are on the same Wi-Fi network\n"
                    "• Wireless debugging is enabled\n"
                    "• The IP, port, and pairing code are entered correctly\n"
                    "• The pairing code hasn't expired\n\n"
                    "Tip: Try generating a new pairing code on your device."
                )
        finally:
            self.pair_btn.config(state=tk.NORMAL, text="Pair Device")

    def _on_disconnect(self):
        """Prompt the user to confirm, then disconnect the active wireless device."""
        if not self.scrcpy_manager.serial:
            return
        if messagebox.askyesno(
                "Disconnect Device?",
                f"Are you sure you want to disconnect from:\n\n{self.scrcpy_manager.serial}\n\n"
                "You'll need to reconnect to use ThorCPY wirelessly again."
        ):
            logger.info("Disconnecting wireless device")
            success = self.scrcpy_manager.disconnect_wireless()
            if success:
                messagebox.showinfo(
                    "Disconnected",
                    "Device disconnected successfully.\n\n"
                    "You can reconnect anytime using the 'Quick Connect' section."
                )
                self.result = 'disconnected'
                self._update_status()
            else:
                messagebox.showerror(
                    "Disconnection Failed",
                    "Failed to disconnect the device.\n\n"
                    "Try restarting ThorCPY if the problem persists."
                )

    def _on_close(self):
        """
        Save inputs, release modal grab, then destroy the dialog.
        Brings the main ThorCPY pygame window to foreground after closing.
        Operations are ordered to avoid Tkinter errors on destruction.
        """
        self._save_inputs()
        try:
            self.dialog.grab_release()
        except Exception as GrabReleaseError:
            logger.warning(f"Error releasing dialog grab: {GrabReleaseError}")
        try:
            self.dialog.destroy()
        except Exception as DialogDestroyError:
            logger.warning(f"Error destroying dialog: {DialogDestroyError}")

        # Bring the main ThorCPY pygame window to foreground
        try:
            import ctypes
            from ctypes import wintypes

            user32 = ctypes.windll.user32

            # Find the ThorCPY Control Panel window by title
            hwnd = user32.FindWindowW(None, "ThorCPY Control Panel")

            if hwnd:
                # Bring window to foreground
                # SW_RESTORE = 9 (restore if minimized)
                user32.ShowWindow(hwnd, 9)
                user32.SetForegroundWindow(hwnd)
                logger.debug("Main ThorCPY window brought to foreground")
            else:
                logger.debug("Could not find ThorCPY Control Panel window")
        except Exception as ForegroundError:
            logger.warning(f"Error bringing main window to foreground: {ForegroundError}")

        logger.info("Wireless connection dialog closed")

    def show(self):
        """Block until the dialog is closed, then return the result."""
        self.dialog.wait_window()
        return self.result


def show_wireless_dialog(parent=None, scrcpy_manager=None, config=None):
    """
    Show the wireless connection dialog.
    parent is optional, scrcpy_manager is required, config is optional for persisting inputs.
    """
    if not scrcpy_manager:
        logger.error("Cannot show wireless dialog: no scrcpy_manager provided")
        return None
    dialog = WirelessConnectionDialog(parent, scrcpy_manager, config=config)
    return dialog.show()