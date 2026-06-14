# ESP32-S3 CSI Node

Single firmware for two ESP32-S3 boards. Each board can work as:

- `rx`: receive ESP-NOW packets, collect CSI, print `CSI_DATA` CSV over serial.
- `tx`: continuously send ESP-NOW packets at a configured frequency.

The mode is changed through the serial monitor and saved in NVS.

## Serial commands

Type commands in the ESP-IDF monitor and press Enter:

```text
help
status
mode tx
mode rx
freq 50
channel 11
output csv
output bin
reboot
```

Changing `mode`, `freq`, or `channel` saves the value and restarts the board.
Changing `output` switches RX serial output between readable CSV and high-throughput binary records.

## Build and flash in VSCode

1. Open `F:\1\csi\esp32s3_csi_node` in VSCode.
2. Install or open the Espressif IDF extension.
3. Run `ESP-IDF: Configure ESP-IDF Extension` if this PC has not been configured yet.
4. Set target to `esp32s3`.
5. Select port `COM14`.
6. Build, flash, and monitor from the ESP-IDF bottom toolbar.

Equivalent ESP-IDF terminal commands:

```powershell
idf.py set-target esp32s3
idf.py -p COM14 -b 921600 flash monitor
```

After flashing both boards:

1. Connect board A and run `mode tx`.
2. Connect board B and run `mode rx`.
3. For quick live plots, keep RX in CSV mode:

```powershell
cd F:\1\csi
python tools\csi_capture.py --port COM14 --baud 921600 --out data\raw\test_rx.csv --label test --duration 60
```

4. For real dataset capture, switch RX to binary mode and use the binary logger:

```text
output bin
```

```powershell
cd F:\1\csi
python tools\csi_binary_capture.py --port COM14 --baud 921600 --out data\raw\test_rx.csibin --label test --duration 60
python tools\csi_binary_inspect.py data\raw\test_rx.csibin
```

## Defaults

- Default mode: `rx`
- Default channel: `11`
- Default TX frequency: `50 Hz`
- ESP-IDF monitor baud: `921600` on USB Serial/JTAG. Flash baud is `921600`.
- Wi-Fi bandwidth: `HT40`

Keep both boards on the same channel. Put TX and RX at least 1 meter apart for first tests.
