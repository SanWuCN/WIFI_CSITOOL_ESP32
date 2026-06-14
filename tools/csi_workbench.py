from __future__ import annotations

import csv
import json
import os
import platform
import queue
import shutil
import subprocess
import sys
import threading
import time
import tkinter as tk
from collections import deque
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import matplotlib
import numpy as np
import serial
from serial.tools import list_ports

matplotlib.use("TkAgg")
matplotlib.rcParams["font.sans-serif"] = [
    "Microsoft YaHei",
    "SimHei",
    "SimSun",
    "Arial Unicode MS",
    "DejaVu Sans",
]
matplotlib.rcParams["axes.unicode_minus"] = False
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure

from csi_binary_common import BinaryCsiRecord, pop_record_from_buffer
from csi_common import CsiFrame, ESP32_TIMED_COLUMNS, parse_csi_line, valid_amplitude, valid_complex_csi


APP_NAME = "SwCSI"
APP_VERSION = "V1.0.2"
CONTACT_EMAIL = "1292053575@qq.com"
if getattr(sys, "frozen", False):
    PROJECT_ROOT = Path(sys.executable).resolve().parent
    RESOURCE_ROOT = Path(getattr(sys, "_MEIPASS", PROJECT_ROOT))
else:
    PROJECT_ROOT = Path(__file__).resolve().parents[1]
    RESOURCE_ROOT = PROJECT_ROOT
if sys.platform == "darwin":
    APP_DATA_DIR = Path.home() / "Library" / "Application Support" / APP_NAME
elif getattr(sys, "frozen", False):
    APP_DATA_DIR = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / APP_NAME
else:
    APP_DATA_DIR = PROJECT_ROOT
ASSETS_DIR = PROJECT_ROOT / "assets"
RESOURCE_ASSETS_DIR = RESOURCE_ROOT / "assets"
ICON_PNG = ASSETS_DIR / "swcsi_icon.png"
ICON_ICO = ASSETS_DIR / "swcsi_icon.ico"
RESOURCE_ICON_PNG = RESOURCE_ASSETS_DIR / "swcsi_icon.png"
RESOURCE_ICON_ICO = RESOURCE_ASSETS_DIR / "swcsi_icon.ico"
SETTINGS_PATH = APP_DATA_DIR / "swcsi_settings.json"
DEFAULT_OUT_DIR = APP_DATA_DIR / "data" / "raw"
DEFAULT_BAUD = 921600
MAX_FRAMES = 240
PLOT_REFRESH_MS = 100
SMOOTH_WINDOW = 7
DOPPLER_WINDOW = 64
DOPPLER_HOP = 4
DOPPLER_NFFT = 128
DOPPLER_MIN_FRAMES = 32

LANGUAGES = {
    "zh": "简体中文",
    "en": "English",
}

TEXT = {
    "zh": {
        "title": f"{APP_NAME} {APP_VERSION} - Wi-Fi CSI 工作台",
        "serial_connection": "串口连接",
        "port": "端口",
        "refresh": "刷新",
        "baud": "波特率",
        "connect": "连接",
        "disconnect": "断开",
        "device_control": "设备控制",
        "tx_rate": "发送频率",
        "channel": "信道",
        "apply": "应用",
        "capture_profile": "采集信息",
        "label": "标签",
        "scene": "实验场景",
        "subject": "受试者",
        "layout": "链路布局",
        "notes": "备注",
        "directory": "目录",
        "file": "文件",
        "start_capture": "开始采集",
        "stop_capture": "停止采集",
        "open_data_dir": "打开数据目录",
        "export_capture": "导出数据包",
        "export_project": "导出工作台包",
        "subcarrier": "子载波",
        "runtime_log": "运行日志",
        "overview": "实时总览",
        "doppler_stft": "Doppler/STFT",
        "not_connected": "未连接",
        "stats_idle": "帧数=0 错误=0 帧率=0.0Hz RSSI=N/A 子载波=N/A",
        "menu_file": "文件",
        "menu_edit": "编辑",
        "menu_view": "视图",
        "menu_help": "帮助",
        "settings": "设置",
        "save_project": "保存工程",
        "load_project": "加载工程",
        "exit": "退出",
        "about": "关于 SwCSI",
        "language": "界面语言",
        "default_dir": "默认数据目录",
        "contact": "联系方式",
        "save": "保存",
        "cancel": "取消",
        "project_saved": "工程已保存",
        "project_loaded": "工程已加载",
        "project_filetypes": "SwCSI 工程",
        "all_files": "所有文件",
    },
    "en": {
        "title": f"{APP_NAME} {APP_VERSION} - Wi-Fi CSI Workbench",
        "serial_connection": "Serial",
        "port": "Port",
        "refresh": "Refresh",
        "baud": "Baud",
        "connect": "Connect",
        "disconnect": "Disconnect",
        "device_control": "Device Control",
        "tx_rate": "TX Rate",
        "channel": "Channel",
        "apply": "Apply",
        "capture_profile": "Capture Profile",
        "label": "Label",
        "scene": "Scenario",
        "subject": "Subject",
        "layout": "Link Layout",
        "notes": "Notes",
        "directory": "Directory",
        "file": "File",
        "start_capture": "Start Capture",
        "stop_capture": "Stop Capture",
        "open_data_dir": "Open Data Folder",
        "export_capture": "Export Data Package",
        "export_project": "Export Workbench Package",
        "subcarrier": "Subcarrier",
        "runtime_log": "Runtime Log",
        "overview": "Overview",
        "doppler_stft": "Doppler/STFT",
        "not_connected": "Disconnected",
        "stats_idle": "frames=0 errors=0 rate=0.0Hz RSSI=N/A subcarriers=N/A",
        "menu_file": "File",
        "menu_edit": "Edit",
        "menu_view": "View",
        "menu_help": "Help",
        "settings": "Settings",
        "save_project": "Save Project",
        "load_project": "Load Project",
        "exit": "Exit",
        "about": "About SwCSI",
        "language": "Language",
        "default_dir": "Default Data Folder",
        "contact": "Contact",
        "save": "Save",
        "cancel": "Cancel",
        "project_saved": "Project saved",
        "project_loaded": "Project loaded",
        "project_filetypes": "SwCSI Project",
        "all_files": "All Files",
    },
}


class SerialReader(threading.Thread):
    def __init__(self, port: str, baud: int, events: queue.Queue, stop_event: threading.Event):
        super().__init__(daemon=True)
        self.port = port
        self.baud = baud
        self.events = events
        self.stop_event = stop_event
        self.serial: serial.Serial | None = None

    def run(self) -> None:
        try:
            with serial.Serial(self.port, self.baud, timeout=1.0) as ser:
                self.serial = ser
                self.events.put(("state", f"connected {self.port} @ {self.baud}"))
                while not self.stop_event.is_set():
                    raw_line = ser.readline()
                    if not raw_line:
                        continue
                    received_at = time.time()
                    try:
                        frame = parse_csi_line(raw_line)
                    except Exception as exc:
                        self.events.put(("bad", f"{exc}: {raw_line!r}"))
                        continue

                    if frame is None:
                        text = raw_line.decode("utf-8", errors="ignore").strip()
                        if text:
                            self.events.put(("log", text))
                        continue

                    self.events.put(("frame", (received_at, frame)))
        except Exception as exc:
            self.events.put(("error", str(exc)))
        finally:
            self.events.put(("state", "disconnected"))

    def write_line(self, command: str) -> None:
        if not self.serial or not self.serial.is_open:
            raise RuntimeError("Serial port is not open.")
        self.serial.write((command.strip() + "\n").encode("utf-8"))
        self.serial.flush()


class BinarySerialReader(threading.Thread):
    def __init__(self, port: str, baud: int, events: queue.Queue, stop_event: threading.Event):
        super().__init__(daemon=True)
        self.port = port
        self.baud = baud
        self.events = events
        self.stop_event = stop_event
        self.serial: serial.Serial | None = None
        self.skipped = 0

    def run(self) -> None:
        buffer = bytearray()
        try:
            with serial.Serial(self.port, self.baud, timeout=0.05) as ser:
                self.serial = ser
                self.events.put(("state", f"connected {self.port} @ {self.baud} BIN"))
                while not self.stop_event.is_set():
                    chunk = ser.read(4096)
                    if not chunk:
                        continue
                    buffer.extend(chunk)
                    while True:
                        result = pop_record_from_buffer(buffer)
                        if result is None:
                            break
                        record, record_bytes, skipped = result
                        self.skipped += skipped
                        if skipped and (self.skipped <= 128 or self.skipped % 4096 == 0):
                            self.events.put(("bin_skip", self.skipped))
                        self.events.put(("binary_frame", (time.time(), record, record_bytes)))
        except Exception as exc:
            self.events.put(("error", str(exc)))
        finally:
            self.events.put(("state", "disconnected"))

    def write_line(self, command: str) -> None:
        if not self.serial or not self.serial.is_open:
            raise RuntimeError("Serial port is not open.")
        self.serial.write((command.strip() + "\n").encode("utf-8"))
        self.serial.flush()


class CaptureWriter:
    def __init__(self):
        self.file = None
        self.writer: csv.writer | None = None
        self.header_written = False
        self.header_columns: list[str] | None = None
        self.path: Path | None = None
        self.started_at = 0.0
        self.count = 0
        self.metadata: dict[str, str | float | int] = {}

    @property
    def active(self) -> bool:
        return self.file is not None

    def start(self, path: Path, metadata: dict[str, str | float | int]) -> None:
        self.stop()
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self.file = path.open("w", encoding="utf-8", newline="")
        self.writer = csv.writer(self.file)
        self.header_written = False
        self.header_columns = None
        self.started_at = time.time()
        self.count = 0
        self.metadata = metadata

        meta_path = path.with_suffix(".json")
        meta = {
            **metadata,
            "csv_file": str(path),
            "started_at_unix": self.started_at,
            "source": "ESP32-S3 CSI workbench",
        }
        meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    def write(self, frame: CsiFrame, label: str, pc_timestamp: float | None = None) -> bool:
        if not self.file or not self.writer:
            return True
        if not self.header_written:
            self.writer.writerow(["pc_timestamp", "label", *frame.columns])
            self.header_written = True
            self.header_columns = list(frame.columns)
        elif self.header_columns != frame.columns:
            return False
        if pc_timestamp is None:
            pc_timestamp = time.time()
        self.writer.writerow([f"{pc_timestamp:.6f}", label, *frame.values])
        self.count += 1
        if self.count % 50 == 0:
            self.file.flush()
        return True

    def stop(self) -> None:
        if self.file:
            self.file.flush()
            self.file.close()
        self.file = None
        self.writer = None
        self.header_written = False
        self.header_columns = None


class BinaryCaptureWriter:
    def __init__(self):
        self.file = None
        self.summary_file = None
        self.summary_writer: csv.writer | None = None
        self.path: Path | None = None
        self.count = 0
        self.started_at = 0.0

    @property
    def active(self) -> bool:
        return self.file is not None

    def start(self, path: Path, metadata: dict[str, str | float | int]) -> None:
        self.stop()
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self.file = path.open("wb")
        self.summary_file = path.with_suffix(".summary.csv").open("w", encoding="utf-8", newline="")
        self.summary_writer = csv.writer(self.summary_file)
        self.summary_writer.writerow([
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
        self.count = 0
        self.started_at = time.time()
        meta = {
            **metadata,
            "binary_file": str(path),
            "summary_file": str(path.with_suffix(".summary.csv")),
            "started_at_unix": self.started_at,
            "format": "ESP32-S3 CSI binary v1",
            "source": "ESP32-S3 CSI workbench",
        }
        path.with_suffix(".json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    def write(self, record: BinaryCsiRecord, record_bytes: bytes, pc_timestamp: float) -> None:
        if not self.file or not self.summary_writer:
            return
        h = record.header
        self.file.write(record_bytes)
        self.summary_writer.writerow([
            f"{pc_timestamp:.6f}",
            h["record_seq"],
            h["tx_seq"],
            h["tx_payload_found"],
            h["tx_payload_offset"],
            h["rx_timestamp_us"],
            h["tx_timestamp_us"],
            h["rssi"],
            h["channel"],
            h["csi_len"],
        ])
        self.count += 1
        if self.count % 100 == 0:
            self.file.flush()
            self.summary_file.flush()

    def stop(self) -> None:
        if self.file:
            self.file.flush()
            self.file.close()
        if self.summary_file:
            self.summary_file.flush()
            self.summary_file.close()
        self.file = None
        self.summary_file = None
        self.summary_writer = None


class CsiWorkbench(tk.Tk):
    def __init__(self):
        super().__init__()
        self.settings = self._load_settings()
        self.title(TEXT[self.settings.get("language", "zh")]["title"])
        self.geometry("1280x820")
        self.minsize(1080, 720)
        self._set_app_icon()
        self._configure_style()

        self.events: queue.Queue = queue.Queue()
        self.stop_event = threading.Event()
        self.reader: SerialReader | BinarySerialReader | None = None
        self.csv_capture = CaptureWriter()
        self.binary_capture = BinaryCaptureWriter()

        self.amplitude_history: deque[np.ndarray] = deque(maxlen=MAX_FRAMES)
        self.complex_history: deque[np.ndarray] = deque(maxlen=MAX_FRAMES)
        self.raw_history: deque[list[int]] = deque(maxlen=MAX_FRAMES)
        self.rssi_history: deque[float] = deque(maxlen=MAX_FRAMES)
        self.timestamps: deque[float] = deque(maxlen=MAX_FRAMES)
        self.tx_seq_history: deque[float] = deque(maxlen=MAX_FRAMES)
        self.tx_time_history: deque[float] = deque(maxlen=MAX_FRAMES)
        self.rx_time_history: deque[float] = deque(maxlen=MAX_FRAMES)
        self.pc_time_history: deque[float] = deque(maxlen=MAX_FRAMES)
        self.frame_count = 0
        self.bad_count = 0
        self.last_frame_time = 0.0
        self.current_columns: list[str] = []
        self.latest_frame: CsiFrame | None = None
        self.binary_skipped = 0
        self.ui_text: dict[str, object] = {}
        self.menu_buttons: dict[str, ttk.Menubutton] = {}

        self._build_vars()
        self._build_layout()
        self._apply_language()
        self._refresh_ports()
        self.after(80, self._poll_events)
        self.after(250, self._redraw)

    def _build_vars(self) -> None:
        self.port_var = tk.StringVar()
        self.baud_var = tk.StringVar(value=str(DEFAULT_BAUD))
        self.stream_mode_var = tk.StringVar(value="BIN")
        self.language_var = tk.StringVar(value=self.settings.get("language", "zh"))
        self.label_var = tk.StringVar(value="test")
        self.out_dir_var = tk.StringVar(value=self.settings.get("default_out_dir", str(DEFAULT_OUT_DIR)))
        self.filename_var = tk.StringVar(value=time.strftime("%Y%m%d_%H%M%S_test.csibin"))
        self.status_var = tk.StringVar(value=self._text("not_connected"))
        self.stats_var = tk.StringVar(value=self._text("stats_idle"))
        self.channel_var = tk.StringVar(value="11")
        self.freq_var = tk.StringVar(value="50")
        self.subcarrier_var = tk.IntVar(value=20)
        self.doppler_mode_var = tk.StringVar(value="合成")
        self.scene_var = tk.StringVar(value="实验室")
        self.subject_var = tk.StringVar(value="s01")
        self.layout_var = tk.StringVar(value="lineofsight")
        self.notes_var = tk.StringVar(value="")
        self.stream_mode_var.trace_add("write", self._stream_mode_changed)

    def _load_settings(self) -> dict[str, str]:
        if not SETTINGS_PATH.exists():
            return {"language": "zh", "default_out_dir": str(DEFAULT_OUT_DIR)}
        try:
            data = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
            language = data.get("language", "zh")
            if language not in LANGUAGES:
                language = "zh"
            return {
                "language": language,
                "default_out_dir": data.get("default_out_dir", str(DEFAULT_OUT_DIR)),
            }
        except Exception:
            return {"language": "zh", "default_out_dir": str(DEFAULT_OUT_DIR)}

    def _save_settings(self) -> None:
        self.settings = {
            "language": self.language_var.get() if self.language_var.get() in LANGUAGES else "zh",
            "default_out_dir": self.out_dir_var.get() or str(DEFAULT_OUT_DIR),
        }
        SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
        SETTINGS_PATH.write_text(json.dumps(self.settings, ensure_ascii=False, indent=2), encoding="utf-8")

    def _set_app_icon(self) -> None:
        try:
            ico = RESOURCE_ICON_ICO if RESOURCE_ICON_ICO.exists() else ICON_ICO
            png = RESOURCE_ICON_PNG if RESOURCE_ICON_PNG.exists() else ICON_PNG
            if sys.platform == "win32" and ico.exists():
                self.iconbitmap(str(ico))
            if png.exists():
                self._icon_image = tk.PhotoImage(file=str(png))
                self.iconphoto(True, self._icon_image)
        except Exception:
            self._icon_image = None

    def _configure_style(self) -> None:
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        default_font = ("Microsoft YaHei UI", 10)
        heading_font = ("Microsoft YaHei UI", 10, "bold")
        self.option_add("*Font", default_font)
        style.configure("TLabel", font=default_font, padding=(0, 1))
        style.configure("TButton", font=default_font, padding=(8, 4))
        style.configure("TMenubutton", font=default_font, padding=(8, 4))
        style.configure("Header.TLabel", font=heading_font)
        style.configure("Toolbar.TFrame", background="#f4f6f8")
        style.configure("Toolbar.TButton", padding=(8, 3))

    def _text(self, key: str) -> str:
        language = self.language_var.get() if hasattr(self, "language_var") else self.settings.get("language", "zh")
        return TEXT.get(language, TEXT["zh"]).get(key, TEXT["zh"].get(key, key))

    def _remember_text(self, key: str, widget: object) -> object:
        self.ui_text[key] = widget
        return widget

    def _stream_mode_changed(self, *_args) -> None:
        suffix = ".csibin" if self.stream_mode_var.get().upper() == "BIN" else ".csv"
        current = self.filename_var.get().strip()
        if not current:
            self.filename_var.set(time.strftime(f"%Y%m%d_%H%M%S_test{suffix}"))
            return
        self.filename_var.set(str(Path(current).with_suffix(suffix)))

    def _build_layout(self) -> None:
        self.columnconfigure(0, weight=0)
        self.columnconfigure(1, weight=1)
        self.rowconfigure(0, weight=0)
        self.rowconfigure(1, weight=1)

        toolbar = ttk.Frame(self, padding=(8, 6), style="Toolbar.TFrame")
        toolbar.grid(row=0, column=0, columnspan=2, sticky="ew")
        toolbar.columnconfigure(10, weight=1)

        ttk.Button(toolbar, text="☰", width=3, style="Toolbar.TButton", command=self._open_settings).grid(row=0, column=0, padx=(0, 4))
        ttk.Button(toolbar, text="‹", width=3, style="Toolbar.TButton", command=lambda: self.notebook.select(0)).grid(row=0, column=1, padx=(0, 2))
        ttk.Button(toolbar, text="›", width=3, style="Toolbar.TButton", command=lambda: self.notebook.select(1)).grid(row=0, column=2, padx=(0, 8))

        self.file_button = ttk.Menubutton(toolbar, text="文件")
        self.file_menu = tk.Menu(self.file_button, tearoff=False)
        self.file_button["menu"] = self.file_menu
        self.file_button.grid(row=0, column=3, padx=(0, 4))

        self.edit_button = ttk.Menubutton(toolbar, text="编辑")
        self.edit_menu = tk.Menu(self.edit_button, tearoff=False)
        self.edit_button["menu"] = self.edit_menu
        self.edit_button.grid(row=0, column=4, padx=(0, 4))

        self.view_button = ttk.Menubutton(toolbar, text="视图")
        self.view_menu = tk.Menu(self.view_button, tearoff=False)
        self.view_button["menu"] = self.view_menu
        self.view_button.grid(row=0, column=5, padx=(0, 4))

        self.help_button = ttk.Menubutton(toolbar, text="帮助")
        self.help_menu = tk.Menu(self.help_button, tearoff=False)
        self.help_button["menu"] = self.help_menu
        self.help_button.grid(row=0, column=6, padx=(0, 8))

        self.menu_buttons = {
            "menu_file": self.file_button,
            "menu_edit": self.edit_button,
            "menu_view": self.view_button,
            "menu_help": self.help_button,
        }
        self._rebuild_menus()

        ttk.Label(toolbar, text=f"{APP_NAME} {APP_VERSION}", style="Header.TLabel").grid(row=0, column=10, sticky="e")

        left = ttk.Frame(self, padding=10)
        left.grid(row=1, column=0, sticky="ns")
        left.columnconfigure(1, weight=1)

        plot_area = ttk.Frame(self, padding=(0, 10, 10, 10))
        plot_area.grid(row=1, column=1, sticky="nsew")
        plot_area.rowconfigure(0, weight=1)
        plot_area.columnconfigure(0, weight=1)

        self._remember_text("serial_connection", ttk.Label(left, style="Header.TLabel")).grid(row=0, column=0, columnspan=3, sticky="w")
        self._remember_text("port", ttk.Label(left)).grid(row=1, column=0, sticky="w", pady=(8, 0))
        self.port_combo = ttk.Combobox(left, textvariable=self.port_var, width=18, state="readonly")
        self.port_combo.grid(row=1, column=1, sticky="ew", pady=(8, 0))
        self._remember_text("refresh", ttk.Button(left, command=self._refresh_ports)).grid(row=1, column=2, padx=(6, 0), pady=(8, 0))

        self._remember_text("baud", ttk.Label(left)).grid(row=2, column=0, sticky="w", pady=(6, 0))
        ttk.Entry(left, textvariable=self.baud_var, width=12).grid(row=2, column=1, sticky="ew", pady=(6, 0))
        self.stream_mode_combo = ttk.Combobox(
            left,
            textvariable=self.stream_mode_var,
            width=8,
            state="readonly",
            values=["BIN", "CSV"],
        )
        self.stream_mode_combo.grid(row=2, column=2, sticky="ew", padx=(6, 0), pady=(6, 0))

        self.connect_button = ttk.Button(left, text=self._text("connect"), command=self._toggle_connect)
        self.ui_text["connect"] = self.connect_button
        self.connect_button.grid(row=3, column=0, columnspan=3, sticky="ew", pady=(10, 0))

        ttk.Separator(left).grid(row=4, column=0, columnspan=3, sticky="ew", pady=12)

        self._remember_text("device_control", ttk.Label(left, style="Header.TLabel")).grid(row=5, column=0, columnspan=3, sticky="w")
        ttk.Button(left, text="status", command=lambda: self._send_command("status")).grid(row=6, column=0, sticky="ew", pady=(8, 0))
        ttk.Button(left, text="mode tx", command=lambda: self._send_command("mode tx")).grid(row=6, column=1, sticky="ew", padx=(6, 0), pady=(8, 0))
        ttk.Button(left, text="mode rx", command=lambda: self._send_command("mode rx")).grid(row=6, column=2, sticky="ew", padx=(6, 0), pady=(8, 0))
        ttk.Button(left, text="output csv", command=lambda: self._send_command("output csv")).grid(row=7, column=0, sticky="ew", pady=(8, 0))
        ttk.Button(left, text="output bin", command=lambda: self._send_command("output bin")).grid(row=7, column=1, columnspan=2, sticky="ew", padx=(6, 0), pady=(8, 0))

        self._remember_text("tx_rate", ttk.Label(left)).grid(row=8, column=0, sticky="w", pady=(8, 0))
        ttk.Entry(left, textvariable=self.freq_var, width=10).grid(row=8, column=1, sticky="ew", pady=(8, 0))
        self._remember_text("apply_freq", ttk.Button(left, command=lambda: self._send_command(f"freq {self.freq_var.get()}"))).grid(row=8, column=2, sticky="ew", padx=(6, 0), pady=(8, 0))

        self._remember_text("channel", ttk.Label(left)).grid(row=9, column=0, sticky="w", pady=(8, 0))
        ttk.Entry(left, textvariable=self.channel_var, width=10).grid(row=9, column=1, sticky="ew", pady=(8, 0))
        self._remember_text("apply_channel", ttk.Button(left, command=lambda: self._send_command(f"channel {self.channel_var.get()}"))).grid(row=9, column=2, sticky="ew", padx=(6, 0), pady=(8, 0))

        ttk.Separator(left).grid(row=10, column=0, columnspan=3, sticky="ew", pady=12)

        self._remember_text("capture_profile", ttk.Label(left, style="Header.TLabel")).grid(row=11, column=0, columnspan=3, sticky="w")
        self._remember_text("label", ttk.Label(left)).grid(row=12, column=0, sticky="w", pady=(8, 0))
        ttk.Entry(left, textvariable=self.label_var).grid(row=12, column=1, columnspan=2, sticky="ew", pady=(8, 0))

        self._remember_text("scene", ttk.Label(left)).grid(row=13, column=0, sticky="w", pady=(8, 0))
        ttk.Entry(left, textvariable=self.scene_var).grid(row=13, column=1, columnspan=2, sticky="ew", pady=(8, 0))

        self._remember_text("subject", ttk.Label(left)).grid(row=14, column=0, sticky="w", pady=(8, 0))
        ttk.Entry(left, textvariable=self.subject_var).grid(row=14, column=1, columnspan=2, sticky="ew", pady=(8, 0))

        self._remember_text("layout", ttk.Label(left)).grid(row=15, column=0, sticky="w", pady=(8, 0))
        ttk.Entry(left, textvariable=self.layout_var).grid(row=15, column=1, columnspan=2, sticky="ew", pady=(8, 0))

        self._remember_text("notes", ttk.Label(left)).grid(row=16, column=0, sticky="w", pady=(8, 0))
        ttk.Entry(left, textvariable=self.notes_var).grid(row=16, column=1, columnspan=2, sticky="ew", pady=(8, 0))

        self._remember_text("directory", ttk.Label(left)).grid(row=17, column=0, sticky="w", pady=(8, 0))
        ttk.Entry(left, textvariable=self.out_dir_var, width=28).grid(row=17, column=1, sticky="ew", pady=(8, 0))
        ttk.Button(left, text="...", command=self._choose_out_dir, width=4).grid(row=17, column=2, sticky="ew", padx=(6, 0), pady=(8, 0))

        self._remember_text("file", ttk.Label(left)).grid(row=18, column=0, sticky="w", pady=(8, 0))
        ttk.Entry(left, textvariable=self.filename_var).grid(row=18, column=1, columnspan=2, sticky="ew", pady=(8, 0))

        self.capture_button = ttk.Button(left, text=self._text("start_capture"), command=self._toggle_capture)
        self.ui_text["start_capture"] = self.capture_button
        self.capture_button.grid(row=19, column=0, columnspan=3, sticky="ew", pady=(10, 0))

        self._remember_text("open_data_dir", ttk.Button(left, command=self._open_out_dir)).grid(row=20, column=0, columnspan=3, sticky="ew", pady=(8, 0))
        self._remember_text("export_capture", ttk.Button(left, command=self._export_capture_package)).grid(row=21, column=0, columnspan=3, sticky="ew", pady=(8, 0))
        self._remember_text("export_project", ttk.Button(left, command=self._export_project_package)).grid(row=22, column=0, columnspan=3, sticky="ew", pady=(8, 0))

        self._remember_text("subcarrier", ttk.Label(left)).grid(row=23, column=0, sticky="w", pady=(12, 0))
        self.subcarrier_scale = ttk.Scale(left, from_=0, to=127, variable=self.subcarrier_var, orient="horizontal")
        self.subcarrier_scale.grid(row=23, column=1, columnspan=2, sticky="ew", pady=(12, 0))

        ttk.Label(left, text="Doppler").grid(row=24, column=0, sticky="w", pady=(8, 0))
        self.doppler_mode_combo = ttk.Combobox(
            left,
            textvariable=self.doppler_mode_var,
            width=10,
            state="readonly",
            values=["合成", "当前子载波"],
        )
        self.doppler_mode_combo.grid(row=24, column=1, columnspan=2, sticky="ew", pady=(8, 0))

        ttk.Separator(left).grid(row=25, column=0, columnspan=3, sticky="ew", pady=12)
        ttk.Label(left, textvariable=self.status_var, foreground="#2255aa").grid(row=26, column=0, columnspan=3, sticky="w")
        ttk.Label(left, textvariable=self.stats_var, wraplength=280).grid(row=27, column=0, columnspan=3, sticky="w", pady=(6, 0))

        self._remember_text("runtime_log", ttk.Label(left, style="Header.TLabel")).grid(row=28, column=0, columnspan=3, sticky="w", pady=(12, 0))
        self.log_text = tk.Text(left, height=14, width=42, wrap="word")
        self.log_text.grid(row=29, column=0, columnspan=3, sticky="nsew")

        self.notebook = ttk.Notebook(plot_area)
        self.notebook.grid(row=0, column=0, sticky="nsew")
        overview_tab = ttk.Frame(self.notebook)
        doppler_tab = ttk.Frame(self.notebook)
        overview_tab.rowconfigure(0, weight=1)
        overview_tab.columnconfigure(0, weight=1)
        doppler_tab.rowconfigure(0, weight=1)
        doppler_tab.columnconfigure(0, weight=1)
        self.notebook.add(overview_tab, text="实时总览")
        self.notebook.add(doppler_tab, text="Doppler/STFT")

        self.figure = Figure(figsize=(10, 8), dpi=100)
        self.ax_heat = self.figure.add_subplot(321)
        self.ax_sub = self.figure.add_subplot(322)
        self.ax_rssi = self.figure.add_subplot(323)
        self.ax_iq = self.figure.add_subplot(324)
        self.ax_latest_amp = self.figure.add_subplot(325)
        self.ax_timing = self.figure.add_subplot(326)
        self.figure.tight_layout(pad=2.0)
        self.canvas = FigureCanvasTkAgg(self.figure, master=overview_tab)
        self.canvas.get_tk_widget().grid(row=0, column=0, sticky="nsew")

        self.doppler_figure = Figure(figsize=(10, 8), dpi=100)
        self.ax_doppler_spec = self.doppler_figure.add_subplot(221)
        self.ax_doppler_signal = self.doppler_figure.add_subplot(222)
        self.ax_doppler_profile = self.doppler_figure.add_subplot(223)
        self.ax_doppler_phase = self.doppler_figure.add_subplot(224)
        self.doppler_figure.tight_layout(pad=2.0)
        self.doppler_canvas = FigureCanvasTkAgg(self.doppler_figure, master=doppler_tab)
        self.doppler_canvas.get_tk_widget().grid(row=0, column=0, sticky="nsew")

    def _rebuild_menus(self) -> None:
        self.file_menu.delete(0, "end")
        self.file_menu.add_command(label=self._text("save_project"), command=self._save_project)
        self.file_menu.add_command(label=self._text("load_project"), command=self._load_project)
        self.file_menu.add_separator()
        self.file_menu.add_command(label=self._text("settings"), command=self._open_settings)
        self.file_menu.add_separator()
        self.file_menu.add_command(label=self._text("exit"), command=self.destroy)

        self.edit_menu.delete(0, "end")
        self.edit_menu.add_command(label=self._text("settings"), command=self._open_settings)

        self.view_menu.delete(0, "end")
        self.view_menu.add_command(label=self._text("overview"), command=lambda: self.notebook.select(0))
        self.view_menu.add_command(label=self._text("doppler_stft"), command=lambda: self.notebook.select(1))

        self.help_menu.delete(0, "end")
        self.help_menu.add_command(label=self._text("about"), command=self._show_about)

    def _apply_language(self) -> None:
        self.title(self._text("title"))
        for key, widget in self.ui_text.items():
            text_key = "apply" if key.startswith("apply_") else key
            if hasattr(widget, "configure"):
                widget.configure(text=self._text(text_key))
        for key, button in self.menu_buttons.items():
            button.configure(text=self._text(key))
        self.notebook.tab(0, text=self._text("overview"))
        self.notebook.tab(1, text=self._text("doppler_stft"))
        if self.reader:
            self.connect_button.configure(text=self._text("disconnect"))
        elif not (self.csv_capture.active or self.binary_capture.active):
            self.connect_button.configure(text=self._text("connect"))
        if self.csv_capture.active or self.binary_capture.active:
            self.capture_button.configure(text=self._text("stop_capture"))
        else:
            self.capture_button.configure(text=self._text("start_capture"))
        if self.status_var.get() in ("未连接", "Disconnected"):
            self.status_var.set(self._text("not_connected"))
        if self.frame_count == 0:
            self.stats_var.set(self._text("stats_idle"))
        self._rebuild_menus()

    def _project_state(self) -> dict[str, object]:
        return {
            "app": APP_NAME,
            "version": APP_VERSION,
            "saved_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "contact": CONTACT_EMAIL,
            "serial": {
                "port": self.port_var.get(),
                "baud": self.baud_var.get(),
                "stream_mode": self.stream_mode_var.get(),
            },
            "device": {
                "tx_hz": self.freq_var.get(),
                "channel": self.channel_var.get(),
            },
            "capture": {
                "label": self.label_var.get(),
                "scene": self.scene_var.get(),
                "subject": self.subject_var.get(),
                "layout": self.layout_var.get(),
                "notes": self.notes_var.get(),
                "out_dir": self.out_dir_var.get(),
                "filename": self.filename_var.get(),
            },
            "view": {
                "subcarrier": int(self.subcarrier_var.get()),
                "doppler_mode": self.doppler_mode_var.get(),
                "language": self.language_var.get(),
            },
        }

    def _save_project(self) -> None:
        target = filedialog.asksaveasfilename(
            title=self._text("save_project"),
            defaultextension=".swcsi",
            filetypes=[
                (self._text("project_filetypes"), "*.swcsi"),
                (self._text("all_files"), "*.*"),
            ],
        )
        if not target:
            return
        Path(target).write_text(json.dumps(self._project_state(), ensure_ascii=False, indent=2), encoding="utf-8")
        self._append_log(f"{self._text('project_saved')}: {target}")
        messagebox.showinfo(APP_NAME, f"{self._text('project_saved')}\n{target}")

    def _load_project(self) -> None:
        source = filedialog.askopenfilename(
            title=self._text("load_project"),
            filetypes=[
                (self._text("project_filetypes"), "*.swcsi"),
                (self._text("all_files"), "*.*"),
            ],
        )
        if not source:
            return
        data = json.loads(Path(source).read_text(encoding="utf-8"))
        serial_cfg = data.get("serial", {})
        device_cfg = data.get("device", {})
        capture_cfg = data.get("capture", {})
        view_cfg = data.get("view", {})

        self.port_var.set(serial_cfg.get("port", self.port_var.get()))
        self.baud_var.set(serial_cfg.get("baud", self.baud_var.get()))
        self.stream_mode_var.set(serial_cfg.get("stream_mode", self.stream_mode_var.get()))
        self.freq_var.set(device_cfg.get("tx_hz", self.freq_var.get()))
        self.channel_var.set(device_cfg.get("channel", self.channel_var.get()))
        self.label_var.set(capture_cfg.get("label", self.label_var.get()))
        self.scene_var.set(capture_cfg.get("scene", self.scene_var.get()))
        self.subject_var.set(capture_cfg.get("subject", self.subject_var.get()))
        self.layout_var.set(capture_cfg.get("layout", self.layout_var.get()))
        self.notes_var.set(capture_cfg.get("notes", self.notes_var.get()))
        self.out_dir_var.set(capture_cfg.get("out_dir", self.out_dir_var.get()))
        self.filename_var.set(capture_cfg.get("filename", self.filename_var.get()))
        self.subcarrier_var.set(int(view_cfg.get("subcarrier", self.subcarrier_var.get())))
        self.doppler_mode_var.set(view_cfg.get("doppler_mode", self.doppler_mode_var.get()))
        language = view_cfg.get("language", self.language_var.get())
        if language in LANGUAGES:
            self.language_var.set(language)
            self._save_settings()
            self._apply_language()
        self._append_log(f"{self._text('project_loaded')}: {source}")
        messagebox.showinfo(APP_NAME, f"{self._text('project_loaded')}\n{source}")

    def _open_settings(self) -> None:
        dialog = tk.Toplevel(self)
        dialog.title(self._text("settings"))
        dialog.transient(self)
        dialog.resizable(False, False)
        dialog.columnconfigure(1, weight=1)
        try:
            ico = RESOURCE_ICON_ICO if RESOURCE_ICON_ICO.exists() else ICON_ICO
            if sys.platform == "win32" and ico.exists():
                dialog.iconbitmap(str(ico))
        except Exception:
            pass

        ttk.Label(dialog, text=f"{APP_NAME} {APP_VERSION}", style="Header.TLabel").grid(row=0, column=0, columnspan=3, sticky="w", padx=16, pady=(16, 8))
        ttk.Label(dialog, text=self._text("language")).grid(row=1, column=0, sticky="w", padx=16, pady=8)
        language_combo = ttk.Combobox(
            dialog,
            textvariable=self.language_var,
            state="readonly",
            values=list(LANGUAGES.keys()),
            width=18,
        )
        language_combo.grid(row=1, column=1, columnspan=2, sticky="ew", padx=(4, 16), pady=8)

        ttk.Label(dialog, text=self._text("default_dir")).grid(row=2, column=0, sticky="w", padx=16, pady=8)
        ttk.Entry(dialog, textvariable=self.out_dir_var, width=42).grid(row=2, column=1, sticky="ew", padx=(4, 6), pady=8)
        ttk.Button(dialog, text="...", width=4, command=self._choose_out_dir).grid(row=2, column=2, sticky="ew", padx=(0, 16), pady=8)

        ttk.Label(dialog, text=self._text("contact")).grid(row=3, column=0, sticky="w", padx=16, pady=8)
        ttk.Label(dialog, text=CONTACT_EMAIL).grid(row=3, column=1, columnspan=2, sticky="w", padx=(4, 16), pady=8)

        button_row = ttk.Frame(dialog)
        button_row.grid(row=4, column=0, columnspan=3, sticky="e", padx=16, pady=(12, 16))
        ttk.Button(button_row, text=self._text("cancel"), command=dialog.destroy).grid(row=0, column=0, padx=(0, 8))
        ttk.Button(button_row, text=self._text("save"), command=lambda: self._save_settings_dialog(dialog)).grid(row=0, column=1)

    def _save_settings_dialog(self, dialog: tk.Toplevel) -> None:
        self._save_settings()
        self._apply_language()
        dialog.destroy()

    def _show_about(self) -> None:
        messagebox.showinfo(
            self._text("about"),
            f"{APP_NAME} {APP_VERSION}\nWi-Fi CSI capture and sensing workbench\n\nContact: {CONTACT_EMAIL}",
        )

    def _refresh_ports(self) -> None:
        ports = [p.device for p in list_ports.comports()]
        self.port_combo["values"] = ports
        if ports and self.port_var.get() not in ports:
            self.port_var.set(ports[0])
        self._append_log(f"已刷新串口：{', '.join(ports) if ports else '未发现串口'}")

    def _choose_out_dir(self) -> None:
        selected = filedialog.askdirectory(initialdir=self.out_dir_var.get() or str(PROJECT_ROOT))
        if selected:
            self.out_dir_var.set(selected)

    def _open_out_dir(self) -> None:
        out_dir = Path(self.out_dir_var.get())
        out_dir.mkdir(parents=True, exist_ok=True)
        try:
            if sys.platform == "win32":
                os.startfile(out_dir)
            elif sys.platform == "darwin":
                subprocess.run(["open", str(out_dir)], check=False)
            else:
                subprocess.run(["xdg-open", str(out_dir)], check=False)
        except Exception as exc:
            messagebox.showerror("打开目录失败", str(exc))

    def _toggle_connect(self) -> None:
        if self.reader:
            self._disconnect()
        else:
            self._connect()

    def _connect(self) -> None:
        port = self.port_var.get().strip()
        if not port:
            messagebox.showerror(APP_NAME, "请先选择接收端 ESP32-S3 对应的 COM 口。")
            return
        try:
            baud = int(self.baud_var.get())
        except ValueError:
            messagebox.showerror(APP_NAME, "波特率必须是数字，例如 921600。")
            return

        self.stop_event.clear()
        if self.stream_mode_var.get().upper() == "BIN":
            self.reader = BinarySerialReader(port, baud, self.events, self.stop_event)
        else:
            self.reader = SerialReader(port, baud, self.events, self.stop_event)
        self.reader.start()
        self.connect_button.configure(text=self._text("disconnect"))

    def _disconnect(self) -> None:
        self.stop_event.set()
        self.reader = None
        self.connect_button.configure(text=self._text("connect"))

    def _send_command(self, command: str) -> None:
        try:
            if not self.reader:
                raise RuntimeError("请先连接串口。")
            self.reader.write_line(command)
            self._append_log(f"> {command}")
        except Exception as exc:
            messagebox.showerror(APP_NAME, str(exc))

    def _toggle_capture(self) -> None:
        if self.csv_capture.active or self.binary_capture.active:
            self.csv_capture.stop()
            self.binary_capture.stop()
            self.capture_button.configure(text=self._text("start_capture"))
            self._append_log("采集已停止")
            return

        out_dir = Path(self.out_dir_var.get())
        filename = self.filename_var.get().strip()
        binary_mode = self.stream_mode_var.get().upper() == "BIN"
        suffix = ".csibin" if binary_mode else ".csv"
        if not filename:
            filename = time.strftime(f"%Y%m%d_%H%M%S_capture{suffix}")
            self.filename_var.set(filename)
        if not filename.lower().endswith(suffix):
            filename = str(Path(filename).with_suffix(suffix))
            self.filename_var.set(filename)

        metadata = {
            "label": self.label_var.get(),
            "scene": self.scene_var.get(),
            "subject": self.subject_var.get(),
            "layout": self.layout_var.get(),
            "notes": self.notes_var.get(),
            "port": self.port_var.get(),
            "baud": int(self.baud_var.get()),
            "channel_hint": self.channel_var.get(),
            "tx_hz_hint": self.freq_var.get(),
            "stream_mode": self.stream_mode_var.get(),
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        if binary_mode:
            self.binary_capture.start(out_dir / filename, metadata)
        else:
            self.csv_capture.start(out_dir / filename, metadata)
        self.capture_button.configure(text=self._text("stop_capture"))
        self._append_log(f"开始采集：{out_dir / filename}")

    def _export_capture_package(self) -> None:
        source_dir = Path(self.out_dir_var.get())
        if not source_dir.exists():
            messagebox.showerror("导出失败", "当前数据目录不存在。")
            return

        default_name = f"CSI采集数据包_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
        target = filedialog.asksaveasfilename(
            title="导出采集数据包",
            initialfile=default_name,
            defaultextension=".zip",
            filetypes=[("ZIP 压缩包", "*.zip")],
        )
        if not target:
            return
        self._make_zip_from_dir(source_dir, Path(target), include_root=False)
        self._append_log(f"已导出采集数据包：{target}")
        messagebox.showinfo("导出完成", f"采集数据包已导出：\n{target}")

    def _export_project_package(self) -> None:
        default_name = f"SwCSI工作台项目包_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
        target = filedialog.asksaveasfilename(
            title=self._text("export_project"),
            initialfile=default_name,
            defaultextension=".zip",
            filetypes=[("ZIP 压缩包", "*.zip")],
        )
        if not target:
            return

        target_path = Path(target)
        temp_dir = PROJECT_ROOT / ".export_workbench"
        if temp_dir.exists():
            shutil.rmtree(temp_dir)
        temp_dir.mkdir(parents=True)
        try:
            items = [
                PROJECT_ROOT / "README.md",
                PROJECT_ROOT / "LICENSE",
                PROJECT_ROOT / "CHANGELOG.md",
                PROJECT_ROOT / "requirements.txt",
                PROJECT_ROOT / "start_csi_workbench.bat",
                PROJECT_ROOT / "assets" / "swcsi_icon.png",
                PROJECT_ROOT / "assets" / "swcsi_icon.ico",
                PROJECT_ROOT / "tools" / "csi_workbench.py",
                PROJECT_ROOT / "tools" / "csi_common.py",
                PROJECT_ROOT / "tools" / "csi_binary_common.py",
                PROJECT_ROOT / "tools" / "csi_binary_capture.py",
                PROJECT_ROOT / "tools" / "csi_binary_inspect.py",
                PROJECT_ROOT / "tools" / "csi_quality_report.py",
                PROJECT_ROOT / "tools" / "csi_capture.py",
                PROJECT_ROOT / "tools" / "csi_plot_csv.py",
                PROJECT_ROOT / "tools" / "close_esp_idf_monitors.ps1",
                PROJECT_ROOT / "docs" / "CSI-workbench.md",
                PROJECT_ROOT / "docs" / "release-v1.0.1.md",
                PROJECT_ROOT / "docs" / "ESP32-S3-CSI-roadmap.md",
                PROJECT_ROOT / "esp32s3_csi_node" / "README.md",
            ]
            for item in items:
                if not item.exists():
                    continue
                rel = item.relative_to(PROJECT_ROOT)
                dst = temp_dir / rel
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(item, dst)

            export_readme = temp_dir / "导出说明.txt"
            export_readme.write_text(
                f"{APP_NAME} 工作台项目包\n\n"
                "启动方式：双击 start_csi_workbench.bat，或执行 py -3.9 tools\\csi_workbench.py。\n"
                "采集前请关闭 VS Code 的 ESP-IDF Monitor，避免占用同一个 COM 口。\n"
                "RX 板使用 mode rx，TX 板使用 mode tx，二者 channel 必须一致。\n",
                encoding="utf-8",
            )
            self._make_zip_from_dir(temp_dir, target_path, include_root=False)
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

        self._append_log(f"{self._text('export_project')}：{target}")
        messagebox.showinfo(APP_NAME, f"{self._text('export_project')}：\n{target}")

    def _make_zip_from_dir(self, source_dir: Path, target_zip: Path, include_root: bool) -> None:
        import zipfile

        target_zip.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(target_zip, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for path in source_dir.rglob("*"):
                if path.is_dir():
                    continue
                if path == target_zip:
                    continue
                rel = path.relative_to(source_dir.parent if include_root else source_dir)
                zf.write(path, rel)

    def _poll_events(self) -> None:
        while True:
            try:
                kind, payload = self.events.get_nowait()
            except queue.Empty:
                break

            if kind == "frame":
                received_at, frame = payload
                self._handle_frame(frame, received_at)
            elif kind == "binary_frame":
                received_at, record, record_bytes = payload
                frame = self._frame_from_binary_record(record)
                self._handle_frame(frame, received_at, record, record_bytes)
            elif kind == "state":
                text = self._text("not_connected") if payload == "disconnected" else payload.replace("connected", "已连接")
                self.status_var.set(text)
                self._append_log(text)
                if payload == "disconnected":
                    self.connect_button.configure(text=self._text("connect"))
            elif kind == "bad":
                self.bad_count += 1
                if self.bad_count <= 5 or self.bad_count % 100 == 0:
                    self._append_log(f"坏行#{self.bad_count} {payload}")
            elif kind == "error":
                msg = self._friendly_serial_error(payload)
                self._append_log(f"错误 {msg}")
                messagebox.showerror(APP_NAME, msg)
            elif kind == "log":
                self._append_log(payload)
            elif kind == "bin_skip":
                self.binary_skipped = int(payload)

        self.after(80, self._poll_events)

    def _frame_from_binary_record(self, record: BinaryCsiRecord) -> CsiFrame:
        h = record.header
        raw = record.raw_i8.astype(int).tolist()
        values = [
            "CSI_DATA",
            str(h["record_seq"]),
            "bin",
            str(h["rssi"]),
            str(h["rate"]),
            str(h["sig_mode"]),
            str(h["mcs"]),
            str(h["bandwidth"]),
            str(h["smoothing"]),
            str(h["not_sounding"]),
            str(h["aggregation"]),
            str(h["stbc"]),
            str(h["fec_coding"]),
            str(h["sgi"]),
            str(h["noise_floor"]),
            str(h["ampdu_cnt"]),
            str(h["channel"]),
            str(h["secondary_channel"]),
            str(h["local_timestamp_us"]),
            str(h["ant"]),
            str(h["sig_len"]),
            str(h["rx_state"]),
            str(h["tx_seq"]),
            str(h["tx_timestamp_us"]),
            str(h["rx_timestamp_us"]),
            str(h["tx_payload_found"]),
            str(h["tx_payload_offset"]),
            str(h["payload_len"]),
            str(h["csi_len"]),
            str(h["first_word_invalid"]),
            str(raw),
        ]
        return CsiFrame(columns=list(ESP32_TIMED_COLUMNS), values=values, raw=raw)

    def _handle_frame(
        self,
        frame: CsiFrame,
        pc_now: float | None = None,
        binary_record: BinaryCsiRecord | None = None,
        binary_record_bytes: bytes | None = None,
    ) -> None:
        if pc_now is None:
            pc_now = time.time()
        amp = valid_amplitude(frame.raw)
        if amp.size == 0:
            return
        complex_csi = valid_complex_csi(frame.raw)
        self.latest_frame = frame
        self.current_columns = frame.columns
        self.amplitude_history.append(amp)
        self.complex_history.append(complex_csi)
        self.raw_history.append(frame.raw)
        self.timestamps.append(pc_now)
        self.pc_time_history.append(pc_now)
        self._append_timing_history(frame)

        try:
            rssi_index = frame.columns.index("rssi")
            self.rssi_history.append(float(frame.values[rssi_index]))
        except Exception:
            self.rssi_history.append(np.nan)

        self.frame_count += 1
        self.last_frame_time = pc_now
        if binary_record is not None and binary_record_bytes is not None and self.binary_capture.active:
            self.binary_capture.write(binary_record, binary_record_bytes, pc_now)
        elif not self.csv_capture.write(frame, self.label_var.get(), pc_now):
            self.bad_count += 1
            if self.bad_count <= 5 or self.bad_count % 100 == 0:
                self._append_log("坏行#%d 采集文件列格式变化，已丢弃该帧。" % self.bad_count)

    def _redraw(self) -> None:
        frames = list(self.amplitude_history)
        if frames:
            min_len = min(len(x) for x in frames)
            amp = np.vstack([x[:min_len] for x in frames])
            sub = min(max(int(self.subcarrier_var.get()), 0), min_len - 1)
            self.subcarrier_scale.configure(to=max(min_len - 1, 0))

            self.ax_heat.clear()
            self.ax_sub.clear()
            self.ax_rssi.clear()
            self.ax_iq.clear()
            self.ax_latest_amp.clear()
            self.ax_timing.clear()

            self.ax_heat.imshow(amp.T, aspect="auto", origin="lower", interpolation="nearest")
            self.ax_heat.set_title("CSI 幅度热力图")
            self.ax_heat.set_ylabel("子载波")

            raw_amp_line = amp[:, sub]
            smooth_amp_line = self._moving_average(raw_amp_line, SMOOTH_WINDOW)
            self.ax_sub.plot(raw_amp_line, color="#999999", linewidth=1.0, label="原始幅度")
            self.ax_sub.plot(smooth_amp_line, color="#1f77b4", linewidth=1.5, label=f"{SMOOTH_WINDOW}帧平滑")
            self.ax_sub.set_title(f"子载波 {sub}：原始幅度 vs 平滑幅度")
            self.ax_sub.set_ylabel("幅度")
            self.ax_sub.legend(loc="upper right", fontsize=8)

            rssi = np.asarray(list(self.rssi_history), dtype=float)
            self.ax_rssi.plot(rssi, color="#2ca02c", linewidth=1.2)
            self.ax_rssi.set_title("RSSI")
            self.ax_rssi.set_ylabel("dBm")
            self.ax_rssi.set_xlabel("最近帧")

            latest_raw = self.raw_history[-1] if self.raw_history else []
            latest_csi = valid_complex_csi(latest_raw)
            if latest_csi.size:
                self.ax_iq.scatter(latest_csi.real, latest_csi.imag, s=12, alpha=0.75, color="#6f4aa8")
                self.ax_iq.axhline(0, color="#999999", linewidth=0.7)
                self.ax_iq.axvline(0, color="#999999", linewidth=0.7)
                self.ax_iq.set_title("最新帧 I/Q 散点")
                self.ax_iq.set_xlabel("Real")
                self.ax_iq.set_ylabel("Imag")

            latest_amp = amp[-1]
            self.ax_latest_amp.plot(latest_amp, color="#ff7f0e", linewidth=1.1)
            self.ax_latest_amp.set_title("最新帧有效子载波幅度")
            self.ax_latest_amp.set_xlabel("有效子载波")
            self.ax_latest_amp.set_ylabel("幅度")

            self._plot_timing_alignment()

            self.figure.tight_layout(pad=2.0)
            self.canvas.draw_idle()
            self._plot_doppler()

            rate = self._frame_rate()
            latest_rssi = "N/A" if not len(rssi) or np.isnan(rssi[-1]) else f"{rssi[-1]:.0f}dBm"
            timing = self._latest_timing_inline()
            saved_count = self.binary_capture.count if self.binary_capture.active else self.csv_capture.count
            capture_state = f" 已保存={saved_count}" if (self.binary_capture.active or self.csv_capture.active) else ""
            skip_state = f" 跳字节={self.binary_skipped}" if self.binary_skipped else ""
            self.stats_var.set(
                f"帧数={self.frame_count} 错误={self.bad_count} 帧率={rate:.1f}Hz "
                f"RSSI={latest_rssi} 有效子载波={min_len} {timing}{capture_state}{skip_state}"
            )
        self.after(PLOT_REFRESH_MS, self._redraw)

    def _plot_doppler(self) -> None:
        for ax in (
            self.ax_doppler_spec,
            self.ax_doppler_signal,
            self.ax_doppler_profile,
            self.ax_doppler_phase,
        ):
            ax.clear()

        matrix = self._complex_history_matrix()
        if matrix is None or matrix.shape[0] < DOPPLER_MIN_FRAMES:
            self.ax_doppler_spec.axis("off")
            self.ax_doppler_spec.text(
                0.02,
                0.95,
                f"Doppler/STFT\n\n等待至少 {DOPPLER_MIN_FRAMES} 帧有效 CSI。",
                va="top",
                fontsize=11,
            )
            self.doppler_figure.tight_layout(pad=2.0)
            self.doppler_canvas.draw_idle()
            return

        fs = self._sample_rate()
        sub = min(max(int(self.subcarrier_var.get()), 0), matrix.shape[1] - 1)
        series, mode_text = self._doppler_series(matrix, sub)
        if series.size < DOPPLER_MIN_FRAMES:
            self.ax_doppler_spec.axis("off")
            self.ax_doppler_spec.text(0.02, 0.95, "Doppler/STFT\n\n有效动态信号不足。", va="top", fontsize=11)
            self.doppler_figure.tight_layout(pad=2.0)
            self.doppler_canvas.draw_idle()
            return

        spec_db, freqs, centers = self._stft_db(series, fs)
        if spec_db.size:
            extent = [centers[0], centers[-1], freqs[0], freqs[-1]]
            self.ax_doppler_spec.imshow(
                spec_db.T,
                aspect="auto",
                origin="lower",
                interpolation="nearest",
                extent=extent,
                vmin=-45,
                vmax=0,
                cmap="magma",
            )
            self.ax_doppler_spec.axhline(0, color="#eeeeee", linewidth=0.8)
            self.ax_doppler_spec.set_title(f"Doppler/STFT 频谱（{mode_text}，fs={fs:.1f}Hz）")
            self.ax_doppler_spec.set_xlabel("时间 s")
            self.ax_doppler_spec.set_ylabel("Doppler Hz")

            profile = np.nanmean(spec_db, axis=0)
            peak_index = int(np.nanargmax(profile)) if profile.size else 0
            peak_freq = freqs[peak_index] if freqs.size else np.nan
            self.ax_doppler_profile.plot(freqs, profile, color="#c23b22", linewidth=1.3)
            if np.isfinite(peak_freq):
                self.ax_doppler_profile.axvline(peak_freq, color="#333333", linestyle="--", linewidth=0.9)
            self.ax_doppler_profile.set_title(f"平均 Doppler 谱 峰值={peak_freq:.2f}Hz")
            self.ax_doppler_profile.set_xlabel("Doppler Hz")
            self.ax_doppler_profile.set_ylabel("相对能量 dB")
        else:
            self.ax_doppler_spec.axis("off")
            self.ax_doppler_spec.text(0.02, 0.95, "Doppler/STFT\n\n帧数不足以形成 STFT 窗。", va="top", fontsize=11)
            self.ax_doppler_profile.axis("off")

        t = np.arange(series.size, dtype=float) / max(fs, 1e-6)
        dynamic_amp = np.abs(series)
        self.ax_doppler_signal.plot(t, dynamic_amp, color="#1f77b4", linewidth=1.0)
        self.ax_doppler_signal.set_title("合成 CSI 动态幅度")
        self.ax_doppler_signal.set_xlabel("时间 s")
        self.ax_doppler_signal.set_ylabel("幅度")

        if series.size >= 2:
            phase_diff = np.angle(series[1:] * np.conj(series[:-1]))
            self.ax_doppler_phase.plot(t[1:], phase_diff, color="#6f4aa8", linewidth=0.9)
            self.ax_doppler_phase.axhline(0, color="#999999", linewidth=0.7)
            self.ax_doppler_phase.set_title("相邻帧相位差")
            self.ax_doppler_phase.set_xlabel("时间 s")
            self.ax_doppler_phase.set_ylabel("弧度")
        else:
            self.ax_doppler_phase.axis("off")

        self.doppler_figure.tight_layout(pad=2.0)
        self.doppler_canvas.draw_idle()

    def _complex_history_matrix(self) -> np.ndarray | None:
        frames = [x for x in self.complex_history if x.size]
        if not frames:
            return None
        min_len = min(len(x) for x in frames)
        if min_len < 4:
            return None
        matrix = np.vstack([x[:min_len] for x in frames]).astype(np.complex64)
        finite_cols = np.isfinite(matrix.real).all(axis=0) & np.isfinite(matrix.imag).all(axis=0)
        median_amp = np.nanmedian(np.abs(matrix), axis=0)
        good_cols = finite_cols & (median_amp > 1.0)
        if good_cols.sum() < 4:
            return None
        return matrix[:, good_cols]

    def _doppler_series(self, matrix: np.ndarray, sub: int) -> tuple[np.ndarray, str]:
        mode = self.doppler_mode_var.get()
        if mode == "当前子载波":
            sub = min(max(sub, 0), matrix.shape[1] - 1)
            series = matrix[:, sub].astype(np.complex64)
            return self._remove_slow_component(series), f"子载波{sub}"

        amp = np.abs(matrix)
        score = np.nanstd(amp, axis=0) / (np.nanmedian(amp, axis=0) + 1e-6)
        count = int(min(24, max(4, matrix.shape[1] // 4)))
        cols = np.argsort(score)[-count:]
        selected = matrix[:, cols].astype(np.complex64)
        selected /= np.nanmedian(np.abs(selected), axis=0, keepdims=True) + 1e-6
        selected -= np.nanmean(selected, axis=0, keepdims=True)
        try:
            u, s, _vh = np.linalg.svd(selected, full_matrices=False)
            series = u[:, 0] * s[0]
        except np.linalg.LinAlgError:
            series = np.nanmean(selected, axis=1)
        return self._remove_slow_component(series.astype(np.complex64)), f"多子载波合成{len(cols)}"

    def _remove_slow_component(self, series: np.ndarray) -> np.ndarray:
        if series.size < 5:
            return series
        window = min(21, max(5, series.size // 6))
        if window % 2 == 0:
            window += 1
        kernel = np.ones(window, dtype=np.float32) / window
        pad = window // 2
        real = np.convolve(np.pad(series.real, (pad, pad), mode="edge"), kernel, mode="valid")
        imag = np.convolve(np.pad(series.imag, (pad, pad), mode="edge"), kernel, mode="valid")
        detrended = series - (real + 1j * imag)
        scale = np.nanstd(np.abs(detrended))
        if np.isfinite(scale) and scale > 1e-6:
            detrended = detrended / scale
        return detrended

    def _stft_db(self, series: np.ndarray, fs: float) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        n = series.size
        window_len = min(DOPPLER_WINDOW, n)
        if window_len < DOPPLER_MIN_FRAMES:
            return np.empty((0, 0)), np.empty(0), np.empty(0)
        hop = max(1, min(DOPPLER_HOP, window_len // 2))
        window = np.hanning(window_len).astype(np.float32)
        specs = []
        centers = []
        for start in range(0, n - window_len + 1, hop):
            segment = series[start:start + window_len]
            segment = segment - np.nanmean(segment)
            spectrum = np.fft.fftshift(np.fft.fft(segment * window, n=DOPPLER_NFFT))
            power = np.abs(spectrum) ** 2
            specs.append(power)
            centers.append((start + window_len / 2.0) / max(fs, 1e-6))
        if not specs:
            return np.empty((0, 0)), np.empty(0), np.empty(0)
        spec = np.vstack(specs)
        spec_db = 10.0 * np.log10(spec + 1e-12)
        spec_db -= np.nanmax(spec_db)
        freqs = np.fft.fftshift(np.fft.fftfreq(DOPPLER_NFFT, d=1.0 / max(fs, 1e-6)))
        return spec_db, freqs, np.asarray(centers, dtype=float)

    def _sample_rate(self) -> float:
        times = np.asarray(list(self.timestamps), dtype=float)
        if times.size >= 4:
            dt = np.diff(times)
            dt = dt[np.isfinite(dt) & (dt > 0)]
            if dt.size:
                fs = 1.0 / float(np.nanmedian(dt))
                if 1.0 <= fs <= 500.0:
                    return fs
        try:
            configured = float(self.freq_var.get())
        except ValueError:
            configured = 50.0
        return max(1.0, min(configured, 500.0))

    def _frame_value(self, frame: CsiFrame, name: str) -> str | None:
        try:
            return frame.values[frame.columns.index(name)]
        except ValueError:
            return None

    def _frame_float(self, frame: CsiFrame, name: str) -> float:
        value = self._frame_value(frame, name)
        if value is None or value == "":
            return np.nan
        try:
            return float(value)
        except ValueError:
            return np.nan

    def _append_timing_history(self, frame: CsiFrame) -> None:
        self.tx_seq_history.append(self._frame_float(frame, "tx_seq"))
        self.tx_time_history.append(self._frame_float(frame, "tx_timestamp_us"))
        self.rx_time_history.append(self._frame_float(frame, "rx_timestamp_us"))

    def _latest_timing_inline(self) -> str:
        if not self.latest_frame or len(self.rx_time_history) < 2:
            return ""
        tx_seq = self._frame_value(self.latest_frame, "tx_seq")
        if tx_seq is None:
            return ""
        seq = np.asarray(list(self.tx_seq_history), dtype=float)
        rx = np.asarray(list(self.rx_time_history), dtype=float)
        valid_rx = np.isfinite(rx)
        if valid_rx.sum() < 2:
            return f"TX序号={tx_seq}"
        rx_unwrapped = self._unwrap_u32_us(rx[valid_rx])
        rx_dt_ms = np.diff(rx_unwrapped) / 1000.0
        rx_text = f"RX间隔={rx_dt_ms[-1]:.1f}ms" if rx_dt_ms.size else ""
        if not self._seq_is_useful(seq):
            return f"TX序号异常 {rx_text}"
        gaps = np.diff(seq[np.isfinite(seq)])
        lost = int(np.nansum(np.maximum(gaps - 1, 0))) if gaps.size else 0
        return f"TX序号={tx_seq} 丢包估计={lost} {rx_text}"

    def _latest_timing_text(self) -> str:
        if not self.latest_frame:
            return "时间对齐：暂无数据"
        tx_seq = self._frame_value(self.latest_frame, "tx_seq")
        tx_ts = self._frame_value(self.latest_frame, "tx_timestamp_us")
        rx_ts = self._frame_value(self.latest_frame, "rx_timestamp_us")
        payload_len = self._frame_value(self.latest_frame, "tx_payload_len")
        payload_found = self._frame_value(self.latest_frame, "tx_payload_found")
        payload_offset = self._frame_value(self.latest_frame, "tx_payload_offset")
        if tx_seq is None:
            return "接收节奏：当前固件未输出 TX 序号"
        return (
            "接收节奏字段\n"
            f"TX序号：{tx_seq}\n"
            f"TX时间戳：{tx_ts} us\n"
            f"RX时间戳：{rx_ts} us\n"
            f"TX负载检测：{payload_found or '旧固件'}\n"
            f"TX负载偏移：{payload_offset or '旧固件'}\n"
            f"TX负载长度：{payload_len or '旧固件'}\n"
            "注意：两块 ESP32 的绝对时间戳不是同一个时钟，不能直接相减当传播延迟。"
        )

    def _plot_timing_alignment(self) -> None:
        seq = np.asarray(list(self.tx_seq_history), dtype=float)
        tx_us = np.asarray(list(self.tx_time_history), dtype=float)
        rx_us = np.asarray(list(self.rx_time_history), dtype=float)
        pc_s = np.asarray(list(self.pc_time_history), dtype=float)

        valid_rx = np.isfinite(rx_us) & np.isfinite(pc_s)
        if valid_rx.sum() < 2:
            self.ax_timing.axis("off")
            self.ax_timing.text(
                0.02,
                0.95,
                "接收节奏/丢包检查\n\n当前数据不足。",
                va="top",
                fontsize=10,
            )
            return

        rx_unwrapped = self._unwrap_u32_us(rx_us[valid_rx])
        pc_valid = pc_s[valid_rx]
        seq_valid = seq[valid_rx] if seq.size == valid_rx.size else np.full(rx_unwrapped.shape, np.nan)
        tx_valid = tx_us[valid_rx] if tx_us.size == valid_rx.size else np.full(rx_unwrapped.shape, np.nan)

        use_seq_axis = self._seq_is_useful(seq_valid)
        x = seq_valid if use_seq_axis else np.arange(rx_unwrapped.size, dtype=float)
        rx_dt_ms = np.diff(rx_unwrapped) / 1000.0
        pc_dt_ms = np.diff(pc_valid) * 1000.0

        self.ax_timing.plot(x[1:], rx_dt_ms, color="#d62728", linewidth=1.2, label="RX硬件间隔")
        self.ax_timing.plot(x[1:], pc_dt_ms, color="#1f77b4", linewidth=1.0, alpha=0.75, label="PC到达间隔")

        tx_dt_ms = np.asarray([])
        finite_tx = np.isfinite(tx_valid)
        if finite_tx.sum() >= 2:
            tx_unwrapped = self._unwrap_u32_us(tx_valid[finite_tx])
            candidate = np.diff(tx_unwrapped) / 1000.0
            if candidate.size and 0 < np.nanmedian(candidate) < 2000 and np.nanpercentile(np.abs(candidate), 95) < 5000:
                tx_x = x[finite_tx][1:] if x[finite_tx].size == tx_unwrapped.size else np.arange(candidate.size)
                tx_dt_ms = candidate
                self.ax_timing.plot(tx_x, tx_dt_ms, color="#ff7f0e", linewidth=1.0, alpha=0.75, label="TX发送间隔")

        self.ax_timing.set_title("接收节奏/丢包检查")
        self.ax_timing.set_xlabel("TX序号" if use_seq_axis else "帧索引")
        self.ax_timing.set_ylabel("相邻帧间隔 ms")

        lost = 0
        seq_status = "TX序号异常或旧固件"
        if use_seq_axis:
            seq_gap = np.diff(seq_valid[np.isfinite(seq_valid)])
            lost = int(np.nansum(np.maximum(seq_gap - 1, 0))) if seq_gap.size else 0
            if seq_gap.size:
                expected = np.nanmedian(rx_dt_ms) if rx_dt_ms.size else 1.0
                self.ax_timing.plot(x[1:], np.maximum(np.diff(seq_valid) - 1, 0) * expected, color="#9467bd", linewidth=0.8, alpha=0.55, label="丢包提示")
            seq_status = f"估计丢包={lost}"

        latest_rx = rx_dt_ms[-1] if rx_dt_ms.size else np.nan
        jitter = float(np.nanpercentile(rx_dt_ms, 95) - np.nanpercentile(rx_dt_ms, 5)) if rx_dt_ms.size >= 4 else 0.0
        self.ax_timing.text(
            0.02,
            0.05,
            f"{seq_status}  最新RX间隔={latest_rx:.2f}ms  抖动P95-P5={jitter:.2f}ms",
            transform=self.ax_timing.transAxes,
            fontsize=9,
            bbox={"facecolor": "white", "alpha": 0.7, "edgecolor": "#cccccc"},
        )
        self.ax_timing.legend(loc="upper left", fontsize=8)

    def _seq_is_useful(self, seq: np.ndarray) -> bool:
        finite = seq[np.isfinite(seq)]
        if finite.size < 2:
            return False
        gaps = np.diff(finite)
        return np.nanmax(finite) > np.nanmin(finite) and np.nanmedian(gaps) > 0

    def _unwrap_u32_us(self, values: np.ndarray) -> np.ndarray:
        if values.size == 0:
            return values
        unwrapped = values.astype(float).copy()
        offset = 0.0
        previous = unwrapped[0]
        wrap = float(2**32)
        for i in range(1, unwrapped.size):
            current = unwrapped[i] + offset
            if current - previous < -wrap / 2:
                offset += wrap
                current = unwrapped[i] + offset
            elif current - previous > wrap / 2:
                offset -= wrap
                current = unwrapped[i] + offset
            unwrapped[i] = current
            previous = current
        return unwrapped

    def _moving_average(self, values: np.ndarray, window: int) -> np.ndarray:
        if values.size == 0 or window <= 1:
            return values
        window = min(window, values.size)
        kernel = np.ones(window, dtype=float) / window
        padded = np.pad(values, (window - 1, 0), mode="edge")
        return np.convolve(padded, kernel, mode="valid")

    def _frame_rate(self) -> float:
        times = list(self.timestamps)
        if len(times) < 2:
            return 0.0
        window = times[-1] - times[0]
        if window <= 0:
            return 0.0
        return (len(times) - 1) / window

    def _append_log(self, text: str) -> None:
        self.log_text.insert("end", text + "\n")
        self.log_text.see("end")

    def _friendly_serial_error(self, text: str) -> str:
        if "PermissionError" in text or "拒绝访问" in text:
            return (
                text
                + "\n\nCOM 口被占用。请关闭 VS Code 的 ESP-IDF Monitor、其他串口助手、"
                "旧的上位机窗口，或断开后重新插拔设备。"
            )
        if "Unexpected CSI column count" in text or "CSI length mismatch" in text:
            return (
                text
                + "\n\nCSI 行解析失败。常见原因是串口波特率过低或波特率不一致。"
                "建议固件和上位机都使用 921600；如果仍然错误多，可以降低 TX 频率，例如 freq 50。"
            )
        if "FileNotFoundError" in text or "系统找不到" in text:
            return text + "\n\n没有找到该 COM 口，请点击“刷新”并重新选择端口。"
        return text

    def destroy(self) -> None:
        self.csv_capture.stop()
        self.binary_capture.stop()
        self.stop_event.set()
        super().destroy()


def main() -> None:
    app = CsiWorkbench()
    app.mainloop()


if __name__ == "__main__":
    main()
