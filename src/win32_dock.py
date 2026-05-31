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

# src/win32_dock.py

import sys
import time
import ctypes
import logging
from ctypes import wintypes

# Setup logger for this module
logger = logging.getLogger(__name__)

# Win32 DLLs
user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

# Constants for GetWindowLong / SetWindowLong
GWL_STYLE = -16  # Standard window style
GWL_EXSTYLE = -20  # Extended window style

# Window style flags
WS_CHILD = 0x40000000  # Make window a child of another
WS_VISIBLE = 0x10000000  # Make window visible
WS_BORDER = 0x00800000  # Thin border
WS_CAPTION = 0x00C00000  # Title bar (includes WS_BORDER)
WS_THICKFRAME = 0x00040000  # Resizable frame
WS_MINIMIZEBOX = 0x00020000  # Minimize button
WS_MAXIMIZEBOX = 0x00010000  # Maximize button
WS_SYSMENU = 0x00080000  # System menu (close button)
WS_TABSTOP = 0x00010000
WS_EX_CONTROLPARENT = 0x00010000

# Window clipping flags
WS_CLIPCHILDREN = 0x02000000  # Prevent parent from drawing over children
WS_CLIPSIBLINGS = 0x04000000  # Prevent siblings from drawing over each other

# Window combination styles
WS_OVERLAPPEDWINDOW = 0x00CF0000  # Standard overlapped window (title bar, resize, min/max/close buttons)

# Set focus
WM_SETFOCUS = 0x0007

# SetWindowPos flags
SWP_NOZORDER = 0x0004  # Don't change Z order
SWP_NOACTIVATE = 0x0010  # Don't activate window
SWP_FRAMECHANGED = 0x0020  # Forces style refresh
SWP_NOMOVE = 0x0002  # Don't move
SWP_NOSIZE = 0x0001  # Don't resize
SWP_NOCOPYBITS = 0x0100  # Force full redraw

# Timing constants
MIN_SYNC_INTERVAL = 0.016  # Minimum time between sync operations (60 FPS)
THREAD_ATTACH_TIMEOUT = 0.5  # Timeout for thread attachment operations (seconds)
DETACH_RETRY_DELAY = 0.01  # Delay between detach retry attempts (seconds)
MAX_DETACH_ATTEMPTS = 3  # Maximum number of detach retry attempts


# Main Dock Manager Class
class Win32Dock:
    """
    Handles embedding two windows (top/bottom) inside a container window,
    and synchronizes their position and size when docked/undocked.
    """

    def __init__(self):
        """
        Initialize the window manager.
        """
        logger.info("Initializing Win32Dock")
        self.hwnd_container = None
        self.hwnd_top = None
        self.hwnd_bottom = None
        self._last_sync = 0
        self._min_sync_interval = MIN_SYNC_INTERVAL
        self._last_top_geom = None
        self._last_bottom_geom = None
        logger.debug("Win32Dock initialized with null window handles")

    def sync(self, tx, ty, bx, by, w1, h1, w2, h2, is_docked=True):
        """
        Moves and resizes both embedded windows with accurate border awareness.
        """

        # Throttle rapid updates
        now = time.time()
        if now - self._last_sync < self._min_sync_interval:
            return
        self._last_sync = now

        if not (self.hwnd_top and self.hwnd_bottom):
            if not hasattr(self, "_sync_warning_logged"):
                logger.debug("Sync skipped: window handles not available yet")
                self._sync_warning_logged = True
            return

        try:
            if is_docked:
                flags = SWP_NOZORDER | SWP_NOACTIVATE
                top_geom = (int(tx), int(ty), int(w1), int(h1))
                bottom_geom = (int(bx), int(by), int(w2), int(h2))

                if top_geom != self._last_top_geom:
                    logger.debug(f"Syncing docked top: {top_geom}")
                    if not user32.SetWindowPos(self.hwnd_top, 0, *top_geom, flags):
                        logger.warning(
                            f"SetWindowPos failed for top window (hwnd={self.hwnd_top})"
                        )
                    self._last_top_geom = top_geom

                if bottom_geom != self._last_bottom_geom:
                    logger.debug(f"Syncing docked bottom: {bottom_geom}")
                    if not user32.SetWindowPos(self.hwnd_bottom, 0, *bottom_geom, flags):
                        logger.warning(
                            f"SetWindowPos failed for bottom window (hwnd={self.hwnd_bottom})"
                        )
                    self._last_bottom_geom = bottom_geom

            else:
                # Account for Title Bars and Borders for undocked mode
                if self.hwnd_container:
                    rect = wintypes.RECT()
                    if not user32.GetWindowRect(
                        self.hwnd_container, ctypes.byref(rect)
                    ):
                        logger.warning(
                            f"GetWindowRect failed for container (hwnd={self.hwnd_container})"
                        )
                        return

                    flags = SWP_NOZORDER | SWP_NOACTIVATE | SWP_FRAMECHANGED

                    # Adjusting the top window
                    style_top = user32.GetWindowLongW(self.hwnd_top, GWL_STYLE)
                    ex_style_top = user32.GetWindowLongW(self.hwnd_top, GWL_EXSTYLE)
                    rect_top = wintypes.RECT(0, 0, int(w1), int(h1))
                    user32.AdjustWindowRectEx(ctypes.byref(rect_top), style_top, False, ex_style_top)

                    w1_adj = rect_top.right - rect_top.left
                    h1_adj = rect_top.bottom - rect_top.top
                    # Shift origin by the border padding so the client content lines up perfectly
                    x1_adj = rect.left + int(tx) + rect_top.left
                    y1_adj = rect.top + int(ty) + rect_top.top
                    top_geom = (x1_adj, y1_adj, w1_adj, h1_adj)

                    # Adjusting the bottom window
                    style_bot = user32.GetWindowLongW(self.hwnd_bottom, GWL_STYLE)
                    ex_style_bot = user32.GetWindowLongW(self.hwnd_bottom, GWL_EXSTYLE)
                    rect_bot = wintypes.RECT(0, 0, int(w2), int(h2))
                    user32.AdjustWindowRectEx(ctypes.byref(rect_bot), style_bot, False, ex_style_bot)

                    w2_adj = rect_bot.right - rect_bot.left
                    h2_adj = rect_bot.bottom - rect_bot.top
                    x2_adj = rect.left + int(bx) + rect_bot.left
                    y2_adj = rect.top + int(by) + rect_bot.top
                    bottom_geom = (x2_adj, y2_adj, w2_adj, h2_adj)

                    # Apply adjusted geometries
                    if top_geom != self._last_top_geom:
                        logger.debug(f"Syncing undocked top: {top_geom}")
                        user32.SetWindowPos(self.hwnd_top, 0, *top_geom, flags)
                        self._last_top_geom = top_geom

                    if bottom_geom != self._last_bottom_geom:
                        logger.debug(f"Syncing undocked bottom: {bottom_geom}")
                        user32.SetWindowPos(self.hwnd_bottom, 0, *bottom_geom, flags)
                        self._last_bottom_geom = bottom_geom
                else:
                    logger.warning("Cannot sync undocked windows: no container handle")

        except Exception as WindowSyncError:
            logger.error(f"Error during window sync: {WindowSyncError}", exc_info=True)

    def invalidate_geom_cache(self):
        """
        Force the next sync() to re-issue SetWindowPos for both windows.
        Call after dock/undock or any operation that changes the
        coordinate space the windows are positioned in.
        """
        self._last_top_geom = None
        self._last_bottom_geom = None

    def force_focus(self, hwnd):
        """Forces keyboard focus by linking thread input queues."""
        if not hwnd or not user32.IsWindow(hwnd):
            return

        target_thread = user32.GetWindowThreadProcessId(hwnd, None)
        current_thread = kernel32.GetCurrentThreadId()

        attached = False
        try:
            if target_thread != current_thread:
                attached = bool(user32.AttachThreadInput(current_thread, target_thread, True))

            user32.SetFocus(hwnd)
            user32.SetForegroundWindow(hwnd)  # Explicitly bring to front
            user32.SendMessageW(hwnd, 0x0007, 0, 0)  # WM_SETFOCUS

            # Give scrcpy/SDL a millisecond to register the change
            time.sleep(0.01)

            logger.debug(f"Keyboard focus linked to HWND: {hwnd}")
        except Exception as e:
            logger.error(f"Focus error: {e}")
        finally:
            if attached:
                user32.AttachThreadInput(current_thread, target_thread, False)

# Window Style Transformers
def apply_docked_style(hwnd):
    """
    Converts a normal top-level window into a child window.

    Removes title bar, borders, resize handles, system menu.
    Adds WS_CHILD + clip flags so Windows stops drawing over it.

    Args:
        hwnd: Window handle to convert to child style
    """
    if not hwnd:
        logger.warning("apply_docked_style called with null hwnd")
        return

    try:
        logger.info(f"Applying docked style to window {hwnd}")

        # Get current style
        style = user32.GetWindowLongW(hwnd, GWL_STYLE)
        if not style:
            logger.error(f"GetWindowLongW failed for hwnd {hwnd}")
            return

        logger.debug(f"Current window style: 0x{style:08x}")

        # Remove all decorations
        style &= ~(
            WS_BORDER
            | WS_CAPTION
            | WS_THICKFRAME
            | WS_MINIMIZEBOX
            | WS_MAXIMIZEBOX
            | WS_SYSMENU
        )

        # Add child mode + clipping
        style |= WS_CHILD | WS_VISIBLE | WS_CLIPCHILDREN | WS_CLIPSIBLINGS | WS_TABSTOP

        logger.debug(f"New window style: 0x{style:08x}")

        # Apply new style
        result = user32.SetWindowLongW(hwnd, GWL_STYLE, style)
        if not result:
            logger.warning(f"SetWindowLongW may have failed for hwnd {hwnd}")
        else:
            logger.debug("Window style applied successfully")

    except Exception as e:
        logger.error(f"Error applying docked style to hwnd {hwnd}: {e}", exc_info=True)

    # Force Windows to recalculate the non-client area to prevent ghosting
    try:
        logger.debug(f"Forcing frame change for hwnd {hwnd}")
        result = user32.SetWindowPos(
            hwnd, 0, 0, 0, 0, 0,
            SWP_NOZORDER | SWP_NOACTIVATE | SWP_FRAMECHANGED | SWP_NOMOVE | SWP_NOSIZE)
        if not result:
            logger.warning(f"SetWindowPos frame change may have failed for hwnd {hwnd}")
        else:
            logger.debug(f"Docked style applied successfully to hwnd {hwnd}")

        # Force complete redraw to fix transparency and remove white bar artifacts
        # InvalidateRect marks the entire window for redrawing
        user32.InvalidateRect(hwnd, None, True)
        # UpdateWindow forces immediate redraw
        user32.UpdateWindow(hwnd)
        logger.debug(f"Forced window redraw for proper transparency rendering on hwnd {hwnd}")

    except Exception as FrameForceError:
        logger.error(f"Error forcing frame change for hwnd {hwnd}: {FrameForceError}", exc_info=True)


def apply_undocked_style(hwnd):
    """
    Restore a child window back to a normal resizable desktop window.
    """
    if not hwnd:
        logger.warning("apply_undocked_style called with null hwnd")
        return

    try:
        logger.info(f"Applying undocked style to window {hwnd}")

        # Get current window dimensions (which equals the target content size)
        rect = wintypes.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(rect))
        orig_w = rect.right - rect.left
        orig_h = rect.bottom - rect.top

        style = user32.GetWindowLongW(hwnd, GWL_STYLE)
        ex_style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)

        # Modify styles and detatch from parent
        style &= ~WS_CHILD
        style |= WS_OVERLAPPEDWINDOW | WS_VISIBLE | WS_CLIPCHILDREN | WS_CLIPSIBLINGS

        user32.SetWindowLongW(hwnd, GWL_STYLE, style)

        user32.SetParent(hwnd, None)

        # Calculate the required outer window size to keep the original content size
        needed_rect = wintypes.RECT(0, 0, orig_w, orig_h)
        user32.AdjustWindowRectEx(ctypes.byref(needed_rect), style, False, ex_style)
        target_w = needed_rect.right - needed_rect.left
        target_h = needed_rect.bottom - needed_rect.top

        # We temporarily size it 1 pixel off, then immediately drop it to target size to make SDL realise the content size
        user32.SetWindowPos(
            hwnd, 0, rect.left, rect.top, target_w + 1, target_h + 1,
            SWP_NOZORDER | SWP_NOACTIVATE | SWP_FRAMECHANGED
        )

        # Snap it back to the correct size
        user32.SetWindowPos(
            hwnd, 0, rect.left, rect.top, target_w, target_h,
            SWP_NOZORDER | SWP_NOACTIVATE | SWP_FRAMECHANGED | SWP_NOCOPYBITS
        )

        # Redraw it
        user32.InvalidateRect(hwnd, None, True)
        user32.UpdateWindow(hwnd)

    except Exception as UndockedStylingError:
        logger.error(f"Error applying undocked style to hwnd {hwnd}: {UndockedStylingError}", exc_info=True)


# Focus / Input Manager
def set_foreground_with_attach(hwnd):
    """
    Safely set foreground window with thread attachment.
    """
    if not hwnd or not user32.IsWindow(hwnd):
        logger.warning(f"set_foreground_with_attach called with invalid hwnd: {hwnd}")
        return False

    try:
        logger.debug(f"Attempting to set foreground window: {hwnd}")

        tid_cur = kernel32.GetCurrentThreadId()
        tid_target = user32.GetWindowThreadProcessId(hwnd, None)

        logger.debug(f"Current thread: {tid_cur}, Target thread: {tid_target}")

        # Same thread - no attachment needed
        if tid_cur == tid_target:
            logger.debug("Same thread - skipping AttachThreadInput")
            try:
                result = user32.SetForegroundWindow(hwnd)
                if result:
                    logger.info(f"Window {hwnd} brought to foreground (same thread)")
                return bool(result)
            except Exception as ForegroundWindowError:
                logger.error(f"Error setting foreground window (same thread): {ForegroundWindowError}",
                             exc_info=True)
                return False

        # Validate target thread
        if not tid_target:
            logger.warning("Could not get the target window's thread ID")
            return False

        # Try without attachment first (safer on Windows 10)
        try:
            result = user32.SetForegroundWindow(hwnd)
            if result:
                logger.info(f"Window {hwnd} brought to foreground (no attachment needed)")
                return True
        except Exception as e:
            logger.debug(f"SetForegroundWindow without attachment failed: {e}")

        # Windows 10 Check
        is_win10 = sys.getwindowsversion().build < 22000

        if is_win10:
            logger.debug("Windows 10 detected - using conservative foreground approach")
            # On Windows 10, just try once without thread attachment
            # to avoid stability issues
            try:
                user32.BringWindowToTop(hwnd)
                user32.SetFocus(hwnd)
                logger.info(f"Window {hwnd} focus attempt (Win10 safe mode)")
                return True
            except Exception as e:
                logger.warning(f"Safe focus failed on Win10: {e}")
                return False

        # Windows 11+ - can try thread attachment
        attached = False
        attach_timeout = time.time() + THREAD_ATTACH_TIMEOUT

        try:
            attached = bool(user32.AttachThreadInput(tid_cur, tid_target, True))
            if not attached:
                logger.warning("Failed to attach thread input")
                return False

            logger.debug("Thread input queues attached successfully")

            # Quick focus with timeout check
            if time.time() < attach_timeout:
                try:
                    user32.SetForegroundWindow(hwnd)
                    user32.SetActiveWindow(hwnd)
                    user32.SetFocus(hwnd)
                    logger.info(f"Window {hwnd} brought to foreground (with attachment)")
                    return True
                except Exception as ForegroundWindowSetError:
                    logger.error(f"Error setting foreground window: {ForegroundWindowSetError}")
                    return False

        except Exception as ThreadAttachmentError:
            logger.warning(f"Error during thread attachment: {ThreadAttachmentError}")
            return False

        finally:
            # CRITICAL: Always detach with multiple attempts and timeout
            if attached:
                detach_success = False
                for attempt in range(MAX_DETACH_ATTEMPTS):
                    try:
                        # Add small delay before detach to prevent race condition
                        time.sleep(DETACH_RETRY_DELAY)
                        detach_result = user32.AttachThreadInput(tid_cur, tid_target, False)
                        if detach_result:
                            logger.debug(f"Thread input queues detached (attempt {attempt + 1})")
                            detach_success = True
                            break
                    except Exception as DetachError:
                        logger.error(f"Detach attempt {attempt + 1} failed: {DetachError}")

                if not detach_success:
                    logger.critical("FAILED TO DETACH THREAD INPUT - SYSTEM MAY BE UNSTABLE")

    except Exception as ForegroundAttachCriticalError:
        logger.error(f"Critical error in set_foreground_with_attach: {ForegroundAttachCriticalError}",
                     exc_info=True)
        return False
