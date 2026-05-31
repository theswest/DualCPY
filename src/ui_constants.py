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

# src/ui_constants.py

import os
import sys
import logging
import tkinter as tk
import customtkinter as ctk
from ctypes import windll

logger = logging.getLogger(__name__)

# Colours
BG_COLOUR      = "#121418"
PANEL_COLOUR   = "#1e2128"
BORDER_COLOUR  = "#2d3139"
TEXT_COLOUR    = "#c8cdd8"
ACCENT_COLOUR  = "#4000D4"
ACCENT2_COLOUR = "#6A4BF4"
TOP_COLOUR     = "#A241ED"
BOTTOM_COLOUR  = "#936aad"
SUCCESS_COLOUR = "#2ecc71"
DANGER_COLOUR  = "#e74c3c"
WARNING_COLOUR = "#f39c12"

# Font / asset helpers
CALSANS_FAMILY = "Cal Sans"

# Tracks whether CalSans was successfully registered with Win32
_calsans_loaded = False


def resource_path(rel):
    """Resolve a resource path for both dev and PyInstaller contexts"""
    try:
        if hasattr(sys, "_MEIPASS"):
            path = os.path.join(sys._MEIPASS, rel)
            logger.debug(f"Resource path (PyInstaller): {path}")
            return path
        path = os.path.join(os.path.abspath("."), rel)
        logger.debug(f"Resource path (dev): {path}")
        return path
    except Exception as e:
        logger.error(f"Failed to resolve resource path for '{rel}': {e}")
        return rel


ICON_PATH = resource_path("assets/icon.png")
FONT_PATH = resource_path("assets/fonts/CalSans-Regular.ttf")


def load_calsans():
    """Register CalSans-Regular with Win32"""
    global _calsans_loaded

    if _calsans_loaded:
        return True
    try:
        FR_PRIVATE = 0x10
        result = windll.gdi32.AddFontResourceExW(FONT_PATH, FR_PRIVATE, 0)

        if result > 0:
            _calsans_loaded = True
            logger.info(f"CalSans loaded from {FONT_PATH}")
        else:
            logger.warning(
                f"AddFontResourceExW returned 0 for {FONT_PATH} - "
                "font may not render; falling back to CTK default"
            )

    except Exception as e:
        logger.warning(f"CalSans load failed: {e}: falling back to CTK default")

    return _calsans_loaded


def make_font(size, weight="normal"):
    """Return a CTkFont using CalSans if loaded, otherwise the CTK default"""
    if _calsans_loaded:
        return ctk.CTkFont(family=CALSANS_FAMILY, size=size, weight=weight)

    return ctk.CTkFont(size=size, weight=weight)


def apply_window_icon(window):
    """Apply the DualCPY icon to any CTk window or Toplevel"""
    try:
        img = tk.PhotoImage(file=ICON_PATH)
        window.iconphoto(True, img)
        window._icon_image = img
    except Exception:
        pass