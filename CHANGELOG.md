# Changelog

## 0.4.0 - [Addtimestamp]
### Added
- Update bundled scrcpy version to scrcpy 4.0
### Bugfixes
- Improved launch codec and paramaters (@tommywaaf)
- Improved bundled binary location (@tommywaaf)
- More resistant adb server retry logic (@tommywaaf)
- Improved video codec options (@tommywaaf)
- Improve scrcpy window launch commands (@tommywaaf)
- Only redraw screens when changes occur (@tommywaaf)
- Only calls for windows to be docked when necessary (@tommywaaf) 
- Allow users to resize and move undocked windows (@tommywaaf) with correct rendering sizing and scale (@theswest)
- Build bundled as onedir rather than onefile to improve launch speed in subsequent runs
- Increase process priority


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
