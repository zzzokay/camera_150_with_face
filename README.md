# camera_150：单路 USB3 摄像头标定、RKNN 自动运镜、人脸检录与技术台

本目录是一套面向 **RK3588 / Linux / USB3 摄像头** 的篮球赛事智能拍摄系统，包含以下独立又互相配合的模块：

| 模块 | 说明 |
|------|------|
| 相机标定 | USB/V4L2 摄像头棋盘格标定与实时畸变矫正 |
| RKNN 自动运镜 | 单路 RKNN 人物检测 + 导播状态机 + 本地录制 / RTSP 推流 |
| 人脸检录 | Haar + LBPH 人脸采集、训练、识别与签到 CSV 记录 |
| 技术台 V2 | PyQt5 计分面板 + HTTP 状态服务 + PC 远端 viewer |
| 视频录制 | 未矫正 / 矫正后视频的独立录制工具 |
| 一键启停 | `start_all_techtable.py` / `stop_all_techtable.py` 管理全部进程 |

> 当前工程是"单路摄像头"版本：只做单目 undistort，不做 stereoRectify、双目极线矫正或拼接。

---

## 目录结构

```text
/home/elf/work/camera_150/
├── README.md
├── calib_usb3_camera_150.py          # 相机标定三合一工具
├── camera_usb3_calib.npz             # 已生成单目标定结果
├── mediamtx_rk3588.yml               # MediaMTX RTSP 服务器配置
├── record_usb3_camera_150.py         # 录制未矫正 / 矫正视频（可同时录两份）
├── record_undistorted_usb3_camera_150.py  # 实时畸变矫正 + 录制
├── face_checkin_lbph.py              # 人脸检录（Haar + LBPH）
├── start_all_techtable.py            # 一键启动全部进程
├── stop_all_techtable.py             # 一键停止全部进程
├── calib_usb3_images/                # 32 张标定原图
├── model/
│   ├── basketball_player_fp_2.1.0.rknn   # RKNN 人物检测模型
│   └── labels.txt                        # 标签文件（person）
├── camera_movement_modified/         # RKNN 自动运镜模块
│   ├── single_rknn_base.py               # 通用基础：摄像头采集、RKNN检测、NMS、平滑
│   ├── predict1_weighted.py              # 战团 / 热点分析
│   ├── predict1_director.py              # 导播状态机：pan/zoom/窗口切换
│   ├── single_rknn_director_view720_record_local.py   # 720p 本地录制主程序 ★推荐
│   ├── single_rknn_director_view720_network_stream.py # 720p 网络推流主程序
│   ├── single_rknn_director_view1920_record_local.py  # 旧版 1920 裁切程序
│   ├── debug_view1920/                   # 截图默认目录
│   ├── director_videos/                  # 录制视频默认目录
│   └── stream_logs/                      # 推流日志目录
├── techtable_v2/                     # 技术台 V2 模块
│   ├── rk_techtable_panel.py             # PyQt5 计分主控端
│   ├── state_store.py                    # JSON 状态持久化
│   ├── scoreboard_overlay.py             # 比分条叠加
│   ├── viewer_client.py                  # PC 远端观赛客户端
│   ├── game_state.json                   # 比赛状态文件
│   ├── events.jsonl                      # 事件日志
│   └── sample_roster.json                # 示例球员名单
├── face_checkin/                     # 人脸检录数据目录
│   ├── dataset/                          # 人员人脸样本
│   ├── trainer/                          # LBPH 模型 + 标签映射
│   └── records/                          # 检录 CSV 记录
├── face_env/                         # Python 虚拟环境（人脸检录用）
├── recorded_videos/                  # 录制视频输出目录
├── undistorted_videos/               # 矫正视频输出目录
└── __pycache__/
```

---

## 运行环境

### 硬件和系统

- **RK3588** 或兼容 RKNNLite 的 Rockchip 平台
- Linux，支持 V4L2
- USB 摄像头，默认 `/dev/video41`，建议支持 `MJPG 1920x1080@30fps`
- NPU 可用（加载 `.rknn` 模型）
- 窗口预览需本地显示环境或正确配置 `DISPLAY`

### Python 依赖

```bash
# 自动运镜模块
opencv-python / cv2
numpy
rknnlite.api         # Rockchip 提供

# 人脸检录模块（使用独立虚拟环境）
opencv-contrib-python  # 含 cv2.face.LBPHFaceRecognizer
numpy

# 技术台 V2
PyQt5
numpy
```

人脸检录使用独立虚拟环境 `face_env/`：

```bash
source face_env/bin/activate
python3 -c "import cv2; print(hasattr(cv2, 'face'))"
```

### 系统依赖

```bash
ffmpeg -version                       # 录制和推流依赖
ffmpeg -hide_banner -encoders | grep rkmpp  # 检查硬件编码器
```

---

## 一、相机标定

标定工具：[calib_usb3_camera_150.py](calib_usb3_camera_150.py)，支持采集、标定、实时矫正三种模式。

### 标定板参数

| 参数 | 值 |
|------|-----|
| 棋盘格图案 | 12 × 9 方格 |
| 内角点 | 11 × 8 |
| 方格边长 | 22.0 mm |

### 采集标定图片

```bash
cd /home/elf/work/camera_150
python3 calib_usb3_camera_150.py \
  --mode capture \
  --device /dev/video41 \
  --width 1920 --height 1080 --fps 30 \
  --output-dir calib_usb3_images \
  --board-cols 11 --board-rows 8 --square-size 22.0 \
  --display-scale 0.5
```

| 按键 | 功能 |
|------|------|
| `c` | 检测到棋盘格角点时保存 |
| `s` | 不检查角点，直接保存原图 |
| `q` / `Esc` | 退出 |

### 计算标定参数

```bash
python3 calib_usb3_camera_150.py \
  --mode calibrate \
  --input-dir calib_usb3_images \
  --output camera_usb3_calib.npz \
  --board-cols 11 --board-rows 8 --square-size 22.0 \
  --alpha 0.0
```

### 当前标定结果

| 字段 | 值 |
|------|-----|
| `image_size` | 1920 × 1080 |
| `rms` | ~0.755 |
| `mean_error` | ~0.078 px |
| `square_size` | 22.0 mm |

误差参考：< 0.3 px 很好 / 0.3~0.8 px 正常可用 / 0.8~1.5 px 勉强 / > 1.5 px 建议重采集。

### 实时查看矫正效果

```bash
python3 calib_usb3_camera_150.py \
  --mode undistort \
  --device /dev/video41 \
  --width 1920 --height 1080 --fps 30 \
  --calib-file camera_usb3_calib.npz \
  --show-original --display-scale 0.5
```

---

## 二、RKNN 自动运镜（核心模块）

模块目录：[camera_movement_modified/](camera_movement_modified/)

### 处理流程

```text
USB 摄像头 (1920×1080)
    ↓
单目畸变矫正 (camera_usb3_calib.npz)
    ↓
RKNN 人物检测 (每隔 N 帧)
    ↓
检测框 NMS / 指数平滑 / 轨迹匹配
    ↓
predict1_weighted: 主战区、热点、快攻、焦点分析
    ↓
predict1_director: 导播状态机（窗口/pan/zoom/驻留）
    ↓
裁切导播视野 → 1280×720 输出
    ↓
预览 / 本地 H.264 录制 / RTSP 网络推流
```

### 本地录制（推荐）

```bash
cd /home/elf/work/camera_150/camera_movement_modified

python3 single_rknn_director_view720_record_local.py \
  --device /dev/video41 \
  --calib-file /home/elf/work/camera_150/camera_usb3_calib.npz \
  --model /home/elf/work/camera_150/model/basketball_player_fp_2.1.0.rknn \
  --labels /home/elf/work/camera_150/model/labels.txt \
  --view-width 1280 --view-height 720 \
  --render-mode sample \
  --detect-interval 3 --conf 0.25 --nms 0.45 \
  --record-dir /home/elf/work/camera_150/camera_movement_modified/director_videos \
  --save-dir /home/elf/work/camera_150/camera_movement_modified/debug_view1920
```

| 按键 | 功能 |
|------|------|
| `r` / `Space` | 开始 / 停止录制 |
| `s` | 保存当前预览截图 |
| `q` / `Esc` | 退出 |

### 网络推流（RTSP + MediaMTX + VLC）

**第一步**：启动 MediaMTX RTSP 服务器

```bash
mkdir -p ~/stream_server
cp mediamtx_rk3588.yml ~/stream_server/
cd ~/stream_server
./mediamtx mediamtx_rk3588.yml
```

**第二步**：启动运镜推流

```bash
cd /home/elf/work/camera_150/camera_movement_modified

python3 single_rknn_director_view720_network_stream.py \
  --device /dev/video41 \
  --calib-file /home/elf/work/camera_150/camera_usb3_calib.npz \
  --model /home/elf/work/camera_150/model/basketball_player_fp_2.1.0.rknn \
  --labels /home/elf/work/camera_150/model/labels.txt \
  --view-width 1280 --view-height 720 \
  --render-mode sample \
  --detect-interval 3 --conf 0.25 --nms 0.45 \
  --stream-mode rtsp \
  --stream-url rtsp://127.0.0.1:8554/director \
  --stream-fps 25 --stream-bitrate 4M \
  --stream-encoder h264_rkmpp
```

**第三步**：VLC 拉流观看

```text
媒体 → 打开网络串流 → rtsp://RK3588的IP:8554/director
```

推流脚本内置 watchdog 心跳机制：FFmpeg 崩溃、RTSP 断开或管道异常后自动重连，缓冲区只保留最新帧避免延迟堆积。

### 主要参数速查

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--device` | `/dev/video41` | 摄像头设备节点 |
| `--calib-file` | - | 标定 `.npz` 文件，**建议显式传入本目录路径** |
| `--model` | - | RKNN 模型，**建议显式传入** |
| `--labels` | - | 标签文件，**建议显式传入** |
| `--view-width/height` | 1280/720 | 输出画面尺寸 |
| `--render-mode` | `sample` | `sample`=样本同款导播框；`legacy`=旧版锚点裁切 |
| `--conf` | 0.25 | 人物检测置信度阈值 |
| `--nms` | 0.45 | NMS IoU 阈值 |
| `--detect-interval` | 3 | 每隔 N 帧做一次 RKNN 检测 |
| `--smooth` | 0.70 | 检测框平滑系数 |
| `--headless` | 关闭 | 无窗口运行 |
| `--display-scale` | 0.5 | 预览窗口缩放 |
| `--record-encoder` | `h264_rkmpp` | 录制编码器；不可用时改 `libx264` |
| `--stream-encoder` | `h264_rkmpp` | 推流编码器；不可用时改 `libx264` |
| `--stream-fps` | 25 | 推流帧率 |
| `--stream-bitrate` | 4M | 推流码率 |

> **路径提醒**：`single_rknn_base.py` 中部分默认路径仍指向旧工程。建议运行时显式传入 `--model`、`--labels`、`--calib-file`、`--record-dir`、`--save-dir` 等参数。

---

## 三、人脸检录

脚本：[face_checkin_lbph.py](face_checkin_lbph.py)

使用 **Haar Cascade 人脸检测 + LBPH 人脸识别**，支持采集、训练、识别签到三种模式。

### 安装依赖（使用独立虚拟环境）

```bash
cd /home/elf/work/camera_150
source face_env/bin/activate
python3 -m pip install opencv-contrib-python numpy
python3 -c "import cv2; print(hasattr(cv2, 'face'))"  # 应输出 True
```

### 采集人员人脸

```bash
source face_env/bin/activate
python3 face_checkin_lbph.py \
  --mode enroll \
  --person-id 001 \
  --name 张三 \
  --device /dev/video41 \
  --width 1920 --height 1080 --fps 30 \
  --calib-file camera_usb3_calib.npz \
  --samples 40
```

采集时缓慢左右转头和抬头低头，按 `q` / `Esc` 提前退出，达到 `--samples` 数量后自动结束。样本保存在 `face_checkin/dataset/<编号>__<姓名>/`。

### 训练识别模型

```bash
source face_env/bin/activate
python3 face_checkin_lbph.py --mode train
```

生成 `face_checkin/trainer/lbph_model.yml` 和 `labels.json`。

### 实时识别并检录

```bash
source face_env/bin/activate
python3 face_checkin_lbph.py \
  --mode recognize \
  --device /dev/video41 \
  --calib-file camera_usb3_calib.npz
```

同一身份连续识别达到 `--stable-hits`（默认 5）次后写入 `face_checkin/records/checkin_YYYYMMDD.csv`，同一人员当天只登记一次。

### 一条命令训练后立即识别

```bash
source face_env/bin/activate
python3 face_checkin_lbph.py \
  --mode train-recognize \
  --device /dev/video41 \
  --calib-file camera_usb3_calib.npz
```

### 人脸检录重要参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--samples` | 40 | 每人目标样本数 |
| `--recognition-threshold` | 68.0 | LBPH 最大接受距离，越小越严格 |
| `--stable-hits` | 5 | 连续识别稳定帧数 |
| `--manual-capture` | 关闭 | 手动模式：满足质量门槛后按 `c` 保存 |
| `--min-face-size` | 140 | 忽略小于此像素的人脸 |
| `--headless` | 关闭 | 无窗口运行 |

> **说明**：`face_checkin_lbph.py` 包含质量筛选（亮度/清晰度/眼睛检测/人脸稳定/重复过滤），能有效减少非人脸和模糊帧进入训练集。后续项目可替换为 RetinaFace/SCRFD + ArcFace 并转为 RKNN 在 NPU 上运行。

---

## 四、技术台 V2

模块目录：[techtable_v2/](techtable_v2/)

PyQt5 篮球计分面板，在 RK3588 本地 LCD 显示视频 + 叠加比分条，同时通过 HTTP 提供状态接口供 PC 远端客户端同步。

### 启动技术台主控

```bash
cd /home/elf/work/camera_150
python3 techtable_v2/rk_techtable_panel.py \
  --rtsp rtsp://127.0.0.1:8554/director \
  --state techtable_v2/game_state.json \
  --roster techtable_v2/sample_roster.json \
  --state-host 0.0.0.0 \
  --state-port 8010
```

启动后：
- **网页计分**：`http://RK_IP:8010/`
- **状态接口**：`http://RK_IP:8010/state`

### PC 远端观赛客户端

```bash
python3 techtable_v2/viewer_client.py \
  --rtsp rtsp://RK_IP:8554/director \
  --state-url http://RK_IP:8010/state
```

### 技术台功能

- 两队比分、节次、时间
- 球员得分和犯规记录
- 球队犯规累计
- JSON 状态持久化 + JSONL 事件日志
- 客户端侧叠加比分条，不修改原始推流

---

## 五、视频录制工具

### record_usb3_camera_150.py

支持三种录制模式：

```bash
# 只录制未矫正原始视频
python3 record_usb3_camera_150.py --mode raw --calib-file camera_usb3_calib.npz

# 只录制矫正后视频
python3 record_usb3_camera_150.py --mode undistort --calib-file camera_usb3_calib.npz

# 同时录制两份
python3 record_usb3_camera_150.py --mode both --calib-file camera_usb3_calib.npz

# 录制 60 秒自动停止
python3 record_usb3_camera_150.py --mode both --duration 60
```

### record_undistorted_usb3_camera_150.py

实时畸变矫正预览 + 按需录制：

```bash
# 手动按 r 开始/停止录制
python3 record_undistorted_usb3_camera_150.py \
  --device /dev/video41 \
  --calib-file camera_usb3_calib.npz

# 无窗口自动录制 60 秒
python3 record_undistorted_usb3_camera_150.py \
  --headless --auto-record --record-seconds 60 \
  --device /dev/video41 --calib-file camera_usb3_calib.npz
```

---

## 六、一键启停

### 启动全部进程

```bash
cd /home/elf/work/camera_150
python3 start_all_techtable.py
```

自动打开 3 个终端窗口：

| 序号 | 进程 | 说明 |
|------|------|------|
| 1 | MediaMTX | RTSP 服务器 (8554) |
| 2 | 导播推流 | RKNN 运镜 + RTSP 推流 |
| 3 | 技术台主控 | PyQt5 面板 + HTTP 状态 (8010) |

### 停止全部进程

```bash
python3 stop_all_techtable.py
```

自动结束以上三个进程并检查端口占用。

---

## 七、故障排查

### 摄像头打不开

```bash
ls /dev/video*
v4l2-ctl --list-devices
v4l2-ctl -d /dev/video41 --all
```

如果实际节点不是 `/dev/video41`，通过 `--device` 修改。

### OpenCV 窗口不显示

```bash
export DISPLAY=:0
```

或使用 `--headless` 无窗口模式。

### RKNN 模型加载失败

1. 确认模型路径正确
2. 确认 NPU 驱动和 RKNNLite 版本匹配
3. 尝试不指定单核：`--rknn-core -1`

### 没有 h264_rkmpp 编码器

```bash
ffmpeg -hide_banner -encoders | grep rkmpp
```

如果没有输出，改用软件编码：`--record-encoder libx264` 或 `--stream-encoder libx264`。

### RTSP 推流失败

```bash
ss -lntp | grep 8554    # 确认 MediaMTX 在监听
```

### VLC 打不开 RTSP

- 确认电脑和 RK3588 在同一局域网
- VLC 使用 `媒体 → 打开网络串流`，不要进入 `媒体 → 串流`
- 地址格式：`rtsp://RK3588的IP:8554/director`

### 网络画面延迟增大

推流缓冲已采用"只保留最新帧"策略。VLC 端可调低网络缓存：`工具 → 偏好设置 → 输入/编解码器 → 网络缓存 → 100~300 ms`。

---

## 当前工程状态

- 已有 32 张 USB 摄像头标定原图
- 已有单目标定文件 `camera_usb3_calib.npz`（RMS ~0.755，正常可用）
- 标定分辨率 1920×1080
- RKNN 人物检测模型已部署，标签为 `person`
- 720p 运镜输出 + 本地录制 / RTSP 推流均可正常运行
- 人脸检录（Haar + LBPH）采集、训练、识别流程完整可用
- 技术台 V2 PyQt5 面板 + HTTP 状态服务 + PC viewer 配套完整
- 推流内置 watchdog 自动重连
- 运行时建议显式传入 `camera_150` 目录下的模型、标签、标定等路径
