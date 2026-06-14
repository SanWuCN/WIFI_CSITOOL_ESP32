from __future__ import annotations

import argparse
import ast
import csv
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

from csi_common import phase, valid_amplitude


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Plot amplitude and phase from a saved ESP32 CSI CSV.")
    parser.add_argument("csv_file", help="CSV file captured by tools/csi_capture.py or esp-csi tools.")
    parser.add_argument("--subcarrier", type=int, default=20, help="Subcarrier index to plot over time.")
    parser.add_argument("--limit", type=int, default=0, help="Limit number of frames. 0 means all frames.")
    return parser.parse_args()


def load_frames(path: Path, limit: int) -> tuple[np.ndarray, np.ndarray]:
    amplitudes: list[np.ndarray] = []
    phases: list[np.ndarray] = []

    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        if "data" not in reader.fieldnames:
            raise ValueError("CSV must contain a 'data' column.")

        for row in reader:
            raw = ast.literal_eval(row["data"])
            amplitudes.append(valid_amplitude(raw))
            phases.append(phase(raw))
            if limit and len(amplitudes) >= limit:
                break

    if not amplitudes:
        raise ValueError("No CSI frames found.")

    min_len = min(len(x) for x in amplitudes)
    amp = np.vstack([x[:min_len] for x in amplitudes])
    ph = np.vstack([x[:min_len] for x in phases])
    return amp, ph


def main() -> None:
    args = parse_args()
    csv_path = Path(args.csv_file)
    amp, ph = load_frames(csv_path, args.limit)
    sub = min(max(args.subcarrier, 0), amp.shape[1] - 1)

    fig, axes = plt.subplots(3, 1, figsize=(12, 9), constrained_layout=True)
    axes[0].imshow(amp.T, aspect="auto", origin="lower", interpolation="nearest")
    axes[0].set_title("CSI amplitude heatmap")
    axes[0].set_ylabel("Subcarrier")

    axes[1].plot(amp[:, sub])
    axes[1].set_title(f"Amplitude over time, subcarrier {sub}")
    axes[1].set_ylabel("Amplitude")

    axes[2].plot(np.unwrap(ph[:, sub]))
    axes[2].set_title(f"Unwrapped phase over time, subcarrier {sub}")
    axes[2].set_xlabel("Frame")
    axes[2].set_ylabel("Phase")

    plt.show()


if __name__ == "__main__":
    main()
