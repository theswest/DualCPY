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
from tkinter import ttk, messagebox
import logging
import re

logger = logging.getLogger(__name__)

# Connection defaults
DEFAULT_CONNECT_PORT = "5555"

# Dialog window dimensions
DIALOG_WIDTH = 520
DIALOG_HEIGHT = 620
DIALOG_MIN_HEIGHT = 580
DIALOG_PADDING = 15


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
        self.dialog.title("Wireless Connection")
        self.dialog.geometry(f"{DIALOG_WIDTH}x{DIALOG_HEIGHT}")
        self.dialog.resizable(False, True)
        self.dialog.minsize(DIALOG_WIDTH, DIALOG_MIN_HEIGHT)

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
        Build and lay out all dialog widgets.
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

        # Dialog heading
        ttk.Label(main_frame, text="Wireless ADB Connection", font=("Arial", 14, "bold")).pack(pady=(0, 10))

        # Current connection status
        status_frame = ttk.LabelFrame(main_frame, text="Current Status", padding=8)
        status_frame.pack(fill=tk.X, pady=(0, 10))
        self.status_label = ttk.Label(status_frame, text="Checking...", wraplength=460)
        self.status_label.pack()

        # Connect by IP section
        connect_frame = ttk.LabelFrame(main_frame, text="Connect by IP", padding=8)
        connect_frame.pack(fill=tk.X, pady=(0, 10))
        ip_frame = ttk.Frame(connect_frame)
        ip_frame.pack(fill=tk.X, pady=(0, 5))
        ttk.Label(ip_frame, text="IP Address:").pack(side=tk.LEFT, padx=(0, 5))
        self.ip_entry = ttk.Entry(ip_frame, width=20)
        self.ip_entry.pack(side=tk.LEFT, padx=(0, 5))
        ttk.Label(ip_frame, text="Port:").pack(side=tk.LEFT, padx=(5, 5))
        self.port_entry = ttk.Entry(ip_frame, width=8)
        self.port_entry.pack(side=tk.LEFT)
        self.connect_btn = ttk.Button(connect_frame, text="Connect", command=self._on_connect)
        self.connect_btn.pack(pady=(5, 0))

        # Pairing section: used for first-time wireless setup
        pairing_frame = ttk.LabelFrame(main_frame, text="Pair with Code (First Time Setup)", padding=8)
        pairing_frame.pack(fill=tk.X, pady=(0, 10))
        ttk.Label(
            pairing_frame,
            text="Go to Settings > Developer options > Wireless debugging, then tap\n"
                 "'Pair device with pairing code' to get your IP, Port and 6-digit code.",
            wraplength=460, justify=tk.LEFT
        ).pack(pady=(0, 8), anchor=tk.W)
        pair_input_frame = ttk.Frame(pairing_frame)
        pair_input_frame.pack(fill=tk.X, pady=(0, 5))
        ttk.Label(pair_input_frame, text="IP Address:").pack(side=tk.LEFT, padx=(0, 4))
        self.pair_address_entry = ttk.Entry(pair_input_frame, width=16)
        self.pair_address_entry.pack(side=tk.LEFT, padx=(0, 8))
        ttk.Label(pair_input_frame, text="Port:").pack(side=tk.LEFT, padx=(0, 4))
        self.pair_port_entry = ttk.Entry(pair_input_frame, width=8)
        self.pair_port_entry.pack(side=tk.LEFT, padx=(0, 8))
        ttk.Label(pair_input_frame, text="Code:").pack(side=tk.LEFT, padx=(0, 4))
        self.pair_code_entry = ttk.Entry(pair_input_frame, width=10)
        self.pair_code_entry.pack(side=tk.LEFT)
        self.pair_btn = ttk.Button(pairing_frame, text="Pair Device", command=self._on_pair)
        self.pair_btn.pack(pady=(5, 0))

        # Bottom action bar
        bottom_frame = ttk.Frame(main_frame)
        bottom_frame.pack(fill=tk.X)
        self.disconnect_btn = ttk.Button(
            bottom_frame, text="Disconnect Wireless",
            command=self._on_disconnect, state=tk.DISABLED
        )
        self.disconnect_btn.pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(bottom_frame, text="Close", command=self._on_close).pack(side=tk.RIGHT)

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

        # Pairing fields from saved configs
        pair_ip = self.config.get("wireless_pair_ip", "") if self.config else ""
        pair_port = self.config.get("wireless_pair_port", "") if self.config else ""
        self._set_entry(self.pair_address_entry, pair_ip)
        self._set_entry(self.pair_port_entry, pair_port)

    def _save_inputs(self):
        """
        Persist current field values to config.
        Pairing code is intentionally never saved.
        """
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
            self.disconnect_btn.config(state=tk.DISABLED)
        elif self.scrcpy_manager.connection_mode == 'wireless':
            status_text = f"Connected wirelessly: {self.scrcpy_manager.serial}"
            self.disconnect_btn.config(state=tk.NORMAL)
        elif self.scrcpy_manager.connection_mode == 'usb':
            status_text = f"Connected via USB: {self.scrcpy_manager.serial}"
            self.disconnect_btn.config(state=tk.DISABLED)
        else:
            status_text = f"Connected: {self.scrcpy_manager.serial} (mode unknown)"
            self.disconnect_btn.config(state=tk.DISABLED)
        self.status_label.config(text=status_text)

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
            messagebox.showerror("Invalid IP", "Please enter a valid IP address (e.g., 192.168.1.100)")
            return

        try:
            port_num = int(port)
            if port_num < 1 or port_num > 65535:
                raise ValueError()
        except ValueError:
            messagebox.showerror("Invalid Port", "Please enter a valid port number (1-65535)")
            return

        logger.info(f"Attempting wireless connection to {ip}:{port}")

        # Disable button to prevent double-clicks during connection attempt
        self.connect_btn.config(state=tk.DISABLED, text="Connecting...")
        self.dialog.update()

        try:
            success = self.scrcpy_manager.connect_wireless(ip, port_num)
            if success:
                messagebox.showinfo(
                    "Success",
                    f"Successfully connected to {ip}:{port}\n\n"
                    "You can now close this dialog and start scrcpy."
                )
                self.result = 'connected'
                self._update_status()
            else:
                messagebox.showerror(
                    "Connection Failed",
                    f"Could not connect to {ip}:{port}\n\n"
                    "Please check:\n"
                    "• Device is on and connected to the same network\n"
                    "• Wireless debugging is enabled on the device\n"
                    "• IP address and port are correct"
                )
        finally:
            self.connect_btn.config(state=tk.NORMAL, text="Connect")

    def _on_pair(self):
        """
        Validate fields and attempt ADB wireless pairing using a 6-digit code.
        On success, autofills the Connect IP field to streamline the follow-up connection step.
        """
        ip = self.pair_address_entry.get().strip()
        port_str = self.pair_port_entry.get().strip()
        pairing_code = self.pair_code_entry.get().strip()

        if not self._validate_ip(ip):
            messagebox.showerror("Invalid IP", "Please enter a valid IP address (e.g., 192.168.1.100)")
            return

        try:
            port_num = int(port_str)
            if port_num < 1 or port_num > 65535:
                raise ValueError()
        except ValueError:
            messagebox.showerror("Invalid Port", "Please enter a valid port number (1-65535)")
            return

        if not pairing_code or not pairing_code.isdigit() or len(pairing_code) != 6:
            messagebox.showerror(
                "Invalid Pairing Code",
                "Please enter a 6-digit pairing code from your device's\n'Wireless debugging' settings."
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
                    "Now connect using the 'Connect by IP' section.\n"
                    "Use the IP and Port shown in the main Wireless debugging settings."
                )
                # Autofill connect IP to reduce friction for the follow-up step
                self._set_entry(self.ip_entry, ip)
            else:
                messagebox.showerror(
                    "Pairing Failed",
                    f"Could not pair with {address}\n\n"
                    "Please check:\n"
                    "• Device is on and connected to the same network\n"
                    "• Wireless debugging is enabled on the device\n"
                    "• IP address, port and pairing code are correct\n"
                    "• The pairing code hasn't expired (generate a new one if needed)"
                )
        finally:
            self.pair_btn.config(state=tk.NORMAL, text="Pair Device")

    def _on_disconnect(self):
        """Prompt the user to confirm, then disconnect the active wireless device."""
        if not self.scrcpy_manager.serial:
            return
        if messagebox.askyesno("Disconnect", f"Disconnect from {self.scrcpy_manager.serial}?"):
            logger.info("Disconnecting wireless device")
            success = self.scrcpy_manager.disconnect_wireless()
            if success:
                messagebox.showinfo("Disconnected", "Device disconnected successfully.")
                self.result = 'disconnected'
                self._update_status()
            else:
                messagebox.showerror("Error", "Failed to disconnect device.")

    def _on_close(self):
        """
        Save inputs, release modal grab, then destroy the dialog.
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