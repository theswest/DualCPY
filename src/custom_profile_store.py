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

# src/custom_profile_store.py

import os
import uuid
import json
import logging
from dataclasses import asdict

from src.device_profile import DeviceProfile

logger = logging.getLogger(__name__)

JSON_INDENT = 4
DEFAULT_ENCODING = "utf-8"


class CustomProfileStore:
    """
    Saves user-created DeviceProfiles to custom_profiles.json
    """

    def __init__(self, path):
        self.path = path
        try:
            dir_path = os.path.dirname(self.path)
            if dir_path:
                os.makedirs(dir_path, exist_ok=True)
        except Exception as e:
            logger.error(f"Failed to create custom profile directory: {e}", exc_info=True)
            raise

    # Helpers

    def _load_raw(self) -> dict:
        """Return the whole JSON dict from disk, or {} if there's a failure."""
        if not os.path.exists(self.path):
            return {}
        try:
            with open(self.path, "r", encoding=DEFAULT_ENCODING) as f:
                data = json.load(f)
            if not isinstance(data, dict):
                logger.error("custom_profiles.json doesn't contain a dictionary. Resetting.")
                return {}
            return data
        except json.JSONDecodeError as e:
            logger.error(f"JSON decode error in {self.path}: {e}")
            return {}
        except Exception as e:
            logger.error(f"Failed to read {self.path}: {e}", exc_info=True)
            return {}

    def _write_raw(self, data: dict):
        """Write raw dict to disk"""
        with open(self.path, "w", encoding=DEFAULT_ENCODING) as f:
            json.dump(data, f, indent=JSON_INDENT)

    # Profile storage API
    def load_all(self):
        """
        Return all custom profiles, found by their key
        Skips any bad records
        """
        raw = self._load_raw()
        profiles = {}
        for key, values in raw.items():
            try:
                profiles[key] = DeviceProfile(**values)
            except (TypeError, KeyError) as e:
                logger.warning(f"Skipping messed up for custom profile '{key}': {e}")
        return profiles

    def save(self, profile: DeviceProfile, overwrite_key: str = None):
        """
        Save (or overwrite/edits) a custom profile
        If overwrite_key is provided, it updates that exact JSON entry
        Otherwise, it generates a new unique key
        """
        raw = self._load_raw()

        # Generate keys
        if overwrite_key and overwrite_key in raw:
            key = overwrite_key
        else:
            key = f"{profile.name.lower().replace(' ', '_')}_{uuid.uuid4().hex[:8]}"

        raw[key] = asdict(profile)

        try:
            self._write_raw(raw)
            logger.info(f"Custom profile saved: '{profile.name}' (key: '{key}')")
        except Exception as e:
            logger.error(f"Failed to save custom profile '{profile.name}': {e}", exc_info=True)
            raise

    def find_by_name(self, name: str) -> DeviceProfile | None:
        """
        Case-insensitive lookup by DeviceProfile.name
        Returns None if nothing is found
        """
        for profile in self.load_all().values():
            if profile.name.lower() == name.lower():
                logger.info(f"Custom profile found for '{name}'")
                return profile
        return None

    def find_all_by_device_name(self, device_name: str):
        """
        Return all profiles matching the device's model name
        """
        matches = []

        for profile in self.load_all().values():
            if profile.name.lower() == device_name.lower():
                matches.append(profile)

        return matches

    def delete(self, key: str) -> bool:
        """
        Delete a profile by its storage key
        """
        raw = self._load_raw()
        if key in raw:
            profile_name = raw[key].get("name", "Unknown")
            del raw[key]
            self._write_raw(raw)
            logger.info(f"Custom profile deleted: '{profile_name}' (key: '{key}')")
            return True

        logger.warning(f"Cannot delete key '{key}': not found in custom profiles")
        return False