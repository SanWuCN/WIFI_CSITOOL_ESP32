from __future__ import annotations

import argparse
import csv
import time
from pathlib import Path

import serial

from csi_common import parse_csi_line


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Capture ESP32 CSI_DATA lines from a serial port.")
    parser.add_argument("--port", required=True, help="Receiver serial port, for example COM5.")
    parser.add_argument("--baud", type=int, default=921600, help="Serial baud rate.")
    parser.add_argument("--out", required=True, help="Output CSV path.")
    parser.add_argument("--label", default="", help="Optional label written to each row.")
    parser.add_argument("--duration", type=float, default=0, help="Capture duration in seconds. 0 means until Ctrl+C.")
    parser.add_argument("--log", default="", help="Optional path for non-CSI or bad serial lines.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    log_file = open(args.log, "a", encoding="utf-8", newline="") if args.log else None

    count = 0
    start = time.time()
    header_written = False

    with serial.Serial(args.port, args.baud, timeout=1) as ser, out_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        try:
            while True:
                if args.duration and time.time() - start >= args.duration:
                    break

                line = ser.readline()
                if not line:
                    continue

                try:
                    frame = parse_csi_line(line)
                except Exception as exc:
                    if log_file:
                        log_file.write(f"BAD_LINE,{exc},{line!r}\n")
                    continue

                if frame is None:
                    if log_file:
                        log_file.write(line.decode("utf-8", errors="ignore"))
                    continue

                if not header_written:
                    writer.writerow(["pc_timestamp", "label", *frame.columns])
                    header_written = True

                writer.writerow([f"{time.time():.6f}", args.label, *frame.values])
                count += 1
                if count % 100 == 0:
                    elapsed = max(time.time() - start, 1e-6)
                    print(f"captured={count} rate={count / elapsed:.1f} Hz")
        except KeyboardInterrupt:
            pass
        finally:
            if log_file:
                log_file.close()

    elapsed = max(time.time() - start, 1e-6)
    print(f"done: {count} CSI frames, {elapsed:.1f}s, {count / elapsed:.1f} Hz -> {out_path}")


if __name__ == "__main__":
    main()
