from __future__ import annotations

import struct
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Iterator

import numpy as np


MAGIC = 0x49435345
MAGIC_BYTES = struct.pack("<I", MAGIC)
HEADER_FORMAT = "<IHHHHIIIIIbbBBBBBbBBBBBBBBBBHHHH"
HEADER_SIZE = struct.calcsize(HEADER_FORMAT)
HEADER_FIELDS = [
    "magic",
    "version",
    "header_len",
    "csi_len",
    "payload_len",
    "record_seq",
    "local_timestamp_us",
    "rx_timestamp_us",
    "tx_seq",
    "tx_timestamp_us",
    "rssi",
    "noise_floor",
    "rate",
    "sig_mode",
    "mcs",
    "bandwidth",
    "channel",
    "secondary_channel",
    "smoothing",
    "not_sounding",
    "aggregation",
    "stbc",
    "fec_coding",
    "sgi",
    "ant",
    "first_word_invalid",
    "rx_state",
    "tx_payload_found",
    "tx_payload_offset",
    "sig_len",
    "ampdu_cnt",
    "reserved",
]


@dataclass(frozen=True)
class BinaryCsiRecord:
    header: dict[str, int]
    raw: bytes

    @property
    def raw_i8(self) -> np.ndarray:
        return np.frombuffer(self.raw, dtype=np.int8)

    @property
    def complex_csi(self) -> np.ndarray:
        data = self.raw_i8.astype(np.float32)
        if data.size % 2:
            data = data[:-1]
        imag = data[0::2]
        real = data[1::2]
        csi = real + 1j * imag
        return csi[np.abs(csi) > 0]


def parse_header(data: bytes) -> dict[str, int]:
    if len(data) != HEADER_SIZE:
        raise ValueError(f"Header must be {HEADER_SIZE} bytes, got {len(data)}.")
    values = struct.unpack(HEADER_FORMAT, data)
    header = dict(zip(HEADER_FIELDS, values))
    if header["magic"] != MAGIC:
        raise ValueError(f"Bad magic 0x{header['magic']:08x}.")
    if header["header_len"] != HEADER_SIZE:
        raise ValueError(f"Unsupported header_len={header['header_len']}, expected {HEADER_SIZE}.")
    validate_header(header)
    return header


def validate_header(header: dict[str, int]) -> None:
    if header["version"] != 1:
        raise ValueError(f"Unsupported binary CSI version: {header['version']}.")
    if not 0 < header["csi_len"] <= 1024:
        raise ValueError(f"Invalid csi_len: {header['csi_len']}.")
    if not 0 <= header["payload_len"] <= 512:
        raise ValueError(f"Invalid payload_len: {header['payload_len']}.")
    if not -128 <= header["rssi"] <= 0:
        raise ValueError(f"Invalid rssi: {header['rssi']}.")
    if not -128 <= header["noise_floor"] <= 0:
        raise ValueError(f"Invalid noise_floor: {header['noise_floor']}.")
    if not 1 <= header["channel"] <= 14:
        raise ValueError(f"Invalid channel: {header['channel']}.")
    if header["sig_mode"] not in (0, 1):
        raise ValueError(f"Invalid sig_mode: {header['sig_mode']}.")
    if not 0 <= header["mcs"] <= 7:
        raise ValueError(f"Invalid mcs: {header['mcs']}.")
    if header["bandwidth"] not in (0, 1):
        raise ValueError(f"Invalid bandwidth: {header['bandwidth']}.")
    if header["first_word_invalid"] not in (0, 1):
        raise ValueError(f"Invalid first_word_invalid: {header['first_word_invalid']}.")
    if header["tx_payload_found"] not in (0, 1):
        raise ValueError(f"Invalid tx_payload_found: {header['tx_payload_found']}.")
    if header["tx_payload_found"]:
        if not 0 <= header["tx_payload_offset"] + 12 <= header["payload_len"]:
            raise ValueError(
                f"Invalid tx_payload_offset={header['tx_payload_offset']} "
                f"for payload_len={header['payload_len']}."
            )
    elif header["tx_payload_offset"] != 65535:
        raise ValueError(f"Invalid missing-payload offset: {header['tx_payload_offset']}.")
    if not 0 <= header["sig_len"] <= 4096:
        raise ValueError(f"Invalid sig_len: {header['sig_len']}.")
    if not 0 <= header["ampdu_cnt"] <= 4096:
        raise ValueError(f"Invalid ampdu_cnt: {header['ampdu_cnt']}.")
    if header["reserved"] != 0:
        raise ValueError(f"Invalid reserved field: {header['reserved']}.")


def read_record(stream: BinaryIO) -> BinaryCsiRecord | None:
    header_data = stream.read(HEADER_SIZE)
    if not header_data:
        return None
    if len(header_data) != HEADER_SIZE:
        raise EOFError("Truncated CSI binary header.")
    header = parse_header(header_data)
    raw = stream.read(header["csi_len"])
    if len(raw) != header["csi_len"]:
        raise EOFError("Truncated CSI binary payload.")
    return BinaryCsiRecord(header=header, raw=raw)


def pop_record_from_buffer(buffer: bytearray) -> tuple[BinaryCsiRecord, bytes, int] | None:
    skipped = 0
    index = buffer.find(MAGIC_BYTES)
    if index < 0:
        skipped = max(len(buffer) - len(MAGIC_BYTES) + 1, 0)
        if skipped:
            del buffer[:skipped]
        return None
    if index:
        skipped += index
        del buffer[:index]
    if len(buffer) < HEADER_SIZE:
        return None

    try:
        header = parse_header(bytes(buffer[:HEADER_SIZE]))
    except ValueError:
        del buffer[0]
        return None

    total_len = header["header_len"] + header["csi_len"]
    if len(buffer) < total_len:
        return None

    record_bytes = bytes(buffer[:total_len])
    raw = record_bytes[header["header_len"]:]
    del buffer[:total_len]
    return BinaryCsiRecord(header=header, raw=raw), record_bytes, skipped


def iter_records(path: str | Path) -> Iterator[BinaryCsiRecord]:
    with Path(path).open("rb") as stream:
        while True:
            record = read_record(stream)
            if record is None:
                return
            yield record
