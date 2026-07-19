#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
face_checkin_lbph.py
====================

单目摄像头篮球赛事检录模块：人脸采集、训练、识别与签到记录。

适用工程：
    2026_embeddedSystem_camera_150
    RK3588 / Linux / USB UVC 摄像头 / OpenCV

本脚本为什么先选用 Haar + LBPH？
---------------------------------
1. Haar Cascade 用于“人脸检测”：
   找出画面中人脸的位置，得到矩形框。

2. LBPH（Local Binary Patterns Histograms）用于“人脸识别”：
   把检测到的人脸与已经登记的人脸样本进行比较，从而判断是谁。

3. 这套方法结构简单，适合第一次学习完整的人脸识别流程：
   摄像头采集 -> 人脸检测 -> 样本保存 -> 模型训练 -> 实时预测 -> 检录记录。

4. 它不是最终高精度方案：
   对光照、角度、遮挡和远距离人脸比较敏感。项目后续可以将 Haar/LBPH
   替换为 RetinaFace/SCRFD + ArcFace，并转换为 RKNN 在 RK3588 NPU 上运行。

目录结构
--------
脚本默认在工程根目录创建：

face_checkin/
├── dataset/                       # 每位人员的人脸样本
│   ├── 001__zhangsan/
│   │   ├── 0001.jpg
│   │   └── ...
│   └── 002__lisi/
├── trainer/
│   ├── lbph_model.yml             # LBPH 模型
│   └── labels.json                # 数字标签与人员信息的映射
└── records/
    └── checkin_20260719.csv        # 当天检录记录

典型运行方法
------------
一、安装依赖

    # cv2.face 位于 OpenCV contrib 扩展中。
    python3 -m pip install opencv-contrib-python numpy

    # 检查 cv2.face 是否可用：
    python3 -c "import cv2; print(hasattr(cv2, 'face'))"

二、采集一名球员的人脸

    python3 face_checkin_lbph.py \
      --mode enroll \
      --person-id 001 \
      --name player_001 \
      --device /dev/video41 \
      --calib-file camera_usb3_calib.npz

    采集时：
        - 保证画面中只有一张主要人脸；
        - 缓慢进行轻微左右转头和抬头低头；
        - 按 q 或 Esc 可提前退出；
        - 达到 --samples 指定数量后自动结束。

三、训练识别模型
      

./face_env/bin/python face_checkin_lbph.py \
  --mode train


四、实时识别并检录

./face_env/bin/python face_checkin_lbph.py \
  --mode recognize \
  --device /dev/video41 \
  --calib-file camera_usb3_calib.npz

  
    当同一个身份连续识别达到 --stable-hits 次时，写入当天 CSV。
    同一人员当天默认只登记一次。

五、一条命令训练后立即识别

    python3 face_checkin_lbph.py \
      --mode train-recognize \
      --device /dev/video41 \
      --calib-file camera_usb3_calib.npz

重要说明
--------
1. LBPH 的 confidence 数值越小，表示与训练样本越相似。
2. --recognition-threshold 越小，判断越严格；越大，越容易误认。
3. 建议从 60~75 范围测试，默认值为 68。
4. 为保护个人信息，人脸样本和签到记录均保存在本机，不上传网络。
5. 实际赛事使用前，应取得被采集人员同意，并限制数据访问权限。
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# RK3588 上禁用 OpenCV OpenCL，避免某些 Mali/OpenCL 环境产生额外开销或异常。
# 这项环境变量必须尽量在 import cv2 之前设置。
os.environ.setdefault("OPENCV_OPENCL_RUNTIME", "disabled")

import cv2
import numpy as np

try:
    cv2.ocl.setUseOpenCL(False)
except Exception:
    pass


# ---------------------------------------------------------------------------
# 一、默认配置
# ---------------------------------------------------------------------------

DEFAULT_DEVICE = "/dev/video41"
DEFAULT_WIDTH = 1920
DEFAULT_HEIGHT = 1080
DEFAULT_FPS = 30

DEFAULT_WORK_DIR = "face_checkin"
DEFAULT_CALIB_FILE = "camera_usb3_calib.npz"

# 训练和识别时统一把人脸区域缩放为固定尺寸。
# 固定尺寸有利于让不同时间采集的样本格式一致。
DEFAULT_FACE_WIDTH = 160
DEFAULT_FACE_HEIGHT = 160


# ---------------------------------------------------------------------------
# 二、数据结构
# ---------------------------------------------------------------------------

@dataclass
class CameraCalibration:
    """
    单目相机去畸变参数。

    map1、map2 是 OpenCV remap 使用的查找表。
    每一帧调用 cv2.remap()，即可完成与项目导播脚本一致的单目去畸变。
    """

    image_size: Tuple[int, int]
    map1: np.ndarray
    map2: np.ndarray


@dataclass
class PersonInfo:
    """
    训练模型中的一个人员标签。

    model_label:
        LBPH 内部使用的整数标签。LBPH 不能直接使用字符串姓名。

    person_id:
        赛事检录系统中的人员编号，例如球员编号、学号或报名编号。

    name:
        显示名称。OpenCV 默认字体不支持中文时，画面中可能只正常显示 person_id，
        但 CSV 和 labels.json 仍然能够正确保存 UTF-8 中文。
    """

    model_label: int
    person_id: str
    name: str
    folder: str


# ---------------------------------------------------------------------------
# 三、通用工具函数
# ---------------------------------------------------------------------------

def ensure_directory(path: Path) -> None:
    """如果目录不存在，则递归创建。"""
    path.mkdir(parents=True, exist_ok=True)


def sanitize_path_component(text: str) -> str:
    """
    把人员编号或姓名转换为适合目录名的字符串。

    只保留：
        - 中文字符
        - 英文字母
        - 数字
        - 下划线和短横线

    其他字符替换为下划线，防止姓名中出现 /、空格等字符破坏目录结构。
    """
    cleaned = re.sub(r"[^\w\u4e00-\u9fff-]+", "_", text.strip(), flags=re.UNICODE)
    cleaned = cleaned.strip("_")
    return cleaned or "unknown"


def create_lbph_recognizer():
    """
    创建 OpenCV LBPH 人脸识别器。

    cv2.face 属于 opencv-contrib 模块，不是所有 OpenCV 安装都包含它。
    因此在这里集中检查，并给出清楚的错误提示。
    """
    if not hasattr(cv2, "face"):
        raise RuntimeError(
            "当前 OpenCV 不包含 cv2.face。\n"
            "请安装带 contrib 模块的版本，例如：\n"
            "  python3 -m pip install opencv-contrib-python\n"
            "安装后检查：\n"
            "  python3 -c \"import cv2; print(hasattr(cv2, 'face'))\""
        )

    if not hasattr(cv2.face, "LBPHFaceRecognizer_create"):
        raise RuntimeError("当前 cv2.face 中没有 LBPHFaceRecognizer_create()。")

    return cv2.face.LBPHFaceRecognizer_create(
        radius=1,
        neighbors=8,
        grid_x=8,
        grid_y=8,
    )


def find_default_cascade() -> Path:
    """
    查找 OpenCV 自带的正面人脸 Haar 分类器。

    常见 pip 安装会提供：
        cv2.data.haarcascades/haarcascade_frontalface_default.xml

    部分 Linux 系统包会把文件安装在 /usr/share/opencv4/haarcascades/。
    """
    candidates: List[Path] = []

    if hasattr(cv2, "data") and hasattr(cv2.data, "haarcascades"):
        candidates.append(
            Path(cv2.data.haarcascades) / "haarcascade_frontalface_default.xml"
        )

    candidates.extend(
        [
            Path("/usr/share/opencv4/haarcascades/haarcascade_frontalface_default.xml"),
            Path("/usr/share/opencv/haarcascades/haarcascade_frontalface_default.xml"),
        ]
    )

    for path in candidates:
        if path.is_file():
            return path

    raise RuntimeError(
        "没有找到 haarcascade_frontalface_default.xml。\n"
        "可以使用 --cascade-file 显式指定该文件。"
    )


def load_face_detector(cascade_file: Optional[str]) -> cv2.CascadeClassifier:
    """加载 Haar 人脸检测模型。"""
    cascade_path = Path(cascade_file) if cascade_file else find_default_cascade()

    if not cascade_path.is_file():
        raise RuntimeError(f"人脸检测模型不存在: {cascade_path}")

    detector = cv2.CascadeClassifier(str(cascade_path))
    if detector.empty():
        raise RuntimeError(f"人脸检测模型加载失败: {cascade_path}")

    print(f"[人脸检测] Haar 模型: {cascade_path}")
    return detector


def resize_for_display(frame: np.ndarray, scale: float) -> np.ndarray:
    """仅缩放显示窗口，不改变原始识别坐标。"""
    if abs(scale - 1.0) < 1e-6:
        return frame

    interpolation = cv2.INTER_AREA if scale < 1.0 else cv2.INTER_LINEAR
    return cv2.resize(
        frame,
        None,
        fx=scale,
        fy=scale,
        interpolation=interpolation,
    )


def normalize_face(face_gray: np.ndarray, face_size: Tuple[int, int]) -> np.ndarray:
    """
    对人脸 ROI 做统一预处理。

    步骤：
        1. 缩放到固定尺寸；
        2. 直方图均衡化，减轻整体亮暗差异。

    注意：
        这里是入门级预处理，没有做人脸关键点定位和对齐。
        后续使用 ArcFace 时，应增加眼睛关键点对齐。
    """
    width, height = face_size
    resized = cv2.resize(face_gray, (width, height), interpolation=cv2.INTER_AREA)
    equalized = cv2.equalizeHist(resized)
    return equalized


def detect_faces(
    detector: cv2.CascadeClassifier,
    gray: np.ndarray,
    min_face_size: int,
) -> List[Tuple[int, int, int, int]]:
    """
    在灰度图中检测人脸。

    scaleFactor=1.1：
        每次把图像尺度缩小约 10%，搜索不同大小的人脸。

    minNeighbors=5：
        候选框至少需要一定数量的邻近检测支持。
        数值增大可减少误检，但也可能漏检。

    minSize：
        忽略太小的人脸。篮球场远景中的人脸像素过少，本来也不适合识别。
    """
    faces = detector.detectMultiScale(
        gray,
        scaleFactor=1.1,
        minNeighbors=5,
        flags=cv2.CASCADE_SCALE_IMAGE,
        minSize=(min_face_size, min_face_size),
    )

    # OpenCV 可能返回 tuple 或 ndarray，这里统一转换为 Python 元组列表。
    result = [tuple(int(v) for v in face) for face in faces]

    # 面积大的脸排在前面。登记人员时默认使用最大人脸。
    result.sort(key=lambda item: item[2] * item[3], reverse=True)
    return result


def draw_text(
    image: np.ndarray,
    text: str,
    position: Tuple[int, int],
    scale: float = 0.7,
    thickness: int = 2,
) -> None:
    """
    使用 OpenCV 绘制英文、数字和部分 ASCII 文本。

    cv2.putText 默认不支持中文。
    为保证脚本只依赖 OpenCV，这里不强制引入 Pillow。
    中文姓名仍会正确写入 JSON 和 CSV。
    """
    cv2.putText(
        image,
        text,
        position,
        cv2.FONT_HERSHEY_SIMPLEX,
        scale,
        (255, 255, 255),
        thickness,
        cv2.LINE_AA,
    )


# ---------------------------------------------------------------------------
# 四、摄像头与去畸变
# ---------------------------------------------------------------------------

def open_camera(
    device: str,
    width: int,
    height: int,
    fps: int,
) -> cv2.VideoCapture:
    """
    按项目当前 USB 摄像头方式打开设备。

    关键设置：
        CAP_V4L2：
            Linux 下显式使用 V4L2 后端。

        CAP_PROP_BUFFERSIZE = 1：
            尽量减少 OpenCV/V4L2 缓冲，避免读取到积压旧帧。

        MJPG：
            1920x1080@30fps 时，USB 摄像头常用 MJPEG 传输，
            比未压缩 YUYV 更节省 USB 带宽。
    """
    cap = cv2.VideoCapture(device, cv2.CAP_V4L2)
    if not cap.isOpened():
        raise RuntimeError(f"无法打开摄像头: {device}")

    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, int(width))
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, int(height))
    cap.set(cv2.CAP_PROP_FPS, int(fps))

    real_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    real_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    real_fps = float(cap.get(cv2.CAP_PROP_FPS))
    fourcc_value = int(cap.get(cv2.CAP_PROP_FOURCC))
    fourcc_text = "".join(
        chr((fourcc_value >> (8 * index)) & 0xFF) for index in range(4)
    )

    print(f"[摄像头] 设备: {device}")
    print(
        f"[摄像头] 实际参数: "
        f"{real_width}x{real_height} @ {real_fps:.1f}fps, FOURCC={fourcc_text}"
    )
    return cap


class LatestFrameCamera:
    """
    后台采集线程，只保存最新一帧。

    为什么需要这个类？
    ------------------
    普通写法是：

        while True:
            ret, frame = cap.read()
            做识别...

    如果识别速度低于摄像头帧率，摄像头内部可能积压旧帧，显示延迟越来越大。

    本类把“采集”和“识别”解耦：
        - 采集线程持续读取摄像头；
        - latest_frame 始终被新画面覆盖；
        - 主线程每次只处理最近一帧；
        - 处理不完的旧帧直接丢弃。

    这与项目导播基础模块的实时策略一致。
    """

    def __init__(
        self,
        device: str,
        width: int,
        height: int,
        fps: int,
    ) -> None:
        self.device = device
        self.width = width
        self.height = height
        self.fps = fps

        self.cap: Optional[cv2.VideoCapture] = None
        self.thread: Optional[threading.Thread] = None
        self.stop_event = threading.Event()
        self.lock = threading.Lock()

        self.latest_frame: Optional[np.ndarray] = None
        self.latest_index = -1
        self.latest_timestamp = 0.0
        self.read_fail_count = 0

    def start(self) -> "LatestFrameCamera":
        """打开摄像头并启动后台线程。"""
        self.cap = open_camera(
            self.device,
            self.width,
            self.height,
            self.fps,
        )
        self.thread = threading.Thread(
            target=self._capture_loop,
            name="face-checkin-camera",
            daemon=True,
        )
        self.thread.start()
        return self

    def _capture_loop(self) -> None:
        """采集线程函数，不在主线程中直接调用。"""
        assert self.cap is not None

        frame_index = 0

        while not self.stop_event.is_set():
            ok, frame = self.cap.read()

            if not ok or frame is None:
                self.read_fail_count += 1
                time.sleep(0.005)
                continue

            with self.lock:
                # 使用赋值覆盖，而不是建立无限队列。
                self.latest_frame = frame
                self.latest_index = frame_index
                self.latest_timestamp = time.time()

            frame_index += 1

    def wait_first_frame(self, timeout: float = 5.0) -> bool:
        """等待摄像头产生第一帧，超时返回 False。"""
        start_time = time.time()

        while time.time() - start_time < timeout:
            with self.lock:
                ready = self.latest_frame is not None

            if ready:
                return True

            time.sleep(0.01)

        return False

    def get_latest(self) -> Tuple[int, Optional[np.ndarray], float]:
        """
        取得最新帧。

        返回 frame.copy()，避免主线程处理图像时与采集线程的数据引用互相影响。
        """
        with self.lock:
            if self.latest_frame is None:
                return -1, None, 0.0

            return (
                self.latest_index,
                self.latest_frame.copy(),
                self.latest_timestamp,
            )

    def stop(self) -> None:
        """停止线程并释放摄像头。"""
        self.stop_event.set()

        if self.thread is not None:
            self.thread.join(timeout=1.0)

        if self.cap is not None:
            self.cap.release()


def load_camera_calibration(calib_file: Optional[str]) -> Optional[CameraCalibration]:
    """
    加载项目现有的 camera_usb3_calib.npz。

    返回 None 的情况：
        - 用户传入 --no-undistort；
        - 文件不存在；
        - 调用方明确不使用校准文件。

    需要字段：
        camera_matrix
        dist_coeffs
        new_camera_matrix
        image_size
    """
    if not calib_file:
        print("[去畸变] 已禁用。")
        return None

    path = Path(calib_file)
    if not path.is_file():
        print(f"[去畸变] 警告：找不到校准文件，将使用原始画面: {path}")
        return None

    data = np.load(str(path))
    required_fields = {
        "camera_matrix",
        "dist_coeffs",
        "new_camera_matrix",
        "image_size",
    }

    missing = required_fields.difference(data.files)
    if missing:
        raise RuntimeError(
            f"校准文件缺少字段: {sorted(missing)}，文件: {path}"
        )

    camera_matrix = data["camera_matrix"].astype(np.float64)
    dist_coeffs = data["dist_coeffs"].astype(np.float64)
    new_camera_matrix = data["new_camera_matrix"].astype(np.float64)

    image_size_array = np.asarray(data["image_size"]).reshape(-1)
    if image_size_array.size < 2:
        raise RuntimeError(f"image_size 字段格式错误: {data['image_size']}")

    image_size = (
        int(image_size_array[0]),
        int(image_size_array[1]),
    )

    map1, map2 = cv2.initUndistortRectifyMap(
        camera_matrix,
        dist_coeffs,
        None,
        new_camera_matrix,
        image_size,
        cv2.CV_16SC2,
    )

    print(
        f"[去畸变] 已加载: {path}, "
        f"标定分辨率={image_size[0]}x{image_size[1]}"
    )

    return CameraCalibration(
        image_size=image_size,
        map1=map1,
        map2=map2,
    )


def apply_undistort(
    frame: np.ndarray,
    calibration: Optional[CameraCalibration],
) -> np.ndarray:
    """
    对当前帧执行单目去畸变。

    如果实际摄像头分辨率与标定分辨率不一致，为防止错误 remap，
    这里发出异常，而不是默默使用不匹配的参数。
    """
    if calibration is None:
        return frame

    frame_height, frame_width = frame.shape[:2]
    expected_width, expected_height = calibration.image_size

    if (frame_width, frame_height) != (expected_width, expected_height):
        raise RuntimeError(
            "摄像头分辨率与标定文件不一致："
            f"frame={frame_width}x{frame_height}, "
            f"calib={expected_width}x{expected_height}。"
            "请调整 --width/--height，或使用 --no-undistort。"
        )

    return cv2.remap(
        frame,
        calibration.map1,
        calibration.map2,
        interpolation=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_CONSTANT,
    )


# ---------------------------------------------------------------------------
# 五、人员样本采集
# ---------------------------------------------------------------------------

def enroll_person(
    args: argparse.Namespace,
    detector: cv2.CascadeClassifier,
    calibration: Optional[CameraCalibration],
) -> None:
    """
    采集一位人员的人脸样本。

    采集逻辑：
        1. 实时检测人脸；
        2. 选择面积最大的人脸；
        3. 按固定时间间隔自动保存；
        4. 保存前执行固定尺寸缩放和直方图均衡化；
        5. 达到目标数量后退出。

    为什么不每一帧都保存？
        连续视频相邻帧非常相似。
        使用 sample_interval 可以减少大量重复样本，让数据更有变化。
    """
    if not args.person_id or not args.name:
        raise ValueError(
            "enroll 模式必须同时提供 --person-id 和 --name。"
        )

    dataset_dir = Path(args.work_dir) / "dataset"
    ensure_directory(dataset_dir)

    safe_id = sanitize_path_component(args.person_id)
    safe_name = sanitize_path_component(args.name)
    person_folder = dataset_dir / f"{safe_id}__{safe_name}"
    ensure_directory(person_folder)

    # person.json 保存用户输入的原始编号和姓名。
    # 目录名为了兼容文件系统会进行字符清洗，但元数据不做清洗，
    # 因此中文、空格和标点仍可完整保留在 labels.json 与检录 CSV 中。
    person_metadata_path = person_folder / "person.json"
    person_metadata = {
        "person_id": args.person_id.strip(),
        "name": args.name.strip(),
        "updated_at": datetime.now().isoformat(timespec="seconds"),
    }
    with person_metadata_path.open("w", encoding="utf-8") as file:
        json.dump(person_metadata, file, ensure_ascii=False, indent=2)

    existing_samples = sorted(person_folder.glob("*.jpg"))
    sample_count = len(existing_samples)

    print(f"[登记] 人员编号: {args.person_id}")
    print(f"[登记] 姓名: {args.name}")
    print(f"[登记] 样本目录: {person_folder}")
    print(f"[登记] 已有样本: {sample_count}")
    print(f"[登记] 目标样本总数: {args.samples}")

    camera = LatestFrameCamera(
        args.device,
        args.width,
        args.height,
        args.fps,
    ).start()

    if not camera.wait_first_frame():
        camera.stop()
        raise RuntimeError("等待摄像头第一帧超时。")

    last_frame_index = -1
    last_save_time = 0.0
    window_name = "Face Enrollment - q/ESC to quit"

    try:
        while sample_count < args.samples:
            frame_index, frame, _ = camera.get_latest()

            if frame is None or frame_index == last_frame_index:
                time.sleep(0.002)
                continue

            last_frame_index = frame_index
            frame = apply_undistort(frame, calibration)

            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            gray_for_detection = cv2.equalizeHist(gray)
            faces = detect_faces(
                detector,
                gray_for_detection,
                args.min_face_size,
            )

            now = time.time()
            status_text = "No face"

            if faces:
                # 登记时只使用最大的人脸，减少旁人进入画面造成的错误数据。
                x, y, width, height = faces[0]

                cv2.rectangle(
                    frame,
                    (x, y),
                    (x + width, y + height),
                    (255, 255, 255),
                    2,
                )

                status_text = "Face detected"

                # 当距离上一次保存超过指定间隔，才保存新样本。
                if now - last_save_time >= args.sample_interval:
                    face_roi = gray[y : y + height, x : x + width]

                    if face_roi.size > 0:
                        normalized = normalize_face(
                            face_roi,
                            (args.face_width, args.face_height),
                        )

                        sample_count += 1
                        sample_path = person_folder / f"{sample_count:04d}.jpg"

                        if not cv2.imwrite(str(sample_path), normalized):
                            raise RuntimeError(f"保存样本失败: {sample_path}")

                        last_save_time = now
                        status_text = f"Saved {sample_count}/{args.samples}"
                        print(f"[登记] 已保存: {sample_path}")

            draw_text(
                frame,
                f"ID: {args.person_id}",
                (30, 40),
            )
            draw_text(
                frame,
                f"Samples: {sample_count}/{args.samples}",
                (30, 75),
            )
            draw_text(
                frame,
                status_text,
                (30, 110),
            )
            draw_text(
                frame,
                "Turn head slowly; keep one person in view",
                (30, 145),
                scale=0.6,
            )

            if not args.headless:
                display = resize_for_display(frame, args.display_scale)
                cv2.imshow(window_name, display)
                key = cv2.waitKey(1) & 0xFF

                if key in (ord("q"), 27):
                    print("[登记] 用户提前结束采集。")
                    break

    finally:
        camera.stop()
        cv2.destroyAllWindows()

    print(
        f"[登记] 完成，人员 {args.person_id} 当前共有 "
        f"{sample_count} 张有效样本。"
    )
    print("[下一步] 执行 --mode train 重新训练模型。")


# ---------------------------------------------------------------------------
# 六、训练 LBPH 模型
# ---------------------------------------------------------------------------

def parse_person_folder(folder_name: str) -> Tuple[str, str]:
    """
    从目录名“人员编号__姓名”中解析人员信息。

    使用 split("__", 1)，只在第一个双下划线处分割。
    """
    if "__" not in folder_name:
        raise ValueError(
            f"样本目录命名不符合 person_id__name 格式: {folder_name}"
        )

    person_id, name = folder_name.split("__", 1)
    return person_id, name


def train_model(args: argparse.Namespace) -> None:
    """
    扫描 dataset 目录，训练 LBPH 模型。

    LBPH train() 需要：
        faces:
            灰度人脸图像列表。

        labels:
            与每张图像一一对应的整数标签数组。

    labels.json 用于保存：
        0 -> 人员 001
        1 -> 人员 002
        ...

    识别时，LBPH 返回整数标签，再通过 labels.json 找回人员编号和姓名。
    """
    recognizer = create_lbph_recognizer()

    work_dir = Path(args.work_dir)
    dataset_dir = work_dir / "dataset"
    trainer_dir = work_dir / "trainer"

    ensure_directory(dataset_dir)
    ensure_directory(trainer_dir)

    person_folders = sorted(
        path for path in dataset_dir.iterdir() if path.is_dir()
    )

    if not person_folders:
        raise RuntimeError(
            f"没有找到人员样本目录: {dataset_dir}\n"
            "请先使用 --mode enroll 采集人脸。"
        )

    face_images: List[np.ndarray] = []
    numeric_labels: List[int] = []
    label_mapping: Dict[str, Dict[str, str]] = {}

    next_model_label = 0

    for folder in person_folders:
        # 新版样本目录优先读取 person.json，以保留原始中文姓名和标点。
        # 旧版目录没有 person.json 时，仍兼容从 person_id__name 目录名解析。
        metadata_path = folder / "person.json"
        if metadata_path.is_file():
            try:
                with metadata_path.open("r", encoding="utf-8") as file:
                    metadata = json.load(file)
                person_id = str(metadata["person_id"])
                name = str(metadata["name"])
            except (OSError, KeyError, ValueError, TypeError, json.JSONDecodeError) as error:
                print(f"[训练] 人员元数据无效，跳过 {folder}: {error}")
                continue
        else:
            try:
                person_id, name = parse_person_folder(folder.name)
            except ValueError as error:
                print(f"[训练] 跳过目录: {error}")
                continue

        image_paths = sorted(folder.glob("*.jpg"))
        if not image_paths:
            print(f"[训练] 跳过空目录: {folder}")
            continue

        valid_count = 0

        for image_path in image_paths:
            face = cv2.imread(str(image_path), cv2.IMREAD_GRAYSCALE)

            if face is None:
                print(f"[训练] 无法读取，跳过: {image_path}")
                continue

            normalized = normalize_face(
                face,
                (args.face_width, args.face_height),
            )

            face_images.append(normalized)
            numeric_labels.append(next_model_label)
            valid_count += 1

        if valid_count == 0:
            continue

        label_mapping[str(next_model_label)] = {
            "person_id": person_id,
            "name": name,
            "folder": folder.name,
            "sample_count": str(valid_count),
        }

        print(
            f"[训练] label={next_model_label}, "
            f"id={person_id}, name={name}, samples={valid_count}"
        )

        next_model_label += 1

    if not face_images:
        raise RuntimeError("没有可用于训练的有效人脸图像。")

    labels_array = np.asarray(numeric_labels, dtype=np.int32)

    print(
        f"[训练] 开始训练：人员数={len(label_mapping)}, "
        f"样本数={len(face_images)}"
    )

    recognizer.train(face_images, labels_array)

    model_path = trainer_dir / "lbph_model.yml"
    labels_path = trainer_dir / "labels.json"

    recognizer.write(str(model_path))

    labels_payload = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "face_size": [args.face_width, args.face_height],
        "labels": label_mapping,
    }

    with labels_path.open("w", encoding="utf-8") as file:
        json.dump(labels_payload, file, ensure_ascii=False, indent=2)

    print(f"[训练] 模型已保存: {model_path}")
    print(f"[训练] 标签映射已保存: {labels_path}")


# ---------------------------------------------------------------------------
# 七、识别与检录
# ---------------------------------------------------------------------------

def load_trained_model(
    work_dir: str,
) -> Tuple[object, Dict[int, PersonInfo], Tuple[int, int]]:
    """加载 LBPH 模型、标签映射和训练时的人脸尺寸。"""
    trainer_dir = Path(work_dir) / "trainer"
    model_path = trainer_dir / "lbph_model.yml"
    labels_path = trainer_dir / "labels.json"

    if not model_path.is_file() or not labels_path.is_file():
        raise RuntimeError(
            "没有找到训练模型。\n"
            f"应存在：{model_path}\n"
            f"以及：{labels_path}\n"
            "请先运行 --mode train。"
        )

    recognizer = create_lbph_recognizer()
    recognizer.read(str(model_path))

    with labels_path.open("r", encoding="utf-8") as file:
        payload = json.load(file)

    face_size_value = payload.get(
        "face_size",
        [DEFAULT_FACE_WIDTH, DEFAULT_FACE_HEIGHT],
    )
    face_size = (
        int(face_size_value[0]),
        int(face_size_value[1]),
    )

    people: Dict[int, PersonInfo] = {}

    for label_text, info in payload.get("labels", {}).items():
        label = int(label_text)
        people[label] = PersonInfo(
            model_label=label,
            person_id=str(info["person_id"]),
            name=str(info["name"]),
            folder=str(info["folder"]),
        )

    if not people:
        raise RuntimeError(f"标签映射为空: {labels_path}")

    print(f"[识别] 模型: {model_path}")
    print(f"[识别] 已登记人员数: {len(people)}")
    return recognizer, people, face_size


def read_checked_in_ids(record_path: Path) -> set[str]:
    """
    读取当天 CSV 中已经检录的人员编号。

    脚本重新启动后仍然不会重复登记同一个人。
    """
    checked_in: set[str] = set()

    if not record_path.is_file():
        return checked_in

    with record_path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        for row in reader:
            person_id = row.get("person_id")
            if person_id:
                checked_in.add(person_id)

    return checked_in


def append_checkin_record(
    record_path: Path,
    person: PersonInfo,
    confidence: float,
) -> bool:
    """
    把一条检录记录追加到 CSV。

    返回：
        True  表示成功写入；
        False 表示该人员今天已经存在，未重复写入。
    """
    checked_in_ids = read_checked_in_ids(record_path)

    if person.person_id in checked_in_ids:
        return False

    ensure_directory(record_path.parent)
    file_exists = record_path.is_file()

    now = datetime.now()

    with record_path.open("a", encoding="utf-8-sig", newline="") as file:
        fieldnames = [
            "date",
            "time",
            "person_id",
            "name",
            "confidence",
        ]
        writer = csv.DictWriter(file, fieldnames=fieldnames)

        if not file_exists:
            writer.writeheader()

        writer.writerow(
            {
                "date": now.strftime("%Y-%m-%d"),
                "time": now.strftime("%H:%M:%S"),
                "person_id": person.person_id,
                "name": person.name,
                "confidence": f"{confidence:.2f}",
            }
        )

    return True


class StableIdentityCounter:
    """
    连续识别稳定器。

    仅凭一帧就检录容易误判。
    因此要求同一个 label 连续出现 stable_hits 次后才确认身份。

    当前实现按“本轮所有人脸中最可信的已知身份”更新。
    对单人依次站到检录摄像头前的使用方式最合适。
    """

    def __init__(self, stable_hits: int) -> None:
        self.stable_hits = max(1, int(stable_hits))
        self.current_label: Optional[int] = None
        self.hit_count = 0

    def update(self, label: Optional[int]) -> Tuple[Optional[int], int, bool]:
        """
        返回：
            当前候选标签；
            连续命中次数；
            是否刚刚达到稳定阈值。
        """
        if label is None:
            self.current_label = None
            self.hit_count = 0
            return None, 0, False

        if label == self.current_label:
            self.hit_count += 1
        else:
            self.current_label = label
            self.hit_count = 1

        confirmed = self.hit_count == self.stable_hits
        return self.current_label, self.hit_count, confirmed


def recognize_and_checkin(
    args: argparse.Namespace,
    detector: cv2.CascadeClassifier,
    calibration: Optional[CameraCalibration],
) -> None:
    """
    实时识别人脸并自动检录。

    对每一帧：
        1. 读取最新帧；
        2. 单目去畸变；
        3. Haar 检测人脸；
        4. 每张人脸送入 LBPH；
        5. confidence 小于阈值 -> 已知人员；
        6. 同一身份连续命中多次 -> 写入 CSV。
    """
    recognizer, people, trained_face_size = load_trained_model(args.work_dir)

    records_dir = Path(args.work_dir) / "records"
    ensure_directory(records_dir)

    today_text = datetime.now().strftime("%Y%m%d")
    record_path = records_dir / f"checkin_{today_text}.csv"

    checked_in_ids = read_checked_in_ids(record_path)
    stable_counter = StableIdentityCounter(args.stable_hits)

    print(f"[检录] 当天记录文件: {record_path}")
    print(f"[检录] 启动前已检录人数: {len(checked_in_ids)}")
    print(
        f"[检录] 识别阈值: {args.recognition_threshold:.1f} "
        "(LBPH 数值越小越相似)"
    )

    camera = LatestFrameCamera(
        args.device,
        args.width,
        args.height,
        args.fps,
    ).start()

    if not camera.wait_first_frame():
        camera.stop()
        raise RuntimeError("等待摄像头第一帧超时。")

    last_frame_index = -1
    window_name = "Face Check-in - q/ESC to quit"
    fps_value = 0.0
    fps_last_time: Optional[float] = None
    status_message = "Ready"
    status_expire_time = 0.0

    try:
        while True:
            frame_index, frame, _ = camera.get_latest()

            if frame is None or frame_index == last_frame_index:
                time.sleep(0.002)
                continue

            last_frame_index = frame_index

            now_perf = time.perf_counter()
            if fps_last_time is not None:
                delta = now_perf - fps_last_time
                if delta > 1e-6:
                    instant_fps = 1.0 / delta
                    fps_value = (
                        instant_fps
                        if fps_value <= 1e-6
                        else 0.9 * fps_value + 0.1 * instant_fps
                    )
            fps_last_time = now_perf

            frame = apply_undistort(frame, calibration)
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            gray_for_detection = cv2.equalizeHist(gray)

            faces = detect_faces(
                detector,
                gray_for_detection,
                args.min_face_size,
            )

            # 保存本帧最可信的已知身份。
            # LBPH confidence 越小越可信，因此找最小值。
            best_known_label: Optional[int] = None
            best_known_confidence = float("inf")

            for x, y, width, height in faces:
                face_roi = gray[y : y + height, x : x + width]

                if face_roi.size == 0:
                    continue

                normalized = normalize_face(
                    face_roi,
                    trained_face_size,
                )

                predicted_label, confidence = recognizer.predict(normalized)
                confidence = float(confidence)

                person = people.get(int(predicted_label))
                is_known = (
                    person is not None
                    and confidence <= args.recognition_threshold
                )

                if is_known:
                    display_name = f"{person.person_id} {person.name}"
                    box_thickness = 3

                    if confidence < best_known_confidence:
                        best_known_confidence = confidence
                        best_known_label = int(predicted_label)
                else:
                    display_name = "UNKNOWN"
                    box_thickness = 2

                cv2.rectangle(
                    frame,
                    (x, y),
                    (x + width, y + height),
                    (255, 255, 255),
                    box_thickness,
                )

                # 标签放在人脸框上方；空间不足时放到框内。
                label_y = y - 10 if y > 30 else y + 25
                draw_text(
                    frame,
                    f"{display_name}  score={confidence:.1f}",
                    (x, label_y),
                    scale=0.65,
                    thickness=2,
                )

            candidate_label, hit_count, confirmed = stable_counter.update(
                best_known_label
            )

            if confirmed and candidate_label is not None:
                person = people[candidate_label]

                was_written = append_checkin_record(
                    record_path,
                    person,
                    best_known_confidence,
                )

                if was_written:
                    checked_in_ids.add(person.person_id)
                    status_message = (
                        f"CHECKED IN: {person.person_id} {person.name}"
                    )
                    print(
                        f"[检录成功] id={person.person_id}, "
                        f"name={person.name}, "
                        f"confidence={best_known_confidence:.2f}"
                    )
                else:
                    status_message = (
                        f"ALREADY CHECKED IN: {person.person_id}"
                    )

                status_expire_time = time.time() + 3.0

            if time.time() > status_expire_time:
                status_message = "Ready"

            candidate_text = "None"
            if candidate_label is not None and candidate_label in people:
                candidate_person = people[candidate_label]
                candidate_text = (
                    f"{candidate_person.person_id} "
                    f"{hit_count}/{args.stable_hits}"
                )

            draw_text(
                frame,
                f"FPS: {fps_value:.1f}",
                (30, 40),
            )
            draw_text(
                frame,
                f"Faces: {len(faces)}",
                (30, 75),
            )
            draw_text(
                frame,
                f"Candidate: {candidate_text}",
                (30, 110),
            )
            draw_text(
                frame,
                f"Checked in today: {len(checked_in_ids)}",
                (30, 145),
            )
            draw_text(
                frame,
                status_message,
                (30, 180),
                scale=0.75,
                thickness=2,
            )

            if args.headless:
                # headless 模式没有窗口，也没有键盘事件。
                # 通常使用 Ctrl+C 结束。
                continue

            display = resize_for_display(frame, args.display_scale)
            cv2.imshow(window_name, display)
            key = cv2.waitKey(1) & 0xFF

            if key in (ord("q"), 27):
                print("[检录] 用户退出。")
                break

    finally:
        camera.stop()
        cv2.destroyAllWindows()


# ---------------------------------------------------------------------------
# 八、命令行参数
# ---------------------------------------------------------------------------

def build_argument_parser() -> argparse.ArgumentParser:
    """创建命令行参数解析器。"""
    parser = argparse.ArgumentParser(
        description="单目摄像头篮球赛事人脸检录模块（Haar + LBPH）",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    parser.add_argument(
        "--mode",
        required=True,
        choices=[
            "enroll",
            "train",
            "recognize",
            "train-recognize",
        ],
        help=(
            "enroll=采集人员样本；"
            "train=训练模型；"
            "recognize=识别并检录；"
            "train-recognize=训练后立即识别"
        ),
    )

    # 摄像头参数与现有 camera_150 工程保持一致。
    parser.add_argument("--device", default=DEFAULT_DEVICE)
    parser.add_argument("--width", type=int, default=DEFAULT_WIDTH)
    parser.add_argument("--height", type=int, default=DEFAULT_HEIGHT)
    parser.add_argument("--fps", type=int, default=DEFAULT_FPS)

    parser.add_argument(
        "--calib-file",
        default=DEFAULT_CALIB_FILE,
        help="项目单目相机标定 npz 文件",
    )
    parser.add_argument(
        "--no-undistort",
        action="store_true",
        help="不加载标定文件，直接使用摄像头原始画面",
    )

    parser.add_argument(
        "--work-dir",
        default=DEFAULT_WORK_DIR,
        help="样本、模型和检录 CSV 的根目录",
    )
    parser.add_argument(
        "--cascade-file",
        default=None,
        help="Haar XML 文件；省略时自动搜索 OpenCV 自带文件",
    )

    # enroll 模式参数。
    parser.add_argument(
        "--person-id",
        default=None,
        help="人员唯一编号，仅 enroll 模式需要",
    )
    parser.add_argument(
        "--name",
        default=None,
        help="人员姓名，仅 enroll 模式需要",
    )
    parser.add_argument(
        "--samples",
        type=int,
        default=40,
        help="每位人员目标样本总数",
    )
    parser.add_argument(
        "--sample-interval",
        type=float,
        default=0.25,
        help="自动保存两张样本之间的最短时间，单位秒",
    )

    # 人脸检测与统一尺寸参数。
    parser.add_argument(
        "--min-face-size",
        type=int,
        default=100,
        help="忽略宽高小于该像素的人脸",
    )
    parser.add_argument(
        "--face-width",
        type=int,
        default=DEFAULT_FACE_WIDTH,
    )
    parser.add_argument(
        "--face-height",
        type=int,
        default=DEFAULT_FACE_HEIGHT,
    )

    # recognize 模式参数。
    parser.add_argument(
        "--recognition-threshold",
        type=float,
        default=68.0,
        help="LBPH 最大接受距离，越小越严格",
    )
    parser.add_argument(
        "--stable-hits",
        type=int,
        default=5,
        help="同一身份连续识别多少帧后确认检录",
    )

    parser.add_argument(
        "--display-scale",
        type=float,
        default=0.65,
        help="显示窗口缩放比例，不影响识别分辨率",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="无窗口运行；使用 Ctrl+C 结束",
    )

    return parser


def validate_arguments(args: argparse.Namespace) -> None:
    """在执行前检查容易写错的参数。"""
    if args.width <= 0 or args.height <= 0:
        raise ValueError("--width 和 --height 必须大于 0。")

    if args.fps <= 0:
        raise ValueError("--fps 必须大于 0。")

    if args.samples <= 0:
        raise ValueError("--samples 必须大于 0。")

    if args.sample_interval < 0:
        raise ValueError("--sample-interval 不能小于 0。")

    if args.min_face_size <= 0:
        raise ValueError("--min-face-size 必须大于 0。")

    if args.face_width <= 0 or args.face_height <= 0:
        raise ValueError("人脸训练尺寸必须大于 0。")

    if args.recognition_threshold <= 0:
        raise ValueError("--recognition-threshold 必须大于 0。")

    if args.stable_hits <= 0:
        raise ValueError("--stable-hits 必须大于 0。")

    if args.display_scale <= 0:
        raise ValueError("--display-scale 必须大于 0。")


# ---------------------------------------------------------------------------
# 九、程序入口
# ---------------------------------------------------------------------------

def main() -> int:
    """
    主函数只负责调度不同模式。

    将 enroll/train/recognize 分成独立函数的好处：
        - 每部分逻辑清晰；
        - 方便单独调试；
        - 后续可以把识别模块接到 Web 或技术台界面；
        - 未来替换 RKNN 模型时，不需要重写检录 CSV 逻辑。
    """
    parser = build_argument_parser()
    args = parser.parse_args()
    validate_arguments(args)

    print("=" * 72)
    print("篮球赛事人脸检录模块")
    print(f"mode      : {args.mode}")
    print(f"work_dir  : {Path(args.work_dir).resolve()}")
    print("=" * 72)

    # train 模式只读取磁盘样本，不需要打开摄像头和 Haar 检测器。
    if args.mode == "train":
        train_model(args)
        return 0

    if args.mode == "train-recognize":
        train_model(args)

    detector = load_face_detector(args.cascade_file)

    calib_file = None if args.no_undistort else args.calib_file
    calibration = load_camera_calibration(calib_file)

    if args.mode == "enroll":
        enroll_person(args, detector, calibration)
        return 0

    if args.mode in ("recognize", "train-recognize"):
        recognize_and_checkin(args, detector, calibration)
        return 0

    raise RuntimeError(f"未处理的模式: {args.mode}")


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\n[退出] 收到 Ctrl+C。")
        raise SystemExit(0)
    except Exception as error:
        print(f"\n[错误] {error}", file=sys.stderr)
        raise SystemExit(1)
