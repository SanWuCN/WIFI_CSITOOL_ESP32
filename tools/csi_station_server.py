from __future__ import annotations

import argparse
import binascii
import hashlib
import json
import threading
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import serial
from serial.tools import list_ports


PROJECT_ROOT = Path(__file__).resolve().parents[1]
STATE_DIR = PROJECT_ROOT / "data" / "station"
FIRMWARE_DIR = STATE_DIR / "firmware"
DEVICES_PATH = STATE_DIR / "devices.json"


INDEX_HTML = r"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>ESP32-S3 CSI 基站管理</title>
  <style>
    body{font-family:Segoe UI,Microsoft YaHei,sans-serif;margin:0;background:#f6f7f9;color:#1f2937}
    header{background:#18212f;color:white;padding:14px 22px}
    main{display:grid;grid-template-columns:330px 1fr;gap:16px;padding:16px}
    section{background:white;border:1px solid #d9dee7;border-radius:6px;padding:14px}
    h2{font-size:16px;margin:0 0 12px}
    label{display:block;font-size:13px;margin:8px 0 3px;color:#4b5563}
    input,select,button{font:inherit;box-sizing:border-box}
    input,select{width:100%;padding:7px;border:1px solid #cbd5e1;border-radius:4px}
    button{padding:7px 10px;border:1px solid #9aa7b7;background:#edf2f7;border-radius:4px;cursor:pointer}
    button.primary{background:#2563eb;color:white;border-color:#1d4ed8}
    button.danger{background:#fee2e2;border-color:#fca5a5}
    table{width:100%;border-collapse:collapse;font-size:13px}
    th,td{border-bottom:1px solid #e5e7eb;padding:8px;text-align:left;vertical-align:top}
    code{background:#f1f5f9;padding:2px 4px;border-radius:3px}
    .row{display:flex;gap:8px;align-items:center}
    .row>*{flex:1}
    .log{height:170px;overflow:auto;background:#0f172a;color:#d1e7ff;padding:10px;border-radius:4px;font-family:Consolas,monospace;font-size:12px}
  </style>
</head>
<body>
  <header><strong>ESP32-S3 CSI 基站管理</strong></header>
  <main>
    <div>
      <section>
        <h2>绑定设备</h2>
        <label>设备地址/ID</label><input id="devId" placeholder="rx-001">
        <label>名称</label><input id="devName" placeholder="实验室 RX">
        <label>传输方式</label><select id="transport"><option value="serial">Serial</option><option value="http">HTTP OTA</option></select>
        <label>串口/URL</label><input id="endpoint" placeholder="COM15 或 http://192.168.4.2">
        <button class="primary" onclick="bindDevice()">绑定/更新</button>
      </section>
      <section>
        <h2>上传固件</h2>
        <input id="fwFile" type="file" accept=".bin">
        <label>版本备注</label><input id="fwNote" placeholder="v0.2 standby+bin">
        <button class="primary" onclick="uploadFirmware()">上传并校验</button>
        <p id="fwResult"></p>
      </section>
    </div>
    <section>
      <h2>设备列表</h2>
      <table>
        <thead><tr><th>地址</th><th>名称</th><th>端点</th><th>控制</th></tr></thead>
        <tbody id="devices"></tbody>
      </table>
      <h2 style="margin-top:18px">固件仓库</h2>
      <table>
        <thead><tr><th>ID</th><th>文件</th><th>CRC32</th><th>SHA256</th><th>大小</th></tr></thead>
        <tbody id="firmware"></tbody>
      </table>
      <h2 style="margin-top:18px">日志</h2>
      <div id="log" class="log"></div>
    </section>
  </main>
<script>
async function api(path, opts={}) {
  const res = await fetch(path, opts);
  const text = await res.text();
  let data; try { data = JSON.parse(text); } catch { data = {text}; }
  if (!res.ok) throw new Error(data.error || text || res.statusText);
  return data;
}
function log(msg){const el=document.getElementById('log'); el.textContent += `[${new Date().toLocaleTimeString()}] ${msg}\n`; el.scrollTop=el.scrollHeight;}
async function refresh(){
  const state = await api('/api/state');
  document.getElementById('devices').innerHTML = state.devices.map(d => `
    <tr><td><code>${d.id}</code></td><td>${d.name||''}</td><td>${d.transport}:${d.endpoint}</td>
    <td>
      <div class="row">
        <button onclick="cmd('${d.id}','status')">status</button>
        <button onclick="cmd('${d.id}','mode standby')">待机</button>
        <button onclick="cmd('${d.id}','mode rx')">RX</button>
        <button onclick="cmd('${d.id}','mode tx')">TX</button>
      </div>
      <div class="row" style="margin-top:6px">
        <button onclick="cmd('${d.id}','output bin')">BIN</button>
        <button onclick="cmd('${d.id}','output csv')">CSV</button>
        <button onclick="promptCmd('${d.id}')">自定义</button>
      </div>
    </td></tr>`).join('');
  document.getElementById('firmware').innerHTML = state.firmware.map(f => `
    <tr><td><code>${f.id}</code></td><td>${f.filename}</td><td><code>${f.crc32}</code></td><td><code>${f.sha256.slice(0,16)}...</code></td><td>${f.size}</td></tr>`).join('');
}
async function bindDevice(){
  const body = {
    id: devId.value.trim(), name: devName.value.trim(), transport: transport.value,
    endpoint: endpoint.value.trim()
  };
  await api('/api/devices', {method:'POST', headers:{'content-type':'application/json'}, body:JSON.stringify(body)});
  log(`绑定设备 ${body.id}`);
  refresh();
}
async function cmd(id, command){
  const ret = await api(`/api/devices/${encodeURIComponent(id)}/command`, {method:'POST', headers:{'content-type':'application/json'}, body:JSON.stringify({command})});
  log(`${id}> ${command}\n${ret.output||''}`);
}
function promptCmd(id){ const command = prompt('输入命令，例如 freq 50 或 channel 11'); if(command) cmd(id, command); }
async function uploadFirmware(){
  const file = fwFile.files[0]; if(!file) return alert('请选择 .bin 文件');
  const buf = await file.arrayBuffer();
  const note = encodeURIComponent(fwNote.value || '');
  const ret = await api(`/api/firmware?filename=${encodeURIComponent(file.name)}&note=${note}`, {method:'POST', body:buf});
  fwResult.innerHTML = `CRC32 <code>${ret.crc32}</code><br>SHA256 <code>${ret.sha256}</code>`;
  log(`上传固件 ${ret.filename}`);
  refresh();
}
refresh().catch(e=>log(e.message));
</script>
</body>
</html>
"""


def ensure_state() -> None:
    FIRMWARE_DIR.mkdir(parents=True, exist_ok=True)
    if not DEVICES_PATH.exists():
        DEVICES_PATH.write_text("[]", encoding="utf-8")


def read_devices() -> list[dict]:
    ensure_state()
    return json.loads(DEVICES_PATH.read_text(encoding="utf-8"))


def write_devices(devices: list[dict]) -> None:
    ensure_state()
    DEVICES_PATH.write_text(json.dumps(devices, ensure_ascii=False, indent=2), encoding="utf-8")


def list_firmware() -> list[dict]:
    ensure_state()
    items = []
    for meta_path in sorted(FIRMWARE_DIR.glob("*.json"), reverse=True):
        try:
            items.append(json.loads(meta_path.read_text(encoding="utf-8")))
        except Exception:
            continue
    return items


def send_serial_command(port: str, command: str, baud: int = 921600) -> str:
    with serial.Serial(port, baud, timeout=0.7) as ser:
        ser.reset_input_buffer()
        ser.write((command.strip() + "\n").encode("utf-8"))
        ser.flush()
        time.sleep(0.25)
        return ser.read(4096).decode("utf-8", errors="replace")


class Handler(BaseHTTPRequestHandler):
    server_version = "CSIStation/0.1"

    def _send(self, data: bytes, content_type: str = "application/json", status: int = 200) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _json(self, obj, status: int = 200) -> None:
        self._send(json.dumps(obj, ensure_ascii=False).encode("utf-8"), status=status)

    def _body(self) -> bytes:
        length = int(self.headers.get("Content-Length", "0"))
        return self.rfile.read(length) if length else b""

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/":
            self._send(INDEX_HTML.encode("utf-8"), "text/html; charset=utf-8")
            return
        if parsed.path == "/api/state":
            self._json({"devices": read_devices(), "firmware": list_firmware(), "ports": [p.device for p in list_ports.comports()]})
            return
        if parsed.path.startswith("/firmware/"):
            name = Path(parsed.path).name
            path = FIRMWARE_DIR / name
            if not path.exists() or path.suffix != ".bin":
                self._json({"error": "firmware not found"}, HTTPStatus.NOT_FOUND)
                return
            self._send(path.read_bytes(), "application/octet-stream")
            return
        self._json({"error": "not found"}, HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/devices":
            payload = json.loads(self._body().decode("utf-8"))
            if not payload.get("id") or not payload.get("endpoint"):
                self._json({"error": "id and endpoint are required"}, HTTPStatus.BAD_REQUEST)
                return
            devices = [d for d in read_devices() if d.get("id") != payload["id"]]
            payload.setdefault("transport", "serial")
            payload["updated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
            devices.append(payload)
            write_devices(devices)
            self._json(payload)
            return

        if parsed.path.startswith("/api/devices/") and parsed.path.endswith("/command"):
            dev_id = parsed.path.split("/")[3]
            payload = json.loads(self._body().decode("utf-8"))
            command = payload.get("command", "")
            device = next((d for d in read_devices() if d.get("id") == dev_id), None)
            if not device:
                self._json({"error": "device not found"}, HTTPStatus.NOT_FOUND)
                return
            if device.get("transport") != "serial":
                self._json({"error": "HTTP device command/OTA firmware endpoint is planned but not enabled in firmware yet."}, HTTPStatus.NOT_IMPLEMENTED)
                return
            try:
                output = send_serial_command(device["endpoint"], command)
            except Exception as exc:
                self._json({"error": str(exc)}, HTTPStatus.INTERNAL_SERVER_ERROR)
                return
            self._json({"ok": True, "output": output})
            return

        if parsed.path == "/api/firmware":
            query = parse_qs(parsed.query)
            filename = Path(query.get("filename", ["firmware.bin"])[0]).name
            note = query.get("note", [""])[0]
            if not filename.endswith(".bin"):
                self._json({"error": "firmware filename must end with .bin"}, HTTPStatus.BAD_REQUEST)
                return
            blob = self._body()
            if not blob:
                self._json({"error": "empty firmware"}, HTTPStatus.BAD_REQUEST)
                return
            sha256 = hashlib.sha256(blob).hexdigest()
            crc32 = f"{binascii.crc32(blob) & 0xffffffff:08x}"
            fw_id = f"{int(time.time())}_{crc32}"
            out_name = f"{fw_id}_{filename}"
            out_path = FIRMWARE_DIR / out_name
            out_path.write_bytes(blob)
            meta = {
                "id": fw_id,
                "filename": out_name,
                "original_filename": filename,
                "size": len(blob),
                "crc32": crc32,
                "sha256": sha256,
                "note": note,
                "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                "url": f"/firmware/{out_name}",
            }
            (FIRMWARE_DIR / f"{fw_id}.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
            self._json(meta)
            return

        self._json({"error": "not found"}, HTTPStatus.NOT_FOUND)

    def log_message(self, fmt: str, *args) -> None:
        print("[%s] %s" % (self.log_date_time_string(), fmt % args))


def main() -> None:
    parser = argparse.ArgumentParser(description="ESP32-S3 CSI station management web UI.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8088)
    args = parser.parse_args()
    ensure_state()
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"CSI station server: http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        threading.Thread(target=server.shutdown, daemon=True).start()


if __name__ == "__main__":
    main()
