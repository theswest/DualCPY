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

# src/ui_pygame.py

import pygame
import os
import tkinter as tk
import time
import logging
from ctypes import windll, byref, wintypes
import sys
from src.win32_darkmode import enable_dark_titlebar

# Setup logger for this module
logger = logging.getLogger(__name__)

# Colour Conversion Fallback
DEFAULT_HEX_COLOUR = (255,255,255)

# Loading screen configuration
LOADING_SCREEN_WIDTH = 400
LOADING_SCREEN_HEIGHT = 200
LOADING_SCREEN_FONT_SIZE = 36
LOADING_ANIMATION_FRAME_COUNT = 120
LOADING_SCREEN_COLOR = (18, 20, 24)
LOADING_SCREEN_X = 60
LOADING_SCREEN_Y = 80

# Control panel window configuration
CONTROL_PANEL_OFFSET_X = 460
CONTROL_PANEL_WIDTH = 450
# A bit taller than upstream to accommodate the FPS / RESTART row
CONTROL_PANEL_HEIGHT = 950

# Font sizes
LARGE_FONT_SIZE = 24
MEDIUM_FONT_SIZE = 16
SMALL_FONT_SIZE = 14

# Colour palette hex values
BG_HEX = "#121418"
PANEL_HEX = "#1e2128"
BORDER_HEX = "#2d3139"
TEXT_HEX = "#c8cdd8"
ACCENT_HEX = "#4a90e2"
TOP_HEX = "#e74c3c"
BOTTOM_HEX = "#3498db"
SUCCESS_HEX = "#2ecc71"
DANGER_HEX = "#e74c3c"
WARNING_HEX = "#f39c12"

# Status message config
INITIAL_STATUS_MESSAGE_TIME = 0
STATUS_MESSAGE_DURATION = 2.0
DEFAULT_STATUS_MESSAGE_TYPE = "info"

# Preset config
DEFAULT_PRESET_NAME = "NewPreset"
PRESET_CACHE_TIME = 0.5

# Slider dimensions and positioning
SLIDER_LABEL_X = 40
SLIDER_RECT_LEFT = 350
SLIDER_RECT_WIDTH = 60
SLIDER_RECT_HEIGHT = 25
SLIDER_BORDER_RADIUS = 3

SLIDER_TRACK_OFFSET_Y = 30
SLIDER_TRACK_RECT_LEFT = 40
SLIDER_TRACK_RECT_WIDTH = 370
SLIDER_TRACK_RECT_HEIGHT = 4
SLIDER_TRACK_BORDER_RADIUS = 2

SLIDER_HANDLE_FALLBACK_VALUE = 0.5
SLIDER_HANDLE_OFFSET_X = 8
SLIDER_HANDLE_OFFSET_Y = 6
SLIDER_HANDLE_WIDTH = 16
SLIDER_HANDLE_HEIGHT = 16

# Slider value constraints
SLIDER_DRAG_MINIMUM = 0.0
SLIDER_DRAG_MAXIMUM = 1.0

# Scale change detection threshold
SCALE_CHANGE_MIN_DETECTION = 0.01

# UI layout positions
TITLE_MARGIN_X = 20
TITLE_MARGIN_Y = 20
TITLE_SEPARATOR_Y = 60
TITLE_SEPARATOR_LEFT = 20
TITLE_SEPARATOR_RIGHT = 430

LAYOUT_HEADER_X = 20
LAYOUT_HEADER_Y = 80

# Global scale slider config
SLIDER_SCALE_Y = 120
GLOBAL_SCALE_MIN = 0.3
GLOBAL_SCALE_MAX = 1.0

RESTART_NOTIF_X = 40
RESTART_NOTIF_Y = 165

# Slider positions
SCREEN_MIN_POS = -500
SCREEN_MAX_POS = 1500
SLIDER_TOP_X_Y = 190
SLIDER_TOP_Y_Y = 250
SLIDER_BOTTOM_X_Y = 310
SLIDER_BOTTOM_Y_Y = 370

# FPS selector + RESTART row
FPS_BUTTON_X = 40
FPS_BUTTON_Y = 410
FPS_BUTTON_WIDTH = 180
FPS_BUTTON_HEIGHT = 36

# FPS dropdown menu (drawn last so it overlays everything below it).
FPS_MENU_ITEM_HEIGHT = 30
FPS_MENU_PADDING = 4

RESTART_BUTTON_X = 230
RESTART_BUTTON_Y = 410
RESTART_BUTTON_WIDTH = 180
RESTART_BUTTON_HEIGHT = 36

# Dock/Undock button
UNDOCK_BUTTON_X = 40
UNDOCK_BUTTON_Y = 460
UNDOCK_BUTTON_WIDTH = 180
UNDOCK_BUTTON_HEIGHT = 36

# Screenshot button
SCREENSHOT_BUTTON_X = 230
SCREENSHOT_BUTTON_Y = 460
SCREENSHOT_BUTTON_WIDTH = 180
SCREENSHOT_BUTTON_HEIGHT = 36

# Wireless button
WIRELESS_BUTTON_X = 40
WIRELESS_BUTTON_Y = 505
WIRELESS_BUTTON_WIDTH = 370
WIRELESS_BUTTON_HEIGHT = 36

STATUS_TEXT_X = 225
STATUS_TEXT_Y = 550

# Preset section layout
PRESET_DIVIDER_Y = 555
PRESET_DIVIDER_LEFT = 20
PRESET_DIVIDER_RIGHT = 430

PRESET_HEADER_X = 20
PRESET_HEADER_Y = 575

PRESET_Y = 610
PRESET_HEIGHT = 35

PRESET_INPUT_X = 40
PRESET_INPUT_WIDTH = 250

PRESET_TEXT_PADDING_X = 10

PRESET_SAVE_BUTTON_X = 300
PRESET_SAVE_BUTTON_WIDTH = 110

PRESET_BORDER_RADIUS = 5

# Win32 SetWindowPos flags
SWP_NOZORDER = 0x0004
SWP_NOACTIVATE = 0x0010
SWP_FRAMECHANGED = 0x0020
SWP_NOMOVE = 0x0002
SWP_NOSIZE = 0x0001

# Text colors for buttons
WHITE_TEXT = (255, 255, 255)
BLACK_TEXT = (0, 0, 0)

# Preset list layout
PRESET_LIST_HEADER_X = 20
PRESET_LIST_HEADER_Y = 670
PRESET_LIST_Y_OFFSET = 705

PRESET_ROW_X = 30
PRESET_ROW_WIDTH = 390
PRESET_ROW_HEIGHT = 40
PRESET_NAME_X_OFFSET = 15

PRESET_LOAD_BUTTON_X = 260
PRESET_DELETE_BUTTON_X = 340
PRESET_BUTTON_Y_OFFSET = 5
PRESET_BUTTON_WIDTH = 70
PRESET_BUTTON_HEIGHT = 30
BUTTON_BORDER_RADIUS = 4

PRESET_ROW_SPACING = 45

# Error message durations
ERROR_STATUS_DURATION = 3.0
SLIDER_ERROR_STATUS_DURATION = 1.5

# Windows clipboard and GDI constants
CF_BITMAP = 2  # Clipboard format for bitmap images
SRCCOPY = 0x00CC0020  # BitBlt copy mode (straight pixel copy)
SW_SHOW = 5


def resource_path(rel):
    """
    Get absolute path to resource, works for python files and for PyInstaller

    PyInstaller bundles resources to a temporary folder (_MEIPASS).
    In development, resources are relative to the script location

    Args:
        rel: Relative path to resource

    Returns:
        Absolute path to resource
    """
    try:
        if hasattr(sys, "_MEIPASS"):
            path = os.path.join(sys._MEIPASS, rel)
            logger.debug(f"Resource path (PyInstaller): {path}")
            return path
        path = os.path.join(os.path.abspath("."), rel)
        logger.debug(f"Resource path (dev): {path}")
        return path
    except Exception as PathResolutionError:
        logger.error(f"Failed to resolve resource path for '{rel}': {PathResolutionError}")
        return rel

# Assets path
FONT_PATH = resource_path("assets/fonts/CalSans-Regular.ttf")
ICON_PATH = resource_path("assets/icon.png")


def hex_to_rgb(hex_color):
    """
    Convert hex color to RGB tuple

    Supports multiple formats:
    "#FF0000", "FF0000". "0xFF0000"

    Args:
        hex_color: Hex string (e.g., "#FF0000" or "FF0000") or int (0xFF0000)

    Returns:
        tuple: (r, g, b)
    """
    try:
        if isinstance(hex_color, int):
            hex_color = f"{hex_color:06x}"

        if isinstance(hex_color, str):
            hex_color = hex_color.lstrip("#")

        rgb = tuple(int(hex_color[i : i + 2], 16) for i in (0, 2, 4))
        return rgb
    except Exception as HexConversionError:
        logger.error(f"Failed to convert hex color '{hex_color}': {HexConversionError}")
        return DEFAULT_HEX_COLOUR


# Loading Screen Manager
def show_loading_screen():
    """
    Shows a small startup screen for about 2 seconds.
    """
    logger.info("Initializing loading screen")

    try:
        pygame.init()
    except Exception as PygameInitError:
        logger.error(f"Failed to initialize pygame for loading screen: {PygameInitError}")
        return

    # Set window icon
    try:
        icon_surface = pygame.image.load(ICON_PATH)
        pygame.display.set_icon(icon_surface)
        logger.debug("Loading screen icon set successfully")
    except Exception as LoadingScreenInitError:
        logger.warning(f"Failed to load icon for loading screen: {LoadingScreenInitError}")

    # Initialize window
    try:
        screen = pygame.display.set_mode((LOADING_SCREEN_WIDTH, LOADING_SCREEN_HEIGHT))
        pygame.display.set_caption("ThorCPY Loading...")
        logger.debug("Loading screen window created")
    except Exception as LoadingScreenCreationError:
        logger.error(f"Failed to create loading screen window: {LoadingScreenCreationError}")
        return

    # Enable the dark titlebar for the window
    try:
        info = pygame.display.get_wm_info()
        hwnd = info.get("window")
        if hwnd:
            enable_dark_titlebar(hwnd)
            logger.debug("Loading screen dark titlebar enabled")
    except Exception as DarkTitlebarEnableError:
        logger.warning(f"Failed to enable dark titlebar for loading screen: {DarkTitlebarEnableError}")

    # Setup font
    try:
        font = pygame.font.Font(FONT_PATH, LOADING_SCREEN_FONT_SIZE)
        logger.debug("Loading screen font loaded")
    except Exception as LoadingFontError:
        logger.warning(f"Failed to load custom font, using default: {LoadingFontError}")
        font = pygame.font.SysFont("Arial", LOADING_SCREEN_FONT_SIZE)

    # Animation loop
    clock = pygame.time.Clock()
    logger.debug(f"Starting loading screen animation ({LOADING_ANIMATION_FRAME_COUNT} frames)")
    for frame in range(LOADING_ANIMATION_FRAME_COUNT):
        try:
            screen.fill(LOADING_SCREEN_COLOR)
            txt = font.render("Starting ThorCPY...", True, (200, 200, 200))
            screen.blit(txt, (LOADING_SCREEN_X, LOADING_SCREEN_Y))
            pygame.display.flip()
            clock.tick(LOADING_ANIMATION_FRAME_COUNT/2)
        except Exception as LoadingScreenRenderError:
            logger.error(f"Error during loading screen render at frame {frame}: {LoadingScreenRenderError}")
            break

    # Cleanup
    try:
        pygame.display.quit()
        logger.info("Loading screen closed")
    except Exception as LoadingScreenCloseError:
        logger.warning(f"Error closing loading screen: {LoadingScreenCloseError}")


# Main Pygame UI class
class PygameUI:
    """
    Main controller UI
    Renders the control panel and manages user interaction
    """

    def __init__(self, launcher):
        """
        Initialize the control panel UI.

        Args:
            launcher: Reference to main Launcher instance for state access
        """
        logger.info("Initializing PygameUI")

        # Reference to the main launcher and controller object
        self.l = launcher

        try:
            pygame.init()
            logger.debug("Pygame initialized for UI")
        except Exception as PygameInitError:
            logger.error(f"Failed to initialize pygame: {PygameInitError}")
            raise

        # Set window icon
        try:
            icon_surface = pygame.image.load(ICON_PATH)
            pygame.display.set_icon(icon_surface)
            logger.debug("UI window icon set successfully")
        except Exception as IconLoadError:
            logger.warning(f"Failed to load UI icon: {IconLoadError}")

        # Position the UI on the far right of the screen
        try:
            root = tk.Tk()
            sw = root.winfo_screenwidth()
            root.destroy()
            x_pos = sw - CONTROL_PANEL_OFFSET_X
            os.environ["SDL_VIDEO_WINDOW_POS"] = f"{x_pos},50"
            logger.debug(f"UI window position set to ({x_pos}, 50)")
        except Exception as ControlWindowPositionError:
            logger.warning(f"Failed to position UI window: {ControlWindowPositionError}")

        # Create window
        try:
            self.screen = pygame.display.set_mode((CONTROL_PANEL_WIDTH, CONTROL_PANEL_HEIGHT))
            pygame.display.set_caption("ThorCPY Control Panel")
            logger.debug("UI window created successfully")
        except Exception as UICreationError:
            logger.error(f"Failed to create UI window: {UICreationError}")
            raise

        # Enable the dark titlebar for the window
        try:
            info = pygame.display.get_wm_info()
            hwnd = info.get("window")
            if hwnd:
                enable_dark_titlebar(hwnd)
                logger.debug("UI window dark titlebar enabled")
        except Exception as DarkTitlebarError:
            logger.warning(f"Failed to enable dark titlebar for UI window: {DarkTitlebarError}")

        # Load font
        try:
            self.font_lg = pygame.font.Font(FONT_PATH, LARGE_FONT_SIZE)
            self.font_md = pygame.font.Font(FONT_PATH, MEDIUM_FONT_SIZE)
            self.font_sm = pygame.font.Font(FONT_PATH, SMALL_FONT_SIZE)
            logger.debug("UI fonts loaded successfully")
        except Exception as UIFontLoadError:
            logger.warning(f"Failed to load custom fonts, using default: {UIFontLoadError}")
            self.font_lg = pygame.font.SysFont("Arial", LARGE_FONT_SIZE)
            self.font_md = pygame.font.SysFont("Arial", MEDIUM_FONT_SIZE)
            self.font_sm = pygame.font.SysFont("Arial", SMALL_FONT_SIZE)

        # Colors
        self.colors = {
            "bg": hex_to_rgb(BG_HEX),
            "panel": hex_to_rgb(PANEL_HEX),
            "border": hex_to_rgb(BORDER_HEX),
            "text": hex_to_rgb(TEXT_HEX),
            "accent": hex_to_rgb(ACCENT_HEX),
            "top": hex_to_rgb(TOP_HEX),
            "bot": hex_to_rgb(BOTTOM_HEX),
            "success": hex_to_rgb(SUCCESS_HEX),
            "danger": hex_to_rgb(DANGER_HEX),
            "warning": hex_to_rgb(WARNING_HEX),
        }

        try:
            raw_logo = pygame.image.load(ICON_PATH).convert_alpha()
            self.title_logo = pygame.transform.smoothscale(raw_logo, (40, 40))
        except Exception as TitleLogoError:
            logger.warning(f"Failed to prep title logo: {TitleLogoError}")
            self.title_logo = None

        # Slider interaction
        self.dragging = None  # Currently dragged slider
        self.m_locked = False  # If mouse has been released
        self.pressed_button = None  # Track which button was pressed

        # Status message
        self.status_msg = ""
        self.status_time = INITIAL_STATUS_MESSAGE_TIME
        self.status_duration = STATUS_MESSAGE_DURATION
        self.status_type = DEFAULT_STATUS_MESSAGE_TYPE

        # Preset input
        self.preset_name = DEFAULT_PRESET_NAME
        self.active_input = False

        # Slider input
        self.active_slider_input = None
        self.input_buffer = ""

        # Cached presets
        self._preset_cache = None
        self._preset_cache_time = 0

        # Track scale changes
        self._scale_changed = False
        self._original_scale = self.l.global_scale

        # FPS dropdown menu state.
        self._fps_menu_open = False

        logger.info("PygameUI initialization complete")

    def invalidate_preset_cache(self):
        """Force preset list to reload on the next access"""
        self._preset_cache = None
        logger.debug("Preset cache invalidated")

    def get_presets(self):
        """
        Get preset list with caching to reduce file I/O.
        Cache is invalidated after PRESET_CACHE_TIME seconds or manually via invalidate_preset_cache().

        Returns:
            dict: Preset name -> preset data mapping
        """
        current_time = time.time()

        if self._preset_cache is None or (current_time - self._preset_cache_time) > PRESET_CACHE_TIME:
            self._preset_cache = self.l.store.load_all()
            self._preset_cache_time = current_time
            logger.debug(
                f"Preset cache refreshed with {len(self._preset_cache)} presets"
            )

        return self._preset_cache

    def show_status(self, msg, status_type=DEFAULT_STATUS_MESSAGE_TYPE,
                    duration=STATUS_MESSAGE_DURATION):
        """
        Display a status message at the bottom of the UI

        Args:
            msg: Message to display
            status_type: Type of message (info, success, error, warning)
            duration: How long to show the message in seconds
        """
        logger.debug(f"Showing status: [{status_type}] {msg}")
        self.status_msg = msg
        self.status_type = status_type
        self.status_time = time.time()
        self.status_duration = duration

    def take_screenshot(self):
        """
        Takes a screenshot of both windows and copies it to the clipboard

        Uses windows GDI to get the container window's client area
        Only works when windows are docked
        """
        logger.info("Taking screenshot of docked windows")
        user32 = windll.user32
        gdi32 = windll.gdi32

        try:
            if not self.l.hwnd_container or not self.l.docked:
                logger.warning(
                    "Screenshot aborted: container not available or not docked"
                )
                self.show_status("Must be docked to screenshot", "warning")
                return

            # Get container window area
            rect = wintypes.RECT()
            if not user32.GetClientRect(self.l.hwnd_container, byref(rect)):
                logger.error("Failed to get container client rect")
                self.show_status("Screenshot failed", "error")
                return

            w = rect.right - rect.left
            h = rect.bottom - rect.top
            logger.debug(f"Container dimensions: {w}x{h}")

            # Get Device Contexts
            hwnd_dc = user32.GetDC(self.l.hwnd_container)
            if not hwnd_dc:
                logger.error("Failed to get container DC")
                self.show_status("Screenshot failed", "error")
                return

            mem_dc = gdi32.CreateCompatibleDC(hwnd_dc)
            if not mem_dc:
                logger.error("Failed to create compatible DC")
                user32.ReleaseDC(self.l.hwnd_container, hwnd_dc)
                self.show_status("Screenshot failed", "error")
                return

            bitmap = gdi32.CreateCompatibleBitmap(hwnd_dc, w, h)
            if not bitmap:
                logger.error("Failed to create compatible bitmap")
                gdi32.DeleteDC(mem_dc)
                user32.ReleaseDC(self.l.hwnd_container, hwnd_dc)
                self.show_status("Screenshot failed", "error")
                return

            # Copy pixels to bitmap
            old_bitmap = gdi32.SelectObject(mem_dc, bitmap)
            success = gdi32.BitBlt(mem_dc, 0, 0, w, h, hwnd_dc, 0, 0, SRCCOPY)

            if not success:
                logger.error("BitBlt failed during screenshot")
                self.show_status("Screenshot failed", "error")
            else:
                # Copy the bitmap to clipboard
                user32.OpenClipboard(0)
                user32.EmptyClipboard()
                user32.SetClipboardData(CF_BITMAP, bitmap)
                user32.CloseClipboard()
                logger.info("Screenshot copied to clipboard successfully")
                self.show_status("Screenshot copied to clipboard", "success")

            # Cleanup GDI objects
            gdi32.SelectObject(mem_dc, old_bitmap)
            gdi32.DeleteObject(bitmap)
            gdi32.DeleteDC(mem_dc)
            user32.ReleaseDC(self.l.hwnd_container, hwnd_dc)

        except Exception as ScreenshotErrot:
            logger.error(f"Screenshot error: {ScreenshotErrot}", exc_info=True)
            self.show_status("Screenshot failed", "error")

    def draw_slider(self, label, y_pos, val, min_val, max_val, color, attr_name):
        """
        Draw a slider control with editable value box

        Args:
            label: Label text for the slider
            y_pos: Y position to draw at
            val: Current value
            min_val: Minimum value
            max_val: Maximum value
            color: Color for the slider
            attr_name: Attribute name (tx, ty, bx, by) for keyboard input
        """
        try:
            mx, my = pygame.mouse.get_pos()
            m_click = pygame.mouse.get_pressed()[0]

            # Draw label
            self.screen.blit(self.font_md.render(label, True, self.colors["text"]),
                             (SLIDER_LABEL_X, y_pos))

            # Value display box
            val_box = pygame.Rect(SLIDER_RECT_LEFT, y_pos, SLIDER_RECT_WIDTH, SLIDER_RECT_HEIGHT)
            box_hover = val_box.collidepoint(mx, my)
            box_active = self.active_slider_input == attr_name

            box_color = (
                self.colors["accent"]
                if box_active
                else (self.colors["border"] if box_hover else self.colors["panel"])
            )
            pygame.draw.rect(self.screen, box_color, val_box, border_radius=SLIDER_BORDER_RADIUS)

            # Format value text
            if box_active:
                val_text = self.input_buffer
            elif attr_name == "global_scale":
                val_text = f"{val:.2f}"
            else:
                val_text = str(int(val))

            val_render = self.font_sm.render(val_text, True, self.colors["text"])
            val_rect = val_render.get_rect(center=val_box.center)
            self.screen.blit(val_render, val_rect)

            # Activate keyboard input on click
            if m_click and box_hover and not self.m_locked:
                if not box_active:
                    self.active_slider_input = attr_name
                    if attr_name == "global_scale":
                        self.input_buffer = f"{val:.2f}"
                    else:
                        self.input_buffer = str(int(val))
                    self.active_input = False
                    logger.debug(f"Activated slider input for {attr_name}")
                self.m_locked = True

            # Draw slider Track
            track_y = y_pos + SLIDER_TRACK_OFFSET_Y
            track_rect = pygame.Rect(SLIDER_TRACK_RECT_LEFT, track_y, SLIDER_TRACK_RECT_WIDTH,
                                     SLIDER_TRACK_RECT_HEIGHT)
            pygame.draw.rect(
                self.screen, self.colors["border"], track_rect, border_radius=SLIDER_TRACK_BORDER_RADIUS
            )

            # Calculate handle position
            norm_val = ((val - min_val) / (max_val - min_val) if max_val != min_val else SLIDER_HANDLE_FALLBACK_VALUE)
            handle_x = SLIDER_LABEL_X + int(norm_val * SLIDER_TRACK_RECT_WIDTH)
            handle_rect = pygame.Rect(handle_x - SLIDER_HANDLE_OFFSET_X, track_y - SLIDER_HANDLE_OFFSET_Y,
                                      SLIDER_HANDLE_WIDTH, SLIDER_HANDLE_HEIGHT)
            handle_hover = handle_rect.collidepoint(mx, my)

            # Handle with hover feedback
            handle_color = (
                self.colors["text"]
                if handle_hover or self.dragging == attr_name
                else color
            )
            pygame.draw.circle(self.screen, handle_color, (handle_x, track_y + 2), 8)

            # Start drag on click
            if m_click and handle_hover and not self.m_locked and not self.dragging:
                self.dragging = attr_name
                logger.debug(f"Started dragging slider: {attr_name}")

            # Update value whilst dragging
            if self.dragging == attr_name and m_click:
                new_norm = max(SLIDER_DRAG_MINIMUM, min(SLIDER_DRAG_MAXIMUM,
                                                        (mx - SLIDER_TRACK_RECT_LEFT) / SLIDER_TRACK_RECT_WIDTH))
                new_val = min_val + new_norm * (max_val - min_val)
                setattr(self.l, attr_name, new_val)

                # Check to see if global scale has changed
                if (
                    attr_name == "global_scale"
                    and abs(new_val - self._original_scale) > SCALE_CHANGE_MIN_DETECTION
                ):
                    self._scale_changed = True

            # Save on drag release
            if not m_click and self.dragging == attr_name:
                logger.debug(f"Stopped dragging slider: {attr_name}")
                # Save scale separately when scale slider released
                if attr_name == "global_scale":
                    self.l.save_scale()
                else:
                    self.l.save_layout()
                self.dragging = None

        except Exception as SliderDrawError:
            logger.error(f"Error drawing slider '{label}': {SliderDrawError}", exc_info=True)

    def render(self):
        """
        Main render loop for the UI
        Draws all UI elements and handles the mouse interactions
        """
        try:
            mx, my = pygame.mouse.get_pos()
            m_click = pygame.mouse.get_pressed()[0]

            self.screen.fill(self.colors["bg"])

            # Title
            title_txt = self.font_lg.render("ThorCPY Control Panel", True, self.colors["text"])
            self.screen.blit(title_txt, (TITLE_MARGIN_X, TITLE_MARGIN_Y))

            pygame.draw.line(self.screen, self.colors["border"], (TITLE_SEPARATOR_LEFT, TITLE_SEPARATOR_Y),
                             (TITLE_SEPARATOR_RIGHT, TITLE_SEPARATOR_Y))

            # Layout controls header
            self.screen.blit(
                self.font_lg.render("Layout Controls", True, self.colors["text"]),
                (LAYOUT_HEADER_X, LAYOUT_HEADER_Y),
            )

            # Global Scale Slider
            scale_label = (
                f"GLOBAL SCALE - Active: {self.l.launch_scale:.2f}"
            )
            self.draw_slider(
                scale_label,
                SLIDER_SCALE_Y,
                self.l.global_scale,
                GLOBAL_SCALE_MIN,
                GLOBAL_SCALE_MAX,
                self.colors["accent"],
                "global_scale",
            )

            # Restart notification for if the scale has changed
            if hasattr(self, "_scale_changed") and self._scale_changed:
                restart_txt = self.font_sm.render(
                    "Restart ThorCPY to apply scale", True, self.colors["warning"]
                )
                self.screen.blit(restart_txt, (RESTART_NOTIF_X, RESTART_NOTIF_Y))

            # Sliders
            self.draw_slider(
                "TOP X", SLIDER_TOP_X_Y, self.l.tx, SCREEN_MIN_POS, SCREEN_MAX_POS,
                self.colors["top"], "tx"
            )
            self.draw_slider(
                "TOP Y", SLIDER_TOP_Y_Y, self.l.ty, SCREEN_MIN_POS, SCREEN_MAX_POS,
                self.colors["top"], "ty"
            )
            self.draw_slider(
                "BOTTOM X", SLIDER_BOTTOM_X_Y, self.l.bx, SCREEN_MIN_POS, SCREEN_MAX_POS,
                self.colors["bot"], "bx"
            )
            self.draw_slider(
                "BOTTOM Y", SLIDER_BOTTOM_Y_Y, self.l.by, SCREEN_MIN_POS, SCREEN_MAX_POS,
                self.colors["bot"], "by"
            )

            # FPS selector. Click opens a small popup with each
            # allowed FPS value; pick one to set, or click outside to
            # dismiss. The dropdown itself is rendered LAST in this
            # method so it stacks on top of everything else.
            fps_btn = pygame.Rect(
                FPS_BUTTON_X, FPS_BUTTON_Y, FPS_BUTTON_WIDTH, FPS_BUTTON_HEIGHT
            )
            fps_hover = fps_btn.collidepoint(mx, my)
            current_fps = getattr(self.l, "max_fps", 60)
            fps_face = (
                self.colors["accent"] if self._fps_menu_open
                else (self.colors["border"] if fps_hover else self.colors["panel"])
            )
            fps_text_color = WHITE_TEXT if self._fps_menu_open else self.colors["text"]
            pygame.draw.rect(self.screen, fps_face, fps_btn, border_radius=PRESET_BORDER_RADIUS)
            fps_text = self.font_md.render(f"FPS: {current_fps}  v", True, fps_text_color)
            self.screen.blit(fps_text, fps_text.get_rect(center=fps_btn.center))

            if fps_hover and m_click and not self.m_locked and not self.dragging:
                self.pressed_button = "fps"
            if not m_click and self.pressed_button == "fps":
                if fps_hover:
                    self._fps_menu_open = not self._fps_menu_open
                self.pressed_button = None

            # RESTART button - hard restart of the whole app so global
            # scale and FPS changes take effect cleanly.
            restart_btn = pygame.Rect(
                RESTART_BUTTON_X, RESTART_BUTTON_Y,
                RESTART_BUTTON_WIDTH, RESTART_BUTTON_HEIGHT,
            )
            restart_hover = restart_btn.collidepoint(mx, my)
            r_face = self.colors["warning"] if restart_hover else hex_to_rgb("#c87a0e")
            pygame.draw.rect(self.screen, r_face, restart_btn, border_radius=PRESET_BORDER_RADIUS)
            r_text = self.font_md.render("RESTART", True, BLACK_TEXT)
            self.screen.blit(r_text, r_text.get_rect(center=restart_btn.center))

            if restart_hover and m_click and not self.m_locked and not self.dragging:
                self.pressed_button = "restart"
            if not m_click and self.pressed_button == "restart":
                if restart_hover and hasattr(self.l, "restart_app"):
                    logger.info("Restart button clicked")
                    self.show_status("Restarting...", "info", duration=0.5)
                    pygame.display.flip()
                    self.l.restart_app()
                self.pressed_button = None

            # Undock/Dock Button
            undock_btn = pygame.Rect(UNDOCK_BUTTON_X, UNDOCK_BUTTON_Y, UNDOCK_BUTTON_WIDTH, UNDOCK_BUTTON_HEIGHT)
            u_hover = undock_btn.collidepoint(mx, my)
            btn_text = "DOCK  WINDOWS" if not self.l.docked else "UNDOCK  WINDOWS"

            btn_color = self.colors["panel"]
            text_color = self.colors["text"]

            pygame.draw.rect(self.screen, btn_color, undock_btn, border_radius=5)
            utxt = self.font_md.render(btn_text, True, text_color)
            text_rect = utxt.get_rect(center=undock_btn.center)
            self.screen.blit(utxt, text_rect)

            # Dock button logic
            if m_click and u_hover and not self.m_locked and not self.dragging:
                self.pressed_button = "dock"

            if not m_click and self.pressed_button == "dock":
                if u_hover:
                    logger.info("Dock toggle button clicked")
                    self.l.toggle_dock()
                self.pressed_button = None

            # Screenshot Button
            shot_btn = pygame.Rect(SCREENSHOT_BUTTON_X, SCREENSHOT_BUTTON_Y, SCREENSHOT_BUTTON_WIDTH,
                                   SCREENSHOT_BUTTON_HEIGHT)
            s_hover = shot_btn.collidepoint(mx, my)

            if self.l.docked:
                s_color = self.colors["panel"] if not s_hover else self.colors["border"]
                s_text_color = self.colors["text"]
                s_label = "SCREENSHOT"
            else:
                s_color = (45, 48, 56)
                s_text_color = (100, 105, 115)
                s_label = "LOCKED (UNDOCKED)"

            pygame.draw.rect(self.screen, s_color, shot_btn, border_radius=5)
            stxt = self.font_md.render(s_label, True, s_text_color)
            stxt_rect = stxt.get_rect(center=shot_btn.center)
            self.screen.blit(stxt, stxt_rect)

            if (
                s_hover
                and m_click
                and not self.m_locked
                and self.l.docked
                and not self.dragging
            ):
                self.take_screenshot()
                self.m_locked = True

            # Wireless Button
            wireless_btn = pygame.Rect(
                WIRELESS_BUTTON_X, WIRELESS_BUTTON_Y,
                WIRELESS_BUTTON_WIDTH, WIRELESS_BUTTON_HEIGHT
            )
            w_hover = wireless_btn.collidepoint(mx, my)

            # Label shows current connection state
            serial = self.l.scrcpy.serial
            mode = self.l.scrcpy.connection_mode
            if serial and mode == 'wireless':
                w_label = f"WIRELESS  •  Connected!"
                w_color = self.colors["success"] if not w_hover else hex_to_rgb("#27ae60")
                w_text_color = BLACK_TEXT
            elif serial and mode == 'usb':
                w_label = "WIRELESS  •  USB connected"
                w_color = self.colors["panel"] if not w_hover else self.colors["border"]
                w_text_color = self.colors["text"]
            else:
                w_label = "WIRELESS  •  No device"
                w_color = self.colors["panel"] if not w_hover else self.colors["border"]
                w_text_color = self.colors["text"]

            pygame.draw.rect(self.screen, w_color, wireless_btn, border_radius=5)
            wtxt = self.font_md.render(w_label, True, w_text_color)
            wtxt_rect = wtxt.get_rect(center=wireless_btn.center)
            self.screen.blit(wtxt, wtxt_rect)

            if w_hover and m_click and not self.m_locked and not self.dragging:
                self.pressed_button = "wireless"

            if not m_click and self.pressed_button == "wireless":
                if w_hover:
                    logger.info("Wireless button clicked — opening connection dialog")
                    self._open_wireless_dialog = True
                self.pressed_button = None

            # Open wireless dialog on main thread (tkinter requirement)
            if getattr(self, '_open_wireless_dialog', False):
                self._open_wireless_dialog = False
                result = self.l.show_connection_dialog()
                if result is True:
                    self.show_status("Wireless connected", "success")
                elif result == 'disconnected':
                    self.show_status("Wireless disconnected", "warning")

            # Status Messages
            if time.time() - self.status_time < self.status_duration:
                color_map = {
                    "success": self.colors["success"],
                    "error": self.colors["danger"],
                    "warning": self.colors["warning"],
                    "info": self.colors["text"],
                }
                status_color = color_map.get(self.status_type, self.colors["text"])
                status_txt = self.font_sm.render(self.status_msg, True, status_color)
                self.screen.blit(status_txt, (STATUS_TEXT_X, STATUS_TEXT_Y))

            # Presets
            pygame.draw.line(self.screen, self.colors["border"], (PRESET_DIVIDER_LEFT, PRESET_DIVIDER_Y),
                             (PRESET_DIVIDER_RIGHT, PRESET_DIVIDER_Y))

            # Save Preset button
            self.screen.blit(
                self.font_lg.render("Save New Preset", True, self.colors["text"]),
                (PRESET_HEADER_X, PRESET_HEADER_Y),
            )
            input_rect = pygame.Rect(PRESET_INPUT_X, PRESET_Y, PRESET_INPUT_WIDTH, PRESET_HEIGHT)
            name_color = (
                self.colors["accent"] if self.active_input else self.colors["border"]
            )
            pygame.draw.rect(
                self.screen, self.colors["panel"], input_rect, border_radius=5
            )
            pygame.draw.rect(self.screen, name_color, input_rect, 1, border_radius=5)

            name_txt = self.font_md.render(self.preset_name, True, self.colors["text"])
            name_rect = name_txt.get_rect(
                midleft=(input_rect.left + PRESET_TEXT_PADDING_X, input_rect.centery)
            )
            self.screen.blit(name_txt, name_rect)

            # Save button
            save_btn = pygame.Rect(PRESET_SAVE_BUTTON_X, PRESET_Y, PRESET_SAVE_BUTTON_WIDTH, PRESET_HEIGHT)
            pygame.draw.rect(self.screen, self.colors["accent"], save_btn, border_radius=PRESET_BORDER_RADIUS)

            sv_txt = self.font_md.render("SAVE", True, WHITE_TEXT)
            sv_rect = sv_txt.get_rect(center=save_btn.center)
            self.screen.blit(sv_txt, sv_rect)

            # Preset List
            self.screen.blit(
                self.font_lg.render("Saved Presets", True, self.colors["text"]),
                (PRESET_LIST_HEADER_X, PRESET_LIST_HEADER_Y),
            )
            presets = self.get_presets()
            y_offset = PRESET_LIST_Y_OFFSET

            # List out all the presets from the json
            for name, data in presets.items():
                row_rect = pygame.Rect(PRESET_ROW_X, y_offset, PRESET_ROW_WIDTH, PRESET_ROW_HEIGHT)
                pygame.draw.rect(
                    self.screen, self.colors["panel"], row_rect, border_radius=PRESET_BORDER_RADIUS
                )

                name_txt = self.font_md.render(name, True, self.colors["text"])
                name_y = y_offset + (PRESET_ROW_HEIGHT  - name_txt.get_height()) // 2
                self.screen.blit(name_txt, (PRESET_ROW_X + PRESET_NAME_X_OFFSET, name_y))

                # Load button
                l_btn = pygame.Rect(PRESET_LOAD_BUTTON_X, y_offset + PRESET_BUTTON_Y_OFFSET, PRESET_BUTTON_WIDTH,
                                    PRESET_BUTTON_HEIGHT)
                pygame.draw.rect(self.screen, self.colors["success"], l_btn, border_radius=BUTTON_BORDER_RADIUS)

                l_txt = self.font_sm.render("LOAD", True, BLACK_TEXT)
                self.screen.blit(l_txt, l_txt.get_rect(center=l_btn.center))

                # Delete Button
                d_btn = pygame.Rect(PRESET_DELETE_BUTTON_X, y_offset + PRESET_BUTTON_Y_OFFSET, PRESET_BUTTON_WIDTH,
                                    PRESET_BUTTON_HEIGHT)
                pygame.draw.rect(self.screen, self.colors["danger"], d_btn, border_radius=BUTTON_BORDER_RADIUS)

                d_txt = self.font_sm.render("DEL", True, WHITE_TEXT)
                self.screen.blit(d_txt, d_txt.get_rect(center=d_btn.center))

                # Load and delete interaction logic
                if m_click and not self.m_locked:
                    if l_btn.collidepoint(mx, my):
                        logger.info(f"Loading preset: {name}")

                        # Scale positions if preset was created at a different scale
                        preset_scale = data.get("global_scale", self.l.launch_scale)
                        current_scale = (self.l.launch_scale)

                        if abs(preset_scale - current_scale) > SCALE_CHANGE_MIN_DETECTION:
                            scale_factor = current_scale / preset_scale
                            self.l.tx = int(data["tx"] * scale_factor)
                            self.l.ty = int(data["ty"] * scale_factor)
                            self.l.bx = int(data["bx"] * scale_factor)
                            self.l.by = int(data["by"] * scale_factor)
                            logger.info(
                                f"Scaled preset from {preset_scale} to {current_scale} (factor: {scale_factor:.2f})"
                            )
                        else:
                            self.l.tx, self.l.ty = data["tx"], data["ty"]
                            self.l.bx, self.l.by = data["bx"], data["by"]

                        # Force immediate sync after loading preset
                        self.force_window_sync()
                        self.show_status(f"Loaded preset: {name}", "success")
                        self.m_locked = True
                    if d_btn.collidepoint(mx, my):
                        logger.info(f"Deleting preset: {name}")
                        self.l.store.delete_preset(name)
                        self.invalidate_preset_cache()  # Refresh cache after deletion
                        self.show_status(f"Deleted preset: {name}", "warning")
                        self.m_locked = True

                y_offset += PRESET_ROW_SPACING

            # Handle Save button click and input field
            if m_click and not self.m_locked:
                if input_rect.collidepoint(mx, my):
                    if not self.active_input:
                        logger.debug("Activated preset name input field")
                    self.active_input = True
                    self.active_slider_input = None
                if save_btn.collidepoint(mx, my):
                    try:
                        logger.info(f"Saving preset: {self.preset_name}")
                        self.l.store.save_preset(
                            self.preset_name,
                            {
                                "tx": self.l.tx,
                                "ty": self.l.ty,
                                "bx": self.l.bx,
                                "by": self.l.by,
                                "global_scale": self.l.launch_scale,
                            },
                        )
                        self.invalidate_preset_cache()
                        self.show_status(f"Saved preset: {self.preset_name}", "success")
                        self.m_locked = True
                    except ValueError as PresetSaveFail:
                        logger.warning(f"Failed to save preset: {PresetSaveFail}")
                        self.show_status(str(PresetSaveFail), "error", duration=ERROR_STATUS_DURATION)
                        self.m_locked = True
                    except Exception as PresetSaveError:
                        logger.error(
                            f"Unexpected error saving preset: {PresetSaveError}", exc_info=True
                        )
                        self.show_status("Failed to save preset", "error")
                        self.m_locked = True

            # FPS dropdown overlay. Drawn LAST so it visually stacks
            # on top of any other widget that happens to sit below
            # the FPS button. Also intercepts mouse so a stray click
            # outside any item just closes the menu.
            if self._fps_menu_open:
                try:
                    from src.launcher import ALLOWED_FPS_VALUES
                except Exception:
                    ALLOWED_FPS_VALUES = (30, 60, 90, 120)

                menu_x = FPS_BUTTON_X
                menu_y = FPS_BUTTON_Y + FPS_BUTTON_HEIGHT + 2
                item_h = FPS_MENU_ITEM_HEIGHT
                pad = FPS_MENU_PADDING
                menu_w = FPS_BUTTON_WIDTH
                menu_h = pad * 2 + item_h * len(ALLOWED_FPS_VALUES)
                menu_rect = pygame.Rect(menu_x, menu_y, menu_w, menu_h)

                # Drop shadow + filled menu
                shadow = pygame.Rect(menu_x + 2, menu_y + 4, menu_w, menu_h)
                pygame.draw.rect(self.screen, (0, 0, 0), shadow,
                                 border_radius=PRESET_BORDER_RADIUS)
                pygame.draw.rect(self.screen, self.colors["panel"], menu_rect,
                                 border_radius=PRESET_BORDER_RADIUS)
                pygame.draw.rect(self.screen, self.colors["border"], menu_rect, 1,
                                 border_radius=PRESET_BORDER_RADIUS)

                clicked_in_item = False
                for i, fps_val in enumerate(ALLOWED_FPS_VALUES):
                    item_rect = pygame.Rect(
                        menu_x + pad,
                        menu_y + pad + i * item_h,
                        menu_w - pad * 2,
                        item_h,
                    )
                    item_hover = item_rect.collidepoint(mx, my)
                    is_current = (fps_val == current_fps)
                    if is_current:
                        face = self.colors["accent"]
                        txt_color = WHITE_TEXT
                    elif item_hover:
                        face = self.colors["border"]
                        txt_color = self.colors["text"]
                    else:
                        face = self.colors["panel"]
                        txt_color = self.colors["text"]
                    pygame.draw.rect(self.screen, face, item_rect, border_radius=3)
                    label = f"{fps_val} FPS"
                    if is_current:
                        label += "  *"
                    item_text = self.font_md.render(label, True, txt_color)
                    self.screen.blit(item_text, item_text.get_rect(center=item_rect.center))

                    if item_hover and m_click and not self.m_locked and not self.dragging:
                        self.pressed_button = f"fps_item_{fps_val}"
                    if not m_click and self.pressed_button == f"fps_item_{fps_val}":
                        if item_hover:
                            if hasattr(self.l, "set_max_fps"):
                                self.l.set_max_fps(fps_val)
                            self.show_status(
                                f"FPS set to {fps_val} (click RESTART to apply)", "info",
                            )
                            self._fps_menu_open = False
                            clicked_in_item = True
                        self.pressed_button = None

                # Click somewhere off-menu (and not on the FPS button itself)
                # closes the menu without changing anything.
                if (not clicked_in_item
                        and m_click and not self.m_locked
                        and not menu_rect.collidepoint(mx, my)
                        and not fps_btn.collidepoint(mx, my)
                        and self.pressed_button is None):
                    self._fps_menu_open = False

            # Release mouse lock
            if not m_click:
                self.m_locked = False

            pygame.display.flip()

        except Exception as UIRenderError:
            logger.error(f"Error during UI render: {UIRenderError}", exc_info=True)

    def force_window_sync(self):
        """
        Force an immediate window sync
        This is called after loading a preset to prevent windows from disappearing
        """
        try:
            if not self.l.docked:
                logger.debug("Skipping force sync - not docked")
                return

            if not (self.l.dock.hwnd_top and self.l.dock.hwnd_bottom):
                logger.warning("Cannot force sync - window handles not available")
                return

            # Bypass throttling
            self.l.dock._last_sync = 0

            user32 = windll.user32
            logger.debug("Force syncing windows and ensuring visibility")

            # Show both windows
            user32.ShowWindow(self.l.dock.hwnd_top, SW_SHOW)
            user32.ShowWindow(self.l.dock.hwnd_bottom, SW_SHOW)

            # Apply new positions
            self.l.dock.sync(
                self.l.tx, self.l.ty, self.l.bx, self.l.by,
                self.l.scrcpy.f_w1, self.l.scrcpy.f_h1,
                self.l.scrcpy.f_w2, self.l.scrcpy.f_h2,
                is_docked=True,
            )

            # Force window style refresh
            user32.SetWindowPos(
                self.l.dock.hwnd_top, 0, 0, 0, 0, 0,
                SWP_NOZORDER | SWP_NOACTIVATE | SWP_FRAMECHANGED | SWP_NOMOVE | SWP_NOSIZE,
            )
            user32.SetWindowPos(
                self.l.dock.hwnd_bottom, 0, 0, 0, 0, 0,
                SWP_NOZORDER | SWP_NOACTIVATE | SWP_FRAMECHANGED | SWP_NOMOVE | SWP_NOSIZE,
            )

            logger.info("Force window sync completed successfully")

        except Exception as WindowSyncError:
            logger.error(f"Error during force window sync: {WindowSyncError}", exc_info=True)

    # Keyboard input for sliders and presets
    def handle_event(self, event):
        """
        Handle keyboard and other pygame events

        Args:
            event: pygame event object
        """
        try:
            if event.type == pygame.KEYDOWN:
                # Slider Keyboard Input
                if self.active_slider_input:
                    if event.key == pygame.K_BACKSPACE:
                        self.input_buffer = self.input_buffer[:-1]
                    elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                        try:
                            # Parse value based on slider data type
                            if self.active_slider_input == "global_scale":
                                new_val = float(self.input_buffer)
                                if abs(new_val - self._original_scale) > SCALE_CHANGE_MIN_DETECTION:
                                    self._scale_changed = True
                            else:
                                new_val = int(self.input_buffer)

                            setattr(self.l, self.active_slider_input, new_val)
                            logger.info(
                                f"Slider {self.active_slider_input} set to {new_val} via input box"
                            )

                            # Save + sync
                            if self.active_slider_input == "global_scale":
                                self.l.save_scale()
                            else:
                                self.l.save_layout()
                                self.force_window_sync()
                        except ValueError:
                            logger.warning(f"Invalid slider input: {self.input_buffer}")
                            self.show_status("Invalid number", "error",
                                             duration=SLIDER_ERROR_STATUS_DURATION)
                        except Exception as SliderValueError:
                            logger.error(f"Error setting slider value: {SliderValueError}")
                        finally:
                            self.active_slider_input = None

                    # Allow digits, negative signs and decimal points
                    elif (event.unicode.isdigit()
                        or (event.unicode == "-" and len(self.input_buffer) == 0)
                        or (event.unicode == "." and "." not in self.input_buffer)):
                        self.input_buffer += event.unicode

                # Preset Name Input
                elif self.active_input:
                    if event.key == pygame.K_BACKSPACE:
                        self.preset_name = self.preset_name[:-1]
                    elif event.key == pygame.K_RETURN:
                        logger.debug("Preset name input deactivated via Enter")
                        self.active_input = False
                    else:
                        self.preset_name += event.unicode

        except Exception as EventHandlingError:
            logger.error(f"Error handling event: {EventHandlingError}", exc_info=True)
