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

# src/launcher.py

import os
import sys
import time
import ctypes
import logging
import threading
import subprocess
import customtkinter as _ctk
from ctypes import wintypes
from tkinter import messagebox
from dataclasses import replace as dc_replace

from src.presets import PresetStore
from src.config import ConfigManager
from src.scrcpy_manager import ScrcpyManager
from src.device_profile import BUILTIN_PROFILES
from src.win32_darkmode import enable_dark_titlebar
from src.wireless_dialog import show_wireless_dialog
from src.device_selector import show_device_selector
from src.custom_profile_store import CustomProfileStore
from src.control_panel import show_loading_screen, CTkUI
from src.device_profile_editor import DeviceProfileEditorDialog
from src.win32_dock import Win32Dock, apply_docked_style, apply_undocked_style
from src.device_detection import detect_device, resolve_adb, get_device_info, get_display_list
from ui_constants import resource_path

logger = logging.getLogger(__name__)

# Win32 window message constants
WM_CLOSE = 0x0010
WM_DESTROY = 0x0002

# Win32 window style constants
WS_OVERLAPPEDWINDOW = 0x00CF0000
WS_VISIBLE = 0x10000000
WS_CLIPCHILDREN = 0x02000000
WS_CLIPSIBLINGS = 0x04000000
WS_EX_CONTROLPARENT = 0x00010000

WM_MOUSEACTIVATE = 0x0021
MA_ACTIVATE = 1

# Window show/hide constants
SW_HIDE = 0
SW_SHOW = 5

# GDI constants
BLACK_BRUSH = 4

# Process creation flags
CREATE_NO_WINDOW = 0x08000000

# Allowed scrcpy FPS values exposed in the control panel
ALLOWED_FPS_VALUES = (30, 60, 90, 120)
DEFAULT_MAX_FPS = 60

# Container window initial position
DEFAULT_CONTAINER_X = 100
DEFAULT_CONTAINER_Y = 100

# Timing constants
SCRCPY_POLL_INTERVAL = 0.1
DOCKING_MONITOR_TIME_DELAY = 0.5

# Math constants
HALF = 0.5


class Launcher:
    """
    Main window controller for DualCPY
    Manages scrcpy instances, docking and undocking behabiour,
    UI rendering and event handling and configuration persistance

    The launcher makes a container window that holds 2 scrcpy instances and controls positioning
    """

    def __init__(self):
        """
        Sets up the launcher with default layouts and configurations
        Sets up scrcpy instance with saved scale
        forces the default layout on boot
        Manages windows docking
        Sorts out Win32 API function signatures
        """
        logger.info("Initializing Launcher with Forced Default Layout")
        self.user32 = ctypes.windll.user32
        self.kernel32 = ctypes.windll.kernel32

        # Load config managers
        self.store = PresetStore("config/layout.json")
        self.config = ConfigManager("config/config.json")
        self.custom_profiles = CustomProfileStore("config/custom_profiles.json")

        # Load scale from config if saved, otherwise let ScrcpyManager fall back to profile
        saved_scale = self.config.get("global_scale", None)
        self.launch_scale = saved_scale

        # Load max FPS from config
        try:
            cfg_fps = int(self.config.get("max_fps", DEFAULT_MAX_FPS))
        except (TypeError, ValueError):
            cfg_fps = DEFAULT_MAX_FPS
        self.max_fps = cfg_fps if cfg_fps in ALLOWED_FPS_VALUES else DEFAULT_MAX_FPS

        # Layout attributes
        self.scrcpy = None
        self.tx = None
        self.ty = None
        self.bx = None
        self.by = None
        self.global_scale = None

        # ADB model name of the connected device
        self.device_model = None

        self._tk_root = None

        # Initialise window management
        self.dock = Win32Dock()
        self.running = False
        self.docked = True
        self.hwnd_container = None
        self._wndproc = None
        self.dock_lock = threading.Lock()

        # Define Win32 API signatures for type safety
        self.LRESULT = ctypes.c_longlong
        self.WPARAM = ctypes.c_ulonglong
        self.LPARAM = ctypes.c_longlong

        try:
            self.user32.DefWindowProcW.argtypes = [
                wintypes.HWND,
                wintypes.UINT,
                self.WPARAM,
                self.LPARAM,
            ]
            self.user32.DefWindowProcW.restype = self.LRESULT
        except Exception as e:
            logger.error(f"Error when defining window argtypes: {e}")
            pass

        # Make sure GDI signatures are wide enough for 64-bit handles
        try:
            self._setup_gdi_signatures()
        except Exception as e:
            logger.error(f"Error when defining GDI argtypes: {e}")

    def _save_device_profile(self, serial: str, profile_key: str, scale: float = None):
        """
        Persist a serial and storage_key (and optionally scale) mapping so that
        the next boot for this device loads the exact profile and scale chosen
        If scale is None the existing saved scale for this serial is left alone
        """
        try:
            cfg = self.config.load()
            device_profiles = cfg.get("device_profiles", {})
            device_profiles[serial] = profile_key
            cfg["device_profiles"] = device_profiles

            if scale is not None:
                device_scales = cfg.get("device_scales", {})
                device_scales[serial] = scale
                cfg["device_scales"] = device_scales

            self.config.save(cfg)

            logger.info(f"Saved device profile mapping: {serial} -> key '{profile_key}'" +
                        (f", scale {scale}" if scale is not None else ""))

        except Exception as e:
            logger.error(f"Failed to save device profile mapping: {e}")

    def _save_device_scale(self, serial: str, scale: float):
        """Keep only the scale for a specific device serial"""
        try:
            cfg = self.config.load()
            device_scales = cfg.get("device_scales", {})
            device_scales[serial] = scale
            cfg["device_scales"] = device_scales
            self.config.save(cfg)
        except Exception as e:
            logger.error(f"Failed to save device scale: {e}")

    def get_default_layout(self):
        """
        Return the centred default layout dictionary for the current profile/scale
        """
        w1, h1 = self.scrcpy.f_w1, self.scrcpy.f_h1
        w2, h2 = self.scrcpy.f_w2, self.scrcpy.f_h2
        ty = 0
        by = int(h1)

        if w1 >= w2:
            tx = 0
            bx = int((w1 - w2) * HALF)
        else:
            bx = 0
            tx = int((w2 - w1) * HALF)
        return {"tx": tx, "ty": ty, "bx": bx, "by": by}

    def save_layout(self):
        """
        Saves current state and scale to config file
        """
        try:
            cfg = self.config.load()
            cfg["tx"] = self.tx
            cfg["ty"] = self.ty
            cfg["bx"] = self.bx
            cfg["by"] = self.by
            cfg["global_scale"] = self.global_scale

            if self.scrcpy and getattr(self.scrcpy, "profile", None):
                cfg["last_profile"] = self.scrcpy.profile.name

            # Persist scale per-device so each device remembers its own scale
            if self.scrcpy and self.global_scale is not None:
                serial = getattr(self.scrcpy, "serial", None)

                if serial:
                    device_scales = cfg.get("device_scales", {})
                    device_scales[serial] = self.global_scale
                    cfg["device_scales"] = device_scales

            self.config.save(cfg)
            logger.info(f"Saved configuration (Scale: {self.global_scale})")

        except Exception as e:
            logger.error(f"Failed to save configuration: {e}")

    def save_scale(self):
        """Save only the global scale to config in a single write"""
        try:
            cfg = self.config.load()
            cfg["global_scale"] = self.global_scale

            if self.scrcpy and self.global_scale is not None:
                serial = getattr(self.scrcpy, "serial", None)

                if serial:
                    device_scales = cfg.get("device_scales", {})
                    device_scales[serial] = self.global_scale
                    cfg["device_scales"] = device_scales

            self.config.save(cfg)

        except Exception as e:
            logger.error(f"Failed to save scale: {e}")

    def _create_wnd_proc(self):
        WM_LBUTTONDOWN = 0x0201
        WM_PARENTNOTIFY = 0x0210

        WNDPROC = ctypes.WINFUNCTYPE(
            self.LRESULT, wintypes.HWND, wintypes.UINT, self.WPARAM, self.LPARAM
        )

        def py_wndproc(hwnd, msg, wp, lp):
            if msg in (WM_CLOSE, WM_DESTROY):
                self.stop()
                return 0

            # Handle activation when the mouse enters/clicks the container
            if msg == WM_MOUSEACTIVATE:
                # Get mouse position relative to container
                pt = wintypes.POINT()
                self.user32.GetCursorPos(ctypes.byref(pt))
                self.user32.ScreenToClient(hwnd, ctypes.byref(pt))

                # Check if mouse is over top or bottom screen and force focus
                if (self.tx <= pt.x <= self.tx + self.scrcpy.f_w1 and
                        self.ty <= pt.y <= self.ty + self.scrcpy.f_h1):
                    self.dock.force_focus(self.dock.hwnd_top)
                elif (self.bx <= pt.x <= self.bx + self.scrcpy.f_w2 and
                      self.by <= pt.y <= self.by + self.scrcpy.f_h2):
                    self.dock.force_focus(self.dock.hwnd_bottom)
                return MA_ACTIVATE

            # This is the ONLY place focus should be handled
            if msg == WM_PARENTNOTIFY:
                if (wp & 0xFFFF) == WM_LBUTTONDOWN:
                    mx = lp & 0xFFFF
                    my = (lp >> 16) & 0xFFFF

                    if (self.tx <= mx <= self.tx + self.scrcpy.f_w1 and
                            self.ty <= my <= self.ty + self.scrcpy.f_h1):
                        self.dock.force_focus(self.dock.hwnd_top)

                    elif (self.bx <= mx <= self.bx + self.scrcpy.f_w2 and
                          self.by <= my <= self.by + self.scrcpy.f_h2):
                        self.dock.force_focus(self.dock.hwnd_bottom)

            return self.user32.DefWindowProcW(hwnd, msg, wp, lp)

        return WNDPROC(py_wndproc)

    def _setup_gdi_signatures(self):
        """
        Tell ctypes the proper signatures for the GDI functions we invoke
        """
        gdi32 = ctypes.windll.gdi32
        gdi32.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
        gdi32.SelectObject.restype = wintypes.HGDIOBJ
        gdi32.CreateCompatibleDC.argtypes = [wintypes.HDC]
        gdi32.CreateCompatibleDC.restype = wintypes.HDC
        gdi32.DeleteDC.argtypes = [wintypes.HDC]
        gdi32.DeleteDC.restype = wintypes.BOOL
        gdi32.DeleteObject.argtypes = [wintypes.HGDIOBJ]
        gdi32.DeleteObject.restype = wintypes.BOOL
        gdi32.BitBlt.argtypes = [
            wintypes.HDC, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
            wintypes.HDC, ctypes.c_int, ctypes.c_int, wintypes.DWORD,
        ]
        gdi32.BitBlt.restype = wintypes.BOOL
        gdi32.GetStockObject.argtypes = [ctypes.c_int]
        gdi32.GetStockObject.restype = wintypes.HGDIOBJ

        self.user32.FillRect.argtypes = [
            wintypes.HDC, ctypes.POINTER(wintypes.RECT), wintypes.HBRUSH,
        ]

        self.user32.FillRect.restype = ctypes.c_int
        self.user32.UpdateWindow.argtypes = [wintypes.HWND]
        self.user32.UpdateWindow.restype = wintypes.BOOL

    def cycle_max_fps(self):
        """
        Cycle through the allowed FPS presets (30 -> 60 -> 120 -> 30)
        Persists to config. Takes effect on the next scrcpy restart;
        the user is expected to click RESTART afterwards.
        """
        try:
            idx = ALLOWED_FPS_VALUES.index(self.max_fps)
        except ValueError:
            idx = ALLOWED_FPS_VALUES.index(DEFAULT_MAX_FPS)
        new_fps = ALLOWED_FPS_VALUES[(idx + 1) % len(ALLOWED_FPS_VALUES)]
        self.set_max_fps(new_fps)
        return new_fps

    def set_max_fps(self, fps):
        """Set the FPS cap and persist; restart required to take effect"""
        if fps not in ALLOWED_FPS_VALUES:
            logger.warning(f"Ignoring out-of-range FPS request: {fps}")
            return
        logger.info(f"FPS preference changed: {self.max_fps} -> {fps}")
        self.max_fps = fps
        try:
            self.config.set("max_fps", fps)
        except Exception as e:
            logger.warning(f"Failed to persist max_fps: {e}")
        # Update the live ScrcpyManager so a restart picks it up
        if hasattr(self, "scrcpy"):
            self.scrcpy.max_fps = fps

    def restart_app(self):
        """
        Restart the entire application. Spawns a fresh main.py (or
        the bundled exe under PyInstaller) and exits this process.
        Used by the control panel after global-scale or FPS changes.
        """
        try:
            if getattr(sys, "frozen", False):
                project_root = os.path.dirname(sys.executable)
                cmd = [sys.executable]
            else:
                project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                main_script = os.path.join(project_root, "main.py")
                cmd = [sys.executable, main_script]

            child_env = os.environ.copy()
            for key in (
                "_MEIPASS2",
                "_PYI_APPLICATION_HOME_DIR",
                "_PYI_PARENT_PROCESS_LEVEL",
                "_PYI_SPLASH_IPC",
            ):
                child_env.pop(key, None)

            logger.info(f"Restarting application: {' '.join(cmd)}")
            subprocess.Popen(cmd, cwd=project_root, env=child_env)

        except Exception as e:
            logger.error(f"Failed to spawn restart process: {e}", exc_info=True)
            return

        self.stop()

    def _create_container_window(self):
        """
        Creates the main container window in a background thread
        Handles both scrcpy windows as children
        Waits for scrcpy dimensions to be available before creating window
        """

        def loop():
            # Wait for the window dimensions
            while self.scrcpy.f_w1 == 0:
                time.sleep(SCRCPY_POLL_INTERVAL)
                if not self.running:
                    return

            # Define window class structure
            class WNDCLASSEX(ctypes.Structure):
                _fields_ = [
                    ("cbSize", wintypes.UINT),
                    ("style", wintypes.UINT),
                    ("lpfnWndProc", ctypes.c_void_p),
                    ("cbClsExtra", ctypes.c_int),
                    ("cbWndExtra", ctypes.c_int),
                    ("hInstance", wintypes.HINSTANCE),
                    ("hIcon", wintypes.HANDLE),
                    ("hCursor", wintypes.HANDLE),
                    ("hbrBackground", wintypes.HANDLE),
                    ("lpszMenuName", wintypes.LPCWSTR),
                    ("lpszClassName", wintypes.LPCWSTR),
                    ("hIconSm", wintypes.HANDLE),
                ]

            # Register the class
            wc = WNDCLASSEX()
            wc.cbSize = ctypes.sizeof(WNDCLASSEX)
            wc.lpfnWndProc = ctypes.cast(self._wndproc, ctypes.c_void_p).value
            wc.lpszClassName = "DualCPYBridge"
            hinst = self.kernel32.GetModuleHandleW(None)
            wc.hInstance = hinst
            wc.hbrBackground = ctypes.windll.gdi32.GetStockObject(BLACK_BRUSH)

            # Load the application icon.
            # We build a list of candidate paths to try in order, because the
            # working directory differs between PyCharm, terminal, and PyInstaller.
            hicon = None
            IMAGE_ICON      = 1
            LR_LOADFROMFILE = 0x00000010
            LR_DEFAULTSIZE  = 0x00000040

            if getattr(sys, "frozen", False):
                # Frozen: try the PyInstaller _MEIPASS bundle, then extract from exe
                icon_candidates = [resource_path("assets/icon.ico")]
            else:
                # Dev: try cwd, the project root (one level above src/), and the
                # directory containing this file - covers all PyCharm run configs
                _this_dir    = os.path.dirname(os.path.abspath(__file__))
                _project_root = os.path.dirname(_this_dir)
                icon_candidates = [
                    os.path.join(os.path.abspath("."), "assets", "icon.ico"),
                    os.path.join(_project_root, "assets", "icon.ico"),
                    os.path.join(_this_dir,     "assets", "icon.ico"),
                ]

            for _path in icon_candidates:
                if not os.path.exists(_path):
                    continue
                try:
                    hicon = self.user32.LoadImageW(
                        None, _path, IMAGE_ICON, 0, 0,
                        LR_LOADFROMFILE | LR_DEFAULTSIZE,
                    )
                    if hicon:
                        logger.debug(f"Container icon loaded from: {_path}")
                        break
                except Exception as e:
                    logger.debug(f"LoadImageW failed for {_path}: {e}")

            # Final fallback for frozen builds: extract icon embedded in the exe
            if not hicon and getattr(sys, "frozen", False):
                try:
                    large_icons = (wintypes.HICON * 1)()
                    small_icons = (wintypes.HICON * 1)()
                    n = ctypes.windll.shell32.ExtractIconExW(
                        sys.executable, 0, large_icons, small_icons, 1,
                    )
                    if n > 0:
                        hicon = large_icons[0]
                        logger.debug("Container icon extracted from exe resources")
                    else:
                        logger.warning("ExtractIconExW returned 0 - container will have blank icon")
                except Exception as e:
                    logger.warning(f"ExtractIconExW failed: {e}")

            if hicon:
                wc.hIcon   = hicon
                wc.hIconSm = hicon

            self.user32.RegisterClassExW(ctypes.byref(wc))

            # Calculate container size to fit both stacked windows
            client_w = max(self.scrcpy.f_w1, self.scrcpy.f_w2 + abs(self.bx))
            client_h = self.scrcpy.f_h1 + self.scrcpy.f_h2

            # Adjustments for window decorations
            rect = wintypes.RECT(0, 0, int(client_w), int(client_h))
            style = WS_OVERLAPPEDWINDOW | WS_VISIBLE | WS_CLIPCHILDREN | WS_CLIPSIBLINGS
            self.user32.AdjustWindowRectEx(
                ctypes.byref(rect), style, False, WS_EX_CONTROLPARENT
            )

            # Build window title with device name if available
            device_label = getattr(self, "device_model", None) or "Unknown Device"
            window_title = f"DualCPY | {device_label}"

            # Create the container window
            hwnd = self.user32.CreateWindowExW(
                WS_EX_CONTROLPARENT,
                "DualCPYBridge",
                window_title,
                style,
                DEFAULT_CONTAINER_X,
                DEFAULT_CONTAINER_Y,
                rect.right - rect.left,
                rect.bottom - rect.top,
                None,
                0,
                ctypes.c_void_p(hinst),
                None,
            )

            if hwnd:
                self.hwnd_container = hwnd
                self.dock.hwnd_container = hwnd
                self.user32.ShowWindow(hwnd, SW_SHOW)

                # Enable the dark titlebar
                enable_dark_titlebar(hwnd)

            # Run the message loop for the container window
            msg = wintypes.MSG()
            while self.running and self.user32.GetMessageW(
                    ctypes.byref(msg), None, 0, 0
            ):
                self.user32.TranslateMessage(ctypes.byref(msg))
                self.user32.DispatchMessageW(ctypes.byref(msg))

        threading.Thread(target=loop, daemon=True).start()

    @property
    def _window_titles(self):
        return self.scrcpy._window_titles()

    def _docking_monitor(self):
        """
        Background thread to continuously montor and dock windows.
        Searches for titles and automatically sets their parent to the container window and applies styling
        """
        while self.running:
            with self.dock_lock:
                if self.hwnd_container and self.docked:
                    # Find scrcpy windows by their titles
                    top_title, bottom_title = self._window_titles
                    topScr = self.user32.FindWindowW(None, top_title)
                    bottomScr = self.user32.FindWindowW(None, bottom_title)

                    # Dock top screen if found and not already docked
                    if topScr and self.user32.GetParent(topScr) != self.hwnd_container:
                        self.user32.SetParent(topScr, self.hwnd_container)
                        apply_docked_style(topScr)
                        self.dock.hwnd_top = topScr

                    # Dock bottom screen if found and not already docked
                    if bottomScr and self.user32.GetParent(bottomScr) != self.hwnd_container:
                        self.user32.SetParent(bottomScr, self.hwnd_container)
                        apply_docked_style(bottomScr)
                        self.dock.hwnd_bottom = bottomScr
            time.sleep(DOCKING_MONITOR_TIME_DELAY)

    def toggle_dock(self):
        """
        Switches between docked and undocked mode
        Updates window styles and visibility
        """
        if not self.dock.hwnd_top or not self.dock.hwnd_bottom:
            logger.warning("Cannot toggle dock: windows not available")
            return

        # Use lock to prevent race condition with _docking_monitor
        with self.dock_lock:
            if self.docked:
                # Undock windows
                logger.info("Undocking windows")
                self.docked = False

                apply_undocked_style(self.dock.hwnd_top)
                apply_undocked_style(self.dock.hwnd_bottom)
                self.user32.ShowWindow(self.hwnd_container, SW_HIDE)

                self.dock.invalidate_geom_cache()
                logger.info("Windows undocked successfully")
            else:
                # Dock windows in a container
                logger.info("Docking windows")
                self.user32.ShowWindow(self.hwnd_container, SW_SHOW)

                top_title, bottom_title = self._window_titles

                # Re-find window handles in case they became invalid after undocking
                topScr = self.user32.FindWindowW(None, top_title)
                bottomScr = self.user32.FindWindowW(None, bottom_title)

                if not topScr or not bottomScr:
                    logger.error("Failed to find scrcpy windows for re-docking")
                    return

                # Update handles to ensure they're current
                self.dock.hwnd_top = topScr
                self.dock.hwnd_bottom = bottomScr

                self.user32.SetParent(self.dock.hwnd_top, self.hwnd_container)
                self.user32.SetParent(self.dock.hwnd_bottom, self.hwnd_container)
                apply_docked_style(self.dock.hwnd_top)
                apply_docked_style(self.dock.hwnd_bottom)
                self.dock.invalidate_geom_cache()
                self.docked = True

                logger.info("Windows docked successfully")

    def show_connection_dialog(self):
        """
        Shows the wireless connection dialog.
        Hides the scrcpy container window first so it doesn't conflict with
        the dialog grab, then restores it when the dialog closes.
        """
        logger.info("Opening wireless connection dialog - hiding scrcpy container")

        # Hide scrcpy container
        if self.hwnd_container:
            self.user32.ShowWindow(self.hwnd_container, SW_HIDE)

        try:
            result = show_wireless_dialog(self._tk_root, self.scrcpy, config=self.config)

            if result == 'connected':
                logger.info("Wireless connection established via dialog")
                return 'connected'
            elif result == 'disconnected':
                logger.info("Device disconnected via dialog")
                return 'disconnected'
            else:
                logger.info("Dialog closed without action")
                return None

        except Exception as e:
            logger.error(f"Error showing wireless dialog: {e}")
            messagebox.showerror(
                "Dialog Error", f"Failed to show wireless connection dialog")
            return None

        finally:
            logger.info("Wireless dialog closed - restoring scrcpy container")
            if self.hwnd_container:
                self.user32.ShowWindow(self.hwnd_container, SW_SHOW)

    def _launch_recovery_editor(self):
        """
        Open the profile editor as a recovery path when scrcpy fails to start.
        """
        if not getattr(self, "_hidden_ctk_root", None):
            self._hidden_ctk_root = _ctk.CTk()
            self._hidden_ctk_root.withdraw()

        DeviceProfileEditorDialog(
            parent=self._hidden_ctk_root,
            custom_store=self.custom_profiles,
            launcher=self,
        ).run()

        self.stop()

    def launch(self):
        self.running = True
        self._wndproc = self._create_wnd_proc()
        show_loading_screen()

        adb_bin = resolve_adb("adb")
        serial = detect_device(adb_bin)

        # If no device is found on boot, use wireless
        if not serial:
            logger.info("No USB device found on boot, offering wireless connection")

            response = messagebox.askyesno(
                "No Device Found",
                "No USB device detected.\n\n"
                "Would you like to connect wirelessly?\n\n"
                "Click Yes to open the wireless connection dialog,\n"
                "or No to exit."
            )

            if response:
                # The dialog requires ScrcpyManager to function.
                # We give it a temporary default profile just to work properly
                default_boot_profile = BUILTIN_PROFILES.get("ayn_thor") or list(BUILTIN_PROFILES.values())[0]
                self.scrcpy = ScrcpyManager(profile=default_boot_profile, scale=self.launch_scale, max_fps=self.max_fps)

                result = show_wireless_dialog(self._tk_root, self.scrcpy, config=self.config)

                if result == 'connected':
                    serial = self.scrcpy.serial
                    logger.info(f"Connected wirelessly to {serial}")
                else:
                    logger.info("No wireless connection established")
                    self.stop()
                    return
            else:
                logger.info("User chose to exit")
                self.stop()
                return

        if self._tk_root is None:
            _hidden = _ctk.CTk()
            _hidden.withdraw()
            self._tk_root = _hidden
            self._hidden_ctk_root = _hidden

        # Resolve device model name
        _dev_info = get_device_info(adb_bin, serial)
        self.device_model = (_dev_info or {}).get("model", "Unknown Device")

        # Check config for a previously saved profile for this serial
        device_profiles_map = self.config.get("device_profiles", {})
        remembered_key = device_profiles_map.get(serial)
        chosen_profile = None

        device_scales_map = self.config.get("device_scales", {})
        remembered_scale = device_scales_map.get(serial)

        if remembered_key:
            logger.info(f"Remembered profile key for {serial}: '{remembered_key}'")
            # Look up by storage key in custom store first
            all_custom = self.custom_profiles.load_all()

            if remembered_key in all_custom:
                chosen_profile = all_custom[remembered_key]
                logger.info(f"Resolved custom profile: '{chosen_profile.nickname or chosen_profile.name}'")
            # Fall back to builtin key lookup
            elif remembered_key in BUILTIN_PROFILES:
                chosen_profile = BUILTIN_PROFILES[remembered_key]
                logger.info(f"Resolved builtin profile: '{chosen_profile.name}'")
            else:
                logger.warning(
                    f"Remembered key '{remembered_key}' no longer exists - "
                    f"falling back to auto-detection"
                )

        if chosen_profile is not None:
            # Apply live display specs (same logic as device_selector)
            display_list = get_display_list(adb_bin, serial)

            if display_list and len(display_list) >= 2:
                flipped = chosen_profile.flipped_screens
                top_display    = display_list[1] if flipped else display_list[0]
                bottom_display = display_list[0] if flipped else display_list[1]

                chosen_profile = dc_replace(
                    chosen_profile,
                    top_display_id=str(top_display["id"]),
                    bottom_display_id=str(bottom_display["id"]),
                    top_screen_width=int(top_display["width"]),
                    top_screen_height=int(top_display["height"]),
                    bottom_screen_width=int(bottom_display["width"]),
                    bottom_screen_height=int(bottom_display["height"]),
                )

            logger.info(f"Using remembered profile: '{chosen_profile.name}'")
        else:
            chosen_profile = show_device_selector(
                BUILTIN_PROFILES,
                adb_bin,
                serial,
                custom_store=self.custom_profiles,
                parent_window=self._tk_root,
            )
            # Clear any stale per-device scale
            if chosen_profile is not None:
                try:
                    cfg = self.config.load()
                    device_scales = cfg.get("device_scales", {})

                    if serial in device_scales:
                        device_scales.pop(serial)
                        cfg["device_scales"] = device_scales
                        self.config.save(cfg)
                        logger.info(
                            f"Cleared stale device scale for {serial} "
                            f"so new profile default ({chosen_profile.default_ui_scale}) takes effect"
                        )

                except Exception as e:
                    logger.warning(f"Could not clear stale device scale: {e}")

                remembered_scale = None

        if chosen_profile is None:
            logger.info("No profile selected, exiting")
            self.stop()
            return

        # Keep this serial
        _custom_all = self.custom_profiles.load_all()
        _profile_key = next(
            (k for k, v in _custom_all.items() if v.name == chosen_profile.name
             and v.nickname == chosen_profile.nickname),
            next(
                (k for k, v in BUILTIN_PROFILES.items() if v.name == chosen_profile.name),
                chosen_profile.name,
            ),
        )

        if remembered_scale is not None:
            self.launch_scale = remembered_scale
            logger.info(f"Using remembered scale for {serial}: {remembered_scale}")
        else:
            self.launch_scale = chosen_profile.default_ui_scale
            logger.info(f"Using profile default scale: {chosen_profile.default_ui_scale}")

        self._save_device_profile(serial, _profile_key)

        # Re-instantiate ScrcpyManager with the actual proper profile
        self.scrcpy = ScrcpyManager(profile=chosen_profile, scale=self.launch_scale, max_fps=self.max_fps)
        self.scrcpy.serial = serial

        # Compute layout now that profile dimensions are known
        self.global_scale = self.scrcpy.scale
        self.launch_scale = self.scrcpy.scale

        w1, h1 = self.scrcpy.f_w1, self.scrcpy.f_h1
        w2, h2 = self.scrcpy.f_w2, self.scrcpy.f_h2

        self.ty = 0
        self.by = int(h1)

        # Screen alignment centering logic
        if w1 >= w2:
            # Top screen is wider (or equal): Top pins to 0, Bottom centers
            self.tx = 0
            self.bx = int((w1 - w2) * HALF)
        else:
            # Bottom screen is wider: Bottom pins to 0, Top centers over it
            self.bx = 0
            self.tx = int((w2 - w1) * HALF)

        logger.info(
            f"Layout set: Top({self.tx}, {self.ty}), Bottom({self.bx}, {self.by}) "
            f"at scale {self.global_scale} for profile '{chosen_profile.name}'"
        )

        # Start scrcpy
        if serial:
            logger.info(f"Starting scrcpy with device: {serial} (mode: {self.scrcpy.connection_mode})")
            try:
                self.scrcpy.start_scrcpy(serial=serial)
            except RuntimeError as e:
                messagebox.showerror(
                    "Scrcpy Failed to Start",
                    str(e) + "\n\nThe profile editor will open so you can fix the extra args.",
                )
                self._launch_recovery_editor()
                return
        else:
            logger.error("No device available to start scrcpy")
            self.stop()
            return

        # Start background threads
        self._create_container_window()
        threading.Thread(target=self._docking_monitor, daemon=True).start()

        # If we created a hidden bootstrap root for the profile dialog, destroy it
        if hasattr(self, "_hidden_ctk_root") and self._hidden_ctk_root:
            try:
                self._hidden_ctk_root.destroy()
            except Exception:
                pass
            self._hidden_ctk_root = None
            self._tk_root = None

        # Create control panel
        self.ui = CTkUI(self)
        self._tk_root = self.ui.window

        self.ui.run()

    def _resize_container_window(self):
        """
        Resize the existing container window to fit the current scrcpy dimensions.
        """
        if not self.hwnd_container:
            logger.warning("_resize_container_window: no container hwnd yet")
            return

        client_w = max(self.scrcpy.f_w1, self.scrcpy.f_w2 + abs(self.bx))
        client_h = self.scrcpy.f_h1 + self.scrcpy.f_h2

        style = WS_OVERLAPPEDWINDOW | WS_VISIBLE | WS_CLIPCHILDREN | WS_CLIPSIBLINGS
        rect  = wintypes.RECT(0, 0, int(client_w), int(client_h))
        self.user32.AdjustWindowRectEx(
            ctypes.byref(rect), style, False, WS_EX_CONTROLPARENT
        )

        new_w = rect.right - rect.left
        new_h = rect.bottom - rect.top

        SWP_NOMOVE = 0x0002
        SWP_NOZORDER = 0x0004
        SWP_NOACTIVATE = 0x0010
        SWP_FRAMECHANGED = 0x0020

        self.user32.SetWindowPos(
            self.hwnd_container, 0,
            0, 0, new_w, new_h,
            SWP_NOMOVE | SWP_NOZORDER | SWP_NOACTIVATE | SWP_FRAMECHANGED,
        )

        logger.info(f"Container resized to {new_w}x{new_h} (client {int(client_w)}x{int(client_h)})")

    def switch_profile(self, profile):
        """
        Switch the active device profile
        """
        logger.info(f"Switching profile to '{profile.name}'")

        serial = self.scrcpy.serial if self.scrcpy else None
        if not serial:
            logger.error("switch_profile: no active serial - cannot restart scrcpy")
            return

        # Stop current scrcpy
        try:
            self.scrcpy.stop()
        except Exception as e:
            logger.warning(f"Error stopping scrcpy during profile switch: {e}")

        # Clear stale dock handles - docking monitor will re-discover them
        with self.dock_lock:
            self.dock.hwnd_top = None
            self.dock.hwnd_bottom = None
            self.dock.invalidate_geom_cache()

        # make a new ScrcpyManager with the new profile's default scale
        self.launch_scale = profile.default_ui_scale
        self.global_scale = profile.default_ui_scale
        self.scrcpy = ScrcpyManager(
            profile=profile,
            scale=self.launch_scale,
            max_fps=self.max_fps,
        )
        self.scrcpy.serial = serial

        # setup default centred layout
        w1, h1 = self.scrcpy.f_w1, self.scrcpy.f_h1
        w2, h2 = self.scrcpy.f_w2, self.scrcpy.f_h2

        self.ty = 0
        self.by = int(h1)

        if w1 >= w2:
            self.tx = 0
            self.bx = int((w1 - w2) * HALF)
        else:
            self.bx = 0
            self.tx = int((w2 - w1) * HALF)

        logger.info(
            f"Profile switch layout: Top({self.tx},{self.ty}) "
            f"Bottom({self.bx},{self.by}) scale={self.global_scale}"
        )

        # Start scrcpy
        try:
            try:
                self.scrcpy.start_scrcpy(serial=serial)
            except RuntimeError as e:
                messagebox.showerror(
                    "Scrcpy Failed to Start",
                    str(e) + "\n\nThe profile editor will open so you can fix the extra args.",
                )
                self._launch_recovery_editor()
                return
        except Exception as e:
            logger.error(f"Failed to restart scrcpy after profile switch: {e}")
            return

        self.save_layout()
        self._resize_container_window()

        # Sync UI
        if hasattr(self, "ui") and self.ui:
            def _sync():
                try:
                    self.ui._sync_sliders_from_launcher()
                    self.ui.show_status(f"Profile loaded: {profile.name}", "success")
                except Exception as e:
                    logger.warning(f"UI sync after profile switch failed: {e}")

            self.ui.window.after(0, _sync)

    def stop(self):
        """
        Shuts down the application
        1) Saves current layout config
        2) Stops all scrcpy processes
        3) Closes the CTK control panel (stops mainloop)
        4) Closes the container window
        5) Force-exits
        """
        if not self.running:
            return
        self.running = False
        self.save_layout()

        # Taskkill the scrcpy processes
        subprocess.run(
            ["taskkill", "/F", "/IM", "scrcpy.exe", "/T"],
            capture_output=True,
            creationflags=CREATE_NO_WINDOW,
        )

        # Stop the CTK main loop
        try:
            if hasattr(self, "ui") and self.ui and self.ui.window:
                self.ui.window.quit()
        except Exception:
            pass

        if self.hwnd_container:
            self.user32.PostMessageW(self.hwnd_container, WM_CLOSE, 0, 0)
        os._exit(0)