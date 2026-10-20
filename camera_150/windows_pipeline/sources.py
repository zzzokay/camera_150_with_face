"""
文件作用：按顺序读取本地视频或 Windows 摄像头，保留源帧号和时间。
输入：视频 Path 或摄像头编号、捕获后端、可选 FPS；输出：VideoFrame。
依赖：OpenCV；调用关系：run -> VideoSource；不依赖 RKNN/FFmpeg 可执行程序。
注意：离线文件不使用“只取最新帧”线程，防止离线测试丢帧或重复处理同帧。
运行示例：见 NEWCOMER_HANDOFF.md。
"""
import logging
import math
import time
from pathlib import Path

import cv2

from .contracts import VideoFrame


class VideoSource:
    """同步视频源；文件用容器时间戳，缺失/不递增时回退源帧号/FPS。"""

    def __init__(self, source: Path | None, camera: int | None = None, backend: str = "auto",
                 fps: float | None = None, width: int = 1920, height: int = 1080):
        self.source, self.camera = source, camera
        self.backend, self.requested_fps = backend, fps
        self.width, self.height = width, height
        self.cap = None
        self.fps = 0.0
        self.frame_count = 0
        self.index = 0
        self.last_timestamp = -1.0
        self.fallback_count = 0
        self.origin_time = None

    def __enter__(self):
        """打开源；FPS 无法确定时拒绝猜测，并在异常前释放设备。"""
        if self.source is not None and not self.source.is_file():
            raise FileNotFoundError(f"视频不存在：{self.source}")
        backends = {"auto": cv2.CAP_ANY, "dshow": cv2.CAP_DSHOW,
                    "msmf": cv2.CAP_MSMF, "ffmpeg": cv2.CAP_FFMPEG}
        value = str(self.source) if self.source is not None else self.camera
        self.cap = cv2.VideoCapture(value, backends[self.backend])
        try:
            if not self.cap.isOpened():
                raise RuntimeError(f"无法打开视频源：{value}，后端={self.backend}")
            if self.camera is not None:
                self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
                self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
                if self.requested_fps:
                    self.cap.set(cv2.CAP_PROP_FPS, self.requested_fps)
            self.fps = float(self.cap.get(cv2.CAP_PROP_FPS))
            if not math.isfinite(self.fps) or self.fps <= 0:
                if not self.requested_fps:
                    raise ValueError("源 FPS 无效，请显式指定 --fps；不会静默假设 30 FPS")
                self.fps = self.requested_fps
                logging.warning("源 FPS 元数据无效，使用显式 --fps=%s", self.fps)
            count = self.cap.get(cv2.CAP_PROP_FRAME_COUNT)
            self.frame_count = int(count) if math.isfinite(count) and count > 0 else 0
            self.backend_name = self.cap.getBackendName()
            return self
        except Exception:
            self.cap.release()
            raise

    def read(self) -> VideoFrame | None:
        """返回下一帧；正常文件结尾返回 None，摄像头断流/提前解码失败抛异常。"""
        ok, frame = self.cap.read()
        if not ok or frame is None:
            if self.camera is not None or (self.frame_count and self.index < self.frame_count - 1):
                raise RuntimeError(f"读取失败，已读 {self.index} 帧，元数据总帧数 {self.frame_count}")
            return None
        if min(frame.shape[:2]) < 2:
            raise ValueError("视频帧宽高至少应为 2 像素")
        if self.camera is not None:
            # Python 3.11/Windows 的 monotonic 可能只有毫秒级精度，缓冲帧会同秒值。
            # perf_counter 也是单调时钟，精度更高；它是收帧时间，并非相机曝光 PTS。
            now = time.perf_counter()
            if self.origin_time is None:
                self.origin_time = now
            timestamp, basis = now - self.origin_time, "capture_monotonic"
        else:
            timestamp = float(self.cap.get(cv2.CAP_PROP_POS_MSEC)) / 1000.0
            basis = "container_pts"
            if not math.isfinite(timestamp) or timestamp < 0 or timestamp <= self.last_timestamp:
                timestamp = self.index / self.fps
                basis = "source_frame_idx/fps"
                self.fallback_count += 1
            if timestamp <= self.last_timestamp:
                raise ValueError("容器 PTS 与帧号/FPS 均不能提供递增时间戳，请转为恒定帧率视频")
        result = VideoFrame(frame, self.index, timestamp, basis)
        self.last_timestamp = timestamp
        self.index += 1
        return result

    def __exit__(self, *_):
        """释放捕获设备，不删除/改写源文件。"""
        if self.cap is not None:
            self.cap.release()
