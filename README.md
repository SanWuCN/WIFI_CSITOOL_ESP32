# SwCSI

SwCSI is a Windows workbench for ESP32-S3 Wi-Fi CSI capture, visualization, and dataset preparation.

This project is built for a two-node ESP32-S3 CSI setup: one node transmits packets continuously, and the other node receives packets, captures CSI, and streams data to a Windows PC through a serial port.

## Features

- Serial control for ESP32-S3 CSI nodes.
- TX/RX/standby mode switching.
- Binary CSI capture for stable dataset collection.
- Real-time CSI amplitude heatmap, RSSI trend, I/Q scatter, timing/loss diagnostics, and Doppler/STFT view.
- Metadata-aware capture workflow for experiments.
- Project save/load files (`.swcsi`).
- Chinese/English UI setting.
- Windows installer and portable package.

## Hardware

- ESP32-S3-N16R8 development boards.
- Two-node link: one TX node and one RX node.
- RX node connected to the Windows PC through USB serial.

## Quick Start

1. Flash the ESP32-S3 firmware in `esp32s3_csi_node`.
2. Set one board to TX mode and one board to RX mode.
3. Use the same Wi-Fi channel on both boards.
4. Start SwCSI on Windows.
5. Select the RX serial port, set baud rate to `921600`, and connect.
6. Use `BIN` mode for formal data collection.

Recommended serial commands:

```text
mode rx
output bin
channel 11
```

On the TX board:

```text
mode tx
channel 11
freq 50
```

## Windows Build

```powershell
cd F:\1\csi
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\build_workbench_installer.ps1
```

Windows build artifacts:

- `dist_installer\SwCSI_V1.0.2_Setup.exe`
- `dist_installer\SwCSI_V1.0.2_Portable.zip`

## macOS Build

Run on macOS:

```bash
cd /path/to/WIFI_CSITOOL_ESP32
bash scripts/build_macos_app.sh
```

macOS build artifacts:

- `dist/SwCSI.app`
- `dist_installer/SwCSI_V1.0.2_macOS.dmg`
- `dist_installer/SwCSI_V1.0.2_macOS.img`

The repository also includes a GitHub Actions workflow: `.github/workflows/build-macos.yml`.

## Contact

Maintainer contact: 1292053575@qq.com

## License

MIT License.
