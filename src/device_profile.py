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

# src/device_profile.py

import math
from dataclasses import dataclass

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
    flipped_screens: bool
    screen_launch_delay: int
    default_ui_scale: float
    nickname: str = ""

    def get_screen_width_ratio(self):
        top_ppi = math.sqrt(self.top_screen_width**2 + self.top_screen_height**2) / self.top_screen_size
        bottom_ppi = math.sqrt(self.bottom_screen_width**2 + self.bottom_screen_height**2) / self.bottom_screen_size

        top_physical_width = self.top_screen_width / top_ppi
        bottom_physical_width = self.bottom_screen_width / bottom_ppi

        return bottom_physical_width / top_physical_width

BUILTIN_PROFILES = {

    # -------------------
    # Dual Screen Devices
    # -------------------

    "ayn_thor": DeviceProfile(
        name="AYN Thor",
        top_display_id="0",
        bottom_display_id="4",
        top_screen_width=1920,
        top_screen_height=1080,
        bottom_screen_width=1240,
        bottom_screen_height=1080,
        top_screen_size=6,
        bottom_screen_size=3.92,
        flipped_screens=False,
        screen_launch_delay=0,
        default_ui_scale=0.6,
        nickname="AYN Thor (Built-In)"
    ),
    "rg_ds": DeviceProfile(
        name="TrebleDroid vanilla",
        top_display_id="2",
        bottom_display_id="0",
        top_screen_width=640,
        top_screen_height=480,
        bottom_screen_width=640,
        bottom_screen_height=480,
        top_screen_size=4,
        bottom_screen_size=4,
        flipped_screens=True,
        screen_launch_delay=3,
        default_ui_scale=1.25,
    ),
    "pocket_ds": DeviceProfile(
        name="Pocket DS",
        top_display_id="0",
        bottom_display_id="3",
        top_screen_width=1920,
        top_screen_height=1080,
        bottom_screen_width=1024,
        bottom_screen_height=768,
        top_screen_size=7,
        bottom_screen_size=5,
        flipped_screens=False,
        screen_launch_delay=0,
        default_ui_scale=0.45,
    ),

    # ------------------------------
    # Assuming RDS addon is attached
    # ------------------------------

    # AYN
    "odin3_rds": DeviceProfile(
        name="Odin3",
        top_display_id="0",
        bottom_display_id="4",
        top_screen_width=1920,
        top_screen_height=1080,
        bottom_screen_width=1920,
        bottom_screen_height=1080,
        top_screen_size=5.5,
        bottom_screen_size=6,
        flipped_screens=True,
        screen_launch_delay=0,
        default_ui_scale=0.45,
    ),
    "odin2_rds": DeviceProfile(
        name="Odin2",
        top_display_id="0",
        bottom_display_id="4",
        top_screen_width=1920,
        top_screen_height=1080,
        bottom_screen_width=1920,
        bottom_screen_height=1080,
        top_screen_size=5.5,
        bottom_screen_size=6,
        flipped_screens=True,
        screen_launch_delay=0,
        default_ui_scale=0.45,
    ),
    "odin2_portal_rds": DeviceProfile(
        name="Odin2 Portal",
        top_display_id="0",
        bottom_display_id="4",
        top_screen_width=1920,
        top_screen_height=1080,
        bottom_screen_width=1920,
        bottom_screen_height=1080,
        top_screen_size=5.5,
        bottom_screen_size=7,
        flipped_screens=True,
        screen_launch_delay=0,
        default_ui_scale=0.45,
    ),
    "odin2_mini_rds": DeviceProfile(
        name="Odin2 Mini",
        top_display_id="0",
        bottom_display_id="4",
        top_screen_width=1920,
        top_screen_height=1080,
        bottom_screen_width=1920,
        bottom_screen_height=1080,
        top_screen_size=5.5,
        bottom_screen_size=5,
        flipped_screens=True,
        screen_launch_delay=0,
        default_ui_scale=0.45,
    ),

    # Retroid
    "rp6_rds": DeviceProfile(
        name="Retroid Pocket 6",
        top_display_id="0",
        bottom_display_id="4",
        top_screen_width=1920,
        top_screen_height=1080,
        bottom_screen_width=1920,
        bottom_screen_height=1080,
        top_screen_size=5.5,
        bottom_screen_size=5.5,
        flipped_screens=True,
        screen_launch_delay=0,
        default_ui_scale=0.45,
    ),
    "rp5_rds": DeviceProfile(
        name="Retroid Pocket 5",
        top_display_id="0",
        bottom_display_id="4",
        top_screen_width=1920,
        top_screen_height=1080,
        bottom_screen_width=1920,
        bottom_screen_height=1080,
        top_screen_size=5.5,
        bottom_screen_size=5.5,
        flipped_screens=True,
        screen_launch_delay=0,
        default_ui_scale=0.45,
    ),
    "rpg2_rds": DeviceProfile(
        name="Retroid Pocket G2",
        top_display_id="0",
        bottom_display_id="4",
        top_screen_width=1920,
        top_screen_height=1080,
        bottom_screen_width=1920,
        bottom_screen_height=1080,
        top_screen_size=5.5,
        bottom_screen_size=5.5,
        flipped_screens=True,
        screen_launch_delay=0,
        default_ui_scale=0.45,
    ),
    "rp4p_rds": DeviceProfile(
        name="Retroid Pocket 4 Pro",
        top_display_id="0",
        bottom_display_id="4",
        top_screen_width=1920,
        top_screen_height=1080,
        bottom_screen_width=1334,
        bottom_screen_height=750,
        top_screen_size=5.5,
        bottom_screen_size=4.7,
        flipped_screens=True,
        screen_launch_delay=0,
        default_ui_scale=0.45,
    ),
    "rp4_rds": DeviceProfile(
        name="Retroid Pocket 4",
        top_display_id="0",
        bottom_display_id="4",
        top_screen_width=1920,
        top_screen_height=1080,
        bottom_screen_width=1334,
        bottom_screen_height=750,
        top_screen_size=5.5,
        bottom_screen_size=4.7,
        flipped_screens=True,
        screen_launch_delay=0,
        default_ui_scale=0.45,
    ),
}