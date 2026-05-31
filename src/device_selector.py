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

# src/device_selector.py

import logging
from dataclasses import replace

from src.device_profile import BUILTIN_PROFILES
from src.device_profile_dialog import DeviceProfileDialog
from src.device_detection import get_device_info, get_display_list

logger = logging.getLogger(__name__)


def show_device_selector(
        profiles=None,
        adb_bin=None,
        serial=None,
        custom_store=None,
        parent_window=None,
):
    """
    Return the best DeviceProfile for the connected device without any dialogs
    """
    if not serial or not adb_bin:
        logger.warning("No device serial or adb binary provided to selector.")
        return None

    # Get device details
    device_info = get_device_info(adb_bin, serial)
    if not device_info:
        logger.warning(f"Could not retrieve device properties for {serial}")
        return None

    device_model = device_info.get("model", "Unknown Device")
    logger.info(f"Device detected: '{device_model}' with serial {serial}")

    # Query active displays
    display_list = get_display_list(adb_bin, serial)
    if not display_list or len(display_list) < 2:
        logger.error(f"Device {serial} does not have at least 2 active displays.")
        return None

    logger.info(f"Displays found: {display_list}")

    matched_profile = None

    # Check Custom Profiles Store for a match
    if custom_store:
        custom_matches = custom_store.find_all_by_device_name(device_model)
        if custom_matches:
            # Pick the last saved custom profile
            matched_profile = custom_matches[-1]
            logger.info(f"Auto-selected custom profile: '{matched_profile.nickname or matched_profile.name}'")

    # Check Built-In Profiles if no Custom Profile exists
    if not matched_profile:
        # Match by profile.name
        for p in BUILTIN_PROFILES.values():
            if p.name.lower() == device_model.lower():
                matched_profile = p
                logger.info(f"Auto-selected built-in profile for '{device_model}'")
                break

    # Prompt user to build a new profile
    if not matched_profile:
        logger.info(f"No profiles match '{device_model}'. Prompting user to create a new profile...")

        def on_save(new_prof):
            if custom_store:
                custom_store.save(new_prof)

        dialog = DeviceProfileDialog(
            parent=parent_window,
            device_name=device_model,
            display_list=display_list,
            on_save=on_save
        )
        matched_profile = dialog.run()

        if not matched_profile:
            logger.info("User cancelled creating a new profile configuration.")
            return None

    flipped = matched_profile.flipped_screens

    if not flipped:
        top_display = display_list[0]
        bottom_display = display_list[1]
    else:
        bottom_display = display_list[0]
        top_display = display_list[1]

    logger.info(
        f"Applying specs: top={top_display}, bottom={bottom_display}, flipped={flipped}"
    )

    return replace(
        matched_profile,
        top_display_id=str(top_display["id"]),
        bottom_display_id=str(bottom_display["id"]),
        top_screen_width=int(top_display["width"]),
        top_screen_height=int(top_display["height"]),
        bottom_screen_width=int(bottom_display["width"]),
        bottom_screen_height=int(bottom_display["height"]),
    )