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

# main.py

__version__ = "0.4.0"
__app_name__ = "DualCPY"
__author__ = "the_swest"
__description__ = "Android Dual screen mirroring and docking tool"

import os
import sys
import time
import ctypes
import logging
import tkinter as tk
from ctypes import wintypes
from tkinter import messagebox
from src.launcher import Launcher

REQUIRED_FOLDERS = ["bin", "config", "logs"] # List of required folders that must exist in order to function
WIN11_LOWEST_BUILD = 22000 # Lowest build number of Windows 11
LOG_MULT = 60 # Amount of = to put in the logs as seperators
MB_ICONERROR = 0x10 # Windows error messagebox flag

def setup_logging():
    """
    Configure logging
    """
    log_dir = os.path.join(
        os.path.dirname(sys.executable if hasattr(sys, "_MEIPASS") else __file__),
        "logs",
    )
    os.makedirs(log_dir, exist_ok=True)

    log_file = os.path.join(log_dir, f"dualcpy_{time.strftime('%Y%m%d')}.log")

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[logging.FileHandler(log_file, encoding="utf-8"), logging.StreamHandler()],
    )


def check_windows_version():
    """
    Check if running on Windows 10 and show a warning.
    Windows 11 has build number 22000 or higher.
    Shows a warning message if running on Windows 10 but allows launch.
    """
    logger = logging.getLogger(__name__)

    try:
        version = sys.getwindowsversion()
        build = version.build

        # Windows 11 is build 22000+, Windows 10 is builds 10240-19045
        if build < WIN11_LOWEST_BUILD:
            logger.warning(f"Windows 10 detected (Build {build}) - showing warning message")
            # Show warning
            try:
                root = tk.Tk()
                root.withdraw()
                messagebox.showwarning(
                    "Windows 10 Detected - Known Issues",
                    f"WARNING: You are running Windows 10 (Build {build})\n\n"
                    f"DualCPY has been reported to have stability issues on Windows 10.\n"
                    f"Restarting DualCPY can sometimes fix small issues.\n"
                    f"For the best experience, please use Windows 11.\n\n"
                    f"Continue anyway?",
                )
                root.destroy()
            except Exception as tkErr:
                # Fallback to console message if the messagebox doesn't work
                logger.error(f"GUI warning message failed: {tkErr}")
                print("=" * LOG_MULT)
                print("WARNING: Windows 10 Detected - Unstable Build with Known Issues")
                print("=" * LOG_MULT)
                print(f"You are running Windows 10 (Build {build})")
                print("")
                print("DualCPY has known stability issues on Windows 10.")
                print("")
                print("Restarting DualCPY can sometimes fix small issues")
                print("")
                print("For the best experience, please use Windows 11.")
                print("=" * LOG_MULT)
                print(f"(GUI warning failed: {tkErr})")
                input("\nPress Enter to continue anyway...")
        else:
            logger.info(f"Windows 11 detected (Build {build})")
            print(f"Windows 11 detected (Build {build})")

    except Exception as WinDetectionError:
        logger.error(f"Could not verify Windows version: {WinDetectionError}")
        print(f"Warning: Could not verify Windows version: {WinDetectionError}")


def show_fatal_error(title: str, message: str):
    """Show a fatal error dialog."""
    ctypes.windll.user32.MessageBoxW(
        None,
        message,
        title,
        MB_ICONERROR
    )


def check_runtime_structure():
    """
    Checks that all required folders exist in the application directory.
    Is used when running from python files and with a pyinstaller exe.
    """
    logger = logging.getLogger(__name__)

    is_frozen = hasattr(sys, "_MEIPASS")
    if is_frozen:
        base = os.path.dirname(sys.executable)
    else:
        base = os.path.dirname(os.path.abspath(__file__))

    # When frozen, transparently create the writable folders next to
    # the executable and skip the bin/ check (it lives in _MEIPASS).
    if is_frozen:
        for folder in ("config", "logs"):
            try:
                os.makedirs(os.path.join(base, folder), exist_ok=True)
            except Exception as MkdirError:
                logger.warning(
                    f"Could not create runtime folder '{folder}': {MkdirError}"
                )
        logger.debug(
            f"Frozen runtime: bin/ resolves from _MEIPASS={sys._MEIPASS}; "
            f"config/ and logs/ ensured next to {sys.executable}"
        )
        return

    # From-source path: hard fail if anything is missing.
    missing = [f for f in REQUIRED_FOLDERS if not os.path.isdir(os.path.join(base, f))]

    if missing:
        msg = (
            f"{__app_name__} failed to start.\n\n"
            f"Missing required folders:\n"
            f"{', '.join(missing)}\n\n"
            f"{__app_name__} must be installed with:\n"
            f"bin/, config/, logs/\n\n"
            f"Please reinstall or extract the full build."
        )

        # Log error and show fatal error, also print to console
        logger.critical(msg)
        print(msg)
        show_fatal_error(f"{__app_name__} Startup Error", msg)
        sys.exit(1)


def main():
    """
    DualCPY's main entry point
    Sets up logging, checks windows version, runs folder checks, sets DPI awareness,
    creates the launcher instance and starts the UI.
    """
    print(f"Starting {__app_name__} v{__version__}")
    print("Checking system requirements...")

    # When packaged as a PyInstaller exe, the working directory may
    # be wherever the user double-clicked from (their Desktop, etc).
    # Anchor all relative paths (config/, logs/) to the exe's own
    # directory so the app behaves predictably regardless of how it
    # was launched.
    if getattr(sys, "frozen", False):
        try:
            os.chdir(os.path.dirname(sys.executable))
        except Exception:
            pass

    # Sets up logging before anything else
    setup_logging()
    logger = logging.getLogger(__name__)
    logger.info(f"Starting {__app_name__} v{__version__}")
    logger.info(f"System: Windows Build {sys.getwindowsversion().build}")

    # Check Windows version and show warning if Windows 10
    check_windows_version()

    # Run the folder check
    check_runtime_structure()

    # Set DPI awareness
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
        logger.info("DPI Awareness set successfully")
    except Exception as DpiAwareErr:
        logger.error(f"Could not set DPI Awareness: {DpiAwareErr}")

    # Bump our own process priority to ABOVE_NORMAL_PRIORITY_CLASS.
    # The two scrcpy children run at HIGH (set in scrcpy_manager) so
    # we stay below them and don't risk starving the encoder/decoder,
    # but we sit ABOVE the swarm of NORMAL-priority background apps
    # (Discord, browsers, IDEs, game launchers) that would otherwise
    # share CPU with our message pump and chassis renderer. That
    # sharing is the source of the residual sub-frame audio hiccups.
    try:
        ABOVE_NORMAL_PRIORITY_CLASS = 0x00008000
        kernel32 = ctypes.windll.kernel32
        # 64-bit pseudo-handle from GetCurrentProcess() must NOT be
        # truncated to 32-bit int by ctypes' default signature.
        kernel32.GetCurrentProcess.restype = wintypes.HANDLE
        kernel32.SetPriorityClass.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        kernel32.SetPriorityClass.restype = wintypes.BOOL
        current = kernel32.GetCurrentProcess()
        if kernel32.SetPriorityClass(current, ABOVE_NORMAL_PRIORITY_CLASS):
            logger.info("Host process priority set")
        else:
            err = kernel32.GetLastError()
            logger.warning(f"SetPriorityClass(ABOVE_NORMAL) failed (GetLastError={err})")
    except Exception as PriorityErr:
        logger.warning(f"Could not raise host process priority: {PriorityErr}")

    # Create the main launcher object and start it
    logger.info("Initializing launcher")
    app = Launcher()
    app.launch()


if __name__ == "__main__":
    main()