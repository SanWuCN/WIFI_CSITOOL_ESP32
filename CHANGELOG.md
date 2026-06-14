# Changelog

## SwCSI V1.0.2 - 2026-06-14

- Added macOS application packaging support.
- Added macOS `.dmg` and `.img` build script.
- Added GitHub Actions workflow for macOS builds.
- Moved runtime settings and default data output to user application data directories for better packaged-app behavior.
- Added cross-platform folder opening behavior.

## SwCSI V1.0.1 - 2026-06-14

- Renamed the Windows workbench to SwCSI.
- Added SwCSI application icon.
- Added top application menu with File, Edit, View, and Help entries.
- Added Settings panel with UI language selection and maintainer contact.
- Added project save/load support using `.swcsi` project files.
- Added Doppler/STFT visualization for motion-aware CSI inspection.
- Updated installer and portable package names for SwCSI.

## Previous internal builds

- ESP32-S3 CSI binary capture and parser.
- Real-time CSI workbench with heatmap, RSSI, I/Q, timing/loss diagnostics.
- ESP32-S3 TX/RX/standby serial command firmware.
