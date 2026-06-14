# Widar3.0 Notes For ESP32-S3 CSI

This note summarizes what can and cannot be reused from the downloaded Widar3.0 release in `G:\Widar3.0ReleaseData`.

## Local Files Checked

- `G:\Widar3.0ReleaseData\BVPExtractionCode\Widar3.0Release-Matlab\generate_vs.m`
- `G:\Widar3.0ReleaseData\BVPExtractionCode\Widar3.0Release-Matlab\get_doppler_spectrum.m`
- `G:\Widar3.0ReleaseData\BVPExtractionCode\Widar3.0Release-Matlab\Doppler2VelocityMapping\DVM_main.m`
- `G:\Widar3.0ReleaseData\BVPExtractionCode\Widar3.0Release-Matlab\csi_tool_box\read_bf_file.m`
- `G:\Widar3.0ReleaseData\BVPExtractionCode\Widar3.0Release-Matlab\csi_tool_box\csi_get_all.m`

## Widar3.0 Data Flow

Widar3.0 uses Intel 5300 `.dat` files:

1. `read_bf_file.m` reads binary beamforming-feedback records.
2. `read_bfee` decodes one Intel 5300 CSI record.
3. `get_scaled_csi` applies Intel 5300 scaling.
4. `csi_get_all.m` returns a complex CFR matrix with shape `[packet, 90]`, representing `30 subcarriers * 3 RX antennas`.
5. `get_doppler_spectrum.m` builds Doppler spectra using conjugate multiplication, filtering, PCA, and STFT/CWT.
6. `DVM_main.m` maps Doppler spectra from multiple receivers into body velocity profiles.

## What Transfers To ESP32-S3

- Binary capture first, offline processing later.
- Convert raw CSI into a clean complex matrix `[packet, subcarrier_or_stream]`.
- Drop/repair malformed packets before feature extraction.
- Use conjugate multiplication or reference-subcarrier/reference-link cancellation to suppress static paths.
- Use band-pass filtering and STFT/CWT for motion features.
- Keep metadata about TX/RX position, subject, action, orientation, and repetition.

## What Does Not Transfer Directly

- Intel 5300 scaling functions such as `get_scaled_csi` are hardware-specific.
- Widar3.0 assumes 30 Intel subcarriers and 3 antennas per receiver.
- The released BVP pipeline assumes multiple receivers, commonly `rx_cnt=6`.
- DVM needs known geometry: `Tx_pos`, `Rx_pos`, human position/orientation, and wavelength.
- One ESP32-S3 TX plus one ESP32-S3 RX is a single-link system, so full Widar3.0 position-independent BVP is not directly observable.

## Current ESP32-S3 Format

The current ESP32-S3 CSV format provides one CSI vector per received ESP-NOW packet:

- `tx_seq`: packet sequence from TX.
- `tx_payload_found`: should be `1` for valid new firmware.
- `rx_timestamp_us`: RX-side local timestamp.
- `len`: raw CSI byte count, currently often `384`.
- `data`: int8 raw CSI as `[imag0, real0, imag1, real1, ...]`.

After dropping zero/null subcarriers, current HT40 captures usually contain about `166` valid complex points.

For dataset capture, prefer `.csibin` from `tools\csi_binary_capture.py` over CSV/GUI.

## Recommended Near-Term Pipeline

1. Capture binary CSI with `output bin`.
2. Run `tools\csi_binary_inspect.py` or `tools\csi_quality_report.py`.
3. Convert records to a complex matrix `[packet, 166]`.
4. Resample to a stable rate based on `tx_seq` or `rx_timestamp_us`.
5. Remove static components by subtracting a running mean or using conjugate multiplication against a stable reference subcarrier group.
6. Extract time-frequency features with STFT/CWT for single-link tasks.
7. Start with robust tasks: static empty/person present, simple gestures, posture classes with fixed location.
8. Add more ESP32-S3 RX nodes before attempting Widar-like position-independent localization.
