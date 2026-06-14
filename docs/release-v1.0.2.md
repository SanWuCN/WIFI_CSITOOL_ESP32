# SwCSI V1.0.2

SwCSI V1.0.2 adds macOS packaging support while keeping the Windows workbench workflow unchanged.

## Highlights

- Added macOS app bundle build support.
- Added macOS disk image outputs:
  - `SwCSI_V1.0.2_macOS.dmg`
- Removed the redundant `.img` package; macOS distribution now uses `.dmg`.
- Added GitHub Actions workflow for macOS builds.
- Runtime settings now use user application data directories.
- Folder opening is now cross-platform.

## Build on macOS

```bash
cd /path/to/WIFI_CSITOOL_ESP32
bash scripts/build_macos_app.sh
```

Output:

```text
dist/SwCSI.app
dist_installer/SwCSI_V1.0.2_macOS.dmg
```

## Contact

1292053575@qq.com
