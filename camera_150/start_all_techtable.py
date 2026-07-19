#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
start_all_techtable.py
======================

篮球赛事“检录 -> 导播”一键工作流主程序。

工作流程：
    1. 启动后进入球员选择页面；
    2. 勾选本场需要参赛和检录的球员；
    3. 为名单球员绑定已经训练好的人脸档案；
    4. 在统一 UI 中进行实时人脸识别检录；
    5. 未到场球员可以记录为缺席；
    6. 所有已选球员均为“已检录”或“缺席”后，确认进入导播；
    7. 自动启动 MediaMTX、RKNN 导播推流和技术台；
    8. 本窗口显示 RTSP 导播预览和三个后台进程状态。

运行：
    cd /home/elf/work/camera_150
    python3 start_all_techtable.py

说明：
    - 脚本会优先自动切换到 ./face_env/bin/python，避免修改原导播环境。
    - 导播、技术台仍使用系统 python3，不使用 face_env。
    - 检录与导播都使用 /dev/video41，因此进入导播前会先停止检录线程并释放摄像头。
    - 后台进程 PID 保存到 runtime/techtable_processes.json，供 stop_all_techtable.py 使用。
"""

from __future__ import annotations

import csv
import importlib.util
import json
import os
import shutil
import signal
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple


# ---------------------------------------------------------------------------
# 一、路径与 Python 环境
# ---------------------------------------------------------------------------

PROJECT_DIR = Path(__file__).resolve().parent
FACE_ENV_PYTHON = PROJECT_DIR / "face_env" / "bin" / "python"


def reexec_in_face_environment() -> None:
    """
    检录需要 opencv-contrib-python 中的 cv2.face。

    原有导播环境不应被卸载或重装，因此启动脚本优先在 face_env 中运行。
    使用 os.execve 替换当前进程，不会多留一个父进程。
    """
    if os.environ.get("CAMERA150_FACE_ENV_ACTIVE") == "1":
        return

    if not FACE_ENV_PYTHON.is_file():
        return

    # 比较当前 Python 是否已经在 face_env 里运行。
    # 注意：绝对不能 .resolve()，因为 face_env/bin/python 是到系统 python
    # 的软链接，resolve 后会变成同一个文件，导致永远无法切换环境。
    try:
        already_in_venv = Path(sys.executable) == FACE_ENV_PYTHON
    except Exception:
        already_in_venv = False

    if already_in_venv:
        return

    env = os.environ.copy()
    env["CAMERA150_FACE_ENV_ACTIVE"] = "1"
    # 保存用户原本执行 start_all_techtable.py 时使用的 Python。
    # 进入 face_env 后，导播与技术台仍使用这个解释器。
    env["CAMERA150_SYSTEM_PYTHON"] = sys.executable
    os.execve(
        str(FACE_ENV_PYTHON),
        [str(FACE_ENV_PYTHON), str(Path(__file__).resolve()), *sys.argv[1:]],
        env,
    )


reexec_in_face_environment()

# ---------------------------------------------------------------------------
# Qt / OpenCV GUI 插件隔离
# ---------------------------------------------------------------------------
#
# 本程序的窗口由 PyQt5 创建，不使用 cv2.imshow()。
#
# 非 headless 的 opencv-python / opencv-contrib-python wheel 会携带一套 Qt
# 插件，并可能在 import cv2 时把 QT_QPA_PLATFORM_PLUGIN_PATH 改成：
#
#     .../site-packages/cv2/qt/plugins
#
# 这套插件与 RK3588 Ubuntu 系统安装的 PyQt5/Qt5 可能不兼容，从而出现：
#
#     Could not load the Qt platform plugin "xcb"
#
# 因此采取两层保护：
#   1. face_env 推荐安装 opencv-contrib-python-headless；
#   2. import cv2 之后再次强制恢复系统 Qt 插件路径。
#
os.environ.setdefault("DISPLAY", ":0")
os.environ.setdefault("OPENCV_OPENCL_RUNTIME", "disabled")

SYSTEM_QT_PLUGIN_DIR = "/usr/lib/aarch64-linux-gnu/qt5/plugins"
SYSTEM_QT_PLATFORM_DIR = f"{SYSTEM_QT_PLUGIN_DIR}/platforms"

# 在导入 cv2 前先设置一次。
os.environ["QT_QPA_PLATFORM"] = "xcb"
os.environ["QT_QPA_PLATFORM_PLUGIN_PATH"] = SYSTEM_QT_PLATFORM_DIR
os.environ["QT_PLUGIN_PATH"] = SYSTEM_QT_PLUGIN_DIR

import cv2
import numpy as np

# 关键：GUI 版 OpenCV 可能在 import cv2 时覆盖上面的环境变量，
# 所以必须在导入 PyQt5 之前再恢复一次。
os.environ["QT_QPA_PLATFORM"] = "xcb"
os.environ["QT_QPA_PLATFORM_PLUGIN_PATH"] = SYSTEM_QT_PLATFORM_DIR
os.environ["QT_PLUGIN_PATH"] = SYSTEM_QT_PLUGIN_DIR

from PyQt5.QtCore import QCoreApplication, Qt, QThread, QTimer, pyqtSignal
from PyQt5.QtGui import QImage, QPixmap
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QComboBox,
    QDoubleSpinBox,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

try:
    cv2.ocl.setUseOpenCL(False)
except Exception:
    pass


ROSTER_PATH = PROJECT_DIR / "techtable_v2" / "sample_roster.json"
GAME_STATE_PATH = PROJECT_DIR / "techtable_v2" / "game_state.json"
FACE_WORK_DIR = PROJECT_DIR / "face_checkin"
FACE_LABELS_PATH = FACE_WORK_DIR / "trainer" / "labels.json"
FACE_MAPPING_PATH = FACE_WORK_DIR / "roster_face_mapping.json"
CALIB_FILE = PROJECT_DIR / "camera_usb3_calib.npz"
RUNTIME_DIR = PROJECT_DIR / "runtime"
LOG_DIR = RUNTIME_DIR / "logs"
PID_FILE = RUNTIME_DIR / "techtable_processes.json"
LAUNCHER_PID_FILE = RUNTIME_DIR / "start_all_techtable.pid"

# 当前场次的临时检录数据标记。
# stop_all_techtable.py 根据它删除本场“已检录”数据，但不会删除人脸样本和模型。
ACTIVE_CHECKIN_FILE = RUNTIME_DIR / "active_checkin_session.json"

# 启动时 ffprobe 验证 RTSP 音视频轨道后保存的结果。
RTSP_PROBE_FILE = RUNTIME_DIR / "rtsp_probe.json"

STREAM_DIR = Path.home() / "stream_server"

STATUS_UNSELECTED = "未选择"
STATUS_PENDING = "待检录"
STATUS_CHECKED = "已检录"
STATUS_ABSENT = "缺席"
STATUS_NO_FACE = "无人脸档案"


# ---------------------------------------------------------------------------
# 二、基础文件工具
# ---------------------------------------------------------------------------


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def atomic_write_json(path: Path, payload: Any) -> None:
    ensure_dir(path.parent)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    with temp_path.open("w", encoding="utf-8") as file:
        json.dump(payload, file, ensure_ascii=False, indent=2)
        file.flush()
        os.fsync(file.fileno())
    os.replace(temp_path, path)


def read_json(path: Path, default: Any) -> Any:
    try:
        with path.open("r", encoding="utf-8") as file:
            return json.load(file)
    except Exception:
        return default


def player_key(team: str, number: str, name: str) -> str:
    return f"{team}|{number}|{name}"


def team_text(team: str) -> str:
    return "主队" if team == "home" else "客队"


def find_system_python() -> str:
    """
    face_env 只负责检录 UI；原项目进程仍使用用户原先的系统 Python。

    reexec_in_face_environment() 会在切换前把原解释器写入
    CAMERA150_SYSTEM_PYTHON，优先使用该值，避免误用 face_env。
    """
    original = os.environ.get("CAMERA150_SYSTEM_PYTHON", "").strip()
    if original and Path(original).is_file():
        try:
            if Path(original).resolve() != Path(sys.executable).resolve():
                return original
        except Exception:
            return original

    candidate = shutil.which("python3")
    if candidate:
        try:
            if Path(candidate).resolve() != Path(sys.executable).resolve():
                return candidate
        except Exception:
            return candidate

    for path in ("/usr/bin/python3", "/usr/local/bin/python3"):
        if Path(path).is_file():
            return path

    return "python3"


SYSTEM_PYTHON = find_system_python()


# ---------------------------------------------------------------------------
# 三、动态加载人脸识别脚本
# ---------------------------------------------------------------------------

_FACE_HELPER = None


def load_face_helper():
    """
    优先加载稳定采集版本；若不存在，则兼容原始 face_checkin_lbph.py。

    主 UI 复用其中已经验证过的：
        - 摄像头最新帧线程；
        - 单目去畸变；
        - Haar 人脸检测；
        - LBPH 模型加载；
        - 人脸归一化。
    """
    global _FACE_HELPER
    if _FACE_HELPER is not None:
        return _FACE_HELPER

    candidates = [
        PROJECT_DIR / "face_checkin_lbph_stable.py",
        PROJECT_DIR / "face_checkin_lbph.py",
    ]

    helper_path = next((path for path in candidates if path.is_file()), None)
    if helper_path is None:
        raise RuntimeError(
            "找不到人脸识别脚本。请将 face_checkin_lbph_stable.py "
            "放到工程根目录。"
        )

    spec = importlib.util.spec_from_file_location("camera150_face_helper", helper_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"无法加载人脸识别脚本: {helper_path}")

    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    _FACE_HELPER = module
    return module


# ---------------------------------------------------------------------------
# 四、名单与人脸档案
# ---------------------------------------------------------------------------


def load_roster_rows() -> Tuple[List[Dict[str, Any]], Dict[str, str]]:
    roster = read_json(ROSTER_PATH, {})
    team_names = {
        "home": str(roster.get("home_name", "主队")),
        "away": str(roster.get("away_name", "客队")),
    }

    rows: List[Dict[str, Any]] = []
    players = roster.get("players", {})

    for team in ("home", "away"):
        for player in players.get(team, []) or []:
            number = str(player.get("number", "")).strip()
            name = str(player.get("name", "")).strip()
            rows.append(
                {
                    "key": player_key(team, number, name),
                    "team": team,
                    "team_name": team_names[team],
                    "number": number,
                    "name": name,
                    "explicit_face_id": str(
                        player.get("person_id", player.get("face_id", ""))
                    ).strip(),
                    "face_id": "",
                    "selected": False,
                    "status": STATUS_UNSELECTED,
                    "confidence": None,
                    "checkin_time": "",
                }
            )

    return rows, team_names


def load_face_identities() -> List[Dict[str, str]]:
    payload = read_json(FACE_LABELS_PATH, {})
    identities: List[Dict[str, str]] = []

    for label_text, info in (payload.get("labels", {}) or {}).items():
        identities.append(
            {
                "model_label": str(label_text),
                "person_id": str(info.get("person_id", "")).strip(),
                "name": str(info.get("name", "")).strip(),
                "folder": str(info.get("folder", "")).strip(),
            }
        )

    identities.sort(key=lambda item: (item["person_id"], item["name"]))
    return identities


def auto_match_face_id(
    row: Dict[str, Any],
    identities: List[Dict[str, str]],
    saved_mapping: Dict[str, str],
) -> str:
    """按“已保存映射 -> 显式 ID -> 球衣号 -> 唯一姓名”自动匹配。"""
    saved = str(saved_mapping.get(row["key"], "")).strip()
    valid_ids = {item["person_id"] for item in identities}
    if saved in valid_ids:
        return saved

    explicit = str(row.get("explicit_face_id", "")).strip()
    if explicit in valid_ids:
        return explicit

    number = str(row.get("number", "")).strip()
    if number in valid_ids:
        return number

    name = str(row.get("name", "")).strip()
    matched = [item["person_id"] for item in identities if item["name"] == name]
    if len(matched) == 1:
        return matched[0]

    return ""


# ---------------------------------------------------------------------------
# 五、人脸识别检录线程
# ---------------------------------------------------------------------------


class FaceCheckinThread(QThread):
    frame_ready = pyqtSignal(object)
    status_ready = pyqtSignal(str)
    candidate_ready = pyqtSignal(str, str, float, int)
    checkin_confirmed = pyqtSignal(str, str, float)
    error_ready = pyqtSignal(str)

    def __init__(
        self,
        selected_face_ids: Set[str],
        completed_face_ids: Set[str],
        threshold: float,
        stable_hits: int,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.selected_face_ids = set(selected_face_ids)
        self.completed_face_ids = set(completed_face_ids)
        self.threshold = float(threshold)
        self.stable_hits = max(1, int(stable_hits))
        self._running = True
        self._paused = False
        self._lock = threading.Lock()

    def stop(self) -> None:
        self._running = False
        self.wait(3000)

    def set_paused(self, paused: bool) -> None:
        self._paused = bool(paused)

    def mark_completed(self, face_id: str) -> None:
        with self._lock:
            self.completed_face_ids.add(face_id)

    def run(self) -> None:
        camera = None
        try:
            helper = load_face_helper()
            detector = helper.load_face_detector(None)
            calibration = helper.load_camera_calibration(str(CALIB_FILE))
            recognizer, people, face_size = helper.load_trained_model(str(FACE_WORK_DIR))

            camera = helper.LatestFrameCamera(
                "/dev/video41",
                1920,
                1080,
                30,
            ).start()

            if not camera.wait_first_frame(5.0):
                raise RuntimeError("等待 /dev/video41 第一帧超时。")

            last_frame_index = -1
            current_face_id: Optional[str] = None
            hit_count = 0
            last_emit_face_id: Optional[str] = None

            self.status_ready.emit("摄像头已连接，请让待检录球员正对摄像头")

            while self._running:
                if self._paused:
                    time.sleep(0.05)
                    continue

                frame_index, frame, _ = camera.get_latest()
                if frame is None or frame_index == last_frame_index:
                    time.sleep(0.002)
                    continue
                last_frame_index = frame_index

                frame = helper.apply_undistort(frame, calibration)
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                gray_detection = cv2.equalizeHist(gray)
                faces = helper.detect_faces(detector, gray_detection, 120)

                best: Optional[Tuple[str, str, float]] = None

                for x, y, width, height in faces:
                    roi = gray[y : y + height, x : x + width]
                    if roi.size == 0:
                        continue

                    normalized = helper.normalize_face(roi, face_size)
                    model_label, confidence = recognizer.predict(normalized)
                    confidence = float(confidence)
                    person = people.get(int(model_label))

                    known = person is not None and confidence <= self.threshold
                    if known:
                        face_id = str(person.person_id)
                        name = str(person.name)
                        text = f"ID:{face_id} {confidence:.1f}"
                        if best is None or confidence < best[2]:
                            best = (face_id, name, confidence)
                        box_color = (255, 255, 255)
                    else:
                        text = "UNKNOWN"
                        box_color = (128, 128, 128)

                    cv2.rectangle(
                        frame,
                        (x, y),
                        (x + width, y + height),
                        box_color,
                        2,
                    )
                    text_y = y - 10 if y > 30 else y + 25
                    cv2.putText(
                        frame,
                        text,
                        (x, text_y),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.65,
                        (255, 255, 255),
                        2,
                        cv2.LINE_AA,
                    )

                if best is None:
                    current_face_id = None
                    hit_count = 0
                    last_emit_face_id = None
                    self.candidate_ready.emit("", "未识别", 0.0, 0)
                else:
                    face_id, name, confidence = best

                    if face_id == current_face_id:
                        hit_count += 1
                    else:
                        current_face_id = face_id
                        hit_count = 1
                        last_emit_face_id = None

                    self.candidate_ready.emit(face_id, name, confidence, hit_count)

                    with self._lock:
                        completed = face_id in self.completed_face_ids

                    if face_id not in self.selected_face_ids:
                        self.status_ready.emit(f"识别到未勾选人员：{face_id} {name}")
                    elif completed:
                        self.status_ready.emit(f"{face_id} {name} 已完成检录或已记录缺席")
                    elif hit_count >= self.stable_hits and last_emit_face_id != face_id:
                        last_emit_face_id = face_id
                        self.checkin_confirmed.emit(face_id, name, confidence)

                cv2.putText(
                    frame,
                    f"Selected: {len(self.selected_face_ids)}  Faces: {len(faces)}",
                    (24, 38),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.75,
                    (255, 255, 255),
                    2,
                    cv2.LINE_AA,
                )
                self.frame_ready.emit(frame)

        except Exception as exc:
            self.error_ready.emit(str(exc))
        finally:
            if camera is not None:
                try:
                    camera.stop()
                except Exception:
                    pass


# ---------------------------------------------------------------------------
# 六、RTSP 导播预览线程
# ---------------------------------------------------------------------------


class DirectorPreviewThread(QThread):
    frame_ready = pyqtSignal(object)
    status_ready = pyqtSignal(str)

    def __init__(self, rtsp_url: str, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.rtsp_url = rtsp_url
        self._running = True

    def stop(self) -> None:
        self._running = False
        self.wait(2000)

    def run(self) -> None:
        while self._running:
            cap = cv2.VideoCapture(self.rtsp_url)
            try:
                cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            except Exception:
                pass

            if not cap.isOpened():
                self.status_ready.emit("等待 RTSP 导播流……")
                cap.release()
                time.sleep(1.0)
                continue

            self.status_ready.emit("RTSP 导播流已连接")
            last_emit = 0.0
            while self._running:
                ok, frame = cap.read()
                if not ok or frame is None:
                    self.status_ready.emit("RTSP 中断，正在重连……")
                    break

                # 限制预览帧率 ~15fps，避免信号洪水导致 UI 卡死
                now = time.time()
                if now - last_emit >= 0.066:
                    last_emit = now
                    self.frame_ready.emit(frame)

            cap.release()
            time.sleep(0.5)


# ---------------------------------------------------------------------------
# 七、后台进程管理
# ---------------------------------------------------------------------------


class StartupThread(QThread):
    """在后台线程中启动导播进程，避免 time.sleep 阻塞 UI。"""

    finished = pyqtSignal()
    error = pyqtSignal(str)

    def __init__(self, process_manager: ProcessManager, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.process_manager = process_manager

    def run(self) -> None:
        try:
            self.process_manager.start_all()
            self.finished.emit()
        except Exception as exc:
            self.error.emit(str(exc))


class ProcessManager:
    """直接启动后台进程并记录 PID，不再依赖多个终端窗口。"""

    START_ORDER = ["mediamtx", "director", "techtable"]
    STOP_ORDER = ["techtable", "director", "mediamtx"]

    def __init__(self) -> None:
        ensure_dir(RUNTIME_DIR)
        ensure_dir(LOG_DIR)
        self.processes: Dict[str, subprocess.Popen] = {}
        self.records: Dict[str, Dict[str, Any]] = {}

    @staticmethod
    def is_pid_alive(pid: int) -> bool:
        try:
            os.kill(pid, 0)
            return True
        except ProcessLookupError:
            return False
        except PermissionError:
            return True

    def existing_alive_records(self) -> Dict[str, Dict[str, Any]]:
        payload = read_json(PID_FILE, {})
        alive: Dict[str, Dict[str, Any]] = {}
        for name, record in (payload.get("processes", {}) or {}).items():
            try:
                pid = int(record.get("pid", -1))
            except Exception:
                continue
            if pid > 0 and self.is_pid_alive(pid):
                alive[name] = record
        return alive

    def _write_pid_file(self) -> None:
        atomic_write_json(
            PID_FILE,
            {
                "project_dir": str(PROJECT_DIR),
                "updated_at": datetime.now().isoformat(timespec="seconds"),
                "processes": self.records,
            },
        )

    def _start_one(
        self,
        name: str,
        command: List[str],
        cwd: Path,
        env: Dict[str, str],
    ) -> subprocess.Popen:
        log_path = LOG_DIR / f"{name}.log"
        log_file = log_path.open("ab", buffering=0)

        try:
            process = subprocess.Popen(
                command,
                cwd=str(cwd),
                env=env,
                stdout=log_file,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
        finally:
            # 子进程已继承文件描述符，父进程可以关闭自己的句柄。
            log_file.close()

        time.sleep(0.35)
        return_code = process.poll()
        if return_code is not None:
            raise RuntimeError(
                f"{name} 启动后立即退出，returncode={return_code}。\n"
                f"请查看日志：{log_path}"
            )

        self.processes[name] = process
        self.records[name] = {
            "pid": process.pid,
            "pgid": process.pid,
            "command": command,
            "cwd": str(cwd),
            "log": str(log_path),
            "started_at": datetime.now().isoformat(timespec="seconds"),
        }
        self._write_pid_file()
        return process

    def wait_for_rtsp_audio(
        self,
        url: str,
        timeout: float = 18.0,
    ) -> Dict[str, Any]:
        """
        使用 ffprobe 验证 RTSP 真正包含视频轨和音频轨。

        OpenCV VideoCapture 只会读取视频，因此“预览连接成功”不能证明音频存在。
        这里要求：
            - 至少一条 video stream；
            - 至少一条 AAC audio stream；
            - 音频采样率为 48000 Hz；
            - 音频通道数为 2。

        验证结果写入 runtime/rtsp_probe.json，便于排查。
        """
        ffprobe = shutil.which("ffprobe")
        if not ffprobe:
            raise RuntimeError(
                "找不到 ffprobe，无法确认 RTSP 音频是否存在。"
                "请确认 ffmpeg/ffprobe 已正确安装。"
            )

        command = [
            ffprobe,
            "-v", "error",
            "-rtsp_transport", "tcp",
            "-show_entries",
            "stream=index,codec_type,codec_name,sample_rate,channels",
            "-of", "json",
            url,
        ]

        deadline = time.monotonic() + max(1.0, float(timeout))
        last_detail = "RTSP 尚未就绪"

        while time.monotonic() < deadline:
            try:
                result = subprocess.run(
                    command,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    check=False,
                    timeout=4.0,
                )
            except subprocess.TimeoutExpired:
                last_detail = "ffprobe 单次检测超时"
                time.sleep(0.5)
                continue
            except Exception as exc:
                last_detail = f"ffprobe 执行失败：{exc}"
                time.sleep(0.5)
                continue

            if result.returncode != 0:
                last_detail = result.stderr.strip() or f"ffprobe returncode={result.returncode}"
                time.sleep(0.5)
                continue

            try:
                payload = json.loads(result.stdout or "{}")
            except Exception as exc:
                last_detail = f"ffprobe JSON 解析失败：{exc}"
                time.sleep(0.5)
                continue

            streams = payload.get("streams", []) or []
            video_streams = [
                stream for stream in streams
                if str(stream.get("codec_type", "")).lower() == "video"
            ]
            audio_streams = [
                stream for stream in streams
                if str(stream.get("codec_type", "")).lower() == "audio"
            ]

            if not video_streams:
                last_detail = f"RTSP 中没有视频轨：{streams}"
                time.sleep(0.5)
                continue

            if not audio_streams:
                last_detail = f"RTSP 中没有音频轨：{streams}"
                time.sleep(0.5)
                continue

            audio = audio_streams[0]
            codec = str(audio.get("codec_name", "")).lower()
            sample_rate_text = str(audio.get("sample_rate", "")).strip()
            channels_text = str(audio.get("channels", "")).strip()

            if codec != "aac":
                raise RuntimeError(
                    f"RTSP 已发现音频轨，但编码不是 AAC：{audio}"
                )

            if sample_rate_text and int(sample_rate_text) != 48000:
                raise RuntimeError(
                    f"RTSP 音频采样率不是 48000 Hz：{audio}"
                )

            if channels_text and int(channels_text) != 2:
                raise RuntimeError(
                    f"RTSP 音频不是双声道：{audio}"
                )

            verified = {
                "verified_at": datetime.now().isoformat(timespec="seconds"),
                "url": url,
                "video": video_streams[0],
                "audio": audio,
                "all_streams": streams,
            }
            atomic_write_json(RTSP_PROBE_FILE, verified)
            print(
                "[RTSP 验证] 正常："
                f"video={video_streams[0].get('codec_name')}，"
                f"audio={codec}/{sample_rate_text or '?'}Hz/"
                f"{channels_text or '?'}ch"
            )
            return verified

        raise RuntimeError(
            "RTSP 音视频验收失败。\n"
            "要求：H.264 视频 + AAC 48000 Hz 双声道。\n"
            f"最后一次检测结果：{last_detail}\n"
            f"请查看：{LOG_DIR / 'director.log'} 和 "
            "camera_movement_modified/stream_logs/*.ffmpeg.log"
        )

    def start_all(self) -> None:
        mediamtx_binary = STREAM_DIR / "mediamtx"
        mediamtx_config = STREAM_DIR / "mediamtx_rk3588.yml"
        if not mediamtx_config.is_file():
            mediamtx_config = PROJECT_DIR / "mediamtx_rk3588.yml"

        director_script = (
            PROJECT_DIR
            / "camera_movement_modified"
            / "single_rknn_director_view720_network_stream.py"
        )
        panel_script = PROJECT_DIR / "techtable_v2" / "rk_techtable_panel.py"

        required = [
            mediamtx_binary,
            mediamtx_config,
            director_script,
            panel_script,
            PROJECT_DIR / "model" / "basketball_player_fp_2.1.0.rknn",
            PROJECT_DIR / "model" / "labels.txt",
            CALIB_FILE,
            ROSTER_PATH,
        ]
        missing = [str(path) for path in required if not path.is_file()]
        if missing:
            raise RuntimeError("以下启动文件不存在：\n" + "\n".join(missing))

        env = os.environ.copy()
        env["DISPLAY"] = env.get("DISPLAY", ":0")
        env["QT_QPA_PLATFORM_PLUGIN_PATH"] = "/usr/lib/aarch64-linux-gnu/qt5/plugins/platforms"
        env.pop("QT_PLUGIN_PATH", None)

        commands = {
            "mediamtx": (
                [str(mediamtx_binary), str(mediamtx_config)],
                STREAM_DIR,
            ),
            "director": (
                [
                    SYSTEM_PYTHON,
                    str(director_script),
                    "--device",
                    "/dev/video41",
                    "--calib-file",
                    str(CALIB_FILE),
                    "--model",
                    str(PROJECT_DIR / "model" / "basketball_player_fp_2.1.0.rknn"),
                    "--labels",
                    str(PROJECT_DIR / "model" / "labels.txt"),
                    "--render-mode",
                    "sample",
                    # 板载 LCD 本地 OpenCV 预览缩放比例。
                    # 仅影响本地窗口，不改变 RTSP 的 1280x720 输出。
                    "--display-scale",
                    "0.35",
                    "--stream-mode",
                    "rtsp",
                    "--stream-url",
                    "rtsp://127.0.0.1:8554/director",
                    "--stream-fps",
                    "25",
                    "--stream-bitrate",
                    "4M",
                    "--stream-encoder",
                    "h264_rkmpp",
                    "--stream-audio",
                    "--stream-audio-device", "hw:1,0",
                    "--stream-audio-rate", "48000",
                    "--stream-audio-channels", "2",
                    "--stream-audio-codec", "aac",
                    "--stream-audio-bitrate", "128k",
                ],
                director_script.parent,
            ),
            "techtable": (
                [
                    SYSTEM_PYTHON,
                    str(panel_script),
                    "--rtsp",
                    "rtsp://127.0.0.1:8554/director",
                    "--state",
                    str(GAME_STATE_PATH),
                    "--roster",
                    str(ROSTER_PATH),
                    "--state-host",
                    "0.0.0.0",
                    "--state-port",
                    "8010",
                ],
                PROJECT_DIR,
            ),
        }

        try:
            self._start_one("mediamtx", *commands["mediamtx"], env)
            time.sleep(1.2)
            self._start_one("director", *commands["director"], env)

            # 必须先确认 RTSP 中既有视频也有 AAC 音频，才能进入正式技术台。
            self.wait_for_rtsp_audio(
                "rtsp://127.0.0.1:8554/director",
                timeout=18.0,
            )

            self._start_one("techtable", *commands["techtable"], env)
        except Exception:
            self.stop_all()
            raise

    def status(self, name: str) -> str:
        process = self.processes.get(name)
        if process is not None:
            return "运行中" if process.poll() is None else f"已退出({process.returncode})"

        record = self.existing_alive_records().get(name)
        return "运行中" if record else "未运行"

    def stop_all(self) -> None:
        payload = read_json(PID_FILE, {})
        records = dict(payload.get("processes", {}) or {})

        # 当前启动实例中的记录优先覆盖文件记录。
        records.update(self.records)

        for name in self.STOP_ORDER:
            record = records.get(name)
            if not record:
                continue

            try:
                pid = int(record.get("pid", -1))
            except Exception:
                continue
            if pid <= 0 or not self.is_pid_alive(pid):
                continue

            try:
                pgid = os.getpgid(pid)
                os.killpg(pgid, signal.SIGTERM)
            except ProcessLookupError:
                continue
            except Exception:
                try:
                    os.kill(pid, signal.SIGTERM)
                except Exception:
                    pass

        # 导播进程收到 SIGTERM 后需要停止 FFmpeg、释放摄像头和 NAU8822。
        # 3 秒可能导致过早 SIGKILL，因此延长到 8 秒。
        deadline = time.time() + 8.0
        while time.time() < deadline:
            remaining = []
            for record in records.values():
                try:
                    pid = int(record.get("pid", -1))
                except Exception:
                    continue
                if pid > 0 and self.is_pid_alive(pid):
                    remaining.append(pid)
            if not remaining:
                break
            time.sleep(0.1)

        for record in records.values():
            try:
                pid = int(record.get("pid", -1))
            except Exception:
                continue
            if pid <= 0 or not self.is_pid_alive(pid):
                continue
            try:
                os.killpg(os.getpgid(pid), signal.SIGKILL)
            except Exception:
                try:
                    os.kill(pid, signal.SIGKILL)
                except Exception:
                    pass

        self.processes.clear()
        self.records.clear()
        try:
            PID_FILE.unlink()
        except FileNotFoundError:
            pass


# ---------------------------------------------------------------------------
# 八、主窗口
# ---------------------------------------------------------------------------


class WorkflowWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("RK3588 篮球赛事：检录与自动导播")
        # 板载 LCD 使用紧凑窗口，避免选择页面横向内容超出屏幕。
        self.resize(960, 600)
        self.setMinimumSize(820, 520)

        ensure_dir(RUNTIME_DIR)
        atomic_write_json(LAUNCHER_PID_FILE, {"pid": os.getpid(), "started_at": datetime.now().isoformat(timespec="seconds")})

        self.roster_rows, self.team_names = load_roster_rows()
        self.identities = load_face_identities()
        self.saved_mapping: Dict[str, str] = read_json(FACE_MAPPING_PATH, {})

        for row in self.roster_rows:
            row["face_id"] = auto_match_face_id(row, self.identities, self.saved_mapping)

        self.face_thread: Optional[FaceCheckinThread] = None
        self.preview_thread: Optional[DirectorPreviewThread] = None
        self.process_manager = ProcessManager()
        self.match_id: Optional[str] = None
        self.session_path: Optional[Path] = None
        self.director_started = False

        self.stack = QStackedWidget()
        self.setCentralWidget(self.stack)

        # 启动器只显示“人员选择”和“人脸检录”两页。
        # 检录完成后直接启动原技术台窗口，不再显示启动器自己的进程管理页。
        self.selection_page = self._build_selection_page()
        self.checkin_page = self._build_checkin_page()

        self.stack.addWidget(self.selection_page)
        self.stack.addWidget(self.checkin_page)
        self.stack.setCurrentWidget(self.selection_page)

        self.refresh_selection_table()
        self.refresh_environment_hint()

    # ------------------------- UI 创建 -------------------------

    def _title_label(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setAlignment(Qt.AlignCenter)
        label.setStyleSheet("font-size:22px; font-weight:bold; padding:6px;")
        return label

    def _primary_button(self, text: str) -> QPushButton:
        button = QPushButton(text)
        button.setMinimumHeight(36)
        button.setStyleSheet(
            "QPushButton {font-size:14px; font-weight:bold; color:white; "
            "background:#1e5aa8; border-radius:6px; padding:5px 10px;}"
            "QPushButton:disabled {background:#777;}"
            "QPushButton:pressed {background:#123b70;}"
        )
        return button

    def _normal_button(self, text: str) -> QPushButton:
        button = QPushButton(text)
        button.setMinimumHeight(32)
        button.setStyleSheet(
            "QPushButton {font-size:13px; font-weight:bold; "
            "background:#e8edf3; border-radius:5px; padding:4px 8px;}"
            "QPushButton:pressed {background:#cdd7e2;}"
        )
        return button

    def _danger_button(self, text: str) -> QPushButton:
        button = QPushButton(text)
        button.setMinimumHeight(32)
        button.setStyleSheet(
            "QPushButton {font-size:13px; font-weight:bold; color:white; "
            "background:#9b2c2c; border-radius:5px; padding:4px 8px;}"
            "QPushButton:pressed {background:#6f1d1d;}"
        )
        return button

    def _build_selection_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(self._title_label("第一步：选择本场球员并绑定人脸档案"))

        self.environment_hint = QLabel()
        self.environment_hint.setWordWrap(True)
        self.environment_hint.setStyleSheet(
            "font-size:12px; padding:5px; background:#f4f6f8; border-radius:5px;"
        )
        layout.addWidget(self.environment_hint)

        self.selection_table = QTableWidget()
        self.selection_table.setColumnCount(7)
        self.selection_table.setHorizontalHeaderLabels(
            ["选", "队伍", "号码", "姓名", "人脸档案", "状态", "说明"]
        )
        self.selection_table.setStyleSheet("font-size:12px;")
        self.selection_table.verticalHeader().setVisible(False)
        self.selection_table.setAlternatingRowColors(True)
        self.selection_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        header = self.selection_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.Stretch)
        header.setSectionResizeMode(5, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(6, QHeaderView.ResizeToContents)
        layout.addWidget(self.selection_table, stretch=1)

        controls = QHBoxLayout()
        select_all = self._normal_button("全选")
        select_none = self._normal_button("全部取消")
        select_home = self._normal_button("只选主队")
        select_away = self._normal_button("只选客队")
        select_all.clicked.connect(lambda: self.set_selection_mode("all"))
        select_none.clicked.connect(lambda: self.set_selection_mode("none"))
        select_home.clicked.connect(lambda: self.set_selection_mode("home"))
        select_away.clicked.connect(lambda: self.set_selection_mode("away"))
        controls.addWidget(select_all)
        controls.addWidget(select_none)
        controls.addWidget(select_home)
        controls.addWidget(select_away)
        controls.addStretch(1)

        threshold_label = QLabel("识别阈值")
        self.threshold_spin = QDoubleSpinBox()
        self.threshold_spin.setRange(30.0, 120.0)
        self.threshold_spin.setValue(68.0)
        self.threshold_spin.setDecimals(1)
        self.threshold_spin.setSingleStep(1.0)

        stable_label = QLabel("连续确认帧")
        self.stable_spin = QSpinBox()
        self.stable_spin.setRange(1, 30)
        self.stable_spin.setValue(5)

        controls.addWidget(threshold_label)
        controls.addWidget(self.threshold_spin)
        controls.addWidget(stable_label)
        controls.addWidget(self.stable_spin)
        layout.addLayout(controls)

        self.start_checkin_button = self._primary_button("开始检录")
        self.start_checkin_button.clicked.connect(self.start_checkin)
        layout.addWidget(self.start_checkin_button)
        return page

    def _build_checkin_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(self._title_label("第二步：人脸识别检录"))

        body = QHBoxLayout()

        left = QVBoxLayout()
        self.checkin_video = QLabel("等待启动摄像头……")
        self.checkin_video.setAlignment(Qt.AlignCenter)
        self.checkin_video.setMinimumSize(480, 270)
        self.checkin_video.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.checkin_video.setStyleSheet("background:#111; color:white; font-size:20px;")
        left.addWidget(self.checkin_video, stretch=1)

        self.candidate_label = QLabel("当前识别：无")
        self.candidate_label.setStyleSheet(
            "font-size:16px; font-weight:bold; padding:6px; background:#eef4ff;"
        )
        left.addWidget(self.candidate_label)

        self.checkin_status_label = QLabel("状态：等待检录")
        self.checkin_status_label.setWordWrap(True)
        self.checkin_status_label.setStyleSheet("font-size:12px; padding:4px;")
        left.addWidget(self.checkin_status_label)
        body.addLayout(left, stretch=3)

        right = QVBoxLayout()
        self.checkin_table = QTableWidget()
        self.checkin_table.setColumnCount(6)
        self.checkin_table.setHorizontalHeaderLabels(
            ["队伍", "号码", "姓名", "人脸ID", "状态", "时间/距离"]
        )
        self.checkin_table.verticalHeader().setVisible(False)
        self.checkin_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.checkin_table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        check_header = self.checkin_table.horizontalHeader()
        check_header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        check_header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        check_header.setSectionResizeMode(2, QHeaderView.Stretch)
        check_header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        check_header.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        check_header.setSectionResizeMode(5, QHeaderView.Stretch)
        right.addWidget(self.checkin_table, stretch=1)

        self.progress_label = QLabel("已检录 0 / 缺席 0 / 待检录 0")
        self.progress_label.setStyleSheet("font-size:17px; font-weight:bold; padding:8px;")
        right.addWidget(self.progress_label)
        body.addLayout(right, stretch=2)
        layout.addLayout(body, stretch=1)

        buttons = QGridLayout()
        self.pause_button = self._normal_button("暂停识别")
        self.pause_button.clicked.connect(self.toggle_face_pause)
        continue_button = self._normal_button("继续选择检录成员")
        continue_button.clicked.connect(self.return_to_selection)
        absent_button = self._danger_button("将表格选中成员标记为缺席")
        absent_button.clicked.connect(self.mark_selected_absent)
        restore_button = self._normal_button("恢复选中成员为待检录")
        restore_button.clicked.connect(self.restore_selected_pending)
        self.enter_director_button = self._primary_button("确认检录结果并进入导播")
        self.enter_director_button.clicked.connect(self.enter_director)

        buttons.addWidget(self.pause_button, 0, 0)
        buttons.addWidget(continue_button, 0, 1)
        buttons.addWidget(absent_button, 0, 2)
        buttons.addWidget(restore_button, 0, 3)
        buttons.addWidget(self.enter_director_button, 1, 0, 1, 4)
        layout.addLayout(buttons)
        return page

    def _build_director_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(self._title_label("第三步：自动导播与推流"))

        self.director_video = QLabel("正在启动导播流……")
        self.director_video.setAlignment(Qt.AlignCenter)
        self.director_video.setMinimumSize(560, 315)
        self.director_video.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.director_video.setStyleSheet("background:#111; color:white; font-size:20px;")
        layout.addWidget(self.director_video, stretch=1)

        status_box = QGroupBox("后台服务状态")
        status_layout = QGridLayout(status_box)
        self.mediamtx_status = QLabel("未运行")
        self.director_status = QLabel("未运行")
        self.techtable_status = QLabel("未运行")
        self.rtsp_status = QLabel("等待 RTSP")
        status_layout.addWidget(QLabel("MediaMTX"), 0, 0)
        status_layout.addWidget(self.mediamtx_status, 0, 1)
        status_layout.addWidget(QLabel("RKNN 导播推流"), 1, 0)
        status_layout.addWidget(self.director_status, 1, 1)
        status_layout.addWidget(QLabel("技术台 / 8010"), 2, 0)
        status_layout.addWidget(self.techtable_status, 2, 1)
        status_layout.addWidget(QLabel("本地预览"), 3, 0)
        status_layout.addWidget(self.rtsp_status, 3, 1)
        layout.addWidget(status_box)

        note = QLabel(
            "技术台窗口会自动打开；网页计分：http://RK_IP:8010/　"
            "RTSP：rtsp://RK_IP:8554/director"
        )
        note.setWordWrap(True)
        note.setStyleSheet("font-size:15px; padding:8px; background:#eef4ff;")
        layout.addWidget(note)

        buttons = QHBoxLayout()
        logs_button = self._normal_button("打开日志目录")
        logs_button.clicked.connect(self.open_log_directory)
        restart_button = self._normal_button("重新启动导播服务")
        restart_button.clicked.connect(self.restart_director_services)
        stop_button = self._danger_button("停止全部程序")
        stop_button.clicked.connect(self.stop_all_services)
        buttons.addWidget(logs_button)
        buttons.addWidget(restart_button)
        buttons.addStretch(1)
        buttons.addWidget(stop_button)
        layout.addLayout(buttons)
        return page

    # ------------------------- 名单选择 -------------------------

    def refresh_environment_hint(self) -> None:
        problems = []
        if not FACE_ENV_PYTHON.is_file():
            problems.append("未找到 face_env/bin/python")
        if not FACE_LABELS_PATH.is_file():
            problems.append("未找到 face_checkin/trainer/labels.json，请先训练人脸模型")
        if not self.identities:
            problems.append("当前没有可绑定的人脸档案")
        try:
            has_lbph = hasattr(cv2, "face") and (
                hasattr(cv2.face, "LBPHFaceRecognizer_create")
                or hasattr(cv2.face, "LBPHFaceRecognizer")
            )
        except Exception:
            has_lbph = False
        if not has_lbph:
            problems.append("当前 Python 的 OpenCV 没有 LBPH 接口")

        if problems:
            self.environment_hint.setText("环境检查：⚠ " + "；".join(problems))
            self.environment_hint.setStyleSheet(
                "font-size:14px; padding:9px; background:#fff2cc; border-radius:6px;"
            )
        else:
            self.environment_hint.setText(
                f"环境检查：正常。当前 UI Python：{sys.executable}；"
                f"导播 Python：{SYSTEM_PYTHON}；人脸档案数：{len(self.identities)}"
            )

    def refresh_selection_table(self) -> None:
        self.selection_table.setRowCount(len(self.roster_rows))
        identity_by_id = {item["person_id"]: item for item in self.identities}

        for table_row, row in enumerate(self.roster_rows):
            check_item = QTableWidgetItem()
            check_item.setFlags(
                Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsUserCheckable
            )
            check_item.setCheckState(Qt.Checked if row["selected"] else Qt.Unchecked)
            self.selection_table.setItem(table_row, 0, check_item)

            self.selection_table.setItem(table_row, 1, QTableWidgetItem(row["team_name"]))
            self.selection_table.setItem(table_row, 2, QTableWidgetItem(row["number"]))
            self.selection_table.setItem(table_row, 3, QTableWidgetItem(row["name"]))

            combo = QComboBox()
            combo.addItem("未绑定", "")
            for identity in self.identities:
                combo.addItem(
                    f"{identity['person_id']}｜{identity['name']}",
                    identity["person_id"],
                )
            selected_index = combo.findData(row.get("face_id", ""))
            combo.setCurrentIndex(selected_index if selected_index >= 0 else 0)
            combo.currentIndexChanged.connect(
                lambda _index, r=table_row, c=combo: self.on_face_mapping_changed(r, c)
            )
            self.selection_table.setCellWidget(table_row, 4, combo)

            status = row.get("status", STATUS_UNSELECTED)
            self.selection_table.setItem(table_row, 5, QTableWidgetItem(status))

            face_id = row.get("face_id", "")
            if face_id and face_id in identity_by_id:
                note = "已绑定，可检录"
            else:
                note = "请选择对应的人脸档案"
            self.selection_table.setItem(table_row, 6, QTableWidgetItem(note))

        self.selection_table.resizeRowsToContents()

    def sync_selection_from_table(self) -> None:
        for index, row in enumerate(self.roster_rows):
            item = self.selection_table.item(index, 0)
            row["selected"] = bool(item and item.checkState() == Qt.Checked)

    def on_face_mapping_changed(self, row_index: int, combo: QComboBox) -> None:
        face_id = str(combo.currentData() or "")
        row = self.roster_rows[row_index]
        row["face_id"] = face_id
        if face_id:
            self.saved_mapping[row["key"]] = face_id
        else:
            self.saved_mapping.pop(row["key"], None)
        atomic_write_json(FACE_MAPPING_PATH, self.saved_mapping)

        note_item = self.selection_table.item(row_index, 6)
        if note_item is not None:
            note_item.setText("已绑定，可检录" if face_id else "请选择对应的人脸档案")

    def set_selection_mode(self, mode: str) -> None:
        for index, row in enumerate(self.roster_rows):
            checked = (
                mode == "all"
                or (mode == "home" and row["team"] == "home")
                or (mode == "away" and row["team"] == "away")
            )
            if mode == "none":
                checked = False
            item = self.selection_table.item(index, 0)
            if item is not None:
                item.setCheckState(Qt.Checked if checked else Qt.Unchecked)

    def validate_selected_players(self) -> Tuple[bool, str]:
        selected = [row for row in self.roster_rows if row["selected"]]
        if not selected:
            return False, "请至少勾选一名需要检录的球员。"

        missing = [f"{row['team_name']} {row['number']} {row['name']}" for row in selected if not row.get("face_id")]
        if missing:
            return False, "以下球员没有绑定人脸档案：\n" + "\n".join(missing)

        face_ids = [row["face_id"] for row in selected]
        duplicate_ids = sorted({face_id for face_id in face_ids if face_ids.count(face_id) > 1})
        if duplicate_ids:
            return False, "同一人脸档案不能绑定给多名已选球员：" + ", ".join(duplicate_ids)

        return True, ""

    # ------------------------- 检录 -------------------------

    def start_checkin(self) -> None:
        self.sync_selection_from_table()

        # 尚未完成的非勾选成员恢复为未选择；已完成状态保留审计记录。
        for row in self.roster_rows:
            if not row["selected"] and row["status"] == STATUS_PENDING:
                row["status"] = STATUS_UNSELECTED
            elif row["selected"] and row["status"] in (STATUS_UNSELECTED, STATUS_NO_FACE):
                row["status"] = STATUS_PENDING

        ok, message = self.validate_selected_players()
        if not ok:
            QMessageBox.warning(self, "无法开始检录", message)
            return

        if self.match_id is None:
            self.match_id = datetime.now().strftime("%Y%m%d_%H%M%S")
            self.session_path = FACE_WORK_DIR / "records" / f"checkin_session_{self.match_id}.json"

        self.refresh_checkin_table()
        self.save_session()
        self.stack.setCurrentWidget(self.checkin_page)
        self.start_face_thread()

    def selected_rows(self) -> List[Dict[str, Any]]:
        return [row for row in self.roster_rows if row["selected"]]

    def start_face_thread(self) -> None:
        self.stop_face_thread()

        selected = self.selected_rows()
        selected_face_ids = {row["face_id"] for row in selected}
        completed = {
            row["face_id"]
            for row in selected
            if row["status"] in (STATUS_CHECKED, STATUS_ABSENT)
        }

        self.face_thread = FaceCheckinThread(
            selected_face_ids,
            completed,
            self.threshold_spin.value(),
            self.stable_spin.value(),
            self,
        )
        self.face_thread.frame_ready.connect(self.show_checkin_frame)
        self.face_thread.status_ready.connect(
            lambda text: self.checkin_status_label.setText(f"状态：{text}")
        )
        self.face_thread.candidate_ready.connect(self.on_candidate)
        self.face_thread.checkin_confirmed.connect(self.on_checkin_confirmed)
        self.face_thread.error_ready.connect(self.on_face_error)
        self.face_thread.start()
        self.pause_button.setText("暂停识别")

    def stop_face_thread(self) -> None:
        if self.face_thread is not None:
            self.face_thread.stop()
            self.face_thread = None

    def show_bgr_frame(self, label: QLabel, frame: np.ndarray) -> None:
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        height, width, channels = rgb.shape
        image = QImage(
            rgb.data,
            width,
            height,
            channels * width,
            QImage.Format_RGB888,
        ).copy()
        pixmap = QPixmap.fromImage(image)
        pixmap = pixmap.scaled(
            label.size(),
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation,
        )
        label.setPixmap(pixmap)

    def show_checkin_frame(self, frame: np.ndarray) -> None:
        self.show_bgr_frame(self.checkin_video, frame)

    def on_candidate(self, face_id: str, name: str, confidence: float, hits: int) -> None:
        if not face_id:
            self.candidate_label.setText("当前识别：无")
            return

        selected = next((row for row in self.selected_rows() if row["face_id"] == face_id), None)
        prefix = "已选球员" if selected is not None else "未勾选人员"
        self.candidate_label.setText(
            f"当前识别：{prefix}　{face_id} {name}　"
            f"距离 {confidence:.1f}　连续 {hits}/{self.stable_spin.value()}"
        )

    def on_checkin_confirmed(self, face_id: str, name: str, confidence: float) -> None:
        row = next(
            (
                item
                for item in self.selected_rows()
                if item["face_id"] == face_id and item["status"] == STATUS_PENDING
            ),
            None,
        )
        if row is None:
            return

        row["status"] = STATUS_CHECKED
        row["confidence"] = float(confidence)
        row["checkin_time"] = datetime.now().strftime("%H:%M:%S")

        if self.face_thread is not None:
            self.face_thread.mark_completed(face_id)

        self.append_checkin_csv(row)
        self.save_session()
        self.refresh_checkin_table()
        self.checkin_status_label.setText(
            f"状态：检录成功——{row['team_name']} {row['number']} {row['name']}"
        )

    def on_face_error(self, message: str) -> None:
        self.checkin_status_label.setText(f"状态：检录线程错误：{message}")
        QMessageBox.critical(self, "人脸检录错误", message)

    def toggle_face_pause(self) -> None:
        if self.face_thread is None:
            return
        paused = self.pause_button.text() == "暂停识别"
        self.face_thread.set_paused(paused)
        self.pause_button.setText("继续识别" if paused else "暂停识别")
        self.checkin_status_label.setText("状态：识别已暂停" if paused else "状态：识别已继续")

    def refresh_checkin_table(self) -> None:
        selected = self.selected_rows()
        self.checkin_table.setRowCount(len(selected))

        for table_row, row in enumerate(selected):
            values = [
                row["team_name"],
                row["number"],
                row["name"],
                row["face_id"],
                row["status"],
                (
                    f"{row['checkin_time']} / {row['confidence']:.1f}"
                    if row.get("confidence") is not None
                    else row.get("checkin_time", "")
                ),
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                self.checkin_table.setItem(table_row, column, item)

        checked = sum(row["status"] == STATUS_CHECKED for row in selected)
        absent = sum(row["status"] == STATUS_ABSENT for row in selected)
        pending = sum(row["status"] == STATUS_PENDING for row in selected)
        self.progress_label.setText(
            f"已检录 {checked} / 缺席 {absent} / 待检录 {pending} / 共 {len(selected)}"
        )
        self.enter_director_button.setEnabled(bool(selected) and pending == 0)

    def selected_checkin_table_rows(self) -> List[Dict[str, Any]]:
        selected_players = self.selected_rows()
        row_indexes = sorted({index.row() for index in self.checkin_table.selectedIndexes()})
        return [selected_players[index] for index in row_indexes if 0 <= index < len(selected_players)]

    def mark_selected_absent(self) -> None:
        rows = self.selected_checkin_table_rows()
        if not rows:
            QMessageBox.information(self, "选择球员", "请先在右侧表格中选择需要记录缺席的球员。")
            return

        names = "\n".join(f"{row['team_name']} {row['number']} {row['name']}" for row in rows)
        answer = QMessageBox.question(
            self,
            "确认缺席",
            "确定将以下人员记录为缺席吗？\n\n" + names,
        )
        if answer != QMessageBox.Yes:
            return

        for row in rows:
            if row["status"] == STATUS_CHECKED:
                continue
            row["status"] = STATUS_ABSENT
            row["checkin_time"] = datetime.now().strftime("%H:%M:%S")
            row["confidence"] = None
            if self.face_thread is not None:
                self.face_thread.mark_completed(row["face_id"])

        self.save_session()
        self.refresh_checkin_table()

    def restore_selected_pending(self) -> None:
        rows = self.selected_checkin_table_rows()
        if not rows:
            QMessageBox.information(self, "选择球员", "请先在右侧表格中选择需要恢复的球员。")
            return

        for row in rows:
            if row["status"] == STATUS_ABSENT:
                row["status"] = STATUS_PENDING
                row["checkin_time"] = ""
                row["confidence"] = None

        # 为了让线程重新接收恢复后的 face_id，直接重启检录线程。
        self.save_session()
        self.refresh_checkin_table()
        self.start_face_thread()

    def return_to_selection(self) -> None:
        self.stop_face_thread()
        self.refresh_selection_table()
        self.stack.setCurrentWidget(self.selection_page)

    def append_checkin_csv(self, row: Dict[str, Any]) -> None:
        records_dir = FACE_WORK_DIR / "records"
        ensure_dir(records_dir)
        path = records_dir / f"checkin_{datetime.now().strftime('%Y%m%d')}.csv"
        exists = path.is_file()
        with path.open("a", encoding="utf-8-sig", newline="") as file:
            fieldnames = [
                "match_id",
                "date",
                "time",
                "team",
                "team_name",
                "number",
                "person_id",
                "name",
                "status",
                "confidence",
            ]
            writer = csv.DictWriter(file, fieldnames=fieldnames)
            if not exists:
                writer.writeheader()
            writer.writerow(
                {
                    "match_id": self.match_id or "",
                    "date": datetime.now().strftime("%Y-%m-%d"),
                    "time": row.get("checkin_time", datetime.now().strftime("%H:%M:%S")),
                    "team": row["team"],
                    "team_name": row["team_name"],
                    "number": row["number"],
                    "person_id": row["face_id"],
                    "name": row["name"],
                    "status": row["status"],
                    "confidence": (
                        f"{row['confidence']:.2f}" if row.get("confidence") is not None else ""
                    ),
                }
            )

    def save_session(self) -> None:
        if self.session_path is None:
            return

        # 保存“当前活动场次”标记，停止脚本据此清除本场临时检录结果。
        # 这里只删除签到结果，不会删除 face_checkin/dataset、trainer 或映射关系。
        current_csv_path = (
            FACE_WORK_DIR
            / "records"
            / f"checkin_{datetime.now().strftime('%Y%m%d')}.csv"
        )
        active = read_json(ACTIVE_CHECKIN_FILE, {})
        csv_paths = {
            str(path)
            for path in (active.get("csv_paths", []) or [])
            if str(path).strip()
        }
        csv_paths.add(str(current_csv_path))

        atomic_write_json(
            ACTIVE_CHECKIN_FILE,
            {
                "match_id": self.match_id,
                "session_path": str(self.session_path),
                "csv_paths": sorted(csv_paths),
                "updated_at": datetime.now().isoformat(timespec="seconds"),
            },
        )

        selected = self.selected_rows()
        atomic_write_json(
            self.session_path,
            {
                "match_id": self.match_id,
                "updated_at": datetime.now().isoformat(timespec="seconds"),
                "home_name": self.team_names["home"],
                "away_name": self.team_names["away"],
                "players": selected,
                "summary": {
                    "total": len(selected),
                    "checked_in": sum(row["status"] == STATUS_CHECKED for row in selected),
                    "absent": sum(row["status"] == STATUS_ABSENT for row in selected),
                    "pending": sum(row["status"] == STATUS_PENDING for row in selected),
                },
            },
        )

    # ------------------------- 导播 -------------------------

    def enter_director(self) -> None:
        pending = [row for row in self.selected_rows() if row["status"] == STATUS_PENDING]
        if pending:
            QMessageBox.warning(
                self,
                "仍有待检录人员",
                "以下人员尚未检录，也没有记录为缺席：\n"
                + "\n".join(f"{row['team_name']} {row['number']} {row['name']}" for row in pending),
            )
            return

        answer = QMessageBox.question(
            self,
            "进入导播",
            "检录结果已经确认。是否释放检录摄像头并启动自动导播、RTSP 推流和技术台？",
        )
        if answer != QMessageBox.Yes:
            return

        self.stop_face_thread()
        self.checkin_video.clear()
        self.checkin_video.setText("检录摄像头已释放")
        self.save_session()

        alive = self.process_manager.existing_alive_records()
        if alive:
            replace = QMessageBox.question(
                self,
                "发现旧进程",
                "检测到已有导播相关进程正在运行。是否先停止旧进程再重新启动？",
            )
            if replace != QMessageBox.Yes:
                return
            self.process_manager.stop_all()

        # 不进入启动器自己的第三页；继续在检录页显示启动进度。
        # 服务启动完成后会隐藏本窗口，由原 rk_techtable_panel.py 接管 LCD。
        self.enter_director_button.setEnabled(False)
        self.checkin_status_label.setText(
            "状态：正在启动 MediaMTX、带音频 RTSP 导播和技术台……"
        )
        QApplication.processEvents()
        self.start_director_services()

    def start_director_services(self) -> None:
        self.checkin_status_label.setText(
            "状态：正在启动并验证 H.264 + AAC RTSP 流……"
        )
        QApplication.processEvents()

        # 后台线程启动进程并执行 ffprobe 验收，避免阻塞 UI。
        self.startup_thread = StartupThread(self.process_manager, self)
        self.startup_thread.finished.connect(self._on_startup_finished)
        self.startup_thread.error.connect(self._on_startup_error)
        self.startup_thread.start()

    def _on_startup_finished(self) -> None:
        self.director_started = True
        self.checkin_status_label.setText(
            "状态：RTSP 音视频验证通过，技术台已启动。"
        )

        # 技术台是正式比赛界面；启动器隐藏但保持运行，
        # 之后由 stop_all_techtable.py 统一停止全部进程。
        self.hide()

    def _on_startup_error(self, message: str) -> None:
        self.enter_director_button.setEnabled(True)
        self.checkin_status_label.setText(
            "状态：导播启动失败，请查看 runtime/logs。"
        )
        QMessageBox.critical(self, "导播启动失败", message)

    def start_preview_thread(self) -> None:
        if self.preview_thread is not None:
            self.preview_thread.stop()
        self.preview_thread = DirectorPreviewThread(
            "rtsp://127.0.0.1:8554/director",
            self,
        )
        self.preview_thread.frame_ready.connect(
            lambda frame: self.show_bgr_frame(self.director_video, frame)
        )
        self.preview_thread.status_ready.connect(self.rtsp_status.setText)
        self.preview_thread.start()

    def refresh_process_status(self) -> None:
        if not hasattr(self, "mediamtx_status"):
            return
        self.mediamtx_status.setText(self.process_manager.status("mediamtx"))
        self.director_status.setText(self.process_manager.status("director"))
        self.techtable_status.setText(self.process_manager.status("techtable"))

    def restart_director_services(self) -> None:
        answer = QMessageBox.question(self, "重新启动", "确定重新启动全部导播服务吗？")
        if answer != QMessageBox.Yes:
            return
        if self.preview_thread is not None:
            self.preview_thread.stop()
            self.preview_thread = None
        self.process_manager.stop_all()
        self.start_director_services()

    def stop_all_services(self) -> None:
        answer = QMessageBox.question(self, "停止全部", "确定停止技术台、导播推流和 MediaMTX 吗？")
        if answer != QMessageBox.Yes:
            return
        if self.preview_thread is not None:
            self.preview_thread.stop()
            self.preview_thread = None
        self.process_manager.stop_all()
        self.director_started = False
        self.director_video.clear()
        self.director_video.setText("全部导播服务已停止")
        self.rtsp_status.setText("已停止")
        self.refresh_process_status()

    def open_log_directory(self) -> None:
        ensure_dir(LOG_DIR)
        opener = shutil.which("xdg-open")
        if opener:
            subprocess.Popen([opener, str(LOG_DIR)])
        else:
            QMessageBox.information(self, "日志目录", str(LOG_DIR))

    # ------------------------- 退出 -------------------------

    def closeEvent(self, event) -> None:  # noqa: N802
        self.stop_face_thread()
        if self.preview_thread is not None:
            self.preview_thread.stop()
            self.preview_thread = None

        if self.process_manager.existing_alive_records():
            box = QMessageBox(self)
            box.setWindowTitle("关闭工作流窗口")
            box.setText("导播相关进程仍在运行。")
            stop_button = box.addButton("停止全部并退出", QMessageBox.DestructiveRole)
            keep_button = box.addButton("保持后台运行并退出", QMessageBox.AcceptRole)
            cancel_button = box.addButton("取消", QMessageBox.RejectRole)
            box.exec_()

            clicked = box.clickedButton()
            if clicked == cancel_button:
                event.ignore()
                return
            if clicked == stop_button:
                self.process_manager.stop_all()
            elif clicked != keep_button:
                event.ignore()
                return

        try:
            LAUNCHER_PID_FILE.unlink()
        except FileNotFoundError:
            pass
        event.accept()


# ---------------------------------------------------------------------------
# 九、入口
# ---------------------------------------------------------------------------


def main() -> int:
    ensure_dir(RUNTIME_DIR)
    ensure_dir(LOG_DIR)

    # QApplication 创建前锁定 Qt 插件搜索路径。
    # 这里传入的是插件根目录，内部应包含 platforms/libqxcb.so。
    if not Path(SYSTEM_QT_PLUGIN_DIR).is_dir():
        print(
            f"[警告] 系统 Qt 插件目录不存在: {SYSTEM_QT_PLUGIN_DIR}",
            file=sys.stderr,
        )
    else:
        QCoreApplication.setLibraryPaths([SYSTEM_QT_PLUGIN_DIR])

    print(f"[Qt] platform              : {os.environ.get('QT_QPA_PLATFORM')}")
    print(
        "[Qt] platform plugin path  : "
        f"{os.environ.get('QT_QPA_PLATFORM_PLUGIN_PATH')}"
    )
    print(f"[Qt] library paths         : {QCoreApplication.libraryPaths()}")
    print(f"[OpenCV] version           : {cv2.__version__}")
    print(f"[OpenCV] path              : {cv2.__file__}")

    app = QApplication(sys.argv)
    # 检录窗口隐藏后仍需保留启动器进程，直到 stop_all_techtable.py 结束它。
    app.setQuitOnLastWindowClosed(False)
    app.setStyle("Fusion")
    window = WorkflowWindow()
    window.show()
    return app.exec_()


if __name__ == "__main__":
    raise SystemExit(main())
