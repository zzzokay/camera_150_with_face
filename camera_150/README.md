# camera_150：RK3588 篮球赛事智能拍摄系统

单路 USB3 摄像头 + RKNN 人物检测 + 自动运镜 + 人脸检录 + 技术台 + NAU8822 音频。

## 目录结构

```text
camera_150/
├── start_all_techtable.py             # ★ 一键启动：检录 → 导播 → 技术台
├── stop_all_techtable.py              # 一键停止所有后台进程
├── calib_usb3_camera_150.py           # 相机标定三合一（采集/标定/实时矫正）
├── face_checkin_lbph.py               # 独立人脸检录脚本（Haar + LBPH）
├── record_usb3_camera_150.py          # 录制未矫正/矫正视频
├── record_undistorted_usb3_camera_150.py  # 实时畸变矫正 + 按需录制
├── AUDIO_CHAIN.md                     # NAU8822 音频链路文档
├── camera_usb3_calib.npz              # 已生成单目标定结果
├── mediamtx_rk3588.yml                # MediaMTX RTSP 服务器配置
│
├── camera_movement_modified/          # 自动运镜核心模块
│   ├── single_rknn_base.py                # 基础：摄像头采集、RKNN检测、NMS、平滑
│   ├── predict1_weighted.py               # 战团/热点/快攻分析
│   ├── predict1_director.py               # 导播状态机 (pan/zoom/窗口)
│   ├── single_rknn_director_view720_record_local.py   # 720p 本地录制 ★
│   ├── single_rknn_director_view720_network_stream.py # 720p RTSP 网络推流
│   ├── single_rknn_director_view1920_record_local.py  # 旧版 1920 录制
│   ├── audio_chain.py                    # NAU8822 音频参数构造工具
│   ├── debug_view1920/                   # 截图输出
│   ├── director_videos/                  # 录制视频输出
│   └── stream_logs/                      # FFmpeg 推流日志
│
├── techtable_v2/                      # 技术台 V2
│   ├── rk_techtable_panel.py              # PyQt5 计分主控（LCD + HTTP 状态服务）
│   ├── state_store.py                     # JSON 状态持久化
│   ├── scoreboard_overlay.py              # 比分条叠加
│   ├── viewer_client.py                   # PC 远端观赛客户端
│   ├── sample_roster.json                 # 示例球员名单
│   ├── game_state.json                    # 比赛状态
│   └── events.jsonl                       # 事件日志
│
├── face_checkin/                      # 人脸检录数据
│   ├── dataset/                           # 人员人脸样本 (<id>__<name>/)
│   ├── trainer/                           # LBPH 模型 + labels.json
│   └── records/                           # 检录 CSV + 场次 JSON
│
├── face_env/                          # 人脸检录独立虚拟环境 (opencv-contrib-python)
├── model/
│   ├── basketball_player_fp_2.1.0.rknn    # RKNN 人物检测模型
│   └── labels.txt                         # 标签：person
├── audio_patch/                       # 音频链路自动化打补丁工具
├── calib_usb3_images/                 # 32 张标定原图
├── recorded_videos/                   # 录制视频输出
├── undistorted_videos/                # 矫正视频输出
└── runtime/                           # 后台进程 PID + 日志
```

## 硬件与依赖

| 项目 | 要求 |
|------|------|
| 平台 | RK3588，NPU 可用 |
| 摄像头 | USB，默认 `/dev/video41`，建议 MJPG 1920×1080@30fps |
| 音频 | NAU8822 板载声卡 (`hw:1,0`，48kHz/立体声) |
| 系统 | Linux + V4L2 |
| Python | 3.10+，运镜用系统 python，检录用 `face_env/bin/python` |

```bash
# 导播依赖（系统 Python）
opencv-python  numpy  rknnlite.api

# 检录依赖（face_env 虚拟环境）
opencv-contrib-python  numpy

# 系统工具
ffmpeg (含 h264_rkmpp 硬编码支持)
```

---

## 快速启动

```bash
cd /home/elf/work/camera_150
python3 start_all_techtable.py
```

会自动弹出一个 PyQt5 窗口，按流程操作：

1. **选择球员** → 勾选本场需要检录的球员，绑定人脸档案
2. **人脸检录** → 球员正对摄像头，自动识别并确认到场
3. **进入导播** → 自动启动 MediaMTX、RKNN 运镜推流、技术台

启动后：
- 网页计分：`http://RK_IP:8010/`
- RTSP 流：`rtsp://RK_IP:8554/director`
- 停止全部：`python3 stop_all_techtable.py`

---

## 模块详解

### 1. 相机标定

```bash
# 采集棋盘格图片
python3 calib_usb3_camera_150.py --mode capture \
  --device /dev/video41 --output-dir calib_usb3_images

# 计算标定参数
python3 calib_usb3_camera_150.py --mode calibrate \
  --input-dir calib_usb3_images --output camera_usb3_calib.npz

# 实时查看矫正效果
python3 calib_usb3_camera_150.py --mode undistort \
  --device /dev/video41 --calib-file camera_usb3_calib.npz --show-original
```

| 参数 | 值 |
|------|-----|
| 棋盘格 | 12×9 方格，11×8 内角点，22.0mm |
| 标定分辨率 | 1920×1080 |
| 当前 RMS | ~0.755（正常可用） |

### 2. RKNN 自动运镜

**处理流程**：

```text
USB 摄像头 (1920×1080)
    ↓ 单目畸变矫正
RKNN 人物检测 (每 N 帧)
    ↓ NMS / 指数平滑 / 轨迹匹配
战团 & 热点分析 → 导播状态机 (窗口/pan/zoom)
    ↓ 裁切
1280×720 输出 → 本地预览 / H.264 录制 / RTSP 推流
```

**本地录制**：

```bash
cd camera_movement_modified
python3 single_rknn_director_view720_record_local.py \
  --device /dev/video41 \
  --record-fps 25 --record-bitrate 8M --record-encoder h264_rkmpp
```

按键：`r`/空格 开始/停止录制，`s` 截图，`q`/Esc 退出。

**RTSP 推流**：

```bash
# 终端1：启动 MediaMTX
cd ~/stream_server
./mediamtx mediamtx_rk3588.yml

# 终端2：启动推流
cd camera_movement_modified
python3 single_rknn_director_view720_network_stream.py \
  --device /dev/video41 \
  --stream-mode rtsp --stream-url rtsp://127.0.0.1:8554/director \
  --stream-fps 25 --stream-bitrate 4M --stream-encoder h264_rkmpp
```

VLC 拉流：`rtsp://RK_IP:8554/director`

**运镜算法**：
- `predict1_weighted.py`：人物过滤 → 主战区锁定 → 加权热点 → 快攻判断 → 预测提前量
- `predict1_director.py`：左/中/右窗口选择 → pan 惯性与驻留 → zoom 冷却 → 导播框平滑

### 3. 音频链路 (NAU8822)

```text
NAU8822 hw:1,0 (ALSA, 48kHz, 立体声)
    ↓ FFmpeg ALSA 直采 (aresample=async 跟随视频时钟)
AAC 128kbps
    ├── 与 H.264 封装为 MP4（本地录制）
    └── 与 H.264 合流 RTSP（网络推流）
```

**启用音频**：

本地录制加：
```
--record-audio --record-audio-device hw:1,0 --record-audio-rate 48000 \
--record-audio-channels 2 --record-audio-codec aac --record-audio-bitrate 128k
```

网络推流加：
```
--stream-audio --stream-audio-device hw:1,0 --stream-audio-rate 48000 \
--stream-audio-channels 2 --stream-audio-codec aac --stream-audio-bitrate 128k
```

音频参数由 `camera_movement_modified/audio_chain.py` 统一构造，本地录制和推流共用同一套配置。

> **注意**：`hw:1,0` 是硬件 PCM 设备，同一时间只能被一个进程独占。如果同时推流和录像，应让同一个 FFmpeg 进程采集一次音频后 tee 分发，不要同时启动两个都直接读 `hw:1,0` 的进程。

详见 [AUDIO_CHAIN.md](AUDIO_CHAIN.md)。

### 4. 人脸检录

Haar Cascade 人脸检测 + LBPH 人脸识别。支持采集、训练、识别签到。

```bash
# 使用独立虚拟环境
source face_env/bin/activate

# 采集人员人脸
python3 face_checkin_lbph.py --mode enroll \
  --person-id 001 --name 张三 \
  --device /dev/video41 --calib-file camera_usb3_calib.npz --samples 40

# 训练模型
python3 face_checkin_lbph.py --mode train

# 实时识别并检录
python3 face_checkin_lbph.py --mode recognize \
  --device /dev/video41 --calib-file camera_usb3_calib.npz

# 训练后立即识别
python3 face_checkin_lbph.py --mode train-recognize \
  --device /dev/video41 --calib-file camera_usb3_calib.npz
```

采集时有质量筛选（亮度/清晰度/眼睛检测/稳定帧/去重），样本保存在 `face_checkin/dataset/<id>__<name>/`。

> `start_all_techtable.py` 启动时会自动切换到 `face_env/bin/python`，检录 UI 内直接使用 LBPH 识别，无需手动切换环境。

### 5. 技术台 V2

PyQt5 计分面板，在 RK3588 本地 LCD 显示 RTSP 画面 + 叠加比分条，同时通过 HTTP (8010) 提供状态接口。

```bash
python3 techtable_v2/rk_techtable_panel.py \
  --rtsp rtsp://127.0.0.1:8554/director \
  --state techtable_v2/game_state.json \
  --roster techtable_v2/sample_roster.json \
  --state-host 0.0.0.0 --state-port 8010
```

功能：两队比分、节次/时间、球员得分与犯规、球队犯规累计、JSON 状态持久化、JSONL 事件日志。

PC 远端客户端：
```bash
python3 techtable_v2/viewer_client.py \
  --rtsp rtsp://RK_IP:8554/director \
  --state-url http://RK_IP:8010/state
```

### 6. 视频录制工具

```bash
# 同时录制未矫正 + 矫正视频
python3 record_usb3_camera_150.py --mode both --calib-file camera_usb3_calib.npz

# 实时畸变矫正预览 + 按需录制
python3 record_undistorted_usb3_camera_150.py \
  --device /dev/video41 --calib-file camera_usb3_calib.npz

# 无窗口自动录制 60 秒
python3 record_undistorted_usb3_camera_150.py \
  --headless --auto-record --record-seconds 60
```

---

## 运镜主程序参数速查

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--device` | `/dev/video41` | 摄像头设备 |
| `--width/height/fps` | 1920/1080/30 | 摄像头参数 |
| `--calib-file` | `camera_usb3_calib.npz` | 标定文件 |
| `--model` | `model/basketball_player_fp_2.1.0.rknn` | RKNN 模型 |
| `--labels` | `model/labels.txt` | 标签文件 |
| `--view-width/height` | 1280/720 | 输出分辨率 |
| `--render-mode` | `sample` | `sample`=导播框裁切，`legacy`=锚点裁切 |
| `--conf` | 0.25 | 人物检测阈值 |
| `--nms` | 0.45 | NMS IoU 阈值 |
| `--detect-interval` | 3 | 每隔 N 帧检测一次 |
| `--display-scale` | 0.5 | 预览缩放 |
| `--headless` | 关闭 | 无窗口运行 |
| `--record-encoder` | `h264_rkmpp` | 录制编码器 |
| `--stream-encoder` | `h264_rkmpp` | 推流编码器 |
| `--stream-mode` | `rtsp` | 推流协议，也可 `udp` |

---

## 故障排查

| 现象 | 检查 |
|------|------|
| 摄像头打不开 | `ls /dev/video*`，`v4l2-ctl -d /dev/video41 --all` |
| 窗口不显示 | `export DISPLAY=:0` 或加 `--headless` |
| RKNN 加载失败 | 确认 NPU 驱动 + RKNNLite 版本；尝试 `--rknn-core -1` |
| 无 h264_rkmpp | `ffmpeg -encoders \| grep rkmpp`，不可用改 `libx264` |
| RTSP 不通 | `ss -lntp \| grep 8554`，确认 MediaMTX 已启动 |
| 麦克风没声音 | `alsamixer -c 1` 确认 Capture 开关已打开 |
| 设备被占用 | `fuser -v /dev/snd/pcmC1D0c` |
| 内存不足 | `sudo dumpsys meminfo`；`--print-every 5` 查看 FPS |
| 暂停识别失败 | 关闭 `face_checkin_lbph_stable.py` 再试 |
