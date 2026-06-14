from __future__ import annotations

import argparse
import statistics
from collections import Counter
from pathlib import Path

import numpy as np

from csi_binary_common import iter_records


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Inspect an ESP32-S3 CSI .csibin capture.")
    parser.add_argument("file", help="Path to .csibin file.")
    parser.add_argument("--limit", type=int, default=0, help="Limit records inspected. 0 means all.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    path = Path(args.file)
    records = []
    for i, record in enumerate(iter_records(path)):
        records.append(record)
        if args.limit and i + 1 >= args.limit:
            break
    if not records:
        raise SystemExit("No binary CSI records found.")

    headers = [r.header for r in records]
    seq = np.asarray([h["record_seq"] for h in headers], dtype=np.int64)
    tx_seq = np.asarray([h["tx_seq"] for h in headers], dtype=np.int64)
    rx_ts = np.asarray([h["rx_timestamp_us"] for h in headers], dtype=np.uint32).astype(np.uint64)
    rssi = [h["rssi"] for h in headers]
    found = [h["tx_payload_found"] for h in headers]
    csi_len = [h["csi_len"] for h in headers]
    valid_subcarriers = [r.complex_csi.size for r in records[: min(20, len(records))]]

    seq_gaps = np.diff(seq)
    tx_gaps = np.diff(tx_seq)
    rx_dt = ((np.diff(rx_ts.astype(np.int64)) + 2**31) % 2**32 - 2**31) / 1000.0

    print(f"file={path}")
    print(f"records={len(records)}")
    print(f"record_seq first={seq[0]} last={seq[-1]} missed={int(np.maximum(seq_gaps - 1, 0).sum()) if seq_gaps.size else 0}")
    print(f"tx_payload_found={Counter(found)}")
    print(f"tx_seq unique={len(set(tx_seq.tolist()))} first={tx_seq[0]} last={tx_seq[-1]}")
    if tx_gaps.size:
        print(f"tx_seq gaps={Counter(tx_gaps.tolist()).most_common(8)}")
    if rx_dt.size:
        print(
            "rx_interval_ms "
            f"min={rx_dt.min():.3f} median={statistics.median(rx_dt):.3f} "
            f"p95={np.percentile(rx_dt, 95):.3f} max={rx_dt.max():.3f}"
        )
    print(f"rssi={Counter(rssi).most_common(8)}")
    print(f"csi_len={Counter(csi_len).most_common(8)}")
    print(f"valid_subcarriers_sample={valid_subcarriers}")


if __name__ == "__main__":
    main()
