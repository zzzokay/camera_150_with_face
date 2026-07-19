#!/usr/bin/env python3
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
