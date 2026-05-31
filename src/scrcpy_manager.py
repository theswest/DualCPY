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

# src/scrcpy_manager.py

import os
import re
import time
import ctypes
import logging
import subprocess
from src.device_detection import resolve_adb

# Setup logger for this module
logger = logging.getLogger(__name__)

# Process creation flags and prevent console window from appearing
CREATE_NO_WINDOW = 0x08000000
# HIGH_PRIORITY_CLASS keeps scrcpy from being descheduled under load.
# Important for sustained smoothness when the host CPU has other work.
HIGH_PRIORITY_CLASS = 0x00000080
SCRCPY_CREATION_FLAGS = CREATE_NO_WINDOW | HIGH_PRIORITY_CLASS

# Scrcpy startup retry config
SCRCPY_RETRY_COUNT = 2
SCRCPY_START_DELAY = 1.0

# ADB command timeouts
ADB_CAPTURE_OUTPUT = True
ADB_SERVER_TIMEOUT = 30
ADB_TASKKILL_TIMEOUT = 5
ADB_TCPIP_TIMEOUT = 10
ADB_CONNECT_TIMEOUT = 10
ADB_SERVER_START_RETRIES = 2

# Logging constants
LOG_MULT = 60
LOGFILE_ENCODING = "utf-8"

# Scrcpy default parameters
DEFAULT_MAX_FPS = "60"
DEFAULT_RENDER_DRIVER = "direct3d"
DEFAULT_VIDEO_CODEC = "h264"

# Video bitrate calculation constants
BITRATE_CALC_SCALE_FACTOR = 2.0
TOP_BITRATE_MINIMUM = 12
TOP_BITRATE_SCALE = 24
BOTTOM_BITRATE_MINIMUM = 6
BOTTOM_BITRATE_SCALE = 18

# Timing delays for process management
DISPLAY_INIT_DELAY = 1.2  # Wait for first display to initialize
SCRCPY_CREATION_DELAY = 0.3  # Check if process survives startup
SCRCPY_RETRY_DELAY = 0.7  # Wait between retry attempts

# Process termination timeouts
PROCESS_TERMINATE_TIMEOUT = 2
SCRCPY_TERMINATE_TIMEOUT = 3

# Wireless connection defaults
DEFAULT_WIRELESS_PORT = 5555

# Main ScrcpyManager class
class ScrcpyManager:
    """
    Manages scrcpy instances for controlling and displaying the Thor's screens
    Handles device detection (USB and wireless), window launching, scaling,
    resolution and process management and shutdown
    """

    def __init__(self, profile, scale=None, scrcpy_bin=None,
                 adb_bin=None, enable_audio_top=True, max_fps=int(DEFAULT_MAX_FPS)):
        """
        Initialize the scrcpy manager.
        """
        self.scale = scale if scale is not None else profile.default_ui_scale
        self.profile = profile
        self.processes = []
        self.serial = None
        self.enable_audio_top = enable_audio_top
        self.connection_mode = None
        # Configurable per-instance FPS cap (override the module default)
        self.max_fps = int(max_fps) if max_fps else int(DEFAULT_MAX_FPS)
        self._scrcpy_log_handles = []

        logger.info(
            f"Initializing ScrcpyManager (scale={self.scale}, audio={enable_audio_top}, fps={max_fps})"
        )

        # Calculate top screen resolution based on scale
        self.f_w1 = int(profile.top_screen_width * self.scale)
        self.f_h1 = int(profile.top_screen_height * self.scale)
        logger.debug(f"Top window resolution: {self.f_w1}x{self.f_h1}")

        # Calculate bottom screen resolution based on scale
        self.f_w2 = int(self.f_w1 * profile.get_screen_width_ratio())
        self.f_h2 = int(self.f_w2 * profile.bottom_screen_height / profile.bottom_screen_width)
        logger.debug(f"Bottom window resolution: {self.f_w2}x{self.f_h2}")

        # Locate scrcpy and adb binaries
        self.scrcpy_bin = scrcpy_bin or resolve_adb("scrcpy")
        self.adb_bin = adb_bin or resolve_adb("adb")

        if self.scrcpy_bin:
            logger.info(f"scrcpy binary found: {self.scrcpy_bin}")
        else:
            logger.warning("scrcpy binary not found")

        if self.adb_bin:
            logger.info(f"adb binary found: {self.adb_bin}")
        else:
            logger.warning("adb binary not found")

        # Retry config
        self.scrcpy_retry_count = SCRCPY_RETRY_COUNT
        self.scrcpy_start_delay = SCRCPY_START_DELAY
        logger.debug(f"Retry count: {self.scrcpy_retry_count}, Start delay: {self.scrcpy_start_delay}s")

    def _is_wireless_serial(self, serial):
        """
        Check if a serial number is a wireless connection (IP:PORT)
        """
        # Wireless connections are in format IP:PORT (e.g., 192.168.1.100:5555)
        return ':' in serial and re.match(r'\d+\.\d+\.\d+\.\d+:\d+', serial)

    def connect_wireless(self, ip_address, port=DEFAULT_WIRELESS_PORT):
        """
        Connect to a device wirelessly via ADB
        """
        if not self.adb_bin:
            logger.error("Cannot connect wirelessly: ADB binary not found")
            return False

        target = f"{ip_address}:{port}"
        logger.info(f"Attempting wireless connection to {target}")

        try:
            result = subprocess.run(
                [self.adb_bin, "connect", target],
                capture_output=ADB_CAPTURE_OUTPUT,
                text=True,
                timeout=ADB_CONNECT_TIMEOUT,
            )

            output = result.stdout.strip() if result.stdout else ""

            if result.returncode == 0 and "connected" in output.lower():
                logger.info(f"Successfully connected to {target}")
                self.serial = target
                self.connection_mode = 'wireless'
                return True
            else:
                # Provide helpful error information
                error_msg = output if output else "Unknown error"
                logger.error(f"Failed to connect to {target}: {error_msg}")

                # Detect if this might be a pairing issue
                if port != DEFAULT_WIRELESS_PORT or "refused" in error_msg.lower() or "failed" in error_msg.lower():
                    logger.warning("=" * LOG_MULT)
                    logger.warning("CONNECTION TROUBLESHOOTING:")
                    logger.warning("=" * LOG_MULT)

                    if port != DEFAULT_WIRELESS_PORT:
                        logger.warning(f"Non-standard port detected ({port})")
                        logger.warning("This may be Android 11+ Wireless Debugging mode.")
                        logger.warning("")
                        logger.warning("For Wireless Debugging (random port like 46303):")
                        logger.warning("  1. On device: Developer Options > Wireless Debugging")
                        logger.warning("  2. Tap 'Pair device with pairing code'")
                        logger.warning("  3. You must PAIR first using: adb pair IP:PAIRING_PORT")
                        logger.warning("  4. Enter the 6-digit pairing code shown on device")
                        logger.warning("  5. After pairing, THEN connect using adb connect")
                        logger.warning("")

                    logger.warning("For legacy TCP/IP mode (port 5555):")
                    logger.warning("  1. Connect device via USB first")
                    logger.warning("  2. Enable wireless mode (button in this app)")
                    logger.warning("  3. Disconnect USB cable")
                    logger.warning("  4. Connect using IP:5555")
                    logger.warning("")
                    logger.warning("Make sure:")
                    logger.warning("  • Device and PC are on the same WiFi network")
                    logger.warning("  • Wireless debugging/ADB over network is enabled on device")
                    logger.warning("  • No firewall is blocking the connection")
                    logger.warning("=" * LOG_MULT)

                return False

        except subprocess.TimeoutExpired:
            logger.error(f"Connection timeout for {target}")
            logger.warning("Connection timed out - device may be unreachable or not on the same network")
            return False
        except Exception as WirelessConnectError:
            logger.error(f"Error connecting wirelessly: {WirelessConnectError}")
            return False

    def pair_wireless(self, ip_address, pairing_port, pairing_code):
        """
        Pair with a device using Android 11+ Wireless Debugging pairing

        This is required for the new wireless debugging feature that uses
        random ports and requires initial pairing with a code
        """
        if not self.adb_bin:
            logger.error("Cannot pair wirelessly: ADB binary not found")
            return False

        target = f"{ip_address}:{pairing_port}"
        logger.info(f"Attempting to pair with {target} using pairing code")

        try:
            # The adb pair command expects the pairing code to be provided interactively
            # or we can pass it via stdin
            process = subprocess.Popen(
                [self.adb_bin, "pair", target],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
            )

            # Send the pairing code
            output, _ = process.communicate(input=f"{pairing_code}\n", timeout=ADB_CONNECT_TIMEOUT)

            if process.returncode == 0 and ("successfully paired" in output.lower() or "paired" in output.lower()):
                logger.info(f"Successfully paired with {target}")
                return True
            else:
                logger.error(f"Failed to pair with {target}: {output}")
                return False

        except subprocess.TimeoutExpired:
            logger.error(f"Pairing timeout for {target}")
            return False
        except Exception as PairingError:
            logger.error(f"Error during pairing: {PairingError}")
            return False

    def disconnect_wireless(self, target=None):
        """
        Disconnect a wireless ADB connection
        """
        if not self.adb_bin:
            logger.error("Cannot disconnect: ADB binary not found")
            return False

        disconnect_target = target or self.serial
        if not disconnect_target:
            logger.warning("No target specified for disconnection")
            return False

        logger.info(f"Disconnecting from {disconnect_target}")

        try:
            result = subprocess.run(
                [self.adb_bin, "disconnect", disconnect_target],
                capture_output=ADB_CAPTURE_OUTPUT,
                text=True,
                timeout=ADB_CONNECT_TIMEOUT,
            )

            if result.returncode == 0:
                logger.info(f"Disconnected from {disconnect_target}")
                if disconnect_target == self.serial:
                    self.serial = None
                    self.connection_mode = None
                return True
            else:
                logger.error(f"Failed to disconnect: {result.stdout}")
                return False

        except Exception as DisconnectError:
            logger.error(f"Error disconnecting: {DisconnectError}")
            return False

    def enable_wireless_mode(self, port=DEFAULT_WIRELESS_PORT):
        """
        Enable wireless ADB mode on a USB-connected device
        This switches the device to TCP/IP mode
        """
        if not self.adb_bin:
            logger.error("Cannot enable wireless mode: ADB binary not found")
            return False

        if not self.serial:
            logger.error("Cannot enable wireless mode: No device connected")
            return False

        if self._is_wireless_serial(self.serial):
            logger.warning("Device is already in wireless mode")
            return True

        logger.info(f"Enabling wireless mode on {self.serial} (port {port})")

        try:
            result = subprocess.run(
                [self.adb_bin, "-s", self.serial, "tcpip", str(port)],
                capture_output=ADB_CAPTURE_OUTPUT,
                text=True,
                timeout=ADB_TCPIP_TIMEOUT,
            )

            if result.returncode == 0:
                logger.info(f"Wireless mode enabled on port {port}")
                return True
            else:
                logger.error(f"Failed to enable wireless mode: {result.stdout}")
                return False

        except subprocess.TimeoutExpired:
            logger.error("Timeout enabling wireless mode")
            return False
        except Exception as WirelessEnableError:
            logger.error(f"Error enabling wireless mode: {WirelessEnableError}")
            return False

    def get_device_ip(self):
        """
        Get the IP address of the connected USB device
        """
        if not self.adb_bin or not self.serial:
            logger.error("Cannot get device IP: No device connected")
            return None

        if self._is_wireless_serial(self.serial):
            # Extract IP from wireless serial
            return self.serial.split(':')[0]

        logger.debug("Attempting to retrieve device IP address")

        try:
            # Try to get IP from wlan0 interface
            result = subprocess.run(
                [self.adb_bin, "-s", self.serial, "shell", "ip", "addr", "show", "wlan0"],
                capture_output=ADB_CAPTURE_OUTPUT,
                text=True,
                timeout=ADB_SERVER_TIMEOUT,
            )

            if result.returncode == 0:
                # Parse IP from output (format: "inet 192.168.1.100/24")
                for line in result.stdout.split('\n'):
                    if 'inet ' in line:
                        parts = line.strip().split()
                        for i, part in enumerate(parts):
                            if part == 'inet' and i + 1 < len(parts):
                                ip_with_mask = parts[i + 1]
                                ip = ip_with_mask.split('/')[0]
                                logger.info(f"Device IP address: {ip}")
                                return ip

            logger.warning("Could not find IP address in wlan0 output")
            return None

        except Exception as GetIPError:
            logger.error(f"Error getting device IP: {GetIPError}")
            return None

    @staticmethod
    def default_args(
        width: int,
        height: int,
        bitrate_min: int,
        bitrate_scale: int,
        enable_audio: bool,
    ) -> list[str]:
        """
        Returns the default editable scrcpy args for a single screen.
        Called by profile dialogs to pre-populate the args textboxes.
        """
        pixels = width * height
        bitrate_mbps = max(bitrate_min, int(pixels / 1e6 * bitrate_scale * BITRATE_CALC_SCALE_FACTOR))

        codec_options = (
            "low-latency=1,"
            "priority=0,"
            "operating-rate=120,"
            "bitrate-mode=2,"
            "complexity=0,"
            "i-frame-interval=10,"
            "intra-refresh-period=60"
        )

        args = [
            f"--video-bit-rate={bitrate_mbps}M",
            f"--render-driver={DEFAULT_RENDER_DRIVER}",
            f"--video-codec={DEFAULT_VIDEO_CODEC}",
            f"--video-codec-options={codec_options}",
            "--no-mipmaps",
            "--no-power-on",
            "--no-cleanup",
            "--print-fps",
            "--audio-bit-rate=256K" if enable_audio else "--no-audio",
        ]
        return args

    def _window_titles(self):
        name = self.profile.name
        return f"{name} - Top Screen - DualCPY", f"{name} - Bottom Screen - DualCPY"

    def _read_last_log(self):
        """Pull the last few lines from the most recent scrcpy log file."""
        try:
            if not self._scrcpy_log_handles:
                return ""
            handle = self._scrcpy_log_handles[-1]
            handle.flush()
            path = handle.name
            with open(path, "r", errors="replace") as f:
                lines = f.readlines()
            return "".join(lines[-10:]).strip()
        except Exception:
            return ""

    def start_scrcpy(self, serial=None):
        """
        Start both scrcpy windows (top and bottom screen)
        Supports both USB and wireless connections
        """
        use_serial = serial or self.serial
        if not use_serial:
            raise RuntimeError("No device serial available")

        profile = self.profile

        top_title, bottom_title = self._window_titles()

        logger.info("=" * LOG_MULT)
        logger.info(f"Starting scrcpy for device: {use_serial}")
        logger.info(f"Connection mode: {self.connection_mode or 'unknown'}")
        logger.info("=" * LOG_MULT)

        if not self.scrcpy_bin:
            raise RuntimeError("scrcpy binary not found")

        time.sleep(self.scrcpy_start_delay)

        # Launch top screen
        logger.info("Starting top screen window")
        top_args = profile.extra_scrcpy_args_top or self.default_args(
            self.f_w1, self.f_h1, TOP_BITRATE_MINIMUM, TOP_BITRATE_SCALE,
            enable_audio=self.enable_audio_top,
        )
        self._start_window(
            use_serial,
            profile.top_display_id,
            top_title,
            self.f_w1,
            self.f_h1,
            extra_args=top_args,
            max_fps_override=self.max_fps,
        )

        # Wait for first display to stabilize
        logger.info("Waiting for top screen window to appear before starting bottom...")
        deadline = time.time() + 15.0
        while time.time() < deadline:
            hwnd = ctypes.windll.user32.FindWindowW(None, top_title)
            if hwnd:
                logger.info(f"Top screen window confirmed (HWND: {hwnd}), starting bottom screen")
                break
            time.sleep(0.25)
        else:
            logger.warning("Top screen window not detected within 15s, starting bottom screen anyway")

        logger.info(f"Waiting for server to stabilise...")
        time.sleep(profile.screen_launch_delay)
        logger.info("Server stabilisation delay finished.")

        # Launch bottom screen
        logger.info("Starting bottom screen window")
        bottom_args = profile.extra_scrcpy_args_bottom or self.default_args(
            self.f_w2, self.f_h2, BOTTOM_BITRATE_MINIMUM, BOTTOM_BITRATE_SCALE,
            enable_audio=False,
        )
        self._start_window(
            use_serial,
            profile.bottom_display_id,
            bottom_title,
            self.f_w2,
            self.f_h2,
            extra_args=bottom_args,
        )

        logger.info("All scrcpy windows started successfully")
        logger.info("=" * LOG_MULT)

    def _start_window(
            self,
            serial,
            display_id,
            window_title,
            width,
            height,
            extra_args: list = None,
            max_fps_override=None,
    ):
        """
        Start a single scrcpy window with retry logic.
        extra_args are the fully editable per-screen scrcpy flags
        (bitrate, codec, audio, etc.). Locked args (serial, display-id,
        window-title, max-size, max-fps) are always applied separately.
        """
        label = f"'{window_title}'"
        logger.debug(f"Preparing to start {label} (display {display_id})")

        cmd = [
            self.scrcpy_bin,
            "--serial",       serial,
            "--display-id",   display_id,
            "--window-title", window_title,
            "--max-size",     f"{width}",
            "--max-fps",      str(max_fps_override if max_fps_override is not None else self.max_fps),
            *(extra_args or []),
        ]

        logger.debug(f"Command: {' '.join(cmd)}")

        # Retry logic
        last_exc = None
        for attempt in range(1, self.scrcpy_retry_count + 1):
            try:
                logger.info(f"Starting {label} (attempt {attempt}/{self.scrcpy_retry_count})")

                # IMPORTANT: NEVER use subprocess.PIPE here without a
                # drain thread - scrcpy's stdout/stderr fill the OS
                # pipe buffer (~64 KB on Windows) within seconds, then
                # scrcpy blocks on its next write and the stream stalls.
                #
                # Instead we hand scrcpy a real file handle. The OS
                # writes lazily to disk so there is no buffer-fill
                # deadlock, and we get scrcpy's --print-fps output in
                # a per-instance log file we can tail live with
                # `Get-Content -Wait logs\scrcpy_<role>_*.log` to see
                # the actual on-screen FPS.
                role = "top" if "Top" in window_title else "bottom"
                ts = time.strftime("%Y%m%d_%H%M%S")
                log_dir = "logs"
                try:
                    os.makedirs(log_dir, exist_ok=True)
                except Exception:
                    pass
                log_path = os.path.join(log_dir, f"scrcpy_{role}_{ts}.log")
                try:
                    log_handle = open(log_path, "wb", buffering=0)
                    self._scrcpy_log_handles.append(log_handle)
                    stdout_target = log_handle
                    stderr_target = subprocess.STDOUT
                    logger.info(f"Scrcpy {role} output -> {log_path}")
                except Exception as ScrcpyLogOpenError:
                    logger.warning(
                        f"Could not open scrcpy log file '{log_path}': "
                        f"{ScrcpyLogOpenError} - falling back to DEVNULL"
                    )
                    stdout_target = subprocess.DEVNULL
                    stderr_target = subprocess.DEVNULL

                # Disable SDL2's vsync wait inside scrcpy. With vsync
                # ON, SDL_RenderPresent blocks until the next monitor
                # refresh - on high-refresh-rate monitors (e.g. 144 /
                # 165 / 240 Hz) the timing slots don't align with the
                # 60 Hz incoming frame stream, and scrcpy ends up
                # skipping frames. Setting SDL_RENDER_VSYNC=0 makes
                # the renderer present every decoded frame as soon as
                # it arrives - the small chance of tearing on a
                # 200+ Hz panel is essentially invisible.
                child_env = os.environ.copy()
                child_env["SDL_RENDER_VSYNC"] = "0"
                # Strip PyInstaller bootloader env vars so a frozen-
                # parent's _MEIPASS isn't inherited by scrcpy.
                for _k in (
                    "_MEIPASS2",
                    "_PYI_APPLICATION_HOME_DIR",
                    "_PYI_PARENT_PROCESS_LEVEL",
                    "_PYI_SPLASH_IPC",
                ):
                    child_env.pop(_k, None)

                proc = subprocess.Popen(
                    cmd,
                    creationflags=SCRCPY_CREATION_FLAGS,
                    stdout=stdout_target,
                    stderr=stderr_target,
                    env=child_env,
                )

                # Quick check if process survives startup
                time.sleep(SCRCPY_CREATION_DELAY)
                if proc.poll() is not None:
                    log_tail = self._read_last_log()
                    raise RuntimeError(
                        f"Scrcpy {label} process died immediately (exit code: {proc.poll()})"
                        + (f"\n\nScrcpy output:\n{log_tail}" if log_tail else "")
                    )

                # Start process hidden
                self.processes.append(proc)
                logger.info(
                    f"Scrcpy {label} window started successfully (PID: {proc.pid})"
                )
                return proc

            except Exception as ScrcpyStartError:
                last_exc = ScrcpyStartError
                logger.warning(f"Scrcpy {label} start attempt "
                               f"{attempt}/{self.scrcpy_retry_count} failed: {ScrcpyStartError}")
                if attempt < self.scrcpy_retry_count:
                    logger.debug(f"Waiting {SCRCPY_RETRY_DELAY}s before retry...")
                    time.sleep(SCRCPY_RETRY_DELAY)

        # All attempts failed
        logger.error(f"All {self.scrcpy_retry_count} attempts to start scrcpy {label} window failed")
        raise last_exc

    # Check if process is alive
    def _check_process_alive(self):
        """
        Check if any processes that were tracked have died

        Returns the first process that is no longer alive or None if all are running
        """
        for processName, process in enumerate(self.processes):
            try:
                if process.poll() is not None:
                    logger.warning(f"Process {processName} "
                                   f"(PID: {process.pid}) is no longer alive (exit code: {process.poll()})")
                    return process
            except Exception as ProcessCheckError:
                logger.error(f"Error checking process {processName} status: {ProcessCheckError}")
                return process
        return None

    # Stop Process
    def stop(self):
        """
        Stop and cleanup all scrcpy windows politely, then forcefully if needed.

        Shuts down in the following order:
        1) Gracefully terminate (SIGTERM)
        2) Wait for proceesses to exit
        3) Force kill if needed (taskkill)
        4) Device-side cleanup (kill scrcpy-server, app_process)
        5) Remove ADB port forwards

        Safe to call multiple times
        """
        logger.info("=" * LOG_MULT)
        logger.info("Stopping ScrcpyManager")
        logger.info("=" * LOG_MULT)

        if not self.processes:
            logger.info("No scrcpy processes to stop")
            return

        logger.info(f"Stopping {len(self.processes)} scrcpy process(es)")

        # Attempt graceful termination
        for processName, process in enumerate(list(self.processes)):
            try:
                if process.poll() is None:
                    logger.debug(f"Terminating process {processName} (PID: {process.pid})")
                    process.terminate()
                else:
                    logger.debug(f"Process {processName} (PID: {process.pid}) already stopped")
            except Exception as TerminationError:
                logger.warning(f"Error terminating process {processName}: {TerminationError}")

        # Wait for graceful exit, then force-kill remaining processes
        logger.debug("Waiting for processes to terminate gracefully...")
        for processName, process in enumerate(list(self.processes)):
            try:
                if process.poll() is None:
                    process.wait(timeout=PROCESS_TERMINATE_TIMEOUT)
                    logger.debug(f"Process {processName} (PID: {process.pid}) terminated gracefully")
            except subprocess.TimeoutExpired:
                logger.warning(
                    f"Process {processName} (PID: {process.pid}) did not terminate, forcing kill"
                )
                try:
                    process.kill()
                    logger.debug(f"Process {processName} killed with p.kill()")
                except Exception as ProcessKillError:
                    logger.error(f"Failed to kill process {processName}: {ProcessKillError}")
                    # Last resort -> taskkill
                    try:
                        subprocess.run(
                            ["taskkill", "/F", "/T", "/PID", str(process.pid)],
                            capture_output=ADB_CAPTURE_OUTPUT,
                            timeout=ADB_TASKKILL_TIMEOUT,
                        )
                        logger.debug(f"Process {processName} killed with taskkill")
                    except Exception as TaskKillError:
                        logger.error(f"Taskkill also failed for process {processName}: {TaskKillError}")
            except Exception as ProcessKillWaitingError:
                logger.error(f"Error waiting for process {processName}: {ProcessKillWaitingError}")

        # Clear process list
        process_count = len(self.processes)
        self.processes = []
        logger.info(f"Cleared {process_count} process(es) from tracking list")

        # Close any per-instance scrcpy log files we opened
        for handle in self._scrcpy_log_handles:
            try:
                handle.close()
            except Exception:
                pass
        self._scrcpy_log_handles = []

        # Device-side cleanup (scrcpy server and app_process)
        if self.serial and self.adb_bin:
            logger.info(f"Performing device-side cleanup for {self.serial}")

            # Kill scrcpy server
            try:
                logger.debug("Killing scrcpy-server on device")
                result = subprocess.run(
                    [
                        self.adb_bin,
                        "-s",
                        self.serial,
                        "shell",
                        "pkill",
                        "-f",
                        "scrcpy-server",
                    ],
                    capture_output=ADB_CAPTURE_OUTPUT,
                    timeout=SCRCPY_TERMINATE_TIMEOUT,
                )
                if result.returncode == 0:
                    logger.debug("scrcpy-server killed successfully")
                else:
                    logger.debug(f"pkill scrcpy-server returned {result.returncode} (may not have been running)")
            except subprocess.TimeoutExpired:
                logger.warning("Timeout killing scrcpy-server")
            except Exception as ScrcpyKillError:
                logger.warning(f"Error killing scrcpy-server: {ScrcpyKillError}")

            # Kill app_process
            try:
                logger.debug("Killing app_process on device")
                result = subprocess.run(
                    [
                        self.adb_bin,
                        "-s",
                        self.serial,
                        "shell",
                        "pkill",
                        "-f",
                        "app_process",
                    ],
                    capture_output=ADB_CAPTURE_OUTPUT,
                    timeout=SCRCPY_TERMINATE_TIMEOUT,
                )
                if result.returncode == 0:
                    logger.debug("app_process killed successfully")
                else:
                    logger.debug(f"pkill app_process returned {result.returncode} (may not have been running)")
            except subprocess.TimeoutExpired:
                logger.warning("Timeout killing app_process")
            except Exception as AppProcessKillError:
                logger.warning(f"Error killing app_process: {AppProcessKillError}")

            # Remove port forwards
            try:
                logger.debug("Removing ADB port forwards")
                subprocess.run(
                    [self.adb_bin, "-s", self.serial, "forward", "--remove-all"],
                    capture_output=ADB_CAPTURE_OUTPUT,
                    timeout=SCRCPY_TERMINATE_TIMEOUT,
                )
                logger.debug("Port forwards removed")
            except Exception as PortForwardsKillError:
                logger.warning(f"Error removing port forwards: {PortForwardsKillError}")

            # Remove all reverse forwards
            try:
                logger.debug("Removing ADB reverse forwards")
                subprocess.run(
                    [self.adb_bin, "-s", self.serial, "reverse", "--remove-all"],
                    capture_output=ADB_CAPTURE_OUTPUT,
                    timeout=SCRCPY_TERMINATE_TIMEOUT,
                )
                logger.debug("Reverse forwards removed")
            except Exception as ReverseForwardsKillError:
                logger.warning(f"Error removing reverse forwards: {ReverseForwardsKillError}")

            logger.info("Device-side cleanup complete")
        else:
            if not self.serial:
                logger.debug("Skipping device cleanup: no serial")
            if not self.adb_bin:
                logger.debug("Skipping device cleanup: no ADB binary")

        logger.info("ScrcpyManager stopped successfully")
        logger.info("=" * LOG_MULT)