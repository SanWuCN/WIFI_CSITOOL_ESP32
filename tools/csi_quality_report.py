from __future__ import annotations

import argparse
import ast
import csv
import json
import statistics
from collections import Counter
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Report quality metrics for an ESP32-S3 CSI CSV capture.")
    parser.add_argument("csv_file", help="CSV file saved by csi_workbench.py or csi_capture.py.")
    parser.add_argument("--json", default="", help="Optional output JSON report path.")
    return parser.parse_args()


def as_int(row: dict[str, str], name: str) -> int | None:
    try:
        value = row.get(name)
        if value is None or value == "":
            return None
        return int(float(value))
    except Exception:
        return None


def as_float(row: dict[str, str], name: str) -> float | None:
    try:
        value = row.get(name)
        if value is None or value == "":
            return None
        return float(value)
    except Exception:
        return None


def percentile(values: list[float], pct: float) -> float | None:
    if not values:
        return None
    return float(sorted(values)[round((len(values) - 1) * pct / 100.0)])


def main() -> None:
    args = parse_args()
    path = Path(args.csv_file)
    rows: list[dict[str, str]] = []
    malformed = 0
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fields = reader.fieldnames or []
        for row in reader:
            if None in row or any(row.get(name) is None for name in fields):
                malformed += 1
            rows.append(row)

    valid_rows = []
    invalid_reasons: Counter[str] = Counter()
    for row in rows:
        try:
            channel = as_int(row, "channel")
            length = as_int(row, "len")
            first_word = as_int(row, "first_word")
            raw_text = row.get("data") or ""
            raw = ast.literal_eval(raw_text)
            payload_found = as_int(row, "tx_payload_found") if "tx_payload_found" in row else None
            payload_offset = as_int(row, "tx_payload_offset") if "tx_payload_offset" in row else None
            payload_len = as_int(row, "tx_payload_len") if "tx_payload_len" in row else None

            if channel is None or not 1 <= channel <= 14:
                raise ValueError("bad_channel")
            if length is None or length != len(raw):
                raise ValueError("bad_len")
            if first_word not in (0, 1):
                raise ValueError("bad_first_word")
            if payload_found is not None and payload_found not in (0, 1):
                raise ValueError("bad_payload_found")
            if payload_found == 1 and payload_len is not None and payload_offset is not None:
                if not (0 <= payload_offset + 12 <= payload_len):
                    raise ValueError("bad_payload_offset")
            valid_rows.append(row)
        except Exception as exc:
            invalid_reasons[str(exc)] += 1

    def ints(name: str) -> list[int]:
        return [value for value in (as_int(row, name) for row in valid_rows) if value is not None]

    def floats(name: str) -> list[float]:
        return [value for value in (as_float(row, name) for row in valid_rows) if value is not None]

    ids = ints("id")
    tx_seq = ints("tx_seq")
    rx_ts = ints("rx_timestamp_us")
    pc_ts = floats("pc_timestamp")
    rssi = ints("rssi")
    found = ints("tx_payload_found")

    seq_gaps = [tx_seq[i + 1] - tx_seq[i] for i in range(len(tx_seq) - 1)]
    rx_dt = [((rx_ts[i + 1] - rx_ts[i]) & 0xFFFFFFFF) / 1000.0 for i in range(len(rx_ts) - 1)]
    pc_dt = [(pc_ts[i + 1] - pc_ts[i]) * 1000.0 for i in range(len(pc_ts) - 1)]
    id_missing = (ids[-1] - ids[0] + 1 - len(ids)) if len(ids) >= 2 else 0
    seq_missing = sum(max(gap - 1, 0) for gap in seq_gaps if 0 < gap < 100000)

    report = {
        "file": str(path),
        "rows_total": len(rows),
        "rows_valid": len(valid_rows),
        "rows_malformed": malformed,
        "invalid_reasons": dict(invalid_reasons),
        "id_first": ids[0] if ids else None,
        "id_last": ids[-1] if ids else None,
        "id_missing_est": id_missing,
        "tx_payload_found": dict(Counter(found)),
        "tx_seq_first": tx_seq[0] if tx_seq else None,
        "tx_seq_last": tx_seq[-1] if tx_seq else None,
        "tx_seq_gap_counts": Counter(seq_gaps).most_common(12),
        "tx_seq_missing_est": seq_missing,
        "rx_interval_ms": {
            "min": min(rx_dt) if rx_dt else None,
            "median": statistics.median(rx_dt) if rx_dt else None,
            "p95": percentile(rx_dt, 95),
            "max": max(rx_dt) if rx_dt else None,
        },
        "pc_interval_ms": {
            "min": min(pc_dt) if pc_dt else None,
            "median": statistics.median(pc_dt) if pc_dt else None,
            "p95": percentile(pc_dt, 95),
            "max": max(pc_dt) if pc_dt else None,
        },
        "rssi_counts": Counter(rssi).most_common(12),
    }

    print(json.dumps(report, ensure_ascii=False, indent=2))
    if args.json:
        Path(args.json).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
