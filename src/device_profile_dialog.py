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

# src/device_profile_dialog.py

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

DEFAULT_UI_SCALE   = 0.5
SLOW_DEVICE_DELAY  = 3
FAST_DEVICE_DELAY  = 0
DIALOG_WIDTH       = 480
DIALOG_HEIGHT      = 620


class DeviceProfileDialog:
    """
    Dialog shown when an unrecognised device is connected

    Populates display IDs and resolutions automatically from the live
    display_list; the user only needs to supply the physical diagonal
    screen sizes and toggle two optional flags
    """

    def __init__(self, parent, device_name: str, display_list: list, on_save):
        load_calsans()

        self._result: DeviceProfile | None = None
        self._on_save_cb = on_save
        self._display_list = display_list

        # Dialog window
        if parent:
            self._dialog = ctk.CTkToplevel(parent)
        else:
            self._dialog = ctk.CTkToplevel()

        self._dialog.title("New Device Profile")
        self._dialog.configure(fg_color=BG_COLOUR)
        self._dialog.resizable(False, True)

        # Centre on screen
        self._dialog.update_idletasks()
        sw = self._dialog.winfo_screenwidth()
        sh = self._dialog.winfo_screenheight()
        x  = (sw - DIALOG_WIDTH)  // 2
        y  = (sh - DIALOG_HEIGHT) // 2
        self._dialog.geometry(f"{DIALOG_WIDTH}x{DIALOG_HEIGHT}+{x}+{y}")

        # Make modal
        self._dialog.grab_set()
        self._dialog.focus_force()

        apply_window_icon(self._dialog)

        # Dark titlebar
        if _HAS_DARK_TITLEBAR:
            try:
                self._dialog.update_idletasks()
                hwnd = ctypes.windll.user32.GetParent(self._dialog.winfo_id())
                if not hwnd:
                    hwnd = self._dialog.winfo_id()
                enable_dark_titlebar(hwnd)
            except Exception:
                pass

        # Intercept close button and treat it as cancel
        self._dialog.protocol("WM_DELETE_WINDOW", self._on_cancel)

        # State variables
        self._device_name      = device_name
        self._name_var         = tk.StringVar(value=device_name)
        self._nickname_var     = tk.StringVar(value=device_name)
        self._top_size_var     = tk.StringVar(value="")
        self._bottom_size_var  = tk.StringVar(value="")
        self._scale_var        = tk.StringVar(value=str(DEFAULT_UI_SCALE))
        self._flipped_var      = tk.BooleanVar(value=False)
        self._slow_var         = tk.BooleanVar(value=False)

        # Labels that update when flipped is toggled
        self._top_id_var     = tk.StringVar()
        self._top_res_var    = tk.StringVar()
        self._bottom_id_var  = tk.StringVar()
        self._bottom_res_var = tk.StringVar()
        self._error_var      = tk.StringVar(value="")

        self._refresh_display_vars()

        # Build the UI
        self._build()

    # Display variable helpers
    def _get_top_bottom(self):
        """Return (top_display, bottom_display) using the flipped toggle."""
        if self._flipped_var.get():
            return self._display_list[1], self._display_list[0]
        return self._display_list[0], self._display_list[1]

    def _refresh_display_vars(self):
        top, bottom = self._get_top_bottom()
        self._top_id_var.set(f"Display ID: {top['id']}")
        self._top_res_var.set(f"{top['width']} × {top['height']}")
        self._bottom_id_var.set(f"Display ID: {bottom['id']}")
        self._bottom_res_var.set(f"{bottom['width']} × {bottom['height']}")

    # UI construction
    def _build(self):
        # --- Pinned header (title + divider) ---
        title_row = ctk.CTkFrame(self._dialog, fg_color="transparent")
        title_row.pack(fill="x", padx=20, pady=(18, 4))
        ctk.CTkLabel(
            title_row, text="New Device Profile",
            font=make_font(20, "bold"), text_color=ACCENT2_COLOUR,
        ).pack(side="left")
        ctk.CTkFrame(self._dialog, height=1, fg_color=BORDER_COLOUR).pack(
            fill="x", padx=20, pady=(0, 4)
        )

        # --- Pinned footer (error + buttons) ---
        footer = ctk.CTkFrame(self._dialog, fg_color="transparent")
        footer.pack(side="bottom", fill="x")

        ctk.CTkFrame(footer, height=1, fg_color=BORDER_COLOUR).pack(
            fill="x", padx=20, pady=(4, 4)
        )
        self._error_label = ctk.CTkLabel(
            footer, textvariable=self._error_var,
            text_color=DANGER_COLOUR, font=make_font(12),
        )
        self._error_label.pack(pady=(0, 2))

        btn_row = ctk.CTkFrame(footer, fg_color="transparent")
        btn_row.pack(fill="x", padx=20, pady=(0, 16))
        btn_row.columnconfigure(0, weight=1)
        btn_row.columnconfigure(1, weight=1)
        ctk.CTkButton(
            btn_row, text="Cancel",
            command=self._on_cancel,
            fg_color=PANEL_COLOUR, hover_color=BORDER_COLOUR,
            border_color=BORDER_COLOUR, border_width=1,
            text_color=TEXT_COLOUR, font=make_font(13),
        ).grid(row=0, column=0, sticky="ew", padx=(0, 6))
        ctk.CTkButton(
            btn_row, text="Save Profile",
            command=self._on_save,
            fg_color=ACCENT_COLOUR, hover_color=ACCENT2_COLOUR,
            text_color="white", font=make_font(13, "bold"),
        ).grid(row=0, column=1, sticky="ew", padx=(6, 0))

        # --- Scrollable body ---
        scroll = ctk.CTkScrollableFrame(
            self._dialog,
            fg_color="transparent",
            scrollbar_button_color=BORDER_COLOUR,
        )
        scroll.pack(fill="both", expand=True)
        # Scroll isolation: only active while mouse is inside
        def _scroll(event):
            scroll._parent_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
            return "break"
        scroll._parent_canvas.bind("<Enter>",
            lambda e: scroll._parent_canvas.bind("<MouseWheel>", _scroll))
        scroll._parent_canvas.bind("<Leave>",
            lambda e: scroll._parent_canvas.unbind("<MouseWheel>"))
        # Use scroll as the parent for all body widgets
        self._body = scroll

        # Device name (read-only) + nickname
        name_row = ctk.CTkFrame(self._body, fg_color="transparent")
        name_row.pack(fill="x", padx=20, pady=4)
        name_row.columnconfigure(1, weight=1)
        ctk.CTkLabel(
            name_row, text="Device Name",
            font=make_font(13), text_color=TEXT_COLOUR,
            width=110, anchor="w",
        ).grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(
            name_row, textvariable=self._name_var,
            font=make_font(13, "bold"), text_color=ACCENT2_COLOUR, anchor="w",
        ).grid(row=0, column=1, sticky="w", padx=(10, 0))

        self._field_row("Nickname", self._nickname_var)
        self._field_row("Default scale", self._scale_var)

        # Separator
        ctk.CTkFrame(self._body, height=1, fg_color=BORDER_COLOUR).pack(
            fill="x", padx=20, pady=(8, 4)
        )

        # Screen panels
        screens_frame = ctk.CTkFrame(self._body, fg_color="transparent")
        screens_frame.pack(fill="x", padx=20, pady=4)
        screens_frame.columnconfigure(0, weight=1)
        screens_frame.columnconfigure(1, weight=1)

        self._top_panel    = self._screen_panel(screens_frame, "Top Screen",
                                                self._top_id_var, self._top_res_var,
                                                self._top_size_var, col=0)
        self._bottom_panel = self._screen_panel(screens_frame, "Bottom Screen",
                                                self._bottom_id_var, self._bottom_res_var,
                                                self._bottom_size_var, col=1)

        # Toggles
        ctk.CTkFrame(self._body, height=1, fg_color=BORDER_COLOUR).pack(
            fill="x", padx=20, pady=(8, 4)
        )
        toggles = ctk.CTkFrame(self._body, fg_color="transparent")
        toggles.pack(fill="x", padx=20, pady=4)
        self._toggle_row(
            toggles, label="Internal Screen on Bottom (flip displays)",
            var=self._flipped_var, on_change=self._on_flip_toggle, row=0,
        )
        self._toggle_row(
            toggles, label="Slow device (adds launch delay between screens)",
            var=self._slow_var, on_change=None, row=1,
        )

        # Per-screen args textboxes (at the bottom)
        ctk.CTkFrame(self._body, height=1, fg_color=BORDER_COLOUR).pack(
            fill="x", padx=20, pady=(8, 4)
        )
        self._build_args_boxes()

    def _field_row(self, label_text: str, var: tk.StringVar):
        row = ctk.CTkFrame(self._body, fg_color="transparent")
        row.pack(fill="x", padx=20, pady=4)
        row.columnconfigure(1, weight=1)

        ctk.CTkLabel(
            row, text=label_text,
            font=make_font(13), text_color=TEXT_COLOUR,
            width=110, anchor="w",
        ).grid(row=0, column=0, sticky="w")

        ctk.CTkEntry(
            row, textvariable=var,
            fg_color=PANEL_COLOUR,
            border_color=BORDER_COLOUR,
            text_color=TEXT_COLOUR,
            font=make_font(13),
        ).grid(row=0, column=1, sticky="ew", padx=(10, 0))

    def _build_args_boxes(self):
        """Build per-screen args textboxes pre-populated with default args."""
        top_disp = self._display_list[0]
        bot_disp = self._display_list[1]

        top_defaults = "\n".join(ScrcpyManager.default_args(
            top_disp["width"], top_disp["height"],
            TOP_BITRATE_MINIMUM, TOP_BITRATE_SCALE,
            enable_audio=True,
        ))
        bottom_defaults = "\n".join(ScrcpyManager.default_args(
            bot_disp["width"], bot_disp["height"],
            BOTTOM_BITRATE_MINIMUM, BOTTOM_BITRATE_SCALE,
            enable_audio=False,
        ))

        for label, defaults, attr in [
            ("Top screen args",    top_defaults,    "_top_args_box"),
            ("Bottom screen args", bottom_defaults, "_bottom_args_box"),
        ]:
            ctk.CTkLabel(
                self._body, text=label,
                font=make_font(12), text_color=TEXT_COLOUR, anchor="w",
            ).pack(anchor="w", padx=20, pady=(6, 0))

            box = ctk.CTkTextbox(
                self._body,
                height=130,
                fg_color=PANEL_COLOUR,
                border_color=BORDER_COLOUR,
                text_color=TEXT_COLOUR,
                font=make_font(11),
                wrap="none",
            )
            box.pack(fill="x", padx=20, pady=(2, 0))
            box.insert("1.0", defaults)
            # Scroll isolation: textbox scrolls independently on hover
            def _bind_box(b=box):
                inner = b._textbox
                def _s(event):
                    inner.yview_scroll(int(-1 * (event.delta / 120)), "units")
                    return "break"
                inner.bind("<Enter>", lambda e: inner.bind("<MouseWheel>", _s))
                inner.bind("<Leave>", lambda e: inner.unbind("<MouseWheel>"))
            _bind_box()
            setattr(self, attr, box)

    @staticmethod
    def _parse_args_box(box: ctk.CTkTextbox) -> list[str]:
        raw = box.get("1.0", "end").strip()
        args = [line.strip() for line in raw.splitlines() if line.strip()]
        if args and args[0].lower() == "scrcpy":
            args = args[1:]
        return args

    def _screen_panel(self, parent, title: str,
                      id_var, res_var, size_var, col: int):
        frame = ctk.CTkFrame(parent, fg_color=PANEL_COLOUR, corner_radius=8)
        frame.grid(row=0, column=col, sticky="nsew",
                   padx=(0, 6) if col == 0 else (6, 0), pady=4)
        frame.columnconfigure(0, weight=1)

        ctk.CTkLabel(
            frame, text=title,
            font=make_font(13, "bold"), text_color=ACCENT2_COLOUR,
            anchor="w",
        ).pack(anchor="w", padx=10, pady=(10, 4))

        # Auto-filled read-only info
        ctk.CTkLabel(
            frame, textvariable=id_var,
            font=make_font(11), text_color=BORDER_COLOUR,
            anchor="w",
        ).pack(anchor="w", padx=10)

        ctk.CTkLabel(
            frame, textvariable=res_var,
            font=make_font(11), text_color=TEXT_COLOUR,
            anchor="w",
        ).pack(anchor="w", padx=10, pady=(0, 8))

        # User-supplied diagonal sizes
        ctk.CTkLabel(
            frame, text="Diagonal (inches)",
            font=make_font(11), text_color=TEXT_COLOUR,
            anchor="w",
        ).pack(anchor="w", padx=10)

        ctk.CTkEntry(
            frame, textvariable=size_var,
            placeholder_text='e.g. "5.5"',
            width=120,
            fg_color=BG_COLOUR,
            border_color=BORDER_COLOUR,
            text_color=TEXT_COLOUR,
            font=make_font(13),
        ).pack(anchor="w", padx=10, pady=(2, 12))

        return frame

    def _toggle_row(self, parent, label: str, var: tk.BooleanVar,
                    on_change, row: int):
        frame = ctk.CTkFrame(parent, fg_color="transparent")
        frame.grid(row=row, column=0, columnspan=2, sticky="w", pady=3)

        kwargs = {}
        if on_change:
            kwargs["command"] = on_change

        ctk.CTkCheckBox(
            frame,
            text=label,
            variable=var,
            font=make_font(12),
            text_color=TEXT_COLOUR,
            fg_color=ACCENT_COLOUR,
            hover_color=ACCENT2_COLOUR,
            border_color=BORDER_COLOUR,
            **kwargs,
        ).pack(side="left")

    # Event handlers

    def _on_flip_toggle(self):
        """Swap the displayed display IDs/resolutions when flipped is on"""
        self._refresh_display_vars()

    def _on_cancel(self):
        self._result = None
        self._dialog.destroy()

    def _on_save(self):
        # Validate name
        name = self._device_name

        # Validate scale
        try:
            default_scale = float(self._scale_var.get().strip())
            if default_scale <= 0:
                raise ValueError
        except ValueError:
            self._error_var.set("Default scale must be a positive number (e.g. 0.6).")
            return

        # Parse per-screen args
        top_args    = self._parse_args_box(self._top_args_box)
        bottom_args = self._parse_args_box(self._bottom_args_box)

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

        # Build profile
        top, bottom = self._get_top_bottom()

        profile = DeviceProfile(
            name=name,
            top_display_id=str(top["id"]),
            bottom_display_id=str(bottom["id"]),
            top_screen_width=int(top["width"]),
            top_screen_height=int(top["height"]),
            bottom_screen_width=int(bottom["width"]),
            bottom_screen_height=int(bottom["height"]),
            top_screen_size=top_size,
            bottom_screen_size=bottom_size,
            flipped_screens=self._flipped_var.get(),
            screen_launch_delay=SLOW_DEVICE_DELAY if self._slow_var.get() else FAST_DEVICE_DELAY,
            default_ui_scale=default_scale,
            nickname=self._nickname_var.get().strip(),
            extra_scrcpy_args_top=top_args,
            extra_scrcpy_args_bottom=bottom_args,
        )

        logger.info(f"DeviceProfileDialog: saving new profile '{name}'")

        try:
            self._on_save_cb(profile)
        except Exception as e:
            logger.error(f"on_save callback failed: {e}", exc_info=True)
            self._error_var.set(f"Failed to save: {e}")
            return

        self._result = profile
        self._dialog.destroy()

    # Public entry point
    def run(self):
        """
        Block until the dialog is closed
        Returns the created DeviceProfile, or None if the user cancelled
        """
        self._dialog.wait_window()
        return self._result