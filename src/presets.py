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

# src/presets.py

import os
import re
import json
import logging

# Validation Constants
MAX_PRESET_NAME_LENGTH = 50
INVALID_CHARS = r'[<>:"/\\|?*\x00-\x1f]'

# JSON formatting constants
JSON_INDENT = 4
DEFAULT_ENCODING = "utf-8"


logger = logging.getLogger(__name__)

class PresetStore:
    """
    Manages persistence for layouts.
    """

    def __init__(self, path):
        """
        Initialize storing the preset
        """
        logger.info(f"Initializing PresetStore with path: {path}")
        self.path = path

        # Create directory structure if necessary
        try:
            dir_path = os.path.dirname(self.path)
            if dir_path:
                os.makedirs(dir_path, exist_ok=True)
                logger.debug(f"Ensured directory exists: {dir_path}")
        except Exception as e:
            logger.error(f"Failed to create preset directory: {e}", exc_info=True)
            raise

        # Log if file exists
        if os.path.exists(self.path):
            logger.info(f"Preset file exists: {self.path}")
        else:
            logger.info(
                f"Preset file does not exist yet (will be created on first save): {self.path}"
            )

    @staticmethod
    def validate_preset_name(name):
        """
        Validate preset name
        """
        logger.debug(f"Validating preset name: '{name}'")

        if not name or not name.strip():
            logger.warning("Preset name validation failed: empty name")
            return False, "Preset name cannot be empty"

        if len(name) > MAX_PRESET_NAME_LENGTH:
            logger.warning(
                f"Preset name validation failed: too long ({len(name)} chars)"
            )
            return False, f"Preset name too long (max {MAX_PRESET_NAME_LENGTH} characters)"

        # Check for invalid filesystem characters
        if re.search(INVALID_CHARS, name):
            logger.warning(
                "Preset name validation failed: contains invalid characters"
            )
            return False, "Preset name contains invalid characters"

        # Prevent directory traversal attempts
        if ".." in name or name.startswith("."):
            logger.warning(
                "Preset name validation failed: invalid format (directory traversal attempt?)"
            )
            return False, "Invalid preset name format"

        logger.debug(f"Preset name validation passed: '{name}'")
        return True, ""

    def save_preset(self, name, data):
        """
        Save a preset with validation.
        """
        logger.info(f"Attempting to save preset: '{name}'")

        # Validate name
        is_valid, error = self.validate_preset_name(name)
        if not is_valid:
            logger.error(f"Invalid preset name '{name}': {error}")
            raise ValueError(error)

        try:
            # Load existing presets
            presets = self.load_all()

            # Check if overwriting
            if name in presets:
                logger.info(f"Overwriting existing preset: '{name}'")
            else:
                logger.info(f"Creating new preset: '{name}'")

            # Add/update preset
            presets[name] = data

            # Save to file
            logger.debug(f"Writing presets to {self.path}")
            with open(self.path, "w", encoding=DEFAULT_ENCODING) as file:
                json.dump(presets, file, indent=JSON_INDENT)

            logger.info(f"Successfully saved preset '{name}' with data: {data}")

        except PermissionError as e:
            logger.error(f"Permission denied writing to {self.path}: {e}")
            raise
        except IOError as e:
            logger.error(f"IO error saving preset '{name}': {e}", exc_info=True)
            raise
        except Exception as e:
            logger.error(f"Unexpected error saving preset '{name}': {e}", exc_info=True)
            raise

    def delete_preset(self, name):
        """
        Delete a preset by name
        """
        logger.info(f"Attempting to delete preset: '{name}'")

        try:
            presets = self.load_all()

            if name in presets:
                del presets[name]
                logger.debug(f"Preset '{name}' removed from dictionary")

                # Save updated presets
                with open(self.path, "w", encoding=DEFAULT_ENCODING) as file:
                    json.dump(presets, file, indent=JSON_INDENT)

                logger.info(f"Successfully deleted preset: '{name}'")
                return True
            else:
                logger.warning(f"Cannot delete preset '{name}': does not exist")
                return False

        except PermissionError as e:
            logger.error(f"Permission denied writing to {self.path}: {e}")
            raise
        except IOError as e:
            logger.error(f"IO error deleting preset '{name}': {e}", exc_info=True)
            raise
        except Exception as e:
            logger.error(f"Unexpected error deleting preset '{name}': {e}", exc_info=True)
            raise

    def load_all(self):
        """
        Load all presets from disk
        """
        if not os.path.exists(self.path):
            logger.debug(
                f"Preset file does not exist: {self.path}, returning empty dict"
            )
            return {}

        try:
            logger.debug(f"Loading presets from {self.path}")
            with open(self.path, "r", encoding=DEFAULT_ENCODING) as file:
                presets = json.load(file)

            # Validate structure
            if not isinstance(presets, dict):
                logger.error(f"Preset file contains invalid data type: {type(presets)}")
                return {}

            logger.debug(f"Loaded {len(presets)} preset(s) from disk: {list(presets.keys())}")
            return presets

        except json.JSONDecodeError as e:
            logger.error(f"JSON decode error reading {self.path}: {e}", exc_info=True)
            logger.warning("Returning empty preset dictionary due to corrupted file")
            return {}
        except PermissionError as e:
            logger.error(f"Permission denied reading {self.path}: {e}")
            return {}
        except IOError as e:
            logger.error(f"IO error reading presets: {e}", exc_info=True)
            return {}
        except Exception as e:
            logger.error(f"Unexpected error loading presets: {e}", exc_info=True)
            return {}

    def get_preset(self, name):
        """
        Get a specific preset by name
        """
        logger.debug(f"Retrieving preset: '{name}'")
        presets = self.load_all()

        if name in presets:
            logger.debug(f"Found preset '{name}': {presets[name]}")
            return presets[name]
        else:
            logger.debug(f"Preset '{name}' not found")
            return None

    def list_preset_names(self):
        """
        Get a list of all preset names
        """
        presets = self.load_all()
        names = list(presets.keys())
        logger.debug(f"Listing {len(names)} preset name(s): {names}")
        return names