from __future__ import annotations

import ast
import csv
from dataclasses import dataclass
from io import StringIO
from typing import Iterable

import numpy as np


ESP32_COLUMNS = [
    "type",
    "id",
    "mac",
    "rssi",
    "rate",
    "sig_mode",
    "mcs",
    "bandwidth",
    "smoothing",
    "not_sounding",
    "aggregation",
    "stbc",
    "fec_coding",
    "sgi",
    "noise_floor",
    "ampdu_cnt",
    "channel",
    "secondary_channel",
    "local_timestamp",
    "ant",
    "sig_len",
    "rx_state",
    "len",
    "first_word",
    "data",
]

ESP32_TIMED_COLUMNS = [
    "type",
    "id",
    "mac",
    "rssi",
    "rate",
    "sig_mode",
    "mcs",
    "bandwidth",
    "smoothing",
    "not_sounding",
    "aggregation",
    "stbc",
    "fec_coding",
    "sgi",
    "noise_floor",
    "ampdu_cnt",
    "channel",
    "secondary_channel",
    "local_timestamp",
    "ant",
    "sig_len",
    "rx_state",
    "tx_seq",
    "tx_timestamp_us",
    "rx_timestamp_us",
    "tx_payload_found",
    "tx_payload_offset",
    "tx_payload_len",
    "len",
    "first_word",
    "data",
]

ESP32_TIMED_V1_COLUMNS = [
    "type",
    "id",
    "mac",
    "rssi",
    "rate",
    "sig_mode",
    "mcs",
    "bandwidth",
    "smoothing",
    "not_sounding",
    "aggregation",
    "stbc",
    "fec_coding",
    "sgi",
    "noise_floor",
    "ampdu_cnt",
    "channel",
    "secondary_channel",
    "local_timestamp",
    "ant",
    "sig_len",
    "rx_state",
    "tx_seq",
    "tx_timestamp_us",
    "rx_timestamp_us",
    "tx_payload_len",
    "len",
    "first_word",
    "data",
]

ESP32_TIMED_DELTA_COLUMNS = [
    "type",
    "id",
    "mac",
    "rssi",
    "rate",
    "sig_mode",
    "mcs",
    "bandwidth",
    "smoothing",
    "not_sounding",
    "aggregation",
    "stbc",
    "fec_coding",
    "sgi",
    "noise_floor",
    "ampdu_cnt",
    "channel",
    "secondary_channel",
    "local_timestamp",
    "ant",
    "sig_len",
    "rx_state",
    "tx_seq",
    "tx_timestamp_us",
    "rx_timestamp_us",
    "time_delta_us",
    "len",
    "first_word",
    "data",
]

C5_C6_COLUMNS = [
    "type",
    "id",
    "mac",
    "rssi",
    "rate",
    "noise_floor",
    "fft_gain",
    "agc_gain",
    "channel",
    "local_timestamp",
    "sig_len",
    "rx_state",
    "len",
    "first_word",
    "data",
]


@dataclass(frozen=True)
class CsiFrame:
    columns: list[str]
    values: list[str]
    raw: list[int]

    @property
    def complex_csi(self) -> np.ndarray:
        return raw_to_complex(self.raw)


def decode_serial_line(line: bytes | str) -> str:
    if isinstance(line, bytes):
        return line.decode("utf-8", errors="ignore").strip()
    return line.strip()


def parse_csi_line(line: bytes | str) -> CsiFrame | None:
    text = decode_serial_line(line)
    index = text.find("CSI_DATA")
    if index < 0:
        return None

    text = text[index:]
    values = next(csv.reader(StringIO(text)))
    if len(values) == len(ESP32_TIMED_COLUMNS):
        columns = ESP32_TIMED_COLUMNS
    elif len(values) == len(ESP32_TIMED_V1_COLUMNS):
        try:
            payload_len_or_delta = int(values[-4])
        except ValueError:
            payload_len_or_delta = -1
        columns = ESP32_TIMED_V1_COLUMNS if 0 <= payload_len_or_delta <= 250 else ESP32_TIMED_DELTA_COLUMNS
    elif len(values) == len(ESP32_TIMED_DELTA_COLUMNS):
        columns = ESP32_TIMED_DELTA_COLUMNS
    elif len(values) == len(ESP32_COLUMNS):
        columns = ESP32_COLUMNS
    elif len(values) == len(C5_C6_COLUMNS):
        columns = C5_C6_COLUMNS
    else:
        raise ValueError(f"Unexpected CSI column count: {len(values)}")

    raw = ast.literal_eval(values[-1])
    expected_len = int(values[-3])
    if expected_len != len(raw):
        raise ValueError(f"CSI length mismatch: header={expected_len}, raw={len(raw)}")
    raw = [int(x) for x in raw]
    frame = CsiFrame(columns=columns, values=values, raw=raw)
    validate_frame(frame)
    return frame


def frame_value(frame: CsiFrame, name: str) -> str | None:
    try:
        return frame.values[frame.columns.index(name)]
    except ValueError:
        return None


def frame_int(frame: CsiFrame, name: str) -> int:
    value = frame_value(frame, name)
    if value is None:
        raise ValueError(f"Missing CSI field: {name}")
    return int(value)


def validate_frame(frame: CsiFrame) -> None:
    if frame.values[0] != "CSI_DATA":
        raise ValueError(f"Unexpected CSI record type: {frame.values[0]}")

    length = frame_int(frame, "len")
    if not 0 < length <= 1024:
        raise ValueError(f"Invalid CSI length: {length}")
    if length != len(frame.raw):
        raise ValueError(f"CSI length mismatch: header={length}, raw={len(frame.raw)}")
    if any(x < -128 or x > 127 for x in frame.raw):
        raise ValueError("CSI raw data contains non-int8 values")

    rssi = frame_int(frame, "rssi")
    if not -128 <= rssi <= 20:
        raise ValueError(f"Invalid RSSI: {rssi}")
    channel = frame_int(frame, "channel")
    if not 1 <= channel <= 14:
        raise ValueError(f"Invalid Wi-Fi channel: {channel}")
    bandwidth = frame_int(frame, "bandwidth")
    if bandwidth not in (0, 1):
        raise ValueError(f"Invalid bandwidth flag: {bandwidth}")
    first_word = frame_int(frame, "first_word")
    if first_word not in (0, 1):
        raise ValueError(f"Invalid first_word flag: {first_word}")

    sig_len = frame_int(frame, "sig_len")
    if not 0 <= sig_len <= 4096:
        raise ValueError(f"Invalid sig_len: {sig_len}")

    if "tx_payload_len" in frame.columns:
        payload_len = frame_int(frame, "tx_payload_len")
        if not 0 <= payload_len <= 512:
            raise ValueError(f"Invalid tx_payload_len: {payload_len}")

    if "tx_payload_found" in frame.columns:
        found = frame_int(frame, "tx_payload_found")
        offset = frame_int(frame, "tx_payload_offset")
        payload_len = frame_int(frame, "tx_payload_len")
        if found not in (0, 1):
            raise ValueError(f"Invalid tx_payload_found: {found}")
        if found and not (0 <= offset + 12 <= payload_len):
            raise ValueError(f"Invalid tx_payload_offset={offset} for payload_len={payload_len}")
        if not found and offset != 65535:
            raise ValueError(f"Invalid missing-payload offset: {offset}")


def raw_to_complex(raw: Iterable[int]) -> np.ndarray:
    data = np.asarray(list(raw), dtype=np.float32)
    if data.size % 2:
        data = data[:-1]
    imag = data[0::2]
    real = data[1::2]
    return real + 1j * imag


def amplitude(raw: Iterable[int]) -> np.ndarray:
    return np.abs(raw_to_complex(raw))


def valid_complex_csi(raw: Iterable[int]) -> np.ndarray:
    csi = raw_to_complex(raw)
    return csi[np.abs(csi) > 0]


def valid_amplitude(raw: Iterable[int]) -> np.ndarray:
    return np.abs(valid_complex_csi(raw))


def phase(raw: Iterable[int]) -> np.ndarray:
    return np.angle(raw_to_complex(raw))
