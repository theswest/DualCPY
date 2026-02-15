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

# main.py

__version__ = "0.3.0"
__app_name__ = "ThorCPY"
__author__ = "the_swest"
__description__ = "AYN Thor screen mirroring and docking tool"

import ctypes
import os
import sys
import logging
import time
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

    log_file = os.path.join(log_dir, f"thorcpy_{time.strftime('%Y%m%d')}.log")

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
                import tkinter as tk
                from tkinter import messagebox

                root = tk.Tk()
                root.withdraw()
                messagebox.showwarning(
                    "Windows 10 Detected - Known Issues",
                    f"WARNING: You are running Windows 10 (Build {build})\n\n"
                    f"ThorCPY has been reported to have stability issues on Windows 10.\n"
                    f"Restarting ThorCPY can sometimes fix small issues.\n"
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
                print("ThorCPY has known stability issues on Windows 10.")
                print("")
                print("Restarting ThorCPY can sometimes fix small issues")
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

    # Path logic for pyinstaller exe files
    if hasattr(sys, "_MEIPASS"):
        base = os.path.dirname(sys.executable)
    else:
        base = os.path.dirname(os.path.abspath(__file__))

    # List the missing files and return an error
    missing = [f for f in REQUIRED_FOLDERS if not os.path.isdir(os.path.join(base, f))]

    if missing:
        msg = (
            f"ThorCPY failed to start.\n\n"
            f"Missing required folders:\n"
            f"{', '.join(missing)}\n\n"
            f"ThorCPY must be installed with:\n"
            f"bin/, config/, logs/\n\n"
            f"Please reinstall or extract the full build."
        )

        # Log error and show fatal error, also print to console
        logger.critical(msg)
        print(msg)
        show_fatal_error("ThorCPY Startup Error", msg)
        sys.exit(1)


def main():
    """
    ThorCPY's main entry point
    Sets up logging, checks windows version, runs folder checks, sets DPI awareness,
    creates the launcher instance and starts the UI.
    """
    print(f"Starting {__app_name__} v{__version__}")
    print("Checking system requirements...")

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

    # Create the main launcher object and start it
    logger.info("Initializing launcher")
    app = Launcher()
    app.launch()


if __name__ == "__main__":
    main()