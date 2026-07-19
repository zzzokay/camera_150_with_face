# -*- coding: utf-8 -*-
"""
篮球技术台 V2.1 电脑只读观看端。

用途：
1. 电脑端拉 RK3588 的 RTSP 转播流。
2. 使用 OpenCV 解码视频，并在客户端侧叠加比分条。
3. 使用 ffplay 解码和播放 RTSP 中的 AAC 音频。
4. 实时读取 RK3588 主控端的比赛状态。
5. 只读显示，不提供技术台操作按钮，避免多端各自改比分导致不同步。

说明：
    OpenCV VideoCapture 只能向本程序返回视频帧，不负责扬声器播放。
    因此视频由 OpenCV 处理，音频由独立的 ffplay 进程播放。
    Windows 需要安装 FFmpeg，并保证 ffplay.exe、ffprobe.exe 可用。

推荐运行：
python techtable_v2/viewer_client.py \
  --rtsp rtsp://RK3588的IP:8554/director \
  --state-url http://RK3588的IP:8010/state
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request
from typing import Any, Dict, Optional

import cv2
import numpy as np
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtGui import QImage, QPixmap
from PyQt5.QtWidgets import QApplication, QLabel, QMainWindow, QSizePolicy, QVBoxLayout, QWidget

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)

from scoreboard_overlay import draw_scoreboard
from state_store import default_roster, make_default_state


class VideoThread(QThread):
    frame_ready = pyqtSignal(object)
    status_ready = pyqtSignal(str)

    def __init__(self, rtsp_url: str, target_fps: float = 25.0, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.rtsp_url = rtsp_url
        self.target_fps = max(1.0, float(target_fps))
        self._running = True

    def stop(self) -> None:
        self._running = False
        self.wait(1500)

    def run(self) -> None:
        last_status_ts = 0.0
        # OpenCV 只负责视频。音频由 AudioThread 中的 ffplay 播放。
        os.environ.setdefault(
            "OPENCV_FFMPEG_CAPTURE_OPTIONS",
            "rtsp_transport;tcp|max_delay;500000|stimeout;3000000",
        )

        while self._running:
            cap = cv2.VideoCapture(self.rtsp_url, cv2.CAP_FFMPEG)
            try:
                cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            except Exception:
                pass

            if not cap.isOpened():
                now = time.time()
                if now - last_status_ts > 2.0:
                    self.status_ready.emit("等待视频流……")
                    last_status_ts = now
                cap.release()
                time.sleep(1.0)
                continue

            self.status_ready.emit("视频流已连接")
            frame_interval = 1.0 / self.target_fps
            while self._running:
                t0 = time.time()
                ok, frame = cap.read()
                if not ok or frame is None:
                    self.status_ready.emit("视频流中断，正在重连……")
                    break
                self.frame_ready.emit(frame)
                cost = time.time() - t0
                if cost < frame_interval:
                    time.sleep(frame_interval - cost)
            cap.release()
            time.sleep(0.5)


class AudioThread(QThread):
    """
    Windows RTSP 音频播放线程。

    处理流程：
        ffprobe 检查 RTSP 是否包含音频轨
            ↓
        ffplay 以无画面模式播放音频
            ↓
        音频连接中断后自动重新检查并重连

    这样不会改变现有 OpenCV 视频和比分条逻辑。
    """

    status_ready = pyqtSignal(str)

    def __init__(
        self,
        rtsp_url: str,
        ffplay_bin: str,
        ffprobe_bin: str,
        volume: int,
        log_path: str,
        reconnect_delay: float = 1.0,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self.rtsp_url = rtsp_url
        self.ffplay_bin = str(ffplay_bin)
        self.ffprobe_bin = str(ffprobe_bin)
        self.volume = max(0, min(100, int(volume)))
        self.log_path = os.path.abspath(log_path)
        self.reconnect_delay = max(0.2, float(reconnect_delay))
        self._running = True
        self._process: Optional[subprocess.Popen] = None

    @staticmethod
    def _resolve_program(value: str, fallback_name: str) -> Optional[str]:
        """
        查找 ffplay/ffprobe。

        支持：
        1. --ffplay-bin 指定完整路径；
        2. PATH 中的 ffplay.exe；
        3. viewer_client.py 同目录；
        4. 同目录 ffmpeg/bin/。
        """
        value = str(value or "").strip()
        if value and os.path.isfile(value):
            return os.path.abspath(value)

        if value:
            found = shutil.which(value)
            if found:
                return found

        found = shutil.which(fallback_name)
        if found:
            return found

        executable_name = fallback_name + (".exe" if os.name == "nt" else "")
        candidates = [
            os.path.join(CURRENT_DIR, executable_name),
            os.path.join(CURRENT_DIR, "ffmpeg", "bin", executable_name),
            os.path.join(CURRENT_DIR, "bin", executable_name),
        ]
        for candidate in candidates:
            if os.path.isfile(candidate):
                return os.path.abspath(candidate)
        return None

    @staticmethod
    def _creation_flags() -> int:
        if os.name == "nt" and hasattr(subprocess, "CREATE_NO_WINDOW"):
            return int(subprocess.CREATE_NO_WINDOW)
        return 0

    def stop(self) -> None:
        self._running = False
        self._stop_player()
        self.wait(2500)

    def _stop_player(self) -> None:
        process = self._process
        self._process = None
        if process is None:
            return

        try:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=1.5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=1.0)
        except Exception:
            pass

    def _probe_audio(
        self,
        ffprobe: Optional[str],
    ) -> tuple[Optional[bool], str]:
        """
        返回：
            True：确认存在音频轨；
            False：当前无法读取音频轨，稍后重试；
            None：没有 ffprobe，跳过检测并直接尝试 ffplay。
        """
        if not ffprobe:
            return None, "未找到 ffprobe，跳过音轨检测"

        command = [
            ffprobe,
            "-v", "error",
            "-rtsp_transport", "tcp",
            "-select_streams", "a:0",
            "-show_entries", "stream=codec_name,sample_rate,channels",
            "-of", "json",
            self.rtsp_url,
        ]

        try:
            result = subprocess.run(
                command,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
                timeout=6.0,
                creationflags=self._creation_flags(),
            )
        except subprocess.TimeoutExpired:
            return False, "音频检测超时，正在重试"
        except Exception as exc:
            return False, f"音频检测失败：{exc}"

        if result.returncode != 0:
            detail = result.stderr.strip()
            if len(detail) > 120:
                detail = detail[-120:]
            return False, f"暂未读取到 RTSP 音频：{detail or result.returncode}"

        try:
            payload = json.loads(result.stdout or "{}")
        except Exception:
            return False, "ffprobe 返回内容无法解析"

        streams = payload.get("streams", []) or []
        if not streams:
            return False, "RTSP 当前没有音频轨，正在重试"

        stream = streams[0]
        codec = str(stream.get("codec_name", "unknown"))
        rate = str(stream.get("sample_rate", "?"))
        channels = str(stream.get("channels", "?"))
        return True, f"检测到音频：{codec} / {rate} Hz / {channels} ch"

    def _tail_log(self, limit: int = 3) -> str:
        try:
            with open(self.log_path, "r", encoding="utf-8", errors="replace") as file:
                lines = [line.strip() for line in file.readlines() if line.strip()]
            return " | ".join(lines[-limit:])
        except Exception:
            return ""

    def run(self) -> None:
        ffplay = self._resolve_program(self.ffplay_bin, "ffplay")
        ffprobe = self._resolve_program(self.ffprobe_bin, "ffprobe")

        if not ffplay:
            self.status_ready.emit(
                "没有声音：找不到 ffplay.exe，请安装 FFmpeg 或使用 --ffplay-bin"
            )
            return

        os.makedirs(os.path.dirname(self.log_path), exist_ok=True)

        while self._running:
            probe_ok, probe_text = self._probe_audio(ffprobe)
            self.status_ready.emit(probe_text)

            if probe_ok is False:
                time.sleep(self.reconnect_delay)
                continue

            command = [
                ffplay,
                "-hide_banner",
                "-loglevel", "warning",
                "-nodisp",
                "-vn",
                "-rtsp_transport", "tcp",
                "-fflags", "nobuffer",
                "-flags", "low_delay",
                "-sync", "audio",
                "-volume", str(self.volume),
                self.rtsp_url,
            ]

            try:
                with open(
                    self.log_path,
                    "a",
                    encoding="utf-8",
                    errors="replace",
                ) as log_file:
                    log_file.write(
                        "\n========== ffplay start "
                        + time.strftime("%Y-%m-%d %H:%M:%S")
                        + " ==========\n"
                    )
                    log_file.flush()

                    self._process = subprocess.Popen(
                        command,
                        stdin=subprocess.DEVNULL,
                        stdout=subprocess.DEVNULL,
                        stderr=log_file,
                        creationflags=self._creation_flags(),
                    )

                    self.status_ready.emit(
                        f"声音播放中，音量 {self.volume}"
                    )

                    while self._running and self._process.poll() is None:
                        time.sleep(0.2)

                    return_code = self._process.poll()

            except Exception as exc:
                self.status_ready.emit(f"ffplay 启动失败：{exc}")
                self._process = None
                return

            self._stop_player()

            if self._running:
                detail = self._tail_log()
                if detail:
                    self.status_ready.emit(
                        f"声音中断({return_code})：{detail}"
                    )
                else:
                    self.status_ready.emit(
                        f"声音中断({return_code})，正在重连"
                    )
                time.sleep(self.reconnect_delay)


class StatePollThread(QThread):
    state_ready = pyqtSignal(object)
    status_ready = pyqtSignal(str)

    def __init__(self, state_url: str, interval: float = 0.5, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.state_url = state_url
        self.interval = max(0.1, float(interval))
        self._running = True

    def stop(self) -> None:
        self._running = False
        self.wait(1500)

    def run(self) -> None:
        last_ok = False
        while self._running:
            try:
                req = urllib.request.Request(self.state_url, headers={"Cache-Control": "no-cache"})
                with urllib.request.urlopen(req, timeout=1.0) as resp:
                    raw = resp.read()
                data = json.loads(raw.decode("utf-8"))
                if isinstance(data, dict):
                    self.state_ready.emit(data)
                    if not last_ok:
                        self.status_ready.emit("比分状态已连接")
                    last_ok = True
            except Exception as exc:
                if last_ok:
                    self.status_ready.emit(f"比分状态断开：{exc}")
                else:
                    self.status_ready.emit(f"等待比分状态…… {exc}")
                last_ok = False
            time.sleep(self.interval)


class ViewerWindow(QMainWindow):
    def __init__(self, args: argparse.Namespace):
        super().__init__()
        self.args = args
        self.font_path = args.font
        self.state: Dict[str, Any] = make_default_state(args.period_minutes, default_roster())
        self.video_thread: Optional[VideoThread] = None
        self.audio_thread: Optional[AudioThread] = None
        self.state_thread: Optional[StatePollThread] = None

        self._build_ui()
        self.start_threads()

    def _build_ui(self) -> None:
        self.setWindowTitle("Basketball Viewer V2.1 - 读取 RK 比分状态")
        self.resize(self.args.window_width, self.args.window_height)
        root = QWidget(self)
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        self.video_label = QLabel("等待视频流……")
        self.video_label.setAlignment(Qt.AlignCenter)
        self.video_label.setMinimumSize(640, 360)
        self.video_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.video_label.setStyleSheet("background:#111; color:#ddd; font-size:22px;")
        layout.addWidget(self.video_label, stretch=1)

        self.status_label = QLabel("状态：初始化")
        self.status_label.setStyleSheet("font-size:13px; padding:3px;")
        layout.addWidget(self.status_label)

        self.audio_status_label = QLabel(
            "声音：已关闭" if self.args.no_audio else "声音：正在初始化"
        )
        self.audio_status_label.setStyleSheet(
            "font-size:13px; padding:3px; color:#005bbb;"
        )
        layout.addWidget(self.audio_status_label)

    def start_threads(self) -> None:
        self.video_thread = VideoThread(self.args.rtsp, self.args.preview_fps, self)
        self.video_thread.frame_ready.connect(self.on_frame_ready)
        self.video_thread.status_ready.connect(self.on_video_status)
        self.video_thread.start()

        if not self.args.no_audio:
            self.audio_thread = AudioThread(
                rtsp_url=self.args.rtsp,
                ffplay_bin=self.args.ffplay_bin,
                ffprobe_bin=self.args.ffprobe_bin,
                volume=self.args.volume,
                log_path=self.args.audio_log,
                reconnect_delay=self.args.audio_reconnect_delay,
                parent=self,
            )
            self.audio_thread.status_ready.connect(
                lambda text: self.audio_status_label.setText(f"声音：{text}")
            )
            self.audio_thread.start()

        self.state_thread = StatePollThread(self.args.state_url, self.args.state_interval, self)
        self.state_thread.state_ready.connect(self.on_state_ready)
        self.state_thread.status_ready.connect(self.on_state_status)
        self.state_thread.start()

    def on_video_status(self, text: str) -> None:
        self.status_label.setText(f"状态：{text}｜比分源：{self.args.state_url}")

    def on_state_status(self, text: str) -> None:
        self.status_label.setText(f"状态：{text}｜视频源：{self.args.rtsp}")

    def on_state_ready(self, state: Dict[str, Any]) -> None:
        self.state = state

    def on_frame_ready(self, frame: np.ndarray) -> None:
        frame = draw_scoreboard(frame, self.state, self.font_path)
        self.show_frame(frame)

    def show_frame(self, frame_bgr: np.ndarray) -> None:
        rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb.shape
        bytes_per_line = ch * w
        qimg = QImage(rgb.data, w, h, bytes_per_line, QImage.Format_RGB888).copy()
        pix = QPixmap.fromImage(qimg)
        pix = pix.scaled(self.video_label.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.video_label.setPixmap(pix)

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.key() == Qt.Key_F11:
            self.showNormal() if self.isFullScreen() else self.showFullScreen()
        elif event.key() == Qt.Key_Escape:
            if self.isFullScreen():
                self.showNormal()
            else:
                self.close()
        else:
            super().keyPressEvent(event)

    def closeEvent(self, event) -> None:  # noqa: N802
        if self.video_thread is not None:
            self.video_thread.stop()
        if self.audio_thread is not None:
            self.audio_thread.stop()
        if self.state_thread is not None:
            self.state_thread.stop()
        event.accept()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="篮球技术台 V2.1 电脑只读观看端")
    parser.add_argument("--rtsp", required=True, help="RK3588 RTSP 拉流地址，例如 rtsp://192.168.1.66:8554/director")
    parser.add_argument("--state-url", required=True, help="RK3588 比分状态地址，例如 http://192.168.1.66:8010/state")
    parser.add_argument("--font", default=None, help="中文字体路径，例如 C:/Windows/Fonts/msyh.ttc")
    parser.add_argument("--period-minutes", type=int, default=10, help="每节默认分钟数，仅在状态未连接时用于占位")
    parser.add_argument("--preview-fps", type=float, default=25.0, help="本地预览帧率")
    parser.add_argument("--state-interval", type=float, default=0.5, help="比分状态刷新间隔，单位秒")
    parser.add_argument(
        "--no-audio",
        action="store_true",
        help="关闭 RTSP 音频播放",
    )
    parser.add_argument(
        "--ffplay-bin",
        default="ffplay",
        help="ffplay.exe 的完整路径或命令名",
    )
    parser.add_argument(
        "--ffprobe-bin",
        default="ffprobe",
        help="ffprobe.exe 的完整路径或命令名",
    )
    parser.add_argument(
        "--volume",
        type=int,
        default=100,
        help="播放音量，范围 0~100",
    )
    parser.add_argument(
        "--audio-reconnect-delay",
        type=float,
        default=1.0,
        help="音频中断后的重连间隔，单位秒",
    )
    parser.add_argument(
        "--audio-log",
        default=os.path.join(CURRENT_DIR, "viewer_audio_ffplay.log"),
        help="ffplay 音频日志文件",
    )
    parser.add_argument("--window-width", type=int, default=1280, help="窗口宽度")
    parser.add_argument("--window-height", type=int, default=720, help="窗口高度")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    app = QApplication(sys.argv)
    window = ViewerWindow(args)
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
