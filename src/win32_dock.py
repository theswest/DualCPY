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

import ctypes
import time
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
        logger.debug("Win32Dock initialized with null window handles")

    def sync(self, tx, ty, bx, by, w1, h1, w2, h2, is_docked=True):
        """
        Moves and resizes both embedded windows

        Parameters:
            tx, ty: top window position relative to container
            bx, by: bottom window position relative to container
            w1, h1: top window width/height
            w2, h2: bottom window width/height
            is_docked: whether windows are docked inside container
        """

        # Throttle rapid updates
        now = time.time()
        if now - self._last_sync < self._min_sync_interval:
            return
        self._last_sync = now

        if not (self.hwnd_top and self.hwnd_bottom):
            # Don't spam logs - only log first time
            if not hasattr(self, "_sync_warning_logged"):
                logger.debug("Sync skipped: window handles not available yet")
                self._sync_warning_logged = True
            return

        try:
            # Flags for SetWindowPos: don't change z-order, don't activate, don't copy bits
            flags = SWP_NOZORDER | SWP_NOACTIVATE | SWP_NOCOPYBITS

            if is_docked:
                # Child windows are drawn relative to the container
                logger.debug(
                    f"Syncing docked windows - Top: ({tx}, {ty}, {w1}x{h1}), Bottom: ({bx}, {by}, {w2}x{h2})"
                )

                result_top = user32.SetWindowPos(
                    self.hwnd_top, 0, int(tx), int(ty), int(w1), int(h1), flags
                )
                if not result_top:
                    logger.warning(
                        f"SetWindowPos failed for top window (hwnd={self.hwnd_top})"
                    )

                result_bottom = user32.SetWindowPos(
                    self.hwnd_bottom, 0, int(bx), int(by), int(w2), int(h2), flags
                )
                if not result_bottom:
                    logger.warning(
                        f"SetWindowPos failed for bottom window (hwnd={self.hwnd_bottom})"
                    )

            else:
                # For undocked mode, offset is decided by container's screen position
                if self.hwnd_container:
                    rect = wintypes.RECT()
                    if not user32.GetWindowRect(
                        self.hwnd_container, ctypes.byref(rect)
                    ):
                        logger.warning(
                            f"GetWindowRect failed for container (hwnd={self.hwnd_container})"
                        )
                        return

                    screen_tx = rect.left + int(tx)
                    screen_ty = rect.top + int(ty)
                    screen_bx = rect.left + int(bx)
                    screen_by = rect.top + int(by)

                    logger.debug(
                        f"Syncing undocked windows - Top: ({screen_tx}, {screen_ty}), "
                        f"Bottom: ({screen_bx}, {screen_by})"
                    )

                    user32.SetWindowPos(
                        self.hwnd_top, 0, screen_tx, screen_ty, int(w1), int(h1), flags
                    )
                    user32.SetWindowPos(
                        self.hwnd_bottom,
                        0,
                        screen_bx,
                        screen_by,
                        int(w2),
                        int(h2),
                        flags,
                    )
                else:
                    logger.warning("Cannot sync undocked windows: no container handle")

        except Exception as WindowSyncError:
            logger.error(f"Error during window sync: {WindowSyncError}", exc_info=True)

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

    Args:
        hwnd: Window handle to restore to normal style
    """
    if not hwnd:
        logger.warning("apply_undocked_style called with null hwnd")
        return

    try:
        logger.info(f"Applying undocked style to window {hwnd}")

        # Get current style
        style = user32.GetWindowLongW(hwnd, GWL_STYLE)
        if not style:
            logger.error(f"GetWindowLongW failed for hwnd {hwnd}")
            return

        logger.debug(f"Current window style: 0x{style:08x}")

        # Remove child flag and all decorations
        style &= ~(WS_CHILD | WS_CAPTION | WS_THICKFRAME | WS_MINIMIZEBOX | WS_MAXIMIZEBOX | WS_SYSMENU | WS_BORDER)

        # Keep visible as a top-level window with clipping
        style |= WS_VISIBLE | WS_CLIPCHILDREN | WS_CLIPSIBLINGS

        logger.debug(f"New window style: 0x{style:08x}")

        # Apply new style
        result = user32.SetWindowLongW(hwnd, GWL_STYLE, style)
        if not result:
            logger.warning(f"SetWindowLongW may have failed for hwnd {hwnd}")
        else:
            logger.debug("Window style applied successfully")

        # Detach from container
        logger.debug(f"Detaching window {hwnd} from parent")
        result = user32.SetParent(hwnd, None)
        if not result:
            logger.warning(f"SetParent may have failed for hwnd {hwnd}")

        # Force windows to redraw borders/title bar
        logger.debug(f"Forcing frame change for hwnd {hwnd}")
        result = user32.SetWindowPos(
            hwnd, 0, 0, 0, 0, 0,
            SWP_NOZORDER | SWP_NOACTIVATE | SWP_FRAMECHANGED | SWP_NOMOVE | SWP_NOSIZE)
        if not result:
            logger.warning(f"SetWindowPos frame change may have failed for hwnd {hwnd}")
        else:
            logger.info(f"Undocked style applied successfully to hwnd {hwnd}")

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

        # WINDOWS 10 CHECK - Be extra cautious
        import sys
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
