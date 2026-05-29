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

# src/device_selector.py

from src.device_profile import BUILTIN_PROFILES

def show_device_selector(profiles=None):
    if profiles is None:
        profiles = BUILTIN_PROFILES
    return BUILTIN_PROFILES["ayn_thor"]  # hardcoded for testing