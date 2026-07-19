#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Apply the RK3588 NAU8822 audio-chain changes to camera_150_with_face.

Run from the repository root:
    python3 audio_patch/apply_audio_chain.py --check
    python3 audio_patch/apply_audio_chain.py
"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path


AUDIO_CHAIN_PY = r'''#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""RK3588 / NAU8822 的 FFmpeg 音频参数构造工具。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List


@dataclass(frozen=True)
class AudioConfig:
    """一套同时供本地录像和网络推流使用的音频配置。"""

    enabled: bool = False
    device: str = "hw:1,0"
    sample_rate: int = 48000
    channels: int = 2
    codec: str = "aac"
    bitrate: str = "128k"
    thread_queue_size: int = 1024
    async_samples: int = 1000

    def validate(self) -> None:
        if not self.enabled:
            return
        if not self.device:
            raise ValueError("audio device 不能为空")
        if self.sample_rate <= 0:
            raise ValueError("audio sample_rate 必须大于 0")
        if self.channels not in (1, 2):
            raise ValueError("audio channels 当前仅支持 1 或 2")
        if self.thread_queue_size < 8:
            raise ValueError("audio thread_queue_size 不能小于 8")
        if self.async_samples <= 0:
            raise ValueError("audio async_samples 必须大于 0")


def build_alsa_input_args(config: AudioConfig) -> List[str]:
    """构造 ALSA 实时采集输入参数；禁用音频时返回空列表。"""
    config.validate()
    if not config.enabled:
        return []

    return [
        "-thread_queue_size", str(config.thread_queue_size),
        "-f", "alsa",
        "-ac", str(config.channels),
        "-ar", str(config.sample_rate),
        "-i", config.device,
    ]


def build_audio_output_args(
    config: AudioConfig,
    audio_input_index: int = 1,
) -> List[str]:
    """
    映射并编码音频。

    aresample=async 会通过小幅补偿音频采样来跟随视频时钟，
    first_pts=0 让音频时间轴从 0 开始，减少起播时的音画偏移。
    """
    config.validate()
    if not config.enabled:
        return ["-an"]

    return [
        "-map", f"{audio_input_index}:a:0",
        "-af", f"aresample=async={config.async_samples}:first_pts=0",
        "-c:a", config.codec,
        "-b:a", config.bitrate,
        "-ar", str(config.sample_rate),
        "-ac", str(config.channels),
    ]


def audio_summary(config: AudioConfig) -> str:
    if not config.enabled:
        return "disabled"
    return (
        f"{config.device}, {config.sample_rate} Hz, "
        f"{config.channels} ch, {config.codec} {config.bitrate}"
    )


def add_audio_cli_args(parser, prefix: str) -> None:
    """给 argparse parser 增加统一的音频参数。"""
    parser.add_argument(f"--{prefix}-audio", action="store_true", help="启用 NAU8822/ALSA 音频")
    parser.add_argument(f"--{prefix}-audio-device", default="hw:1,0", help="ALSA 录音设备")
    parser.add_argument(f"--{prefix}-audio-rate", type=int, default=48000, help="音频采样率")
    parser.add_argument(f"--{prefix}-audio-channels", type=int, default=2, help="音频通道数")
    parser.add_argument(f"--{prefix}-audio-codec", default="aac", help="音频编码器")
    parser.add_argument(f"--{prefix}-audio-bitrate", default="128k", help="音频码率")
    parser.add_argument(f"--{prefix}-audio-queue-size", type=int, default=1024, help="ALSA 输入包队列")
    parser.add_argument(f"--{prefix}-audio-async", type=int, default=1000, help="音频异步重采样补偿量")


def audio_config_from_args(args, prefix: str) -> AudioConfig:
    key = prefix.replace("-", "_")
    return AudioConfig(
        enabled=bool(getattr(args, f"{key}_audio")),
        device=str(getattr(args, f"{key}_audio_device")),
        sample_rate=int(getattr(args, f"{key}_audio_rate")),
        channels=int(getattr(args, f"{key}_audio_channels")),
        codec=str(getattr(args, f"{key}_audio_codec")),
        bitrate=str(getattr(args, f"{key}_audio_bitrate")),
        thread_queue_size=int(getattr(args, f"{key}_audio_queue_size")),
        async_samples=int(getattr(args, f"{key}_audio_async")),
    )
'''

AUDIO_CHAIN_MD = r'''# RK3588 NAU8822 正式音频链路

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
'''


REPLACEMENTS: dict[str, list[tuple[str, str]]] = {
    "camera_movement_modified/single_rknn_director_view720_network_stream.py": [
        (
'''from typing import Optional, Tuple
from urllib.parse import urlparse

# RK3588 / Mali 平台上 OpenCV 有时会尝试启用 OpenCL，可能带来额外开销。
''',
'''from typing import Optional, Tuple
from urllib.parse import urlparse

from audio_chain import (
    AudioConfig,
    add_audio_cli_args,
    audio_config_from_args,
    audio_summary,
    build_alsa_input_args,
    build_audio_output_args,
)

# RK3588 / Mali 平台上 OpenCV 有时会尝试启用 OpenCL，可能带来额外开销。
'''),
        (
'''        restart_backoff: float = 2.0,
        check_rtsp_server: bool = True,
        resize_input: bool = True,
    ):
''',
'''        restart_backoff: float = 2.0,
        check_rtsp_server: bool = True,
        resize_input: bool = True,
        audio_config: Optional[AudioConfig] = None,
    ):
'''),
        (
'''        self.check_rtsp_server = bool(check_rtsp_server)
        self.resize_input = bool(resize_input)

        self.slot = LatestFrameSlot()
''',
'''        self.check_rtsp_server = bool(check_rtsp_server)
        self.resize_input = bool(resize_input)
        self.audio = audio_config or AudioConfig(enabled=False)

        self.slot = LatestFrameSlot()
'''),
        (
'''        print(f"  encoder     : {self.encoder}")
        print(f"  bitrate     : {self.bitrate}")
        print(f"  ffmpeg log  : {self.log_path}")
''',
'''        print(f"  encoder     : {self.encoder}")
        print(f"  bitrate     : {self.bitrate}")
        print(f"  audio       : {audio_summary(self.audio)}")
        print(f"  ffmpeg log  : {self.log_path}")
'''),
        (
'''        alive = self.proc is not None and self.proc.poll() is None
        state = "STREAM_ON" if alive else "STREAM_OFF"
        return (
            f"{state} w={self.stats.written} "
            f"drop={self.stats.dropped} rst={self.stats.restart_count}"
        )
''',
'''        alive = self.proc is not None and self.proc.poll() is None
        state = "STREAM_ON" if alive else "STREAM_OFF"
        audio_state = "AON" if self.audio.enabled else "AOFF"
        return (
            f"{state}/{audio_state} w={self.stats.written} "
            f"drop={self.stats.dropped} rst={self.stats.restart_count}"
        )
'''),
        (
'''        cmd = [
            self.ffmpeg_bin,
            "-hide_banner",
            "-loglevel", self.loglevel,
            "-nostdin",

            # 原始 BGR 帧输入。
            "-f", "rawvideo",
            "-pix_fmt", "bgr24",
            "-s", f"{self.width}x{self.height}",
            "-r", str(self.fps),
            "-i", "-",

            # 不推音频。
            "-an",

            # 像素格式转换。
            "-vf", video_filter,
        ]

        cmd += encoder_args

        # flush_packets 可以降低封装端缓存，减少延迟。
        cmd += ["-flush_packets", "1"]
''',
'''        cmd = [
            self.ffmpeg_bin,
            "-hide_banner",
            "-loglevel", self.loglevel,
            "-nostdin",

            # 原始 BGR 帧输入。
            "-f", "rawvideo",
            "-pix_fmt", "bgr24",
            "-s", f"{self.width}x{self.height}",
            "-r", str(self.fps),
            "-i", "-",
        ]

        # 第二路输入由 FFmpeg 直接从 NAU8822/ALSA 采集，Python 不搬运 PCM。
        cmd += build_alsa_input_args(self.audio)

        # 显式映射视频，避免增加音频输入后 FFmpeg 自动选流产生歧义。
        cmd += [
            "-map", "0:v:0",
            "-vf", video_filter,
        ]
        cmd += encoder_args

        # 音频启用时映射 1:a:0 并编码 AAC；禁用时保持 -an。
        cmd += build_audio_output_args(self.audio, audio_input_index=1)

        # flush_packets 可以降低封装端缓存，减少延迟。
        cmd += [
            "-max_muxing_queue_size", "1024",
            "-flush_packets", "1",
        ]
'''),
        (
'''        check_rtsp_server=not args.no_rtsp_check,
        resize_input=True,
    )
''',
'''        check_rtsp_server=not args.no_rtsp_check,
        resize_input=True,
        audio_config=audio_config_from_args(args, "stream"),
    )
'''),
        (
'''    parser.add_argument("--stream-heartbeat-timeout", type=float, default=8.0, help="推流心跳超时，单位秒")
    parser.add_argument("--stream-restart-backoff", type=float, default=2.0, help="FFmpeg 最小重启间隔，单位秒")

    return parser.parse_args()
''',
'''    parser.add_argument("--stream-heartbeat-timeout", type=float, default=8.0, help="推流心跳超时，单位秒")
    parser.add_argument("--stream-restart-backoff", type=float, default=2.0, help="FFmpeg 最小重启间隔，单位秒")

    # NAU8822 / ALSA 正式音频链路。
    add_audio_cli_args(parser, "stream")

    return parser.parse_args()
'''),
        (
'''    print(f"stream_encoder      : {args.stream_encoder}")
    print(f"stream_bitrate      : {args.stream_bitrate}")
    print(f"stream_overlay      : {args.stream_overlay}")
''',
'''    print(f"stream_encoder      : {args.stream_encoder}")
    print(f"stream_bitrate      : {args.stream_bitrate}")
    print(f"stream_audio        : {audio_summary(audio_config_from_args(args, 'stream'))}")
    print(f"stream_overlay      : {args.stream_overlay}")
'''),
    ],
    "camera_movement_modified/single_rknn_director_view720_record_local.py": [
        (
'''from datetime import datetime
from typing import List, Tuple

# RK3588 / Mali 平台上 OpenCV 有时会尝试启用 OpenCL。
''',
'''from datetime import datetime
from typing import List, Optional, Tuple

from audio_chain import (
    AudioConfig,
    add_audio_cli_args,
    audio_config_from_args,
    audio_summary,
    build_alsa_input_args,
    build_audio_output_args,
)

# RK3588 / Mali 平台上 OpenCV 有时会尝试启用 OpenCL。
'''),
        (
'''        encoder: str = "h264_rkmpp",
        queue_size: int = 60,
        prefix: str = "single_director_view720",
    ):
''',
'''        encoder: str = "h264_rkmpp",
        queue_size: int = 60,
        prefix: str = "single_director_view720",
        audio_config: Optional[AudioConfig] = None,
    ):
'''),
        (
'''        self.queue_size = int(queue_size)
        self.prefix = str(prefix)

        self.proc = None
''',
'''        self.queue_size = int(queue_size)
        self.prefix = str(prefix)
        self.audio = audio_config or AudioConfig(enabled=False)

        self.proc = None
'''),
        (
'''    def _build_cmd(self):
        """构造 ffmpeg 命令。输入是 BGR24 原始帧，输出是 mp4。"""
        return [
            "ffmpeg",
            "-y",
            "-hide_banner",
            "-loglevel", "warning",
            "-f", "rawvideo",
            "-pix_fmt", "bgr24",
            "-s", f"{self.frame_w}x{self.frame_h}",
            "-r", str(self.fps),
            "-i", "-",
            "-vf", "format=nv12",
            "-c:v", self.encoder,
            "-b:v", self.bitrate,
            "-maxrate", self.bitrate,
            "-bufsize", bitrate_to_bufsize(self.bitrate),
            "-an",
            "-movflags", "+faststart",
            self.path,
        ]
''',
'''    def _build_cmd(self):
        """构造 FFmpeg 命令：BGR24 视频 + ALSA 音频 -> H.264/AAC MP4。"""
        cmd = [
            "ffmpeg",
            "-y",
            "-hide_banner",
            "-loglevel", "warning",
            "-nostdin",
            "-f", "rawvideo",
            "-pix_fmt", "bgr24",
            "-s", f"{self.frame_w}x{self.frame_h}",
            "-r", str(self.fps),
            "-i", "-",
        ]

        cmd += build_alsa_input_args(self.audio)

        cmd += [
            "-map", "0:v:0",
            "-vf", "format=nv12",
            "-c:v", self.encoder,
            "-b:v", self.bitrate,
            "-maxrate", self.bitrate,
            "-bufsize", bitrate_to_bufsize(self.bitrate),
        ]

        cmd += build_audio_output_args(self.audio, audio_input_index=1)

        cmd += [
            "-max_muxing_queue_size", "1024",
            # 关闭 Python 的视频 stdin 后，以视频流结束作为 MP4 收尾条件。
            "-shortest",
            "-movflags", "+faststart",
            self.path,
        ]

        return cmd
'''),
        (
'''        print(f"  encoder : {self.encoder}")
        print(f"  bitrate : {self.bitrate}")
        print(f"  log     : {self.log_path}")
''',
'''        print(f"  encoder : {self.encoder}")
        print(f"  bitrate : {self.bitrate}")
        print(f"  audio   : {audio_summary(self.audio)}")
        print(f"  log     : {self.log_path}")
'''),
        (
'''        if not self.is_recording:
            return "STANDBY"
        return f"REC w={self.written} q={self.q.qsize() if self.q is not None else 0} d={self.dropped}"
''',
'''        if not self.is_recording:
            return "STANDBY"
        audio_state = "AON" if self.audio.enabled else "AOFF"
        return f"REC/{audio_state} w={self.written} q={self.q.qsize() if self.q is not None else 0} d={self.dropped}"
'''),
        (
'''        queue_size=args.record_queue_size,
        prefix="single_director_view720",
    )
''',
'''        queue_size=args.record_queue_size,
        prefix="single_director_view720",
        audio_config=audio_config_from_args(args, "record"),
    )
'''),
        (
'''    parser.add_argument("--record-queue-size", type=int, default=60, help="录制后台队列大小，满了会丢旧帧")
    parser.add_argument("--record-overlay", action="store_true", help="打开后录制带检测框/状态文字的画面；默认录制干净 view")

    # 性能日志。
''',
'''    parser.add_argument("--record-queue-size", type=int, default=60, help="录制后台队列大小，满了会丢旧帧")
    parser.add_argument("--record-overlay", action="store_true", help="打开后录制带检测框/状态文字的画面；默认录制干净 view")

    # NAU8822 / ALSA 正式音频链路。
    add_audio_cli_args(parser, "record")

    # 性能日志。
'''),
        (
'''    print(f"record_dir         : {args.record_dir}")
    print(f"record_fps/encoder : {args.record_fps} / {args.record_encoder}")
    print("====================================================================\\n")
''',
'''    print(f"record_dir         : {args.record_dir}")
    print(f"record_fps/encoder : {args.record_fps} / {args.record_encoder}")
    print(f"record_audio       : {audio_summary(audio_config_from_args(args, 'record'))}")
    print("====================================================================\\n")
'''),
    ],
    "start_all_techtable.py": [
        (
'''                    "--stream-encoder",
                    "h264_rkmpp",
                ],
''',
'''                    "--stream-encoder",
                    "h264_rkmpp",
                    "--stream-audio",
                    "--stream-audio-device", "hw:1,0",
                    "--stream-audio-rate", "48000",
                    "--stream-audio-channels", "2",
                    "--stream-audio-codec", "aac",
                    "--stream-audio-bitrate", "128k",
                ],
'''),
    ],
}


def replace_once(text: str, old: str, new: str, path: Path) -> str:
    count = text.count(old)
    if count == 0:
        # 修改可能已经应用过，检查 new 内容是否已存在
        if text.count(new) >= 1:
            return text  # 已打，跳过
        raise RuntimeError(f"{path}: 找不到目标片段，且新内容也未出现。仓库版本可能已变化。")
    if count > 1:
        raise RuntimeError(f"{path}: 预期匹配 1 次，实际匹配 {count} 次。仓库版本可能已变化。")
    return text.replace(old, new, 1)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", default=".", help="camera_150_with_face 仓库根目录")
    parser.add_argument("--check", action="store_true", help="只检查，不写文件")
    args = parser.parse_args()

    root = Path(args.repo).resolve()
    changed: dict[Path, str] = {}

    for rel, pairs in REPLACEMENTS.items():
        path = root / rel
        if not path.is_file():
            raise FileNotFoundError(f"找不到目标文件: {path}")
        original = path.read_text(encoding="utf-8")
        text = original
        for old, new in pairs:
            text = replace_once(text, old, new, path)
        if text != original:
            changed[path] = text

    new_files = {
        root / "camera_movement_modified/audio_chain.py": AUDIO_CHAIN_PY,
        root / "AUDIO_CHAIN.md": AUDIO_CHAIN_MD,
    }

    new_files_write: dict[Path, str] = {}
    for path, text in new_files.items():
        if path.exists():
            print(f"[跳过] 新文件已存在: {path}")
        else:
            new_files_write[path] = text

    if not changed and not new_files_write:
        print("所有修改已存在，无需操作。")
        return

    if args.check:
        print("[检查通过] 所有目标片段均唯一匹配。")
        return

    for path, text in changed.items():
        backup = path.with_name(path.name + ".before_audio_chain")
        if not backup.exists():
            shutil.copy2(path, backup)
        path.write_text(text, encoding="utf-8")
        print(f"[已修改] {path}")

    for path, text in new_files_write.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        print(f"[已创建] {path}")

    print("\n完成。下一步执行：")
    print("python3 -m py_compile \\")
    print("  camera_150/camera_movement_modified/audio_chain.py \\")
    print("  camera_150/camera_movement_modified/single_rknn_director_view720_network_stream.py \\")
    print("  camera_150/camera_movement_modified/single_rknn_director_view720_record_local.py \\")
    print("  camera_150/start_all_techtable.py")
    print("然后阅读 camera_150/AUDIO_CHAIN.md 做板端验证。")


if __name__ == "__main__":
    main()
