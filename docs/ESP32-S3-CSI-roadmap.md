# ESP32-S3 WiFi CSI sensing roadmap

This project targets a two-node ESP32-S3 CSI setup:

- TX node: sends fixed-rate ESP-NOW packets.
- RX node: receives packets, extracts CSI, and streams `CSI_DATA` over USB serial to a Windows PC.
- PC side: records raw CSI CSV, appends PC timestamps, visualizes amplitude/phase, and later builds datasets for localization, posture/action recognition, and coarse people-count sensing.

## Recommended firmware base

Use Espressif `esp-csi` first:

- `examples/get-started/csi_send` for the sender.
- `examples/get-started/csi_recv` for the receiver.
- Target should be `esp32s3`.
- Start with channel 11, HT40, 100 Hz send frequency, and `921600` baud.

The StevenMHernandez `ESP32-CSI-Tool` project is still useful as a reference for active AP/STA collection, serial CSV workflows, and Python utilities. For ESP32-S3, Espressif `esp-csi` is the safer base because it explicitly supports the ESP32-S3 series and has newer CSI field handling.

## Flashing flow

Install ESP-IDF first, then clone `esp-csi` outside or inside this folder.

Sender:

```powershell
cd path\to\esp-csi\examples\get-started\csi_send
idf.py set-target esp32s3
idf.py -p COM_TX -b 921600 flash monitor
```

Receiver:

```powershell
cd path\to\esp-csi\examples\get-started\csi_recv
idf.py set-target esp32s3
idf.py -p COM_RX -b 921600 flash
```

Then close `idf.py monitor` on the receiver and let the Python collector open the receiver COM port directly.

## PC collection

Install Python dependencies:

```powershell
python -m pip install -r requirements.txt
```

Record raw CSI:

```powershell
python tools\csi_capture.py --port COM_RX --out data\raw\empty_room_001.csv --label empty_room
python tools\csi_capture.py --port COM_RX --out data\raw\person_zone1_stand_001.csv --label person_zone1_stand --duration 60
```

Plot a saved capture:

```powershell
python tools\csi_plot_csv.py data\raw\person_zone1_stand_001.csv --subcarrier 20
```

## First experiments

Keep the first experiments deliberately small:

1. Empty room baseline: 3 sessions, 60 seconds each.
2. Presence detection: empty vs one standing person, 5 sessions each.
3. Coarse zone localization: 4 to 9 fixed grid points, one person standing still for 30 to 60 seconds per point.
4. Posture/action recognition: standing, sitting, lying, walking, arm wave. Use fixed RX/TX placement at first.
5. Coarse people count: 0, 1, 2 people only. Treat 3+ people as later work unless extra receivers are added.

## Data naming

Use names that encode the experiment:

```text
{room}_{txrx_layout}_{subject}_{label}_{trial}.csv
lab_lineofsight_s01_stand_zone1_001.csv
lab_lineofsight_s01_walk_001.csv
lab_lineofsight_empty_empty_001.csv
```

Minimum metadata to write down beside each session:

- TX/RX distance and height.
- Antenna orientation.
- Channel and bandwidth.
- Send frequency.
- Room layout and obstacles.
- Subject count and position/action.

## Modeling path

Stage 1 should use robust CSI features instead of jumping straight to large models:

- Parse interleaved CSI as complex values: imaginary, real, imaginary, real.
- Convert to amplitude and phase.
- Prefer amplitude for the first model; phase needs calibration and unwrapping.
- Remove invalid subcarriers and obvious outliers.
- Window into 2 to 5 second clips with 50 percent overlap.
- Start with simple baselines: logistic regression, random forest, SVM, or small CNN/LSTM.

For your current `人体行为识别` LSTM code:

- Keep `Network.py` as a possible sequence model.
- Replace hard-coded `F:\WiAR-master\...` paths with project-relative paths before training.
- Remove artificial accuracy offsets in `Training1.py` before using results.
- Adapt `DataProcessing.py` to read collected CSV files rather than WiAR `.npy` files.

## Practical limits with two single-antenna ESP32-S3 boards

This hardware is good for presence, activity recognition, posture/action classification, and coarse zone localization. Fine indoor trajectory tracking, robust multi-person separation, and high-accuracy people counting are harder because many papers rely on antenna arrays, AoA, multiple receivers, or multiple spatial links.

To improve later:

- Add a second receiver at another angle.
- Add more TX/RX links around the room boundary.
- Keep all devices fixed during dataset collection.
- Use external IPEX antennas and consistent orientation.
