# SwCSI 使用说明

SwCSI 是本项目的 Windows 桌面工作台，用于 ESP32-S3 CSI 数据采集、实时可视化和数据导出。

## 启动方式

推荐直接双击：

```text
F:\1\csi\start_csi_workbench.bat
```

或在 PowerShell 中运行：

```powershell
cd F:\1\csi
py -3.9 tools\csi_workbench.py
```

如果你在 Windows `cmd` 里启动，跨盘符切换要写成：

```bat
cd /d F:\1\csi
py -3.9 tools\csi_workbench.py
```

## 板子配置

两块 ESP32-S3 烧录同一个 `esp32s3_csi_node` 固件。

发送端输入：

```text
mode tx
channel 11
freq 50
```

接收端输入：

```text
mode rx
channel 11
```

TX 和 RX 的 `channel` 必须一致。采集时电脑连接 RX 板。

## SwCSI 功能

- 串口连接：选择 RX 板 COM 口，点击“连接”。
- 读取模式：`BIN` 用于二进制实时采集和正式数据保存；`CSV` 用于文字调试和发送/查看设备命令。
- 设备命令：直接发送 `status`、`mode tx`、`mode rx`、`freq`、`channel`。
- 实时显示：CSI 幅度热力图、指定子载波幅度曲线、RSSI 曲线。
- 原始信号对比：显示指定子载波“原始幅度 vs 平滑幅度”、最新帧原始 I/Q 序列、最新帧全子载波幅度。
- Doppler/STFT 视图：把最近 CSI 转成动态序列并做短时频谱，适合观察动作造成的低频 Doppler 能量变化。
- 接收质量检查：新固件会在 TX 包中携带 `magic`、`tx_seq` 和 `tx_timestamp_us`，RX 会输出 `tx_payload_found`、`tx_payload_offset`、`tx_payload_len` 与 `rx_timestamp_us`；上位机会显示 RX 硬件间隔、PC 到达间隔、TX 发送间隔和丢包提示。
- 采集保存：点击“开始采集”保存 CSV，点击“停止采集”结束。
- 元数据记录：自动生成同名 JSON，记录标签、场景、对象、布局、备注、串口、波特率、信道、发送频率和开始时间。
- 打开数据目录：快速打开当前采集目录。
- 导出采集数据包：把当前数据目录中的 CSV/JSON 等采集结果打包成 ZIP。
- 导出工作台项目包：把 SwCSI 源码、启动脚本、依赖文件和说明文档打包成 ZIP，方便拷贝到其他电脑。

## 二进制采集

GUI 已支持 `BIN` 二进制实时模式。CSV 适合调试和观察文字输出，BIN 适合作为最终数据集采集方式。Intel 5300 CSI Tool 的典型流程是内核把 CSI 通过 netlink 交给用户态，用户态 `log_to_file` 直接写二进制记录，再由离线脚本解析。ESP32-S3 这边也提供类似模式：

1. 先用 CSV/GUI 确认 RX 能收到 CSI。
2. 给 RX 板发送：

```text
output bin
```

3. 关闭 VS Code Monitor，打开 SwCSI，左上角读取模式选择 `BIN`，连接 RX 的 COM 口。
4. 点击“开始采集”，文件会保存为 `.csibin`，并同时生成 `.summary.csv` 和 `.json`。

也可以不用 GUI，直接用二进制采集脚本独占 COM 口：

```powershell
cd F:\1\csi
py -3.9 tools\csi_binary_capture.py --port COM15 --baud 921600 --out data\raw\test_rx.csibin --label test --duration 60
```

采完检查质量：

```powershell
py -3.9 tools\csi_binary_inspect.py data\raw\test_rx.csibin
```

质量合格的基本条件：

- `tx_payload_found` 基本全是 `1`。
- `tx_seq gaps` 主要是 `(1, N)`，也就是发送序号连续。
- `rx_interval_ms` 接近发送周期，例如 `freq 50` 时中位数应接近 `20 ms`。
- `valid_subcarriers_sample` 稳定，当前 HT40 配置通常约为 `166`。

如果要回到 GUI/CSV 调试，重新连接 Monitor 后发送：

```text
output csv
```

## 导出说明

### 生成安装包

项目内已经提供安装包构建脚本：

```powershell
cd F:\1\csi
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\build_workbench_installer.ps1
```

生成结果：

- `dist_installer\SwCSI_V1.0.1_Setup.exe`：普通用户安装包，安装到 `%LOCALAPPDATA%\Programs\SwCSI`。
- `dist_installer\SwCSI_V1.0.1_Portable.zip`：便携版，解压后直接运行 `SwCSI.exe`。

安装包会创建桌面快捷方式、开始菜单快捷方式和开始菜单卸载入口。

### 导出采集数据包

用于提交或备份实验数据。内容来自界面中“目录”字段对应的文件夹，通常包括：

- `.csv` 原始 CSI 采集文件
- `.json` 采集元数据文件
- 后续你放入该目录的说明、截图或标注文件

### 导出工作台项目包

用于迁移 SwCSI 程序。压缩包包含：

- `tools/csi_workbench.py`
- `tools/csi_common.py`
- `tools/csi_capture.py`
- `tools/csi_plot_csv.py`
- `requirements.txt`
- `start_csi_workbench.bat`
- `docs/CSI-workbench.md`
- 固件 README 等必要说明

不包含大体积采集数据和论文 PDF。

## 常见问题

### Doppler/STFT 视图怎么看

上方页签切到 `Doppler/STFT`。左侧 `Doppler` 模式建议先用 `合成`，它会从多个动态明显的子载波中提取一条主运动序列；如果想排查某一个子载波，再切到 `当前子载波` 并拖动子载波滑块。

- `Doppler/STFT 频谱`：人在动时，0Hz 附近之外会出现随时间变化的能量条纹。
- `平均 Doppler 谱`：看最近窗口里主要能量集中在哪些 Doppler 频率。
- `合成 CSI 动态幅度`：看动作是否引起可见起伏。
- `相邻帧相位差`：辅助观察快速相位扰动，单天线绝对相位不稳定时不要单独依赖这张图。

如果 RSSI 变化很明显但 Doppler/STFT 很淡，优先尝试让 TX/RX 距离拉开一点，目标 RSSI 大致落在 `-35 dBm` 到 `-60 dBm`，避免近距离强直达径把 CSI 动态淹掉。

### 刷新频率是多少

- TX 默认发送频率：`50 Hz`，可用 `freq 50` 或 `freq 100` 修改。调试阶段建议先用 `50 Hz`，稳定后再升高。
- 上位机串口读取：后台线程实时读取，不主动限速。
- 上位机图表刷新：`100 ms` 一次，约 `10 FPS`。
- 图表缓存：最近 `240` 帧。若 TX 为 100Hz，约显示最近 2.4 秒数据。

### 错误很多怎么办

优先检查波特率。CSI 数据行很长，100Hz 输出时 `115200` 很容易不够，表现为：

- `Unexpected CSI column count`
- `CSI length mismatch`
- 上位机“错误”数量快速增加
- 串口日志中出现半截数组或粘连行

建议先统一为：

```text
固件 monitor baud：921600
上位机 baud：921600
TX 频率：freq 50 或 freq 100
```

如果 `921600` 下仍然错误多，先把 TX 降到：

```text
freq 50
```

### 中文标题显示成方框

上位机已设置 Matplotlib 中文字体候选：

```text
Microsoft YaHei
SimHei
SimSun
Arial Unicode MS
DejaVu Sans
```

如果仍显示方框，说明系统缺少对应字体，可以安装微软雅黑或黑体后重启上位机。

### COM 口拒绝访问

说明该串口被其他程序占用。关闭以下程序后再连接：

- VS Code 的 ESP-IDF Monitor
- 其他串口助手
- 旧的上位机窗口
- 正在运行的 Python 采集脚本

同一个 COM 口同一时间只能被一个程序打开。

### 没有 CSI 图像

检查：

- RX 板是否为 `mode rx`
- TX 板是否为 `mode tx`
- 两块板是否在同一个 `channel`
- 上位机连接的是 RX 板 COM 口
- 串口波特率是否为 `921600`

### 数据怎么二次查看

采集后的 CSV 可以用已有脚本绘图：

```powershell
cd F:\1\csi
py -3.9 tools\csi_plot_csv.py data\raw\your_capture.csv --subcarrier 20
```

### I/Q 图是不是时间对齐图

不是。最新帧 I/Q 图现在显示 Real-vs-Imag 散点，可以理解为一个 CSI 包内部有效子载波的复数分布，不是时间轴。

I 和 Q 是复数 CSI 的两个正交分量，本来就不要求重合，也可能出现方向相反、相位差明显的形态。判断采集是否正常不要看 I/Q 是否“对齐”。

判断采集质量应看“接收节奏/丢包检查”图：

- `RX硬件间隔`：RX 端硬件时间戳的相邻帧间隔。
- `PC到达间隔`：上位机读到完整串口行的相邻间隔。
- `TX发送间隔`：如果新固件正确找到 TX payload，则显示 TX 端发送间隔。
- `丢包提示`：根据 `tx_seq` 序号间隔估计。

后续做动作识别或数据集切片时，建议优先按 `tx_seq` 和 RX 本地时间序列切片，PC 到达时间只作为辅助记录。

旧版固件曾输出 `time_delta_us = rx_timestamp_us - tx_timestamp_us`。这个字段是两个 ESP32 本地时钟的绝对相减，没有物理意义，可能出现几十秒甚至几十分钟的巨大负数。新版固件不再输出该字段，改为输出 `tx_payload_found`、`tx_payload_offset` 和 `tx_payload_len`，用于检查 TX payload 是否按预期携带序号和时间戳。

如果 `tx_payload_found=0` 或 TX 序号一直不变，优先检查：

1. 两块板是否都重新烧录了同一版新固件。
2. RX 板是否为 `mode rx`，TX 板是否为 `mode tx`。
3. 两块板 `channel` 是否一致。
4. 是否仍有大量解析错误或丢包。
5. 串口是否统一为 `921600`。
6. TX 频率是否过高，可先降到 `freq 50`。
7. RX 端是否同时开着 VS Code Monitor 和上位机，导致串口竞争。
