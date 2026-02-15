# ThorCPY - Dual-screen scrcpy docking and control UI for Windows
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

# src/win32_darkmode.py

import ctypes
from ctypes import wintypes
import sys
import logging

# Setup logger for this module
logger = logging.getLogger(__name__)

# Load windows DLLs
# Desktop Window Manager API
dwmapi = ctypes.windll.dwmapi
# Windows GUI Functions
user32 = ctypes.windll.user32

# Windows build version constants
WINDOWS_BUILD_18985 = 18985

# Windows 10/11 dark mode attribute IDs
DWMWA_USE_DARK_MODE_LEGACY = 19
DWMWA_USE_IMMERSIVE_DARK_MODE = 20

def enable_dark_titlebar(hwnd):
    """
    Enables dark mode titlebar for a specific window
    Works on Windows 10 1809+ and Windows 11
    Args:
        hwnd: int, Handle to the window (HWND)
    """
    try:
        version = sys.getwindowsversion().build
        logger.info(f"Build retrieved, running build {version}")

        # Select appropriate dark mode attribute based on Windows version
        if version < WINDOWS_BUILD_18985:
            DWMWA_USE_DARK_MODE = DWMWA_USE_DARK_MODE_LEGACY
        else:
            DWMWA_USE_DARK_MODE = DWMWA_USE_IMMERSIVE_DARK_MODE

        value = wintypes.BOOL(True)
        dwmapi.DwmSetWindowAttribute(
            hwnd, DWMWA_USE_DARK_MODE, ctypes.byref(value), ctypes.sizeof(value)
        )
    except Exception as DarkTitlebarError:
        logger.warning(f"Dark titlebar error: {DarkTitlebarError}")
