# camera_150_with_face：RK3588 篮球赛事智能转播系统

> 文件作用：项目总览与入口导航。RK3588 原功能说明保留在下方；Windows G0 变更后同步本节与交接文档。

## Windows G0 入口（2026-10-20）

本工作分支为 `g0/windows-migration`，原工程基线为 `5bd9c5a437536706f51106a5e86fbb2a7ec46906`。
Windows 使用本地 YOLO `.pt`，复用原 `SmoothTracks`、热点分析和规则运镜，并保存导播与广角调试视频。
只执行 G0；后续双类别、ByteTrack、轨迹数据和 TCN 尚未实施。

- 安装与完整 PowerShell 命令：[NEWCOMER_HANDOFF.md](NEWCOMER_HANDOFF.md)
- 真实结构与调用链：[PROJECT_STRUCTURE.md](PROJECT_STRUCTURE.md)
- 平台依赖和迁移边界：[docs/WINDOWS_COMPATIBILITY.md](docs/WINDOWS_COMPATIBILITY.md)
- 当前状态与证据：[STAGE_PROGRESS.md](STAGE_PROGRESS.md)
- G0 验收：[docs/G0_ACCEPTANCE_REPORT.md](docs/G0_ACCEPTANCE_REPORT.md)

```powershell
python .\run_windows.py --help
python .\check_windows_environment.py --model-dir .\best_sac
```

`best_sac` 的现有文件是 SAC 检查点及优化器状态，未作为 YOLO 加载；实际测试权重路径见交接文档。

---

> 单路 150° USB3 广角摄像头 + RKNN 人物检测 + 自动运镜 + 人脸检录 + 篮球技术台 + H.264/AAC RTSP 网络转播

本项目运行在飞凌 ELF2 / RK3588 平台上，面向班赛、校赛和小型篮球赛事的自动化转播。系统使用单路广角摄像头覆盖球场，通过 RKNN 在 NPU 上实时检测球员，再根据人物分布、主战区、热点和快攻状态生成 1280×720 导播画面。

在导播前，系统提供球员选择和 LBPH 人脸检录；进入比赛后，RK3588 的 LCD 显示视频与技术台，浏览器可以通过 8010 端口操作同一份比赛状态，Windows 客户端则通过 RTSP 接收带 AAC 音频的转播画面。

---

## 1. 系统特点

| 模块 | 功能 |
|---|---|
| 人脸检录 | 球员选择、人脸档案绑定、LBPH 实时识别、到场与缺席登记 |
| 自动导播 | 人物检测、热点分析、快攻判断、平滑 pan/zoom、720p 动态裁切 |
| 比赛状态导播 | 比赛运行时正常跟踪；暂停时保持镜头；罚球时引导至对应篮筐 |
| 技术台 | 比分、节次、比赛时间、24 秒、14 秒回表、暂停、球权、加时、犯规、罚球、换人和技术统计 |
| 多端同步 | RK3588 LCD 与网页技术台共享同一份 JSON 状态 |
| 网络转播 | H.264 视频 + AAC 音频封装为 RTSP |
| Windows 客户端 | 显示 RTSP 视频、叠加比分条、读取 8010 状态、播放 AAC 音频 |
| 数据记录 | 比赛状态 JSON 持久化、事件日志 JSONL |
| 一键管理 | 一键启动检录—导播流程，一键停止并释放摄像头、声卡、端口和后台进程 |

### 比分规则

`home_score` 和 `away_score` 表示全场累计比分。

切换下一节时：

```text
比分不清零
节次增加
本节球队犯规按规则重置
比赛时间重置
24 秒重置
```

第四节结束后若比分相同，进入加时赛。

---

## 2. 整体工作流程

```text
启动 start_all_techtable.py
          │
          ▼
本场球员选择
          │
          ▼
球员与人脸档案绑定检查
          │
          ▼
LBPH 人脸识别检录
          │
          ├── 已到场
          └── 记录缺席
          │
          ▼
确认检录完成
          │
          ├── 释放 /dev/video41
          ├── 启动 MediaMTX
          ├── 启动 RKNN 自动导播
          ├── 启动 NAU8822 音频采集
          ├── 发布 H.264 + AAC RTSP
          ├── ffprobe 自动检查音视频轨
          └── 启动 LCD / 网页技术台
          │
          ▼
检录窗口隐藏，进入正式比赛界面
```

比赛结束后执行：

```bash
python3 stop_all_techtable.py
```

停止脚本会关闭技术台、导播、内部 FFmpeg、MediaMTX 和检录启动器，并清理当前场次的临时检录结果。

---

## 3. 系统架构

```text
                         ┌──────────────────────────────┐
                         │      球员名单 / 人脸模型      │
                         └──────────────┬───────────────┘
                                        │
                              球员选择与人脸检录
                                        │
                                        ▼
USB3 摄像头 /dev/video41 ──► 单目畸变矫正
                                        │
                                        ▼
                                 RKNN 人物检测
                                        │
                                        ▼
                        战团 / 热点 / 快攻 / 预测分析
                                        │
                                        ▼
                  技术台状态策略 NORMAL / HOLD / FREE_THROW
                                        │
                                        ▼
                            pan / zoom 导播状态机
                                        │
                                        ▼
                              1280×720 导播画面
                                        │
               ┌────────────────────────┴────────────────────────┐
               │                                                 │
               ▼                                                 ▼
    FFmpeg h264_rkmpp 视频编码                        RK3588 LCD 技术台
               │
NAU8822 hw:1,0 ─► AAC 48 kHz 双声道
               │
               ▼
      MediaMTX RTSP /director
               │
       ┌───────┴────────┐
       ▼                ▼
Windows 观看端       VLC / OBS / ffplay
```

技术台采用解耦结构：

```text
LCD PyQt5 ───────┐
                  ├── GameController ── game_state.json
网页 /api/action ─┘          │          events.jsonl
                             │
                             └── director_hint
                                      │
                                      ▼
                         director_game_policy.py
                                      │
                                      ▼
                         原自动导播状态机
```

LCD 与网页不分别编写比赛规则，所有动作都经过统一的比赛控制器。

---

## 4. 目录结构

```text
camera_150/
├── README.md
├── start_all_techtable.py
├── stop_all_techtable.py
├── mediamtx_rk3588.yml
├── camera_usb3_calib.npz
├── calib_usb3_camera_150.py
├── record_usb3_camera_150.py
├── record_undistorted_usb3_camera_150.py
├── face_checkin_lbph.py
├── AUDIO_CHAIN.md
│
├── camera_movement_modified/
│   ├── single_rknn_base.py
│   ├── predict1_weighted.py
│   ├── predict1_director.py
│   ├── director_game_policy.py
│   ├── audio_chain.py
│   ├── single_rknn_director_view720_network_stream.py
│   ├── single_rknn_director_view720_record_local.py
│   ├── director_videos/
│   └── stream_logs/
│
├── techtable_v2/
│   ├── rk_techtable_panel.py
│   ├── state_store.py
│   ├── scoreboard_overlay.py
│   ├── viewer_client.py
│   ├── sample_roster.json
│   ├── game_state.json
│   └── events.jsonl
│
├── face_checkin/
│   ├── dataset/
│   ├── trainer/
│   │   ├── lbph_model.yml
│   │   └── labels.json
│   ├── records/
│   └── roster_face_mapping.json
│
├── face_env/
├── model/
│   ├── basketball_player_fp_2.1.0.rknn
│   └── labels.txt
│
└── runtime/
    ├── logs/
    │   ├── mediamtx.log
    │   ├── director.log
    │   └── techtable.log
    ├── techtable_processes.json
    ├── start_all_techtable.pid
    ├── active_checkin_session.json
    └── rtsp_probe.json
```

---

## 5. 硬件环境

| 项目 | 当前配置 |
|---|---|
| 主控 | 飞凌 ELF2 / Rockchip RK3588 |
| 系统 | Ubuntu 22.04 aarch64 |
| 摄像头 | 单路 USB3 UVC 广角摄像头 |
| 默认设备 | `/dev/video41` |
| 输入格式 | MJPG，1920×1080，30 FPS |
| 输出画面 | 1280×720 |
| 本地预览比例 | `display-scale=0.35` |
| AI 加速 | RK3588 NPU / RKNN |
| 音频 | Rockchip NAU8822 |
| 音频设备 | `hw:1,0` |
| 音频格式 | 48 kHz、双声道、AAC 128 kbit/s |
| 视频编码 | `h264_rkmpp` |
| RTSP 服务 | MediaMTX |
| RTSP 端口 | 8554 |
| 技术台端口 | 8010 |

---

## 6. 软件依赖

### 6.1 系统 Python

导播和技术台使用系统 Python 3：

```text
Python 3.10+
numpy
opencv-python
PyQt5
rknnlite.api
Pillow
```

检查：

```bash
python3 - <<'PY'
import cv2
import numpy
from PyQt5.QtWidgets import QApplication
from rknnlite.api import RKNNLite

print("cv2:", cv2.__version__)
print("numpy:", numpy.__version__)
print("dependencies: OK")
PY
```

### 6.2 人脸检录环境

人脸检录需要 `cv2.face`，使用独立环境：

```text
face_env/bin/python
opencv-contrib-python 或 opencv-contrib-python-headless
numpy
```

检查：

```bash
./face_env/bin/python - <<'PY'
import cv2
print("cv2:", cv2.__version__)
print("cv2.face:", hasattr(cv2, "face"))
PY
```

### 6.3 系统工具

```text
ffmpeg
ffprobe
ffplay
arecord
aplay
v4l2-ctl
lsof 或 ss
```

FFmpeg 必须支持 RKMPP：

```bash
ffmpeg -hide_banner -encoders | grep rkmpp
```

预期包含：

```text
h264_rkmpp
```

---

## 7. 使用前检查

### 7.1 摄像头

```bash
v4l2-ctl --list-devices
v4l2-ctl --device /dev/video41 --list-formats-ext
```

测试：

```bash
ffplay -f v4l2 \
  -input_format mjpeg \
  -video_size 1920x1080 \
  -framerate 30 \
  /dev/video41
```

### 7.2 音频设备

```bash
arecord -l
```

预期包含：

```text
card 1: rockchip-nau8822
device 0
```

录音测试：

```bash
arecord \
  -D hw:1,0 \
  -f S16_LE \
  -r 48000 \
  -c 2 \
  -d 10 \
  -V stereo \
  mic_test.wav
```

播放：

```bash
aplay mic_test.wav
```

### 7.3 MediaMTX

默认路径：

```text
/home/elf/stream_server/mediamtx
```

检查：

```bash
ls -l ~/stream_server/mediamtx
ls -l ~/stream_server/mediamtx_rk3588.yml
```

工程根目录中的 `mediamtx_rk3588.yml` 也可以作为备用配置。

### 7.4 模型与标定

```bash
ls -l model/basketball_player_fp_2.1.0.rknn
ls -l model/labels.txt
ls -l camera_usb3_calib.npz
```

---

## 8. 快速启动

```bash
cd /home/elf/work/camera_150
python3 start_all_techtable.py
```

启动界面依次完成：

1. 勾选本场参赛球员；
2. 检查球员与人脸档案绑定；
3. 开始实时人脸识别；
4. 未到场球员标记为缺席；
5. 所有已选球员完成处理；
6. 点击确认进入导播；
7. 等待 RTSP 音视频验证通过；
8. LCD 自动进入技术台界面。

启动成功后：

```text
网页技术台：http://RK3588_IP:8010/
状态接口：http://RK3588_IP:8010/state
RTSP 地址：rtsp://RK3588_IP:8554/director
```

当前网络示例：

```text
网页技术台：http://192.168.137.231:8010/
RTSP 地址：rtsp://192.168.137.231:8554/director
```

---

## 9. 一键停止

```bash
cd /home/elf/work/camera_150
python3 stop_all_techtable.py
```

停止顺序：

```text
技术台
  ↓
RKNN 导播
  ↓
内部 FFmpeg 音视频推流
  ↓
MediaMTX
  ↓
检录启动器
```

停止后还会：

- 释放 `/dev/video41`；
- 释放 `hw:1,0`；
- 释放 8554 和 8010 端口；
- 删除 PID 文件；
- 删除本场临时检录会话；
- 删除本场 CSV 中对应的临时检录行；
- 删除 `runtime/active_checkin_session.json`；
- 删除 `runtime/rtsp_probe.json`。

不会删除：

- 人脸照片；
- LBPH 模型；
- `labels.json`；
- 球员与人脸映射；
- 球员名单；
- 比赛技术统计文件。

---

## 10. 人脸检录

系统使用 Haar Cascade 检测人脸，使用 LBPH 完成人员识别。

### 10.1 采集人脸

```bash
cd /home/elf/work/camera_150

./face_env/bin/python face_checkin_lbph.py \
  --mode enroll \
  --person-id 001 \
  --name 张三 \
  --device /dev/video41 \
  --calib-file camera_usb3_calib.npz \
  --samples 40
```

样本目录：

```text
face_checkin/dataset/001__张三/
```

### 10.2 训练模型

```bash
./face_env/bin/python face_checkin_lbph.py --mode train
```

输出：

```text
face_checkin/trainer/lbph_model.yml
face_checkin/trainer/labels.json
```

### 10.3 独立识别测试

```bash
./face_env/bin/python face_checkin_lbph.py \
  --mode recognize \
  --device /dev/video41 \
  --calib-file camera_usb3_calib.npz
```

### 10.4 一键流程中的检录

`start_all_techtable.py` 会自动切换到：

```text
face_env/bin/python
```

导播和技术台仍由系统 Python 启动，不会污染 RKNN 环境。

检录与导播共用 `/dev/video41`，进入导播前必须先停止识别线程并释放摄像头。

---

## 11. 自动导播

### 11.1 处理流程

```text
USB3 摄像头
    ↓
单目畸变矫正
    ↓
RKNN 人体检测
    ↓
NMS、置信度过滤、目标平滑
    ↓
人物战团和热点分析
    ↓
快攻方向与预测提前量
    ↓
比赛状态策略
    ↓
窗口选择、pan、zoom、防抖
    ↓
1280×720 导播画面
```

### 11.2 核心文件

| 文件 | 作用 |
|---|---|
| `single_rknn_base.py` | 摄像头、RKNN、NMS 和基础工具 |
| `predict1_weighted.py` | 人物分组、主战区、热点和快攻分析 |
| `predict1_director.py` | 导播框、窗口切换、pan/zoom 和防抖 |
| `director_game_policy.py` | 根据比赛状态修改导播行为 |
| `single_rknn_director_view720_network_stream.py` | RTSP 网络转播主程序 |

### 11.3 比赛状态策略

| 策略 | 适用场景 | 行为 |
|---|---|---|
| `NORMAL` | 比赛运行中 | 使用原人物热点和自动运镜 |
| `HOLD` | 赛前、死球、暂停、节间和比赛结束 | 保持当前区域，减小无意义运镜 |
| `FREE_THROW` | 罚球 | 平滑引导至罚球队伍对应篮筐，冻结快速 zoom |

技术台只写入 JSON：

```json
{
  "phase": "FREE_THROW",
  "free_throw_team": "home",
  "director_hint": {
    "mode": "FREE_THROW",
    "reason": "FREE_THROW"
  }
}
```

导播只读该状态，不依赖 PyQt5 或网页服务。

### 11.4 篮筐位置参数

一键启动中可配置：

```text
--left-basket-x-ratio 0.18
--right-basket-x-ratio 0.82
--home-first-half-attack right
```

含义：

- 左篮筐位于画面宽度约 18%；
- 右篮筐位于画面宽度约 82%；
- 主队第 1、2 节向右进攻；
- 下半场和加时自动交换方向。

现场方向相反时：

```text
--home-first-half-attack left
```

临时关闭比赛状态策略：

```text
--disable-game-policy
```

---

## 12. 技术台

### 12.1 状态机

```text
PRE_GAME
PERIOD_RUNNING
PERIOD_PAUSED
TIMEOUT
FREE_THROW
PERIOD_END
OVERTIME
GAME_END
```

### 12.2 功能

```text
全场累计比分
节次与多次加时
比赛时间
24秒开始、暂停和回24
14秒回表
主客队暂停次数
球权指示
球员得分
球员个人犯规
球队单节犯规
个人满犯提醒
球队 BONUS 状态
罚球命中与罚丢
首发和在场球员
换人记录
篮板、助攻、抢断、盖帽和失误
单节球队统计
全场球队统计
球员个人统计
统一撤销
JSON 状态持久化
JSONL 事件日志
```

### 12.3 LCD UI

右侧操作区采用分页：

```text
计分
时间
阵容
统计
```

按钮采用紧凑布局，避免遮挡视频。导播本地 OpenCV 预览参数保持：

```text
--display-scale 0.35
```

### 12.4 网页技术台

浏览器打开：

```text
http://RK3588_IP:8010/
```

状态接口：

```text
http://RK3588_IP:8010/state
```

网页和 LCD 调用同一个比赛控制器，因此任意一端操作后，另一端都会读取到相同状态。

### 12.5 比分与节次

本项目使用全场累计比分：

```text
第1节结束：25 : 20
进入第2节：仍显示 25 : 20
第2节继续累计
```

比分不会在换节时清零。

球队犯规、比赛时间、24 秒和球权按照新节规则单独处理。

---

## 13. RTSP 音视频

### 13.1 服务端链路

```text
Python 原始 BGR 画面
    ↓
FFmpeg rawvideo 输入
    ↓
format=nv12
    ↓
h264_rkmpp
    │
NAU8822 hw:1,0
    ↓
ALSA S16_LE / 48000 Hz / 2 ch
    ↓
aresample=async
    ↓
AAC 128 kbit/s
    │
    └──────────► RTSP /director
```

一键启动使用：

```text
--stream-audio
--stream-audio-device hw:1,0
--stream-audio-rate 48000
--stream-audio-channels 2
--stream-audio-codec aac
--stream-audio-bitrate 128k
```

### 13.2 检查 RTSP 音轨

在 RK3588 或 Windows 上执行：

```bash
ffprobe \
  -v error \
  -rtsp_transport tcp \
  -show_entries stream=index,codec_type,codec_name,sample_rate,channels \
  -of json \
  rtsp://192.168.137.231:8554/director
```

正常应同时看到：

```json
{
  "codec_type": "video",
  "codec_name": "h264"
}
```

以及：

```json
{
  "codec_type": "audio",
  "codec_name": "aac",
  "sample_rate": "48000",
  "channels": 2
}
```

### 13.3 检查是否真正有声音

```bash
ffmpeg \
  -hide_banner \
  -rtsp_transport tcp \
  -i rtsp://192.168.137.231:8554/director \
  -map 0:a:0 \
  -t 10 \
  -af volumedetect \
  -f null -
```

关注：

```text
mean_volume
max_volume
```

如果 `max_volume=-inf dB`，说明有音轨但采集到的是静音。

直接试听：

```bash
ffplay \
  -rtsp_transport tcp \
  -vn \
  rtsp://192.168.137.231:8554/director
```

---

## 14. Windows 观看端

Windows 客户端运行：

```powershell
python techtable_v2/viewer_client.py `
  --rtsp rtsp://192.168.137.231:8554/director `
  --state-url http://192.168.137.231:8010/state
```

处理方式：

```text
OpenCV
    └── 解码视频并绘制比分条

ffplay
    └── 播放同一个 RTSP 中的 AAC 音频

HTTP /state
    └── 获取 RK3588 技术台状态
```

如果 FFmpeg 没有加入 PATH：

```powershell
python techtable_v2/viewer_client.py `
  --rtsp rtsp://192.168.137.231:8554/director `
  --state-url http://192.168.137.231:8010/state `
  --ffplay-bin "D:\ffmpeg\bin\ffplay.exe" `
  --ffprobe-bin "D:\ffmpeg\bin\ffprobe.exe"
```

调整音量：

```powershell
python techtable_v2/viewer_client.py `
  --rtsp rtsp://192.168.137.231:8554/director `
  --state-url http://192.168.137.231:8010/state `
  --volume 70
```

临时关闭声音：

```powershell
python techtable_v2/viewer_client.py `
  --rtsp rtsp://192.168.137.231:8554/director `
  --state-url http://192.168.137.231:8010/state `
  --no-audio
```

音频日志：

```text
techtable_v2/viewer_audio_ffplay.log
```

---

## 15. 独立运行

### 15.1 MediaMTX

```bash
cd ~/stream_server
./mediamtx mediamtx_rk3588.yml
```

### 15.2 网络导播

```bash
cd /home/elf/work/camera_150/camera_movement_modified

python3 single_rknn_director_view720_network_stream.py \
  --device /dev/video41 \
  --calib-file /home/elf/work/camera_150/camera_usb3_calib.npz \
  --model /home/elf/work/camera_150/model/basketball_player_fp_2.1.0.rknn \
  --labels /home/elf/work/camera_150/model/labels.txt \
  --render-mode sample \
  --display-scale 0.35 \
  --stream-mode rtsp \
  --stream-url rtsp://127.0.0.1:8554/director \
  --stream-fps 25 \
  --stream-bitrate 4M \
  --stream-encoder h264_rkmpp \
  --stream-audio \
  --stream-audio-device hw:1,0 \
  --stream-audio-rate 48000 \
  --stream-audio-channels 2 \
  --stream-audio-codec aac \
  --stream-audio-bitrate 128k
```

### 15.3 LCD 与网页技术台

```bash
cd /home/elf/work/camera_150

export DISPLAY=:0

python3 techtable_v2/rk_techtable_panel.py \
  --rtsp rtsp://127.0.0.1:8554/director \
  --state techtable_v2/game_state.json \
  --events techtable_v2/events.jsonl \
  --roster techtable_v2/sample_roster.json \
  --state-host 0.0.0.0 \
  --state-port 8010
```

---

## 16. 相机标定

### 16.1 采集棋盘格

```bash
python3 calib_usb3_camera_150.py \
  --mode capture \
  --device /dev/video41 \
  --output-dir calib_usb3_images
```

### 16.2 计算标定参数

```bash
python3 calib_usb3_camera_150.py \
  --mode calibrate \
  --input-dir calib_usb3_images \
  --output camera_usb3_calib.npz
```

### 16.3 实时查看矫正

```bash
python3 calib_usb3_camera_150.py \
  --mode undistort \
  --device /dev/video41 \
  --calib-file camera_usb3_calib.npz \
  --show-original
```

当前标定参考：

| 参数 | 值 |
|---|---|
| 棋盘格 | 12×9 方格 |
| 内角点 | 11×8 |
| 方格边长 | 22 mm |
| 标定分辨率 | 1920×1080 |

---

## 17. 本地视频录制

```bash
cd /home/elf/work/camera_150/camera_movement_modified

python3 single_rknn_director_view720_record_local.py \
  --device /dev/video41 \
  --calib-file ../camera_usb3_calib.npz \
  --model ../model/basketball_player_fp_2.1.0.rknn \
  --labels ../model/labels.txt \
  --display-scale 0.35 \
  --record-fps 25 \
  --record-bitrate 8M \
  --record-encoder h264_rkmpp
```

常用按键：

| 按键 | 功能 |
|---|---|
| `r` / 空格 | 开始或停止录制 |
| `s` | 保存当前调试画面 |
| `q` / Esc | 退出 |

启用录制音频：

```text
--record-audio
--record-audio-device hw:1,0
--record-audio-rate 48000
--record-audio-channels 2
--record-audio-codec aac
--record-audio-bitrate 128k
```

> `hw:1,0` 是硬件 PCM。同一时间不应让多个独立 FFmpeg 同时占用该设备。

---

## 18. 状态与日志

### 18.1 比赛状态

```text
techtable_v2/game_state.json
```

### 18.2 事件日志

```text
techtable_v2/events.jsonl
```

每一行是一条 JSON 事件，便于赛后分析。

### 18.3 进程日志

```text
runtime/logs/mediamtx.log
runtime/logs/director.log
runtime/logs/techtable.log
```

### 18.4 FFmpeg 日志

```text
camera_movement_modified/stream_logs/
```

### 18.5 PID 文件

```text
runtime/techtable_processes.json
runtime/start_all_techtable.pid
```

---

## 19. 常见问题

### 19.1 LCD 完全没有出现技术台 UI

先检查：

```bash
tail -n 150 runtime/logs/techtable.log
```

若出现：

```text
Could not load the Qt platform plugin "xcb"
```

确认使用系统 Qt 插件：

```bash
export DISPLAY=:0
export QT_QPA_PLATFORM=xcb
export QT_QPA_PLATFORM_PLUGIN_PATH=/usr/lib/aarch64-linux-gnu/qt5/plugins/platforms
export QT_PLUGIN_PATH=/usr/lib/aarch64-linux-gnu/qt5/plugins
```

`rk_techtable_panel.py` 必须在导入 `cv2` 后再次恢复上述 Qt 路径，并在创建 `QApplication` 前调用：

```python
QCoreApplication.setLibraryPaths(
    ["/usr/lib/aarch64-linux-gnu/qt5/plugins"]
)
```

### 19.2 LCD UI 出现，但视频区域无画面

检查 RTSP：

```bash
ffprobe \
  -v error \
  -rtsp_transport tcp \
  rtsp://127.0.0.1:8554/director
```

检查导播：

```bash
tail -n 150 runtime/logs/director.log
```

检查 MediaMTX：

```bash
tail -n 100 runtime/logs/mediamtx.log
```

### 19.3 检录后没有进入技术台

技术台只会在 RTSP 音视频验证通过后启动。

检查：

```bash
cat runtime/rtsp_probe.json
tail -n 150 runtime/logs/director.log
```

### 19.4 RTSP 有画面但没有声音

检查音轨：

```bash
ffprobe \
  -v error \
  -rtsp_transport tcp \
  -select_streams a:0 \
  -show_entries stream=codec_name,sample_rate,channels \
  -of json \
  rtsp://127.0.0.1:8554/director
```

检查录音设备是否被占用：

```bash
fuser -v /dev/snd/*
ps -ef | grep ffmpeg | grep -v grep
```

### 19.5 Windows 客户端有视频但没声音

OpenCV 只负责视频帧，不会自动把 AAC 播放到扬声器。

确认：

```powershell
ffplay -version
ffprobe -version
```

查看：

```text
techtable_v2\viewer_audio_ffplay.log
```

### 19.6 摄像头被占用

```bash
fuser -v /dev/video41
```

先执行：

```bash
python3 stop_all_techtable.py
```

### 19.7 8010 或 8554 被占用

```bash
lsof -i:8010
lsof -i:8554
```

或：

```bash
ss -ltnp | grep -E '8010|8554'
```

### 19.8 停止后仍有 FFmpeg

```bash
ps -ef | grep ffmpeg | grep director | grep -v grep
```

正常情况下 `stop_all_techtable.py` 会使用 RTSP 发布地址进行兜底匹配并终止残留 FFmpeg。

---

## 20. 开发与验证

### 20.1 Python 语法检查

```bash
python3 -m py_compile \
  start_all_techtable.py \
  stop_all_techtable.py \
  techtable_v2/state_store.py \
  techtable_v2/rk_techtable_panel.py \
  techtable_v2/scoreboard_overlay.py \
  camera_movement_modified/director_game_policy.py \
  camera_movement_modified/single_rknn_director_view720_network_stream.py
```

### 20.2 仅测试技术台 UI

```bash
export DISPLAY=:0

python3 techtable_v2/rk_techtable_panel.py \
  --rtsp "" \
  --state techtable_v2/game_state.json \
  --events techtable_v2/events.jsonl \
  --roster techtable_v2/sample_roster.json \
  --no-serve-state
```

### 20.3 检查运行进程

```bash
ps -ef | grep -E \
  'start_all_techtable|rk_techtable_panel|single_rknn_director|mediamtx|ffmpeg' \
  | grep -v grep
```

---

## 21. 安全回滚

修改脚本前建议备份：

```bash
cp start_all_techtable.py start_all_techtable.py.backup
cp stop_all_techtable.py stop_all_techtable.py.backup

cp techtable_v2/state_store.py \
   techtable_v2/state_store.py.backup

cp techtable_v2/rk_techtable_panel.py \
   techtable_v2/rk_techtable_panel.py.backup
```

若使用补丁工具，优先使用工具自动生成的：

```text
backup_techtable_日期_时间/
```

进行恢复。

---

## 22. 已知限制

1. 当前为单路广角摄像头方案，遮挡严重时人物检测和热点判断会受影响。
2. 罚球篮筐位置依赖现场摄像头安装，需要校准左右篮筐比例。
3. Windows 客户端的视频与音频使用两个 RTSP 连接，可能存在少量音画时间差。
4. JSON 与 JSONL 适合小型赛事，不等同于专业数据库或裁判认证设备。
5. 自动导播仍需要人工技术台准确标记暂停、罚球和节次状态。
6. NAU8822 硬件 PCM 不适合被多个独立采集进程同时占用。
7. 当前项目用于工程演示和小型赛事转播，不替代正式赛事裁判系统。

---

## 23. 项目入口

```text
启动：python3 start_all_techtable.py
停止：python3 stop_all_techtable.py

网页：http://RK3588_IP:8010/
状态：http://RK3588_IP:8010/state
RTSP：rtsp://RK3588_IP:8554/director
```

项目仓库：

```text
https://github.com/zzzokay/camera_150_with_face
```
