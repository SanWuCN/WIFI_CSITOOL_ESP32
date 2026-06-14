# SwCSI V1.0.1

SwCSI is a Windows workbench for ESP32-S3 Wi-Fi CSI capture, visualization, and dataset preparation.

## Highlights

- New application name: SwCSI.
- New application icon.
- Professionalized desktop UI text and top menu.
- File menu now supports saving and loading `.swcsi` project files.
- Settings panel supports UI language switching.
- Maintainer contact is included in the application: 1292053575@qq.com.
- Added Doppler/STFT visualization for motion inspection.
- Windows installer and portable package are provided.

## Files

- `SwCSI_V1.0.1_Setup.exe`: Windows installer.
- `SwCSI_V1.0.1_Portable.zip`: portable build.

## Recommended Runtime

- Windows 10/11.
- RX serial baud rate: `921600`.
- Recommended CSI output: `output bin`.
- Recommended TX rate for stable initial tests: `freq 50`.

## Basic Commands

RX node:

```text
mode rx
output bin
channel 11
```

TX node:

```text
mode tx
channel 11
freq 50
```

## Contact

1292053575@qq.com
