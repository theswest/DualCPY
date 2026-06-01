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

# src/device_profile_editor.py

import ctypes
import logging
import tkinter as tk
import customtkinter as ctk

from src.device_profile import DeviceProfile
from src.scrcpy_manager import (
    ScrcpyManager,
    TOP_BITRATE_MINIMUM, TOP_BITRATE_SCALE,
    BOTTOM_BITRATE_MINIMUM, BOTTOM_BITRATE_SCALE,
)
from src.device_profile import BUILTIN_PROFILES
from src.device_profile_dialog import DeviceProfileDialog
from src.device_detection import detect_device, get_device_info, get_display_list, resolve_adb
from src.ui_constants import (
    BG_COLOUR, PANEL_COLOUR, BORDER_COLOUR, TEXT_COLOUR,
    ACCENT_COLOUR, ACCENT2_COLOUR, DANGER_COLOUR,
    make_font, load_calsans, apply_window_icon,
)

try:
    from src.win32_darkmode import enable_dark_titlebar
    _HAS_DARK_TITLEBAR = True
except Exception:
    _HAS_DARK_TITLEBAR = False

logger = logging.getLogger(__name__)

DIALOG_WIDTH  = 520
DIALOG_HEIGHT = 780
SLOW_DELAY    = 3
FAST_DELAY    = 0
DEFAULT_SCALE = 0.5


class DeviceProfileEditorDialog:
    """
    Dialog for viewing, editing, and deleting custom device profiles
    """

    def __init__(self, parent, custom_store, launcher=None):
        load_calsans()

        self._store = custom_store
        self._launcher = launcher
        self._editing_key: str | None = None

        # Dialog window
        self._dialog = ctk.CTkToplevel(parent)
        self._dialog.title("Edit Device Profiles")
        self._dialog.configure(fg_color=BG_COLOUR)
        self._dialog.resizable(True, True)
        self._dialog.minsize(DIALOG_WIDTH, 600)

        self._dialog.update_idletasks()
        sw = self._dialog.winfo_screenwidth()
        sh = self._dialog.winfo_screenheight()
        x  = (sw - DIALOG_WIDTH)  // 2
        y  = (sh - DIALOG_HEIGHT) // 2
        self._dialog.geometry(f"{DIALOG_WIDTH}x{DIALOG_HEIGHT}+{x}+{y}")

        self._dialog.grab_set()
        self._dialog.focus_force()
        self._dialog.protocol("WM_DELETE_WINDOW", self._dialog.destroy)

        apply_window_icon(self._dialog)

        if _HAS_DARK_TITLEBAR:
            try:
                self._dialog.update_idletasks()
                hwnd = ctypes.windll.user32.GetParent(self._dialog.winfo_id())
                if not hwnd:
                    hwnd = self._dialog.winfo_id()
                enable_dark_titlebar(hwnd)
            except Exception:
                pass

        # Build layout
        self._build()

    # Layout
    def _build(self):
        # Title
        title_row = ctk.CTkFrame(self._dialog, fg_color="transparent")
        title_row.pack(fill="x", padx=20, pady=(18, 4))
        ctk.CTkLabel(
            title_row, text="Edit Device Profiles",
            font=make_font(20, "bold"), text_color=ACCENT2_COLOUR,
        ).pack(side="left")

        ctk.CTkFrame(self._dialog, height=1, fg_color=BORDER_COLOUR).pack(
            fill="x", padx=20, pady=(0, 8)
        )

        # Profile list (top half)
        ctk.CTkLabel(
            self._dialog, text="Custom Profiles",
            font=make_font(13, "bold"), text_color=TEXT_COLOUR, anchor="w",
        ).pack(anchor="w", padx=20, pady=(0, 4))

        self._list_frame = ctk.CTkScrollableFrame(
            self._dialog,
            fg_color=PANEL_COLOUR,
            height=280,
            scrollbar_button_color=BORDER_COLOUR,
        )
        self._list_frame.pack(fill="x", padx=20, pady=(0, 8))
        self._list_frame.columnconfigure(0, weight=1)
        # Scroll isolation: only scroll this list while mouse is inside it
        def _lf_scroll(event):
            self._list_frame._parent_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
            return "break"
        self._list_frame._parent_canvas.bind("<Enter>",
            lambda e: self._list_frame._parent_canvas.bind("<MouseWheel>", _lf_scroll))
        self._list_frame._parent_canvas.bind("<Leave>",
            lambda e: self._list_frame._parent_canvas.unbind("<MouseWheel>"))

        # Edit form (bottom half) - hidden until a profile is selected
        ctk.CTkFrame(self._dialog, height=1, fg_color=BORDER_COLOUR).pack(
            fill="x", padx=20, pady=(0, 8)
        )

        self._form_label = ctk.CTkLabel(
            self._dialog, text="Select a profile above to edit it",
            font=make_font(12), text_color=BORDER_COLOUR,
        )
        self._form_label.pack(anchor="w", padx=20, pady=(0, 4))

        self._form_scroll = ctk.CTkScrollableFrame(
            self._dialog,
            fg_color="transparent",
            scrollbar_button_color=BORDER_COLOUR,
        )
        # Scroll isolation for the form scroll itself — only active while mouse is inside.
        def _fs_scroll(event):
            self._form_scroll._parent_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
            return "break"
        self._form_scroll._parent_canvas.bind("<Enter>",
            lambda e: self._form_scroll._parent_canvas.bind("<MouseWheel>", _fs_scroll))
        self._form_scroll._parent_canvas.bind("<Leave>",
            lambda e: self._form_scroll._parent_canvas.unbind("<MouseWheel>"))
        # form_frame lives inside the scrollable container
        self._form_frame = ctk.CTkFrame(self._form_scroll, fg_color="transparent")
        self._form_frame.pack(fill="x", padx=4)
        self._form_frame.columnconfigure(1, weight=1)

        # Form fields (built once, shown/hidden with grid_remove/grid)
        self._name_var        = tk.StringVar()
        self._nickname_var    = tk.StringVar()
        self._top_size_var    = tk.StringVar()
        self._bottom_size_var = tk.StringVar()
        self._scale_var       = tk.StringVar()
        self._flipped_var     = tk.BooleanVar()
        self._slow_var        = tk.BooleanVar()
        self._error_var       = tk.StringVar()

        # Read-only info variables
        self._top_info_var    = tk.StringVar()
        self._bottom_info_var = tk.StringVar()

        self._build_form()

        # Pinned footer (always visible at the bottom)
        self._footer = ctk.CTkFrame(self._dialog, fg_color="transparent")
        self._footer.pack(side="bottom", fill="x")

        ctk.CTkFrame(self._footer, height=1, fg_color=BORDER_COLOUR).pack(
            fill="x", padx=20, pady=(4, 4)
        )

        # Error label in footer so it's never cut off
        self._error_label = ctk.CTkLabel(
            self._footer, textvariable=self._error_var,
            text_color=DANGER_COLOUR, font=make_font(12),
        )
        self._error_label.pack(pady=(0, 2))

        # "New Profile" and "Save Changes" share the same slot, toggled during editing
        self._new_profile_btn = ctk.CTkButton(
            self._footer, text="New Profile",
            command=self._on_new_profile,
            fg_color=ACCENT_COLOUR, hover_color=ACCENT2_COLOUR,
            text_color="white", font=make_font(13, "bold"),
        )
        self._new_profile_btn.pack(fill="x", padx=20, pady=(0, 4))

        self._save_btn = ctk.CTkButton(
            self._footer, text="Save Changes",
            command=self._on_save,
            fg_color=ACCENT_COLOUR, hover_color=ACCENT2_COLOUR,
            text_color="white", font=make_font(13, "bold"),
        )
        # _save_btn is packed only when editing begins

        ctk.CTkButton(
            self._footer, text="Close",
            command=self._dialog.destroy,
            fg_color=PANEL_COLOUR, hover_color=BORDER_COLOUR,
            border_color=BORDER_COLOUR, border_width=1,
            text_color=TEXT_COLOUR, font=make_font(13),
        ).pack(fill="x", padx=20, pady=(0, 16))

        # Populate the list
        self._refresh_list()

    def _build_form(self):
        """Builds the edit form fields inside _form_frame"""
        row = self._form_frame

        def field(label, var, r):
            ctk.CTkLabel(
                row, text=label, font=make_font(12),
                text_color=TEXT_COLOUR, width=130, anchor="w",
            ).grid(row=r, column=0, sticky="w", pady=3)
            ctk.CTkEntry(
                row, textvariable=var,
                fg_color=PANEL_COLOUR,
                border_color=BORDER_COLOUR,
                text_color=TEXT_COLOUR,
                font=make_font(12),
            ).grid(row=r, column=1, sticky="ew", padx=(8, 0))

        # Row 0: Device name
        ctk.CTkLabel(
            row, text="Device name",
            font=make_font(12), text_color=TEXT_COLOUR, width=130, anchor="w",
        ).grid(row=0, column=0, sticky="w", pady=3)
        ctk.CTkLabel(
            row, textvariable=self._name_var,
            font=make_font(12, "bold"), text_color=ACCENT2_COLOUR, anchor="w",
        ).grid(row=0, column=1, sticky="w", padx=(8, 0), pady=3)

        # Row 1: Nickname
        field("Nickname", self._nickname_var, 1)

        # Rows 2-3: Physical screen sizes
        field("Top screen (inches)",    self._top_size_var,    2)
        field("Bottom screen (inches)", self._bottom_size_var, 3)

        # Rows 4-5: Display info
        ctk.CTkLabel(
            row, text="Top display",
            font=make_font(12), text_color=TEXT_COLOUR, width=130, anchor="w",
        ).grid(row=4, column=0, sticky="w", pady=3)
        ctk.CTkLabel(
            row, textvariable=self._top_info_var,
            font=make_font(12), text_color=BORDER_COLOUR, anchor="w",
        ).grid(row=4, column=1, sticky="w", padx=(8, 0), pady=3)

        ctk.CTkLabel(
            row, text="Bottom display",
            font=make_font(12), text_color=TEXT_COLOUR, width=130, anchor="w",
        ).grid(row=5, column=0, sticky="w", pady=3)
        ctk.CTkLabel(
            row, textvariable=self._bottom_info_var,
            font=make_font(12), text_color=BORDER_COLOUR, anchor="w",
        ).grid(row=5, column=1, sticky="w", padx=(8, 0), pady=3)

        # Rows 6-7: Toggles
        ctk.CTkCheckBox(
            row,
            text="Internal screen is on the bottom (flipped)",
            variable=self._flipped_var,
            font=make_font(12), text_color=TEXT_COLOUR,
            fg_color=ACCENT_COLOUR, hover_color=ACCENT2_COLOUR,
            border_color=BORDER_COLOUR,
        ).grid(row=6, column=0, columnspan=2, sticky="w", pady=(6, 2))

        ctk.CTkCheckBox(
            row,
            text="Slow device (3 s launch delay)",
            variable=self._slow_var,
            font=make_font(12), text_color=TEXT_COLOUR,
            fg_color=ACCENT_COLOUR, hover_color=ACCENT2_COLOUR,
            border_color=BORDER_COLOUR,
        ).grid(row=7, column=0, columnspan=2, sticky="w", pady=(2, 6))

        # Row 8: Default scale
        field("Default scale", self._scale_var, 8)

        # Rows 9-12: Per-screen args textboxes
        for label, attr in [
            ("Top screen args",    "_top_args_box"),
            ("Bottom screen args", "_bottom_args_box"),
        ]:
            r_label = 9 if "Top" in label else 11
            r_box   = 10 if "Top" in label else 12
            ctk.CTkLabel(
                row, text=label,
                font=make_font(12), text_color=TEXT_COLOUR,
                width=130, anchor="w",
            ).grid(row=r_label, column=0, columnspan=2, sticky="w", pady=(6, 0))

            box = ctk.CTkTextbox(
                row,
                height=120,
                fg_color=PANEL_COLOUR,
                border_color=BORDER_COLOUR,
                text_color=TEXT_COLOUR,
                font=make_font(11),
                wrap="none",
            )
            box.grid(row=r_box, column=0, columnspan=2, sticky="ew", pady=(2, 4))

            def _autogrow(event, b=box):
                # Grab the exact text and count the physical newlines
                content = b.get("1.0", "end-1c")
                lines = content.count('\n') + 1

                # 14 pixels per line (tight fit for 11pt font), plus 10px for top/bottom borders
                new_height = max(40, lines * 14 + 10)
                b.configure(height=new_height)

            box._textbox.bind("<KeyRelease>", _autogrow)
            setattr(self, attr, box)

        # Hide initially (form_scroll is not yet packed either)
        pass

    # Profile list
    def _refresh_list(self):
        for w in self._list_frame.winfo_children():
            w.destroy()

        # Fetch custom profiles
        custom_profiles = self._store.load_all()

        # Combine profiles - custom profiles take priority if names conflict
        all_profiles = {**{k: v for k, v in BUILTIN_PROFILES.items()}, **custom_profiles}

        # Filter to connected device only, if known
        connected_model = (
            getattr(self._launcher, "device_model", None)
            if self._launcher is not None else None
        )

        if connected_model:
            all_profiles = {
                k: v for k, v in all_profiles.items()
                if v.name.lower() == connected_model.lower()
            }

        if not all_profiles:
            msg = f"No profiles found for '{connected_model}'" if connected_model else "No profiles found"
            ctk.CTkLabel(
                self._list_frame,
                text=msg,
                font=make_font(13), text_color=BORDER_COLOUR,
            ).pack(pady=16)
            return

        for key, profile in all_profiles.items():
            # Check if this profile came from the custom store or is read-only built-in
            is_custom = key in custom_profiles

            row = ctk.CTkFrame(self._list_frame, fg_color="transparent")
            row.pack(fill="x", pady=2)
            row.columnconfigure(0, weight=1)

            display_name = (
                profile.nickname.strip()
                if getattr(profile, "nickname", "").strip()
                else profile.name
            )

            ctk.CTkLabel(
                row, text=display_name,
                font=make_font(13), text_color=TEXT_COLOUR, anchor="w",
            ).grid(row=0, column=0, sticky="w", padx=6)

            # Only show Edit button for custom profiles
            if is_custom:
                ctk.CTkButton(
                    row, text="Edit", width=60,
                    fg_color=ACCENT_COLOUR, hover_color=ACCENT2_COLOUR,
                    font=make_font(12),
                    command=lambda k=key, p=profile: self._load_for_editing(k, p),
                ).grid(row=0, column=1, padx=(2, 2))
            else:
                ctk.CTkFrame(row, width=64, height=1, fg_color="transparent").grid(row=0, column=1, padx=(2, 2))

            if self._launcher is not None:
                ctk.CTkButton(
                    row, text="Load", width=60,
                    fg_color="#1a6b3a", hover_color="#27ae60",
                    font=make_font(12),
                    command=lambda k=key, p=profile: self._on_load_profile(p, k),
                ).grid(row=0, column=2, padx=(0, 2))

            # Only show Delete button if it belongs to custom profiles
            if is_custom:
                ctk.CTkButton(
                    row, text="Delete", width=64,
                    fg_color="#8b2020", hover_color="#c0392b",
                    font=make_font(12),
                    command=lambda k=key, p=profile: self._on_delete(k, p),
                ).grid(row=0, column=3 if self._launcher is not None else 2, padx=(0, 4))

    # Edit form population
    @staticmethod
    def _parse_args_box(box: ctk.CTkTextbox) -> list[str]:
        raw = box.get("1.0", "end").strip()
        args = [line.strip() for line in raw.splitlines() if line.strip()]
        if args and args[0].lower() == "scrcpy":
            args = args[1:]
        return args

    def _load_for_editing(self, key: str, profile: DeviceProfile):
        self._editing_key = key

        self._name_var.set(profile.name)
        self._nickname_var.set(getattr(profile, "nickname", ""))
        self._top_size_var.set(str(profile.top_screen_size))
        self._bottom_size_var.set(str(profile.bottom_screen_size))
        self._flipped_var.set(profile.flipped_screens)
        self._slow_var.set(profile.screen_launch_delay >= SLOW_DELAY)
        self._scale_var.set(str(profile.default_ui_scale))
        self._top_args_box.delete("1.0", "end")
        self._top_args_box.insert("1.0", "\n".join(getattr(profile, "extra_scrcpy_args_top", [])))
        top_lines = int(self._top_args_box._textbox.index("end-1c").split(".")[0])
        self._top_args_box.configure(height=max(40, top_lines * 20 + 10))

        self._bottom_args_box.delete("1.0", "end")
        self._bottom_args_box.insert("1.0", "\n".join(getattr(profile, "extra_scrcpy_args_bottom", [])))
        bot_lines = int(self._bottom_args_box._textbox.index("end-1c").split(".")[0])
        self._bottom_args_box.configure(height=max(40, bot_lines * 20 + 10))
        self._error_var.set("")

        self._top_info_var.set(
            f"ID {profile.top_display_id}  ·  "
            f"{profile.top_screen_width} × {profile.top_screen_height}"
        )
        self._bottom_info_var.set(
            f"ID {profile.bottom_display_id}  ·  "
            f"{profile.bottom_screen_width} × {profile.bottom_screen_height}"
        )

        display_name = (
            self._nickname_var.get().strip()
            if self._nickname_var.get().strip()
            else profile.name
        )

        self._form_label.configure(
            text=f"Editing: {display_name}",
            text_color=ACCENT2_COLOUR,
            font=make_font(13, "bold"),
        )
        self._form_scroll.pack(fill="both", expand=True, padx=20, before=self._footer)
        # Swap New Profile and Save Changes in the footer
        self._new_profile_btn.pack_forget()
        self._save_btn.pack(fill="x", padx=20, pady=(0, 4), in_=self._footer, after=self._error_label)

    # Callbacks
    def _on_new_profile(self):


        adb_bin = resolve_adb("adb")
        serial = detect_device(adb_bin)

        if not serial:
            self._error_var.set("No device connected.")
            return

        info = get_device_info(adb_bin, serial)
        display_list = get_display_list(adb_bin, serial)

        device_name = info.get("model", "Unknown Device")

        dialog = DeviceProfileDialog(
            parent=self._dialog,
            device_name=device_name,
            display_list=display_list,
            on_save=self._store.save,
        )

        profile = dialog.run()
        if profile:
            self._refresh_list()

    def _on_save(self):
        if self._editing_key is None:
            return

        # Load current stored version to preserve read-only fields
        all_profiles = self._store.load_all()
        original = all_profiles.get(self._editing_key)
        if original is None:
            self._error_var.set("Profile no longer exists - please refresh the list.")
            return

        # Validate default scale
        try:
            default_scale = float(self._scale_var.get().strip())
            if default_scale <= 0:
                raise ValueError
        except ValueError:
            self._error_var.set("Default scale must be a positive number (e.g. 0.5).")
            return

        # Validate sizes
        try:
            top_size = float(self._top_size_var.get().strip())
            if top_size <= 0:
                raise ValueError
        except ValueError:
            self._error_var.set("Top screen diagonal must be a positive number.")
            return

        try:
            bottom_size = float(self._bottom_size_var.get().strip())
            if bottom_size <= 0:
                raise ValueError
        except ValueError:
            self._error_var.set("Bottom screen diagonal must be a positive number.")
            return

        # Parse per-screen args
        top_args    = self._parse_args_box(self._top_args_box)
        bottom_args = self._parse_args_box(self._bottom_args_box)

        # Build updated profile
        updated = DeviceProfile(
            name=original.name,
            top_display_id=original.top_display_id,
            bottom_display_id=original.bottom_display_id,
            top_screen_width=original.top_screen_width,
            top_screen_height=original.top_screen_height,
            bottom_screen_width=original.bottom_screen_width,
            bottom_screen_height=original.bottom_screen_height,
            top_screen_size=top_size,
            bottom_screen_size=bottom_size,
            flipped_screens=self._flipped_var.get(),
            screen_launch_delay=SLOW_DELAY if self._slow_var.get() else FAST_DELAY,
            default_ui_scale=default_scale,
            nickname=self._nickname_var.get().strip(),
            extra_scrcpy_args_top=top_args,
            extra_scrcpy_args_bottom=bottom_args,
        )

        try:
            # Pass the _editing_key so it overwrites instead of duplicating
            self._store.save(updated, overwrite_key=self._editing_key)
        except Exception as e:
            self._error_var.set(f"Failed to save: {e}")
            logger.error(f"Profile save failed: {e}", exc_info=True)
            return

        self._error_var.set("")
        logger.info(f"Custom profile updated: '{original.name}'")

        # Collapse the edit form and reset the label
        self._editing_key = None
        self._form_scroll.pack_forget()
        self._form_frame.pack_forget()
        self._save_btn.pack_forget()
        # Swap Save Changes -> New Profile
        self._new_profile_btn.pack(fill="x", padx=20, pady=(0, 4), in_=self._footer, after=self._error_label)
        self._form_label.configure(
            text="Select a profile above to edit it",
            text_color=BORDER_COLOUR,
            font=make_font(12),
        )

        # Refresh list so nickname changes are reflected immediately
        self._refresh_list()

    def _on_load_profile(self, profile: DeviceProfile, profile_key: str):
        """Save serial with storage key to config, clear remembered scale so the
        new profile's default_ui_scale takes effect, then restart"""
        if self._launcher is None:
            return

        serial = self._launcher.scrcpy.serial if self._launcher.scrcpy else None

        if not serial:
            logger.warning("_on_load_profile: no active serial, cannot save mapping")
            return

        display = profile.nickname.strip() if getattr(profile, "nickname", "").strip() else profile.name

        try:
            cfg = self._launcher.config.load()
            device_profiles = cfg.get("device_profiles", {})
            device_profiles[serial] = profile_key
            cfg["device_profiles"] = device_profiles
            # Clear per-device scale so the new profile's default_ui_scale is used
            device_scales = cfg.get("device_scales", {})
            device_scales.pop(serial, None)
            cfg["device_scales"] = device_scales
            self._launcher.config.save(cfg)
            logger.info(f"Profile '{display}' (key: {profile_key}) saved for {serial}, scale cleared, restarting")
        except Exception as e:
            logger.error(f"Failed to save device profile mapping: {e}", exc_info=True)
            return

        # Update the launcher's live scale to the new profile's default
        self._launcher.global_scale = profile.default_ui_scale
        if self._launcher.scrcpy:
            self._launcher.scrcpy.scale = profile.default_ui_scale

        self._dialog.destroy()
        self._launcher.restart_app()

    def _on_delete(self, key: str, profile: DeviceProfile):
        deleted = self._store.delete(key)

        if deleted:
            logger.info(f"Deleted custom profile: '{profile.name}'")
            # If we were editing this profile, hide the form
            if self._editing_key == key:
                self._editing_key = None
                self._form_scroll.pack_forget()
                self._form_frame.pack_forget()
                self._save_btn.pack_forget()
                self._new_profile_btn.pack(fill="x", padx=20, pady=(0, 4), in_=self._footer, after=self._error_label)
                self._new_profile_btn.pack(fill="x", padx=20, pady=(0, 4), before=self._error_label)
                self._form_label.configure(
                    text="Select a profile above to edit it",
                    text_color=BORDER_COLOUR,
                    font=make_font(12),
                )
                self._error_var.set("")
        self._refresh_list()

    # Public entry point
    def run(self):
        """Block until the dialog is closed"""
        self._dialog.wait_window()