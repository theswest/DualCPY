# Changelog

## 0.4.0 - 01-06-2026

> Note: **ThorCPY is now known as DualCPY.**

### Added
- Rebranded the project from ThorCPY to DualCPY, including a brand-new logo
- Complete UI port to customtkinter and redesign with a nicer design language in-mind
- Multi-device support:
  - Automatic device detection over ADB
  - Built-in device profiles for:
    - AYN Thor (Tested),
    - RG DS (Tested),
    - Pocket DS (Tested),
    - Odin 3 + RDS (Tested),
    - Odin 2 + RDS,
    - Odin 2 Portal + RDS,
    - Odin 2 Mini + RDS,
    - Retroid Pocket 6 + RDS,
    - Retroid Pocket G2 + RDS,
    - Retroid Pocket 5 + RDS,
    - Retroid Pocket 4 Pro + RDS
  - Custom user-defined device profiles
  - Device selector on launch with smart selection of the detected device
  - "Last used profile" is remembered in the config and auto-booted per-device
- Profile editor:
  - Ability to add custom profiles with different screen sizes
  - Support for devices with internal monitors on top/bottom
  - Per-profile custom scrcpy launch commands
- Per-device screen ratios are now calculated on boot to allow for any screen ratio
- Gamepad passthrough to the device (`--gamepad=uhid` on the top screen; disabled on the bottom)
  - You may have to reconnect your controller whilst DualCPY is running, this is due to a limitation with android
- FPS selector in the control panel (@tommywaaf)
- Restart button in the control panel (@tommywaaf)
- Added File Transfer window (@DrSkyfaR and @theswest):
  - Ability to transfer files from Windows -> DualCPY and vice versa via adb
  - Delete, rename, and create folders on the device
  - Windows quick-nav shortcuts: Home, Desktop, Downloads, Documents, Pictures
  - Device quick-nav shortcuts: Internal, Download, DCIM, Pictures, Music, Documents
  - Automatic SD card detection with quick-nav pills
  - Inline image previews with file metadata
- Redesigned splash screen with the new DualCPY logo
- App icon is now used as the window favicon across every window
- Additional default scrcpy launch flags: `--no-mipmaps`, `--no-power-on`, `--no-cleanup`
- Configurable screen-launch delay to support lower-powered devices
- Updated the bundled scrcpy version to scrcpy v4.0

### Changed
- Replaced the old Pygame menu with a fully reworked CustomTkinter control panel
- Backend improvements to heavily increase performance and decrease latency
- Undocked windows now have title bars, allowing resizing, reshaping and easier movement (@tommywaaf)
- Rebuilt the wireless connection dialog in CustomTkinter (previously tkinter)
- Added dedicated icon assets for the file browser
- Docked window title now reads "DualCPY | {device name}"
- Undocked window titles now read "{device name} - Top/Bottom Screen - DualCPY"
- Build is now bundled as onedir instead of onefile, improving launch speed on subsequent runs (@tommywaaf)
- Increased process priority for smoother mirroring (@tommywaaf)
- Major backend rework for clarity and conciseness:
  - Moved shared UI constants into their own module to prevent circular imports
  - Removed Thor-specific hardcoded constants from scrcpy_manager to allow for profiles
  - Relocated launch behaviour to be more accessible
- Improved launch codec and parameters (@tommywaaf)
- Improved video codec options (@tommywaaf)
- Improved scrcpy window launch commands (@tommywaaf)
- Improved bundled binary location handling (@tommywaaf)
- More resistant ADB server retry logic (@tommywaaf)
- Screens now only redraw when changes occur (@tommywaaf)
- Windows are now only re-docked when necessary (@tommywaaf)

### Bugfixes
- Fixed many display and rendering issues
- Fixed screenshots not working on built executables
- Undocked windows can now be resized and moved via their title bars (@tommywaaf)
- Fixed title-bar rendering scale when undocking, so windows no longer show borders after undocking (@tommywaaf)
- Fixed rendering size and scale for undocked windows

### Known Issues
- Restarting doesn't work when running from source 


## 0.3.0 - 15-02-2026
### Added
- Added Wireless Support
### Bugfixes
- Fixed issue where bottom screen displays incorrectly, causing non-transparency with screenshots
- Improved window handling to improve stability

## 0.2.0 - 31-01-2026
### Added
- Added ability to change Scrcpy Scale
- Better logging and error handling
### Bugfixes
- Fixed issue with Control Panel crashing on Windows 10 and improved Windows 10 Compatibility
- Updated codebase to become more refined
- Improved window management safeguards for Windows 10


## 0.1.1 - 28-01-2026
### Added
- Added incompatibility warning for Windows 10
- Add thread safety to window focus handling
- Improved dark mode support
### Bugfixes
- Fixed spacing on "DOCK WINDOWS" text 
- Debounce and throttle sync() calls


## 0.1.0 - 26-01-2026
### Added
- Dual-screen scrcpy docking
- Layout presets
- Screenshot capture
- Logging system
- PyInstaller build support
