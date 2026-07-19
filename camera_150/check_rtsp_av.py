#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""检查 camera_150 RTSP 是否同时包含 H.264 视频和 AAC 音频。"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--url",
        default="rtsp://127.0.0.1:8554/director",
    )
    args = parser.parse_args()

    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        print("[FAIL] 找不到 ffprobe", file=sys.stderr)
        return 2

    cmd = [
        ffprobe,
        "-v", "error",
        "-rtsp_transport", "tcp",
        "-show_entries",
        "stream=index,codec_type,codec_name,sample_rate,channels",
        "-of", "json",
        args.url,
    ]

    result = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
        timeout=10,
    )

    if result.returncode != 0:
        print("[FAIL] ffprobe 无法读取 RTSP：", file=sys.stderr)
        print(result.stderr.strip(), file=sys.stderr)
        return 3

    payload = json.loads(result.stdout or "{}")
    streams = payload.get("streams", []) or []
    videos = [s for s in streams if s.get("codec_type") == "video"]
    audios = [s for s in streams if s.get("codec_type") == "audio"]

    print(json.dumps(payload, ensure_ascii=False, indent=2))

    if not videos:
        print("[FAIL] RTSP 中没有视频轨")
        return 4
    if not audios:
        print("[FAIL] RTSP 中没有音频轨")
        return 5

    audio = audios[0]
    codec = str(audio.get("codec_name", "")).lower()
    rate = str(audio.get("sample_rate", ""))
    channels = str(audio.get("channels", ""))

    errors = []
    if codec != "aac":
        errors.append(f"音频编码不是 AAC，而是 {codec or '未知'}")
    if rate and rate != "48000":
        errors.append(f"采样率不是 48000 Hz，而是 {rate}")
    if channels and channels != "2":
        errors.append(f"通道数不是 2，而是 {channels}")

    if errors:
        print("[FAIL] " + "；".join(errors))
        return 6

    print(
        "[PASS] RTSP 音视频正常："
        f"video={videos[0].get('codec_name')}，"
        f"audio={codec}/{rate or '?'}Hz/{channels or '?'}ch"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
