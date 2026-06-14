# ESP32-S3 CSI OTA And Station Management Plan

## Feasibility

ESP32-S3 can support OTA updates with ESP-IDF OTA partitions. The project now has:

- `partitions.csv` with `ota_0` and `ota_1`.
- `otadata` partition.
- `CONFIG_BOOTLOADER_APP_ROLLBACK_ENABLE=y` in `sdkconfig.defaults`.
- `mode standby` in firmware.
- A local HTML station server in `tools/csi_station_server.py`.

## Current Station Server

Start it on Windows:

```powershell
cd F:\1\csi
py -3.9 tools\csi_station_server.py --host 127.0.0.1 --port 8088
```

Open:

```text
http://127.0.0.1:8088
```

Current features:

- Bind a device address such as `rx-001` to a serial port such as `COM15`.
- Send serial commands:
  - `status`
  - `mode standby`
  - `mode rx`
  - `mode tx`
  - `output bin`
  - `output csv`
  - custom commands such as `freq 50` and `channel 11`
- Upload `.bin` firmware.
- Store firmware under `data/station/firmware`.
- Compute and display `CRC32` and `SHA256`.
- Serve uploaded firmware files from `/firmware/<filename>`.

This is a base-station scaffold. It controls current devices over serial. Wireless OTA requires the firmware-side management network task described below.

## Firmware-Side OTA Target Design

Add a management mode/task that runs only when CSI is paused:

1. Device enters `mode standby`.
2. Device connects to a management Wi-Fi network, or opens a temporary AP.
3. Device exposes HTTP endpoints:
   - `GET /api/status`
   - `POST /api/config`
   - `POST /api/reboot`
   - `POST /api/ota`
4. Station server uploads firmware and asks the device to download:

```json
{
  "url": "http://<station-ip>:8088/firmware/<firmware.bin>",
  "crc32": "1234abcd",
  "sha256": "...",
  "size": 745000
}
```

5. Device validates metadata, downloads firmware into the inactive OTA partition, reboots.
6. New app calls `esp_ota_mark_app_valid_cancel_rollback()` only after Wi-Fi/config/self-test passes.
7. If the new app fails to boot or does not mark itself valid, bootloader rolls back to the previous partition.

## Why Standby Is Needed

CSI collection fixes channel, bandwidth, ESP-NOW traffic, and serial/binary output. OTA needs a stable IP network and flash writes. Running both at once can break packet timing or corrupt experiments. Use:

```text
mode standby
```

before OTA, and return to:

```text
mode rx
output bin
```

after a successful update.

## Device Addressing

The station server already treats every ESP32 as a device with:

- `id`: human-readable address, for example `rx-001`.
- `transport`: `serial` now, `http` later.
- `endpoint`: `COM15` now, `http://device-ip` later.

Firmware should later add persistent fields:

- `device_id`
- `device_role`
- `mgmt_ssid`
- `mgmt_password`
- optional `ota_token`

These belong in NVS and should appear in `status`.

## Security Notes

For lab-only use, HTTP OTA is acceptable on an isolated LAN. For real deployment:

- Use HTTPS OTA.
- Sign firmware images.
- Add an OTA token or mutual authentication.
- Keep the rollback path enabled.
