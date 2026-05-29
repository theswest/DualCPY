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

# src/device_profile.py

from dataclasses import dataclass
import math

@dataclass
class DeviceProfile:
    name: str
    top_display_id: str
    bottom_display_id: str
    top_screen_width: int
    top_screen_height: int
    bottom_screen_width: int
    bottom_screen_height: int
    top_screen_size: float
    bottom_screen_size: float
    screen_launch_delay: int
    default_ui_scale: float

    def get_screen_width_ratio(self):
        top_ppi = math.sqrt(self.top_screen_width**2 + self.top_screen_height**2) / self.top_screen_size
        bottom_ppi = math.sqrt(self.bottom_screen_width**2 + self.bottom_screen_height**2) / self.bottom_screen_size

        top_physical_width = self.top_screen_width / top_ppi
        bottom_physical_width = self.bottom_screen_width / bottom_ppi

        return bottom_physical_width / top_physical_width

BUILTIN_PROFILES = {
    "ayn_thor": DeviceProfile(
        name="Ayn Thor",
        top_display_id="0",
        bottom_display_id="4",
        top_screen_width=1920,
        top_screen_height=1080,
        bottom_screen_width=1240,
        bottom_screen_height=1080,
        top_screen_size=6,
        bottom_screen_size=3.92,
        screen_launch_delay=0,
        default_ui_scale=0.6,
    ),
    "rg_ds": DeviceProfile(
        name="RG DS",
        top_display_id="2",
        bottom_display_id="0",
        top_screen_width=640,
        top_screen_height=480,
        bottom_screen_width=640,
        bottom_screen_height=480,
        top_screen_size=4,
        bottom_screen_size=4,
        screen_launch_delay=3,
        default_ui_scale=1.25,
    ),
}