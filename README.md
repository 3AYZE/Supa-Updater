# SupaUpdater

SupaUpdater is a free Windows application and driver updater. It uses WinGet for application updates and Windows Update Agent for optional driver updates. No account, subscription, paid API, or telemetry is required.

## Download

Download the latest release at https://github.com/3AYZE/Supa-Updater/releases/latest.

- **Windows executable:** Download `SupaUpdater.exe` when available. No Python installation is required. The executable uses a single window without a console.
- **Source edition:** Download `SupaUpdater-v1.3.0-source.zip`, extract the `SupaUpdater` folder, and double-click `app.pyw` with Python 3.10+ installed.

Windows 10/11 and WinGet (Microsoft App Installer) are required for software updates. Driver scanning and installation require the Windows Update service and sufficient system permissions.

## Features

- Installed application inventory from the Windows registry.
- WinGet upgrade discovery, search, filters, individual selection, and Update all.
- Sequential update queue with confirmation, stop-after-current, elapsed time, completion-based progress, and persistent results.
- Installed driver inventory for Bluetooth, network, graphics, audio and chipset devices.
- Optional driver discovery and explicitly approved installation through Windows Update Agent; firmware and BIOS installation are excluded.
- Local activity history and diagnostics in `%LOCALAPPDATA%\SupaUpdater`.
- System, Light and Dark themes. The System option follows the Windows app theme.
- Source-edition updates from this repository's GitHub Releases, requiring user confirmation and a verified release-asset SHA-256 digest.

## Limitations and safety

- Windows-specific UI and hardware installations should be validated on your computer before broad updates.
- WinGet's displayed table is locale-sensitive; ambiguous or unrecognized rows are excluded rather than guessed.
- Installation progress is per completed application or driver; exact progress of third-party installers may not be available.
- WinGet reporting no further updates does not independently prove the exact installed version.
- The portable `.exe` currently checks for new releases and opens the download page; in-place self-update is supported by the Python source edition only.
- GitHub asset checksums verify download integrity against repository metadata, not independent publisher identity. Updates are not unattended.
- Save your work and review selected drivers; Bluetooth, network and graphics drivers may briefly disconnect devices, and restart may be required.

## Development

The release is built and tested using `.github/workflows/release.yml` on Windows. Source tests are in `tests/`.

```powershell
py -m unittest discover -s tests -v
```

The UI uses the Python standard library (Tkinter). PyInstaller is used only when generating the optional Windows executable.