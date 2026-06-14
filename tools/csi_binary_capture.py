from __future__ import annotations

import argparse
import csv
import json
import time
from pathlib import Path

import serial

from csi_binary_common import HEADER_SIZE, MAGIC_BYTES, parse_header


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Capture ESP32-S3 CSI binary records from serial.")
    parser.add_argument("--port", required=True, help="Receiver serial port, for example COM15.")
    parser.add_argument("--baud", type=int, default=921600, help="Serial baud rate.")
    parser.add_argument("--out", required=True, help="Output .csibin path.")
    parser.add_argument("--summary", default="", help="Optional summary CSV path.")
    parser.add_argument("--duration", type=float, default=0, help="Capture duration in seconds. 0 means Ctrl+C.")
    parser.add_argument("--label", default="", help="Optional label saved to metadata JSON.")
    return parser.parse_args()


def pop_record(buffer: bytearray) -> tuple[bytes, bytes] | None:
    index = buffer.find(MAGIC_BYTES)
    if index < 0:
        del buffer[:-3]
        return None
    if index:
        del buffer[:index]
    if len(buffer) < HEADER_SIZE:
        return None

    header_data = bytes(buffer[:HEADER_SIZE])
    try:
        header = parse_header(header_data)
    except ValueError:
        del buffer[0]
        return None

    total_len = header["header_len"] + header["csi_len"]
    if len(buffer) < total_len:
        return None
    record = bytes(buffer[:total_len])
    raw = record[header["header_len"]:]
    del buffer[:total_len]
    return record, raw


def main() -> None:
    args = parse_args()
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path = Path(args.summary) if args.summary else out_path.with_suffix(".summary.csv")
    meta_path = out_path.with_suffix(".json")

    start = time.time()
    count = 0
    skipped = 0
    buffer = bytearray()
    summary_file = summary_path.open("w", encoding="utf-8", newline="")
    summary = csv.writer(summary_file)
    summary.writerow([
        "pc_timestamp",
        "record_seq",
        "tx_seq",
        "tx_payload_found",
        "tx_payload_offset",
        "rx_timestamp_us",
        "tx_timestamp_us",
        "rssi",
        "channel",
        "csi_len",
    ])

    meta_path.write_text(
        json.dumps(
            {
                "label": args.label,
                "port": args.port,
                "baud": args.baud,
                "started_at_unix": start,
                "format": "ESP32-S3 CSI binary v1",
                "record_layout": "app_csi_bin_header_t followed by int8 CSI bytes",
                "output_file": str(out_path),
                "summary_file": str(summary_path),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    with serial.Serial(args.port, args.baud, timeout=0.05) as ser, out_path.open("wb") as out_file:
        try:
            while True:
                if args.duration and time.time() - start >= args.duration:
                    break
                chunk = ser.read(4096)
                if not chunk:
                    continue
                before = len(buffer)
                buffer.extend(chunk)
                while True:
                    old_len = len(buffer)
                    result = pop_record(buffer)
                    skipped += max(0, old_len - len(buffer) - (len(result[0]) if result else 0))
                    if result is None:
                        break
                    record, _raw = result
                    header = parse_header(record[:HEADER_SIZE])
                    out_file.write(record)
                    count += 1
                    summary.writerow([
                        f"{time.time():.6f}",
                        header["record_seq"],
                        header["tx_seq"],
                        header["tx_payload_found"],
                        header["tx_payload_offset"],
                        header["rx_timestamp_us"],
                        header["tx_timestamp_us"],
                        header["rssi"],
                        header["channel"],
                        header["csi_len"],
                    ])
                    if count % 100 == 0:
                        elapsed = max(time.time() - start, 1e-6)
                        out_file.flush()
                        summary_file.flush()
                        print(f"captured={count} rate={count / elapsed:.1f} Hz buffer={len(buffer)} skipped={skipped}")
                if before > 1024 * 1024 and len(buffer) == before:
                    buffer.clear()
        except KeyboardInterrupt:
            pass
        finally:
            out_file.flush()
            summary_file.flush()
            summary_file.close()

    elapsed = max(time.time() - start, 1e-6)
    print(f"done: {count} records, {elapsed:.1f}s, {count / elapsed:.1f} Hz -> {out_path}")


if __name__ == "__main__":
    main()
