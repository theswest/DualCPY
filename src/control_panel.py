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

# src/control_panel.py

import os
import sys
import time
import dxcam
import ctypes
import logging
import win32clipboard
import tkinter as tk
import customtkinter as ctk
from PIL import Image
from io import BytesIO
from ctypes import windll, wintypes

from src.win32_darkmode import enable_dark_titlebar
from src.file_transfer_dialog import FileTransferDialog
from src.ui_constants import (
    BG_COLOUR, PANEL_COLOUR, BORDER_COLOUR, TEXT_COLOUR,
    ACCENT_COLOUR, ACCENT2_COLOUR, TOP_COLOUR, BOTTOM_COLOUR,
    SUCCESS_COLOUR, DANGER_COLOUR, WARNING_COLOUR,
    CALSANS_FAMILY, ICON_PATH, FONT_PATH,
    resource_path, load_calsans, make_font, apply_window_icon,
)
from src.device_profile_editor import DeviceProfileEditorDialog

logger = logging.getLogger(__name__)

# Slider range constraints
SCREEN_MIN_POS = -500
SCREEN_MAX_POS = 1500
GLOBAL_SCALE_MIN = 0.3
GLOBAL_SCALE_MAX = 2.5

# Timing
STATUS_MESSAGE_DURATION = 2.0
ERROR_STATUS_DURATION = 3.0
PRESET_CACHE_TIME = 0.5
UPDATE_INTERVAL_MS = 16
LOADING_SCREEN_DURATION = 2000

# Misc
DEFAULT_PRESET_NAME = "NewPreset"
SCALE_CHANGE_THRESHOLD = 0.01

# Win32 SetWindowPos flags
SWP_NOZORDER = 0x0004
SWP_NOACTIVATE = 0x0010
SWP_FRAMECHANGED = 0x0020
SWP_NOMOVE = 0x0002
SWP_NOSIZE = 0x0001
SW_SHOW = 5

# GDI clipboard/copy constants
CF_BITMAP = 2
SRCCOPY = 0x00CC0020

# Loading screen
def show_loading_screen():
    """
    Shows a brief splash screen centered dynamically on the user's monitor.
    """
    logger.info("Showing loading screen")
    load_calsans()
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")

    splash = ctk.CTk()
    splash.iconbitmap()
    splash.title("DualCPY Loading...")

    window_width = 480
    window_height = 190
    screen_width = splash.winfo_screenwidth()
    screen_height = splash.winfo_screenheight()
    center_x = (screen_width - window_width) // 2
    center_y = (screen_height - window_height) // 2.5

    splash.geometry(f"{window_width}x{window_height}+{center_x}+{center_y}")

    splash.resizable(False, False)
    splash.configure(fg_color=BG_COLOUR)

    apply_window_icon(splash)

    # Horizontal layout: DualCPY logo on the left, text block to its right.
    content = ctk.CTkFrame(splash, fg_color="transparent")
    content.pack(expand=True, padx=28)

    try:
        logo_ctk = ctk.CTkImage(Image.open(ICON_PATH), size=(96, 96))
        logo_lbl = ctk.CTkLabel(content, image=logo_ctk, text="")
        logo_lbl._logo_ref = logo_ctk  # keep a reference so it isn't GC'd
        logo_lbl.pack(side="left", padx=(0, 22))
    except Exception as e:
        logger.warning(f"Splash logo failed to load: {e}")

    # Text block sits to the right of the logo, left-aligned within itself.
    text_block = ctk.CTkFrame(content, fg_color="transparent")
    text_block.pack(side="left")

    title_frame = ctk.CTkFrame(text_block, fg_color="transparent")
    title_frame.pack(anchor="w")

    ctk.CTkLabel(
        title_frame,
        text="Dual",
        font=make_font(45, "bold"),
        text_color=ACCENT_COLOUR,
    ).pack(side="left")

    ctk.CTkLabel(
        title_frame,
        text="CPY",
        font=make_font(45, "bold"),
        text_color=ACCENT2_COLOUR,
    ).pack(side="left")

    ctk.CTkLabel(
        text_block,
        text="Starting up...",
        font=make_font(22),
        text_color=TEXT_COLOUR,
    ).pack(anchor="w")

    def _after_idle():
        try:
            splash.update_idletasks()
            hwnd = ctypes.windll.user32.GetParent(splash.winfo_id())
            if not hwnd:
                hwnd = splash.winfo_id()
            enable_dark_titlebar(hwnd)
        except Exception:
            pass

        # Clean shutdown sequence
        def _close_safely():
            splash.quit()
            splash.destroy()

        splash.after(LOADING_SCREEN_DURATION, _close_safely)

    splash.after(50, _after_idle)
    splash.mainloop()
    logger.info("Loading screen closed")


# Main UI
class CTkUI:
    """
    Main control panel
    """
    def __init__(self, launcher):
        logger.info("Initializing Control Panel UI")
        self.l = launcher

        # Making sure that calsans is loaded
        load_calsans()

        # Status bar
        self.status_msg = ""
        self.status_type = "info"
        self._status_after_id = None

        # Preset cache
        self._preset_cache = None
        self._preset_cache_time = 0.0

        # Scale-change tracking
        self._original_scale = self.l.global_scale or 0.6
        self._scale_changed = False
        self._slider_refs = {}

        # Main Window
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self.window = ctk.CTk()
        self.window.iconbitmap()
        self.window.title("DualCPY Control Panel")
        self.window.configure(fg_color=BG_COLOUR)
        self.window.minsize(360, 640)

        # Panel positioning
        try:
            panel_width = 460
            panel_height = 920

            screen_width = self.window.winfo_screenwidth()
            screen_height = self.window.winfo_screenheight()

            # Divide screen into 3 columns
            one_third = screen_width // 3
            right_third_start = one_third * 2

            # Find the midpoint of the rightmost column, then center the panel in it
            pos_x = right_third_start + (one_third - panel_width) // 2

            # Center vertically, but bump up the height a bit
            pos_y = (screen_height - panel_height) // 3.5

            # Safety checks for smaller resolutions or high Windows DPI scaling
            if pos_x + panel_width > screen_width:
                pos_x = screen_width - panel_width - 20
            if pos_y < 20:
                pos_y = 20

            self.window.geometry(f"{panel_width}x{panel_height}+{pos_x}+{pos_y}")
            self.window.update_idletasks()

        except Exception as e:
            logger.warning(f"Failed auto control UI placement, using fallback: {e}")
            self.window.geometry("460x920")

        apply_window_icon(self.window)

        self.window.protocol("WM_DELETE_WINDOW", self._on_close)


        self._build_ui()

        # For screenshots
        self._dxcam = dxcam.create(output_color="BGRA")

        # Making sure titlebar is dark
        try:
            self.window.update_idletasks()
            hwnd = ctypes.windll.user32.GetParent(self.window.winfo_id())
            if not hwnd:
                hwnd = self.window.winfo_id()
            enable_dark_titlebar(hwnd)
        except Exception as e:
            logger.warning(f"Dark titlebar failed: {e}")

        # Starting the syncing loop
        self.window.after(UPDATE_INTERVAL_MS, self._update_loop)

        logger.info("Control UI initialisation finished")

    # UI construction
    def _build_ui(self):
        """Make all widgets inside a frame"""

        # The scrollable frame fills the entire window and responds to resizing
        self._scroll = ctk.CTkScrollableFrame(
            self.window,
            fg_color=BG_COLOUR,
            scrollbar_button_color=BORDER_COLOUR,
            scrollbar_button_hover_color=ACCENT_COLOUR,
        )
        self._scroll.pack(fill="both", expand=True)
        self._scroll.columnconfigure(0, weight=1)

        # Title bar
        title_row = ctk.CTkFrame(self._scroll, fg_color="transparent")
        title_row.pack(fill="x", padx=16, pady=(18, 6))

        try:
            pil_img = Image.open(ICON_PATH).resize((36, 36))
            self._logo_ctk = ctk.CTkImage(pil_img, size=(36, 36))
            ctk.CTkLabel(title_row, image=self._logo_ctk, text="").pack(side="left")
        except Exception:
            self._logo_ctk = None

        ctk.CTkLabel(
            title_row,
            text="DualCPY Control Panel",
            font=make_font(22, "bold"),
            text_color=TEXT_COLOUR,
        ).pack(side="left", padx=10)

        self._separator()

        self._section("Screen Layout")

        # Global scale slider
        safe_scale = self.l.global_scale if self.l.global_scale is not None else 0.6
        self._build_slider("global_scale", "Global Scale",
                           safe_scale, GLOBAL_SCALE_MIN, GLOBAL_SCALE_MAX,
                           color=ACCENT_COLOUR, is_float=True,
                           on_change=self._on_scale_change)

        # Scale restart text, hidden by default until used
        self._scale_notice = ctk.CTkLabel(
            self._scroll, text="",
            text_color=WARNING_COLOUR,
            font=make_font(11),
        )
        self._scale_notice.pack(anchor="w", padx=44, pady=(0, 2))

        # Sliders; top x, top y, bottom x and bottom y
        for attr, label, color in [
            ("tx", "Top X", TOP_COLOUR),
            ("ty", "Top Y", TOP_COLOUR),
            ("bx", "Bottom X", BOTTOM_COLOUR),
            ("by", "Bottom Y", BOTTOM_COLOUR),
        ]:
            val = getattr(self.l, attr, 0) or 0
            self._build_slider(attr, label, val,
                               SCREEN_MIN_POS, SCREEN_MAX_POS,
                               color=color, is_float=False,
                               on_change=self._on_layout_change)

        # Default layout button
        ctk.CTkButton(
            self._scroll,
            text="Reset to Default Position",
            command=self._on_default_layout,
            fg_color=PANEL_COLOUR,
            hover_color=BORDER_COLOUR,
            border_color=BORDER_COLOUR,
            border_width=1,
            text_color=TEXT_COLOUR,
            font=make_font(13),
        ).pack(fill="x", padx=16, pady=(4, 0))

        self._separator()

        self._section("Window Config")

        btn_grid = ctk.CTkFrame(self._scroll, fg_color="transparent")
        # No bottom frame-padding: bottom_btn_row sits flush below so the gap to
        # it matches the 8px gap between rows inside this grid (otherwise the
        # two frames' pady stack and double it).
        btn_grid.pack(fill="x", padx=16, pady=(4, 0))
        btn_grid.columnconfigure(0, weight=1)
        btn_grid.columnconfigure(1, weight=1)

        # FPS selector
        from src.launcher import ALLOWED_FPS_VALUES
        self._fps_var = tk.StringVar(value=f"{self.l.max_fps} FPS")
        ctk.CTkOptionMenu(
            btn_grid,
            variable=self._fps_var,
            values=[f"{v} FPS" for v in ALLOWED_FPS_VALUES],
            command=self._on_fps_change,
            fg_color=PANEL_COLOUR,
            button_color=BORDER_COLOUR,
            button_hover_color=ACCENT_COLOUR,
            text_color=TEXT_COLOUR,
            dropdown_fg_color=PANEL_COLOUR,
            dropdown_hover_color=BORDER_COLOUR,
            dropdown_text_color=TEXT_COLOUR,
            font=make_font(13),
            dropdown_font=make_font(13),
        ).grid(row=0, column=0, sticky="ew", padx=(0, 4), pady=4)

        # Restart Button
        ctk.CTkButton(
            btn_grid,
            text="Restart",
            command=self._on_restart,
            fg_color=PANEL_COLOUR,
            hover_color=BORDER_COLOUR,
            border_color=BORDER_COLOUR,
            border_width=1,
            text_color=TEXT_COLOUR,
            font=make_font(13),
        ).grid(row=0, column=1, sticky="ew", padx=(4, 0), pady=4)

        # Dock/Undock button
        self._dock_btn_text = tk.StringVar(
            value="Undock" if self.l.docked else "Dock"
        )
        self._dock_btn = ctk.CTkButton(
            btn_grid,
            textvariable=self._dock_btn_text,
            command=self._on_dock_toggle,
            fg_color=PANEL_COLOUR,
            hover_color=BORDER_COLOUR,
            border_color=BORDER_COLOUR,
            border_width=1,
            text_color=TEXT_COLOUR,
            font=make_font(13),
        )
        self._dock_btn.grid(row=1, column=0, sticky="ew", padx=(0, 4), pady=4)

        # Screenshot Button
        ctk.CTkButton(
            btn_grid,
            text="Screenshot",
            command=self.take_screenshot,
            fg_color=PANEL_COLOUR,
            hover_color=BORDER_COLOUR,
            border_color=BORDER_COLOUR,
            border_width=1,
            text_color=TEXT_COLOUR,
            font=make_font(13),
        ).grid(row=1, column=1, sticky="ew", padx=(4, 0), pady=4)

        # Wireless + Edit Device Profiles row
        bottom_btn_row = ctk.CTkFrame(self._scroll, fg_color="transparent")
        # Flush against btn_grid above (see note there); keep bottom padding.
        bottom_btn_row.pack(fill="x", padx=16, pady=(0, 4))
        bottom_btn_row.columnconfigure(0, weight=1)
        bottom_btn_row.columnconfigure(1, weight=1)

        ctk.CTkButton(
            bottom_btn_row,
            text="Wireless",
            command=self._on_wireless,
            fg_color=PANEL_COLOUR,
            hover_color=BORDER_COLOUR,
            border_color=BORDER_COLOUR,
            border_width=1,
            text_color=TEXT_COLOUR,
            font=make_font(13),
        ).grid(row=0, column=0, sticky="ew", padx=(0, 4), pady=4)

        ctk.CTkButton(
            bottom_btn_row,
            text="Edit Device Profiles",
            command=self._on_edit_profiles,
            fg_color=PANEL_COLOUR,
            hover_color=BORDER_COLOUR,
            border_color=BORDER_COLOUR,
            border_width=1,
            text_color=TEXT_COLOUR,
            font=make_font(13),
        ).grid(row=0, column=1, sticky="ew", padx=(4, 0), pady=4)

        # File Transfer button (full width, row 1)
        ctk.CTkButton(
            bottom_btn_row,
            text="File Transfer",
            command=self._on_file_transfer,
            fg_color=PANEL_COLOUR,
            hover_color=BORDER_COLOUR,
            border_color=BORDER_COLOUR,
            border_width=1,
            text_color=TEXT_COLOUR,
            font=make_font(13),
        ).grid(row=1, column=0, columnspan=2, sticky="ew", pady=4)

        # Determine the display name of the initial loaded profile
        current_prof = self.l.scrcpy.profile
        display_name = current_prof.nickname.strip() if getattr(current_prof, "nickname", "") else current_prof.name

        # Create and pack the indicator label
        self._current_profile_label = ctk.CTkLabel(
            self.window,
            text=f"Active Profile: {display_name}",
            font=make_font(14, "bold"),
            text_color="#1a6b3a"
        )
        self._current_profile_label.pack(pady=(10, 5))

        # FPS restart warning / status label
        self._status_label = ctk.CTkLabel(
            self._scroll,
            text="",
            font=make_font(12),
            text_color=TEXT_COLOUR,
        )

        self._status_label.pack(pady=(2, 2))

        ctk.CTkFrame(
            self._scroll, height=1, fg_color=BORDER_COLOUR
        ).pack(fill="x", padx=16, pady=4)

        self._section("Presets")

        save_row = ctk.CTkFrame(self._scroll, fg_color="transparent")
        save_row.pack(fill="x", padx=16, pady=4)
        save_row.columnconfigure(0, weight=1)

        self._preset_name_var = tk.StringVar(value=DEFAULT_PRESET_NAME)
        ctk.CTkEntry(
            save_row,
            textvariable=self._preset_name_var,
            placeholder_text="Preset name...",
            fg_color=PANEL_COLOUR,
            border_color=BORDER_COLOUR,
            text_color=TEXT_COLOUR,
            font=make_font(13),
        ).grid(row=0, column=0, sticky="ew", padx=(0, 8))

        ctk.CTkButton(
            save_row,
            text="Save",
            width=80,
            command=self._on_save_preset,
            fg_color=ACCENT_COLOUR,
            hover_color="#3a7fc1",
            font=make_font(13),
        ).grid(row=0, column=1)

        ctk.CTkLabel(
            self._scroll,
            text="Saved Presets",
            font=make_font(13, "bold"),
            text_color=TEXT_COLOUR,
            anchor="w",
        ).pack(anchor="w", padx=16, pady=(10, 2))

        self._preset_list_frame = ctk.CTkScrollableFrame(
            self._scroll,
            fg_color=PANEL_COLOUR,
            height=180,
            scrollbar_button_color=BORDER_COLOUR,
        )
        self._preset_list_frame.pack(fill="x", padx=16, pady=(0, 20))
        self._preset_list_frame.columnconfigure(0, weight=1)

        self.refresh_preset_list()

    # Layout helpers
    def _separator(self):
        ctk.CTkFrame(
            self._scroll, height=1, fg_color=BORDER_COLOUR
        ).pack(fill="x", padx=16, pady=10)

    def _section(self, label):
        ctk.CTkLabel(
            self._scroll,
            text=label,
            font=make_font(14, "bold"),
            text_color=TEXT_COLOUR,
            anchor="w",
        ).pack(anchor="w", padx=16, pady=(4, 2))

    def _build_slider(
        self, attr, label, initial_val,
        min_val, max_val, *, color, is_float, on_change
    ):
        """
        Build one labeled slider row (label | slider | entry) that is
        fully responsive: the slider expands to fill available width.

        The row registers itself in self._slider_refs so preset loads can
        push new values back without re-building widgets.
        """
        row = ctk.CTkFrame(self._scroll, fg_color="transparent")
        row.pack(fill="x", padx=16, pady=3)
        row.columnconfigure(1, weight=1)   # slider column expands

        ctk.CTkLabel(
            row, text=label,
            font=make_font(13),
            text_color=TEXT_COLOUR,
            width=90, anchor="w",
        ).grid(row=0, column=0, sticky="w")

        # Variables
        def to_norm(v):
            return (v - min_val) / (max_val - min_val)

        def from_norm(n):
            return min_val + n * (max_val - min_val)

        if is_float:
            real_var  = tk.DoubleVar(value=round(float(initial_val), 2))
            entry_str = f"{float(initial_val):.2f}"
        else:
            real_var  = tk.IntVar(value=int(initial_val))
            entry_str = str(int(initial_val))

        norm_var  = tk.DoubleVar(value=to_norm(initial_val))
        entry_var = tk.StringVar(value=entry_str)

        # Slider
        def _slider_moved(norm_val):
            if is_float:
                real = round(from_norm(norm_val), 2)
                real_var.set(real)
                entry_var.set(f"{real:.2f}")
            else:
                real = int(round(from_norm(norm_val)))
                real_var.set(real)
                entry_var.set(str(real))
            on_change()

        slider = ctk.CTkSlider(
            row, from_=0.0, to=1.0,
            variable=norm_var,
            command=_slider_moved,
            button_color=color,
            button_hover_color=color,
            progress_color=color,
            fg_color=BORDER_COLOUR,
        )
        slider.grid(row=0, column=1, sticky="ew", padx=10)

        # Entry box
        entry = ctk.CTkEntry(
            row, textvariable=entry_var,
            width=72,
            fg_color=PANEL_COLOUR,
            border_color=BORDER_COLOUR,
            text_color=TEXT_COLOUR,
            font=make_font(13),
        )
        entry.grid(row=0, column=2)

        def _entry_committed(event=None):
            try:
                raw = entry_var.get().strip()
                if is_float:
                    new_val = float(raw)
                    new_val = max(min_val, min(max_val, new_val))
                    real_var.set(round(new_val, 2))
                    entry_var.set(f"{new_val:.2f}")
                else:
                    new_val = int(float(raw))
                    new_val = max(min_val, min(max_val, new_val))
                    real_var.set(new_val)
                    entry_var.set(str(new_val))
                norm_var.set(to_norm(new_val))
                on_change()
            except ValueError:
                self.show_status("Invalid number", "error")
                # Restore last good value
                if is_float:
                    entry_var.set(f"{real_var.get():.2f}")
                else:
                    entry_var.set(str(int(real_var.get())))

        entry.bind("<Return>",   _entry_committed)
        entry.bind("<FocusOut>", _entry_committed)

        # Register so preset loads can sync back
        self._slider_refs[attr] = {
            "real": real_var,
            "norm": norm_var,
            "entry": entry_var,
            "to_norm": to_norm,
            "is_float": is_float,
        }

    # Slider / button callbacks
    def _on_scale_change(self):
        ref = self._slider_refs.get("global_scale")
        if ref is None:
            return
        new_scale = round(float(ref["real"].get()), 2)
        changed = abs(new_scale - self._original_scale) > SCALE_CHANGE_THRESHOLD
        self.l.global_scale = new_scale
        self.l.save_scale()
        if changed:
            self._scale_notice.configure(
                text="Restart required to apply scale change"
            )
            self._scale_changed = True
        else:
            self._scale_notice.configure(text="")

    def _on_default_layout(self):
        """Reset tx/ty/bx/by to the profile's centred default and sync everything"""
        defaults = self.l.get_default_layout()
        for attr, val in defaults.items():
            self.l.__dict__[attr] = val
        self.l.save_layout()
        self._sync_sliders_from_launcher()
        self.force_window_sync()
        self.show_status("Position reset to default", "success")

    def _on_layout_change(self):
        for attr in ("tx", "ty", "bx", "by"):
            ref = self._slider_refs.get(attr)
            if ref:
                setattr(self.l, attr, int(ref["real"].get()))
        self.l.save_layout()
        self.force_window_sync()

    def _on_fps_change(self, value):
        try:
            fps = int(value.split()[0])
            if hasattr(self.l, "set_max_fps"):
                self.l.set_max_fps(fps)
            self.show_status(f"FPS set to {fps} - click Restart to apply", "info")
        except Exception as e:
            logger.error(f"FPS change error: {e}")

    def _on_restart(self):
        if hasattr(self.l, "restart_app"):
            self._scale_changed = False
            self._original_scale = self.l.global_scale
            self._scale_notice.configure(text="")
            self.show_status("Restarting...", "info")
            self.l.restart_app()

    def _on_dock_toggle(self):
        if hasattr(self.l, "toggle_dock"):
            self.l.toggle_dock()
            self._dock_btn_text.set("Undock" if self.l.docked else "Dock")

    def _on_wireless(self):
        """Hide CTK window, open wireless dialog, restore window."""
        self.window.withdraw()
        try:
            result = self.l.show_connection_dialog()
            if result == "connected":
                self.show_status("Wireless connected", "success")
            elif result == "disconnected":
                self.show_status("Device disconnected", "info")
        finally:
            self.window.deiconify()
            self.window.lift()

    def _on_edit_profiles(self):
        """Open the custom device profile editor dialog"""
        self.window.withdraw()

        try:
            DeviceProfileEditorDialog(
                parent=self.window,
                custom_store=self.l.custom_profiles,
                launcher=self.l,
            ).run()

        finally:
            self.window.deiconify()
            self.window.lift()

    def _on_file_transfer(self):
        """Open the dual-pane file transfer dialog."""
        adb_bin = getattr(self.l.scrcpy, "adb_bin", None)
        serial = getattr(self.l.scrcpy, "serial", None)

        if not adb_bin or not serial:
            self.show_status("No device connected for file transfer", "error")
            return

        try:
            dlg = FileTransferDialog(
                parent=self.window,
                adb_bin=adb_bin,
                serial=serial,
            )
            dlg.show()
        except Exception as e:
            logger.error(f"Failed to open File Transfer dialog: {e}", exc_info=True)
            self.show_status("Could not open File Transfer", "error")

    def _on_save_preset(self):
        name = self._preset_name_var.get().strip()
        try:
            self.l.store.save_preset(
                name,
                {
                    "tx": self.l.tx,
                    "ty": self.l.ty,
                    "bx": self.l.bx,
                    "by": self.l.by,
                    "global_scale": self.l.global_scale,
                },
            )
            self.invalidate_preset_cache()
            self.refresh_preset_list()
            self.show_status(f"Saved preset: {name}", "success")
        except ValueError as e:
            self.show_status(str(e), "error",
                             duration=ERROR_STATUS_DURATION)
        except Exception as e:
            logger.error(f"Preset save error: {e}", exc_info=True)
            self.show_status("Failed to save preset", "error")

    def _on_load_preset(self, name):
        data = self.l.store.get_preset(name)
        if not data:
            self.show_status(f"Preset '{name}' not found", "error")
            return
        self.l.tx = data.get("tx", self.l.tx)
        self.l.ty = data.get("ty", self.l.ty)
        self.l.bx = data.get("bx", self.l.bx)
        self.l.by = data.get("by", self.l.by)
        if "global_scale" in data:
            self.l.global_scale = data["global_scale"]
            self.l.launch_scale = data["global_scale"]
            self.l.save_scale()
        self.l.save_layout()
        self._sync_sliders_from_launcher()
        self.force_window_sync()
        self.show_status(f"Loaded preset: {name}", "success")

    def _on_delete_preset(self, name):
        deleted = self.l.store.delete_preset(name)
        if deleted:
            self.invalidate_preset_cache()
            self.refresh_preset_list()
            self.show_status(f"Deleted preset: {name}", "info")
        else:
            self.show_status(f"Preset '{name}' not found", "error")

    def _on_close(self):
        self.l.stop()

    # Preset list
    def refresh_preset_list(self):
        """Destroy and rebuild the scrollable preset list."""
        for w in self._preset_list_frame.winfo_children():
            w.destroy()

        presets = self.get_presets()

        if not presets:
            ctk.CTkLabel(
                self._preset_list_frame,
                text="It's so empty in here...",
                text_color=BORDER_COLOUR,
                font=make_font(18),
            ).pack(pady=10)
            return

        for name in presets:
            row = ctk.CTkFrame(
                self._preset_list_frame,
                fg_color="transparent",
            )
            row.pack(fill="x", pady=2)
            row.columnconfigure(0, weight=1)

            ctk.CTkLabel(
                row, text=name,
                text_color=TEXT_COLOUR,
                anchor="w",
                font=make_font(12),
            ).grid(row=0, column=0, sticky="w", padx=6)

            ctk.CTkButton(
                row, text="Load", width=60,
                fg_color=ACCENT_COLOUR,
                hover_color="#3a7fc1",
                font=make_font(12),
                command=lambda n=name: self._on_load_preset(n),
            ).grid(row=0, column=1, padx=(2, 2))

            ctk.CTkButton(
                row, text="Delete", width=64,
                fg_color="#8b2020",
                hover_color="#c0392b",
                font=make_font(12),
                command=lambda n=name: self._on_delete_preset(n),
            ).grid(row=0, column=2, padx=(0, 4))

    # Public helpers
    def invalidate_preset_cache(self):
        """Force preset list to reload on next access."""
        self._preset_cache = None
        logger.debug("Preset cache invalidated")

    def get_presets(self):
        """Return presets with a short TTL cache to reduce disk I/O."""
        now = time.time()
        if self._preset_cache is None or (now - self._preset_cache_time) > PRESET_CACHE_TIME:
            self._preset_cache = self.l.store.load_all()
            self._preset_cache_time = now
            logger.debug(f"Preset cache refreshed: {len(self._preset_cache)} entries")
        return self._preset_cache

    def show_status(
            self, msg,
            status_type="info",
            duration=STATUS_MESSAGE_DURATION,
    ):
        """Display a timed status message in the panel."""
        logger.debug(f"Status [{status_type}]: {msg}")
        self.status_msg = msg
        self.status_type = status_type

        colour_map = {
            "success": SUCCESS_COLOUR,
            "error": DANGER_COLOUR,
            "warning": WARNING_COLOUR,
            "info": TEXT_COLOUR,
        }
        self._status_label.configure(
            text=msg,
            text_color=colour_map.get(status_type, TEXT_COLOUR),
        )

        if self._status_after_id:
            try:
                self.window.after_cancel(self._status_after_id)
            except Exception:
                pass

        # Hide the status label once the timer expires
        def _clear_status():
            self._status_label.configure(text="")
            self._status_label.pack_forget()

        self._status_after_id = self.window.after(
            int(duration * 1000),
            _clear_status,
        )

    def force_window_sync(self):
        """
        Force an immediate dock sync, bypassing the throttle inside Win32Dock
        """
        try:
            if not self.l.docked:
                logger.debug("Skipping force sync - not docked")
                return
            if not (self.l.dock.hwnd_top and self.l.dock.hwnd_bottom):
                logger.warning("Cannot force sync - window handles not available")
                return

            self.l.dock._last_sync = 0

            user32 = windll.user32
            user32.ShowWindow(self.l.dock.hwnd_top,    SW_SHOW)
            user32.ShowWindow(self.l.dock.hwnd_bottom, SW_SHOW)

            self.l.dock.sync(
                self.l.tx, self.l.ty,
                self.l.bx, self.l.by,
                self.l.scrcpy.f_w1, self.l.scrcpy.f_h1,
                self.l.scrcpy.f_w2, self.l.scrcpy.f_h2,
                is_docked=True,
            )

            flags = SWP_NOZORDER | SWP_NOACTIVATE | SWP_FRAMECHANGED | SWP_NOMOVE | SWP_NOSIZE
            user32.SetWindowPos(self.l.dock.hwnd_top,    0, 0, 0, 0, 0, flags)
            user32.SetWindowPos(self.l.dock.hwnd_bottom, 0, 0, 0, 0, 0, flags)

            logger.info("Force window sync completed")

        except Exception as e:
            logger.error(f"Force window sync error: {e}", exc_info=True)

    def take_screenshot(self):
        try:
            user32 = ctypes.windll.user32
            client_rect = wintypes.RECT()

            user32.GetClientRect(
                self.l.hwnd_container,
                ctypes.byref(client_rect)
            )

            pt = wintypes.POINT(0, 0)

            user32.ClientToScreen(
                self.l.hwnd_container,
                ctypes.byref(pt)
            )

            left = pt.x
            top = pt.y
            right = left + client_rect.right
            bottom = top + client_rect.bottom

            logger.info(
                f"Capturing client region: "
                f"{left}, {top}, {right}, {bottom}"
            )

            frame = self._dxcam.grab(region=(left, top, right, bottom))

            if frame is None:
                logger.error("dxcam returned no frame")
                return

            img = Image.fromarray(frame[:, :, [2, 1, 0]])
            output = BytesIO()
            img.convert("RGB").save(output, "BMP")
            data = output.getvalue()[14:]
            output.close()
            win32clipboard.OpenClipboard()

            try:
                win32clipboard.EmptyClipboard()
                win32clipboard.SetClipboardData(
                    win32clipboard.CF_DIB,
                    data
                )

            finally:
                win32clipboard.CloseClipboard()

            logger.info("Screenshot copied to clipboard")

            self.show_status(
                "Screenshot copied to clipboard",
                "success"
            )

        except Exception as e:
            logger.error(
                f"Screenshot failed: {e}",
                exc_info=True
            )

            self.show_status(
                "Screenshot failed",
                "error"
            )

    # Internal helpers
    def _sync_sliders_from_launcher(self):
        """
        Push current launcher state back into all slider widgets
        """
        # Keep the active-profile label in sync after a hot-swap
        if hasattr(self, "_current_profile_label") and self.l.scrcpy:
            prof = self.l.scrcpy.profile
            display_name = prof.nickname.strip() if getattr(prof, "nickname", "") else prof.name
            self._current_profile_label.configure(text=f"Active Profile: {display_name}")

        updates = {
            "global_scale": self.l.global_scale,
            "tx": self.l.tx,
            "ty": self.l.ty,
            "bx": self.l.bx,
            "by": self.l.by,
        }
        for key, new_val in updates.items():
            ref = self._slider_refs.get(key)
            if ref is None or new_val is None:
                continue
            is_float = ref["is_float"]
            if is_float:
                v = round(float(new_val), 2)
                ref["real"].set(v)
                ref["entry"].set(f"{v:.2f}")
            else:
                v = int(new_val)
                ref["real"].set(v)
                ref["entry"].set(str(v))
            ref["norm"].set(ref["to_norm"](v))

        # Also update scale-change notice
        scale = self.l.global_scale or 0.6
        changed = abs(scale - self._original_scale) > SCALE_CHANGE_THRESHOLD
        self._scale_notice.configure(
            text="Restart required to apply scale change" if changed else ""
        )

    def _update_loop(self):
        try:
            if not self.l.running:
                return

            # Sync scrcpy window positions
            if self.l.dock.hwnd_top or self.l.dock.hwnd_bottom:
                self.l.dock.sync(
                    self.l.tx, self.l.ty,
                    self.l.bx, self.l.by,
                    self.l.scrcpy.f_w1, self.l.scrcpy.f_h1,
                    self.l.scrcpy.f_w2, self.l.scrcpy.f_h2,
                    is_docked=self.l.docked,
                )

            # Keep dock button label in sync with actual state
            expected = "Undock" if self.l.docked else "Dock"
            if self._dock_btn_text.get() != expected:
                self._dock_btn_text.set(expected)

        except Exception as e:
            logger.error(f"Update loop error: {e}", exc_info=True)
        finally:
            if self.l.running:
                self.window.after(UPDATE_INTERVAL_MS, self._update_loop)

    # Main loop
    def run(self):
        """Enter the CTK main loop, Blocks until the window is closed."""
        logger.info("Entering CTkUI main loop")
        self.window.mainloop()
        logger.info("CTkUI main loop exited")