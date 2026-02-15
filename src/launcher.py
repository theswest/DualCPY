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

# src/launcher.py

import threading
import time
import ctypes
import tkinter as tk
from tkinter import messagebox

import pygame
import os
import logging
from ctypes import wintypes

from src.scrcpy_manager import ScrcpyManager, TOP_SCREEN_WINDOW_TITLE, BOTTOM_SCREEN_WINDOW_TITLE
from src.win32_dock import Win32Dock, apply_docked_style, apply_undocked_style
from src.presets import PresetStore
from src.config import ConfigManager
from src.ui_pygame import show_loading_screen
from src.win32_darkmode import enable_dark_titlebar
from src.wireless_dialog import show_wireless_dialog

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

# Default layout positioning
TOP_SCREEN_DEFAULT_X = 0
TOP_SCREEN_DEFAULT_Y = 0
BOTTOM_SCREEN_DEFAULT_X = 0
BOTTOM_SCREEN_DEFAULT_Y = 0
DEFAULT_GLOBAL_SCALE = 0.6

# Container window initial position
DEFAULT_CONTAINER_X = 100
DEFAULT_CONTAINER_Y = 100

# Timing constants
SCRCPY_POLL_INTERVAL = 0.1
DOCKING_MONITOR_TIME_DELAY = 0.5
UI_FPS = 60

# Math constants
HALF = 0.5

# Default config
DEFAULT_LAYOUT = {"tx": TOP_SCREEN_DEFAULT_X, "ty": TOP_SCREEN_DEFAULT_Y,
                  "bx": BOTTOM_SCREEN_DEFAULT_X, "by": BOTTOM_SCREEN_DEFAULT_Y,
                  "global_scale": DEFAULT_GLOBAL_SCALE}


class Launcher:
    """
    Main window controller for ThorCPY
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

        # Load scale or use the default
        self.global_scale = self.config.get(
            "global_scale", DEFAULT_LAYOUT["global_scale"]
        )
        self.launch_scale = self.global_scale

        # Initialize Scrcpy with the saved scale
        self.scrcpy = ScrcpyManager(scale=self.launch_scale)

        # Calculate the forced layout (Top at 0,0 - bottom centred underneath) with scaled dimensions
        w1, h1 = self.scrcpy.f_w1, self.scrcpy.f_h1
        w2, _ = self.scrcpy.f_w2, self.scrcpy.f_h2

        self.tx = TOP_SCREEN_DEFAULT_X
        self.ty = TOP_SCREEN_DEFAULT_Y
        self.by = int(h1)
        self.bx = int(w1 * HALF - w2 * HALF)

        logger.info(
            f"Layout Reset: Top(0,0), Bottom({self.bx}, {self.by}) at Scale {self.global_scale}"
        )

        # Single persistent tkinter root so all dialogs use it as their parent without corrupting control window's state
        self._tk_root = tk.Tk()
        self._tk_root.withdraw()

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
        except Exception as ArgtypeError:
            logger.error(f"Error when defining window argtypes: {ArgtypeError}")
            pass

    def save_layout(self):
        """
        Saves current state and scale to config file in a single write
        Called during shutdown to keep settings.
        """
        try:
            cfg = self.config.load()
            cfg["tx"] = self.tx
            cfg["ty"] = self.ty
            cfg["bx"] = self.bx
            cfg["by"] = self.by
            cfg["global_scale"] = self.global_scale
            self.config.save(cfg)
            logger.info(f"Saved configuration (Scale: {self.global_scale})")
        except Exception as SaveConfigError:
            logger.error(f"Failed to save configuration: {SaveConfigError}")

    def save_scale(self):
        """Save only the global scale to config in a single write"""
        try:
            cfg = self.config.load()
            cfg["global_scale"] = self.global_scale
            self.config.save(cfg)
        except Exception as SaveScaleError:
            logger.error(f"Failed to save scale: {SaveScaleError}")

    def _create_wnd_proc(self):
        # We only need these two for the stable "double-click style" logic
        WM_LBUTTONDOWN = 0x0201
        WM_PARENTNOTIFY = 0x0210

        WNDPROC = ctypes.WINFUNCTYPE(
            self.LRESULT, wintypes.HWND, wintypes.UINT, self.WPARAM, self.LPARAM
        )

        def py_wndproc(hwnd, msg, wp, lp):
            if msg in (WM_CLOSE, WM_DESTROY):
                self.stop()
                return 0

            # New: Handle activation when the mouse enters/clicks the container
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
                    # lp contains coordinates relative to the ThorCPY container
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

    def _create_container_window(self):
        """
        Creates the main container window in a background thread
        Handles both scrcpy windows as children
        Waits for scrcpy dimensions to be available before creating window.
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
            wc.lpszClassName = "ThorFinalBridge"
            hinst = self.kernel32.GetModuleHandleW(None)
            wc.hInstance = hinst
            wc.hbrBackground = ctypes.windll.gdi32.GetStockObject(BLACK_BRUSH)

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

            # Create the container window
            hwnd = self.user32.CreateWindowExW(
                WS_EX_CONTROLPARENT,
                "ThorFinalBridge",
                "ThorCPY",
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

    def _docking_monitor(self):
        """
        Background thread to continuously montor and dock windows.
        Searches for titles and automatically sets their parent to the container window and applies styling
        """
        while self.running:
            with self.dock_lock:
                if self.hwnd_container and self.docked:
                    # Find scrcpy windows by their titles
                    topScr = self.user32.FindWindowW(None, TOP_SCREEN_WINDOW_TITLE)
                    bottomScr = self.user32.FindWindowW(None, BOTTOM_SCREEN_WINDOW_TITLE)

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

                logger.info("Windows undocked successfully")
            else:
                # Dock windows in a container
                logger.info("Docking windows")
                self.user32.ShowWindow(self.hwnd_container, SW_SHOW)

                # Re-find window handles in case they became invalid after undocking
                topScr = self.user32.FindWindowW(None, TOP_SCREEN_WINDOW_TITLE)
                bottomScr = self.user32.FindWindowW(None, BOTTOM_SCREEN_WINDOW_TITLE)

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
                self.docked = True

                logger.info("Windows docked successfully")

    def show_connection_dialog(self):
        """
        Shows the wireless connection dialog
        Hides the scrcpy container and pygame control panel first so their
        Win32 handles don't conflict with the tkinter dialog grab, then
        restores them when the dialog closes
        """
        logger.info("Opening wireless connection dialog — hiding scrcpy windows")

        # Hide pygame control panel
        try:
            info = pygame.display.get_wm_info()
            hwnd_pygame = info.get("window")
            if hwnd_pygame:
                self.user32.ShowWindow(hwnd_pygame, SW_HIDE)
        except Exception as HidePygameError:
            logger.warning(f"Could not hide pygame window: {HidePygameError}")

        # Hide scrcpy container and child windows
        if self.hwnd_container:
            self.user32.ShowWindow(self.hwnd_container, SW_HIDE)

        try:
            result = show_wireless_dialog(self._tk_root, self.scrcpy, config=self.config)

            if result == 'connected':
                logger.info("Wireless connection established via dialog")
                return True
            elif result == 'disconnected':
                logger.info("Device disconnected via dialog")
                return False
            else:
                logger.info("Dialog closed without action")
                return None

        except Exception as DialogError:
            logger.error(f"Error showing wireless dialog: {DialogError}")
            messagebox.showerror(
                "Dialog Error",
                f"Failed to show wireless connection dialog:\n{DialogError}"
            )
            return None

        finally:
            logger.info("Wireless dialog closed — restoring scrcpy windows")
            # Restore scrcpy container
            if self.hwnd_container:
                self.user32.ShowWindow(self.hwnd_container, SW_SHOW)

            # Restore pygame control panel
            try:
                info = pygame.display.get_wm_info()
                hwnd_pygame = info.get("window")
                if hwnd_pygame:
                    self.user32.ShowWindow(hwnd_pygame, SW_SHOW)
                    self.user32.SetForegroundWindow(hwnd_pygame)
            except Exception as ShowPygameError:
                logger.warning(f"Could not restore pygame window: {ShowPygameError}")

    def launch(self):
        """
        Main application entry point.
        Starts all components in the following order:
        1) Shows the loading screen
        2) Detects the android device via ADB or shows wireless window
        3) Start the scrcpy instances for both screens
        4) Creates the container window
        5) Starts the docking monitor
        6) Initialises the Pygame UI
        7) Enter the main event loop which handles:
         - Pygame events
         - Window position syncing
         - UI rendering

        It exits if no device is attached
        """
        self.running = True
        self._wndproc = self._create_wnd_proc()
        show_loading_screen()

        # Detect device
        serial = self.scrcpy.detect_device()

        # If no device found, suggest wireless connection
        if not serial:
            logger.info("No USB device found, offering wireless connection")

            response = messagebox.askyesno(
                "No Device Found",
                "No USB device detected.\n\n"
                "Would you like to connect wirelessly?\n\n"
                "Click Yes to open the wireless connection dialog,\n"
                "or No to exit."
            )

            if response:
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

        # Start scrcpy if no device is connected
        if serial:
            logger.info(f"Starting scrcpy with device: {serial} (mode: {self.scrcpy.connection_mode})")
            self.scrcpy.start_scrcpy(serial)
        else:
            logger.error("No device available to start scrcpy")
            self.stop()
            return

        # Start background threads
        self._create_container_window()
        threading.Thread(target=self._docking_monitor, daemon=True).start()

        # Init UI and event loop
        from src.ui_pygame import PygameUI

        pygame.init()
        self.ui = PygameUI(self)
        clock = pygame.time.Clock()

        while self.running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.stop()
                self.ui.handle_event(event)

            # Sync window positions if they exist
            if self.dock.hwnd_top or self.dock.hwnd_bottom:
                self.dock.sync(
                    self.tx,
                    self.ty,
                    self.bx,
                    self.by,
                    self.scrcpy.f_w1,
                    self.scrcpy.f_h1,
                    self.scrcpy.f_w2,
                    self.scrcpy.f_h2,
                    is_docked=self.docked,
                )
            self.ui.render()
            clock.tick(UI_FPS)

    def stop(self):
        """
        Cleanly shuts down the application
        Performs the following actions:
        1) Saves current layout config
        2) Stops all scrcpy processes
        3) Quits pygame
        4) Close the container window
        5) Force exit
        """
        if not self.running:
            return
        self.running = False
        self.save_layout()

        # Taskkill the scrcpy
        import subprocess
        subprocess.run(
            ["taskkill", "/F", "/IM", "scrcpy.exe", "/T"],
            capture_output=True,
            creationflags=CREATE_NO_WINDOW,
        )
        # Shutdown Pygame UI and close container window
        pygame.quit()
        if self.hwnd_container:
            self.user32.PostMessageW(self.hwnd_container, WM_CLOSE, 0, 0)
        os._exit(0)