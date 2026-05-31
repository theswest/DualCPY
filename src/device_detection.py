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

# src/device_detection.py

import re
import os
import sys
import shutil
import logging
import subprocess

logger = logging.getLogger(__name__)

ADB_INFO_TIMEOUT = 5
ADB_DISPLAY_TIMEOUT = 10

ADB_SERVER_TIMEOUT = 30

CREATE_NO_WINDOW = 0x08000000

# Map key names to Android prop keys
DEVICE_PROPS = {
    "model":        "ro.product.model",
    "manufacturer": "ro.product.manufacturer",
    "android":      "ro.build.version.release",
    "api_level":    "ro.build.version.sdk",
    "cpu_abi":      "ro.product.cpu.abi",
    "device":       "ro.product.device",
}


def resolve_adb(name):
    """
    Locate a bundled binary (scrcpy / adb)

    Search order:
      1. PyInstaller bundle (sys._MEIPASS/bin/) when running as a frozen exe
      2. ./bin next to the running script or exe
      3. The current working directory's bin/
      4. System PATH
    """
    logger.debug(f"Resolving binary: {name}")

    candidates = []

    # PyInstaller _MEIPASS unpacked bundle
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidates.append(os.path.join(meipass, "bin", f"{name}.exe"))

    # ./bin next to the script/exe
    if getattr(sys, "frozen", False):
        exe_dir = os.path.dirname(sys.executable)
    else:
        exe_dir = os.path.dirname(os.path.abspath(__file__))
        # src/ -> project root
        exe_dir = os.path.dirname(exe_dir)
    candidates.append(os.path.join(exe_dir, "bin", f"{name}.exe"))

    # cwd
    candidates.append(os.path.join(os.getcwd(), "bin", f"{name}.exe"))

    for path in candidates:
        if os.path.exists(path):
            logger.info(f"Found {name} at: {path}")
            return path

    # System PATH
    found = shutil.which(name)
    if found:
        logger.info(f"Found {name} in system PATH: {found}")
        return found

    logger.warning(f"Binary '{name}' not found (checked: {candidates})")
    return None

def detect_device(adb_bin):
    logger.info("Starting device detection with ADB")

    if not adb_bin:
        logger.error("Cannot detect device: ADB binary not found")
        return None

    # Start ADB server
    try:
        subprocess.run(
            [adb_bin, "start-server"],
            capture_output=True,
            text=True,
            timeout=ADB_SERVER_TIMEOUT,
            creationflags=CREATE_NO_WINDOW,
        )
    except Exception as e:
        logger.error(f"Failed to start ADB server: {e}")
        return None

    # Try to get devices
    try:
        result = subprocess.run(
            [adb_bin, "devices"],
            capture_output=True,
            text=True,
            timeout=ADB_SERVER_TIMEOUT,
            creationflags=CREATE_NO_WINDOW,
        )

        if result.returncode != 0:
            logger.error(f"'adb devices' failed with code {result.returncode}")
            return None

        lines = result.stdout.strip().splitlines()

        for line in lines[1:]:
            parts = line.split()

            if len(parts) < 2:
                continue

            serial = parts[0]
            status = parts[1]

            if status == "device":
                logger.info(f"Device detected: {serial}")
                return serial

            if status == "unauthorized":
                logger.warning(
                    f"Unauthorized device: {serial} "
                    f"(check device for authorization prompt)"
                )

        logger.warning("No authorized devices found")
        return None

    except subprocess.TimeoutExpired:
        logger.error("'adb devices' timed out")
        return None

    except Exception as e:
        logger.error(f"Device detection failed: {e}")
        return None

def get_device_info(adb_bin, serial):
    """
    Get device properties with adb shell and getprop
    """
    info = {}

    for key, prop in DEVICE_PROPS.items():
        try:
            result = subprocess.run(
                [adb_bin, "-s", serial, "shell", "getprop", prop],
                capture_output=True,
                text=True,
                timeout=ADB_INFO_TIMEOUT,
                creationflags=CREATE_NO_WINDOW,
            )
            if result.returncode == 0:
                info[key] = result.stdout.strip()
            else:
                logger.warning(f"getprop {prop} returned code {result.returncode}")
                info[key] = None
        except subprocess.TimeoutExpired:
            logger.warning(f"Timeout fetching {prop}")
            info[key] = None
        except Exception as e:
            logger.error(f"Error fetching {prop}: {e}")
            info[key] = None

    logger.debug(f"Device info: {info}")
    return info

def get_display_list(adb_bin, serial):
    """
    Gets display IDs and resolutions from the mViewports line in dumpsys display
    """
    try:
        result = subprocess.run(
            [adb_bin, "-s", serial, "shell",
             "dumpsys display | grep mViewports"],
            capture_output=True,
            text=True,
            timeout=ADB_DISPLAY_TIMEOUT,
            creationflags=CREATE_NO_WINDOW,
        )
    except subprocess.TimeoutExpired:
        logger.warning("Timeout fetching display list")
        return []
    except Exception as e:
        logger.error(f"Error fetching display list: {e}")
        return []

    displays = []

    # Each display appears as: displayId=N, ..., deviceWidth=W, deviceHeight=H
    matches = re.findall(r'displayId=(\d+).*?deviceWidth=(\d+),\s*deviceHeight=(\d+)', result.stdout)

    for display_id, width, height in matches:
        displays.append({
            "id": display_id,
            "width": int(width),
            "height": int(height),
        })

    logger.info(f"Displays found: {displays}")
    return displays