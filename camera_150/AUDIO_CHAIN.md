# RK3588 NAU8822 正式音频链路

## 1. 链路结构

```text
NAU8822 板载声卡 hw:1,0
        ↓ ALSA / 48 kHz / 2 ch
FFmpeg ALSA input
        ↓ aresample=async=1000:first_pts=0
AAC 128 kbit/s
        ├── 与 H.264 一起封装为 MP4
        └── 与 H.264 一起推送到 RTSP / MPEG-TS
```

视频仍由 Python 通过 stdin 喂给 FFmpeg；音频由 FFmpeg 直接读取 ALSA，
避免 Python 搬运 PCM、额外复制和音频线程调度抖动。

## 2. 板端能力检查

```bash
arecord -l
ffmpeg -hide_banner -devices | grep -i alsa
ffmpeg -hide_banner -encoders | grep -E 'aac|h264_rkmpp'
```

## 3. 单独验证 FFmpeg 能否读取 NAU8822

```bash
ffmpeg -y \
  -thread_queue_size 1024 \
  -f alsa -ac 2 -ar 48000 -i hw:1,0 \
  -t 5 \
  -c:a aac -b:a 128k \
  nau8822_test.m4a

ffprobe -hide_banner nau8822_test.m4a
```

## 4. 带音频的 RTSP 推流

一键启动脚本已经加入：

```text
--stream-audio
--stream-audio-device hw:1,0
--stream-audio-rate 48000
--stream-audio-channels 2
--stream-audio-codec aac
--stream-audio-bitrate 128k
```

验证：

```bash
ffprobe -hide_banner rtsp://127.0.0.1:8554/director
```

应看到一条 H.264 video stream 和一条 AAC audio stream。

## 5. 带音频的本地 MP4 录制

```bash
python3 camera_movement_modified/single_rknn_director_view720_record_local.py \
  --device /dev/video41 \
  --record-fps 25 \
  --record-bitrate 8M \
  --record-encoder h264_rkmpp \
  --record-audio \
  --record-audio-device hw:1,0 \
  --record-audio-rate 48000 \
  --record-audio-channels 2 \
  --record-audio-codec aac \
  --record-audio-bitrate 128k
```

按 `r` 或空格开始/停止录制。

## 6. 重要限制

`hw:1,0` 是硬件 PCM 设备，通常不应被两个独立进程同时独占。

- 只推流：运行网络推流脚本。
- 只录像：运行本地录制脚本。
- 同时推流和录像：应让同一个 FFmpeg 进程采集一次音频，再通过 tee/fifo 输出到 RTSP 和本地文件；不要同时启动两个都直接读取 `hw:1,0` 的脚本。

若日志出现 `Device or resource busy`：

```bash
fuser -v /dev/snd/pcmC1D0c
sudo lsof /dev/snd/pcmC1D0c
```

## 7. 常见问题

- 没声音：检查 `alsamixer -c 1` 的 Capture 开关和增益。
- 音画逐渐漂移：保持 48000 Hz，不要删除 `aresample=async=1000:first_pts=0`。
- FFmpeg 反复重启：查看 `camera_movement_modified/stream_logs/*.ffmpeg.log`。
