#!/usr/bin/env python3

# -*- coding: utf-8 -*-

"""
face_checkin_lbph_stable.py
===========================

单目摄像头篮球赛事人脸检录模块。

本脚本用于完成参赛人员的人脸信息登记、识别模型训练、实时身份识别
以及检录结果记录，可作为篮球赛事自动转播系统中的赛前检录模块。


主要功能：
1. 采集参赛人员的人脸样本；
2. 对采集画面进行单目畸变矫正；
3. 对人脸样本进行清晰度、亮度和稳定性检查；
4. 使用 LBPH 算法训练本地人脸识别模型；
5. 实时识别已经登记的参赛人员；
6. 使用连续多帧确认方式降低单帧误识别；
7. 自动生成当天的 CSV 检录记录；
8. 同一人员当天默认只记录一次。

## 目录结构

脚本默认在工程根目录下创建 face_checkin 目录：

face_checkin/
├── dataset/                           # 已登记人员的人脸样本
│   ├── 001__player_001/
│   │   ├── 0001.jpg
│   │   ├── 0002.jpg
│   │   └── ...
│   └── 002__player_002/
│       ├── 0001.jpg
│       └── ...
│
├── trainer/                           # 训练结果
│   ├── lbph_model.yml                 # LBPH 人脸识别模型
│   └── labels.json                    # 模型标签与人员信息映射
│
└── records/                           # 检录记录
└── checkin_20260719.csv            # 当天检录结果

人员样本目录采用以下命名格式：

```
人员编号__人员姓名
```

例如：

```
001__player_001
002__player_002
```

其中：

```
人员编号用于保证每位人员身份唯一；
人员姓名用于显示和写入检录记录。
```

## 运行环境说明

原篮球导播工程依赖现有 OpenCV、RKNNLite、Qt 和其他系统组件。

为避免重新安装 OpenCV 后破坏现有导播环境，建议为人脸检录模块单独创建
Python 虚拟环境。

一、创建人脸识别虚拟环境

```
cd /home/elf/work/camera_150

python3 -m venv --system-site-packages face_env
```

二、只在人脸识别环境中安装 OpenCV contrib

```
./face_env/bin/python -m pip install --upgrade pip

./face_env/bin/python -m pip install \
  --ignore-installed \
  --no-deps \
  opencv-contrib-python==4.10.0.84
```

cv2.face 位于 OpenCV contrib 扩展模块中，因此普通的 opencv-python
不一定包含 LBPHFaceRecognizer。

三、检查 LBPH 是否可用

```
./face_env/bin/python - <<'PY'
import cv2

print("OpenCV version:", cv2.__version__)
print("OpenCV path:", cv2.__file__)
print("has cv2.face:", hasattr(cv2, "face"))

if hasattr(cv2, "face"):
    print([name for name in dir(cv2.face) if "LBPH" in name])
PY
```

正常情况下，应能看到：

```
LBPHFaceRecognizer
LBPHFaceRecognizer_create
```

## 典型运行方法

一、采集一名球员的人脸

推荐使用稳定采集和手动确认模式：

```
cd /home/elf/work/camera_150

./face_env/bin/python face_checkin_lbph_stable.py \
  --mode enroll \
  --person-id 001 \
  --name player_001 \
  --device /dev/video41 \
  --calib-file camera_usb3_calib.npz \
  --samples 30 \
  --manual-capture \
  --min-face-size 180 \
  --enroll-min-neighbors 10 \
  --enroll-stable-frames 8 \
  --min-sharpness 100 \
  --min-eyes 1
```

采集时建议：

```
- 画面中只保留一名待登记人员；
- 人脸放在画面中央的引导区域内；
- 保持正面或轻微左右转头；
- 避免快速晃动；
- 避免强烈逆光；
- 确认画面清晰后按 c 保存；
- 按 q 或 Esc 提前退出；
- 达到 --samples 指定数量后自动结束。
```

推荐每位人员采集 25～35 张高质量样本。

样本可以包含：

```
- 正脸；
- 轻微向左；
- 轻微向右；
- 轻微抬头；
- 轻微低头；
- 少量不同表情。
```

不建议采集大角度侧脸，因为当前使用的是正面 Haar 人脸检测模型。

二、训练人脸识别模型

采集完所有人员后执行：

```
./face_env/bin/python face_checkin_lbph_stable.py \
  --mode train
```

训练完成后会生成：

```
face_checkin/trainer/lbph_model.yml
face_checkin/trainer/labels.json
```

每次新增人员、删除错误样本或重新采集样本后，都需要重新执行训练。

三、实时识别并检录

```
./face_env/bin/python face_checkin_lbph_stable.py \
  --mode recognize \
  --device /dev/video41 \
  --calib-file camera_usb3_calib.npz
```

识别过程中：

```
1. Haar Cascade 检测人脸；
2. LBPH 判断当前人员身份；
3. 同一身份连续识别达到 --stable-hits 次；
4. 将人员编号、姓名、时间和匹配距离写入当天 CSV；
5. 同一人员当天不会重复写入。
```

四、训练完成后立即进入识别

```
./face_env/bin/python face_checkin_lbph_stable.py \
  --mode train-recognize \
  --device /dev/video41 \
  --calib-file camera_usb3_calib.npz
```

## 常用参数

1. 人脸识别阈值

   --recognition-threshold 68

LBPH 的匹配距离越小，表示越相似。

```
阈值减小：
    判断更加严格，误识别减少，但可能出现更多 UNKNOWN。

阈值增大：
    更容易识别成功，但误识别概率也会增加。
```

建议先在 55～75 范围内测试。

2. 连续确认帧数

   --stable-hits 5

表示同一个身份需要连续识别 5 帧，才正式写入检录记录。

增大该参数可以降低偶发误识别，但会增加确认时间。

3. 最小人脸尺寸

   --min-face-size 180

用于忽略画面中尺寸过小的人脸。

人脸太小会导致五官纹理不足，不适合进行可靠识别。

4. Haar 检测严格程度

   --enroll-min-neighbors 10

数值越大，人脸检测越严格，误检越少，但也可能增加漏检。

5. 人脸稳定帧数

   --enroll-stable-frames 8

表示人脸框需要连续稳定 8 帧，才允许保存。

6. 清晰度阈值

   --min-sharpness 100

清晰度不足时，脚本不会保存当前人脸。

如果画面肉眼清晰但始终提示模糊，可以适当降低到：

```
--min-sharpness 60
```

7. 眼睛验证

```
--min-eyes 1
```

表示人脸区域中至少需要检测到一只眼睛。

眼睛验证可以明显减少非人脸区域被错误保存。

戴眼镜或轻微侧脸时，如果一直无法通过，可以临时设置：

```
--min-eyes 0
```

关闭眼睛验证后，建议必须配合：

```
--manual-capture
```

8. 禁用单目畸变矫正

```
--no-undistort
```

只有在校准文件不存在，或者摄像头分辨率与标定分辨率不一致时使用。

## 重要说明

1. 人脸样本质量比样本数量更加重要。

   30 张清晰、正确、角度有变化的人脸样本，通常比 100 张包含误检、
   模糊或重复画面的样本效果更好。

2. 训练前应人工检查 dataset 目录。

   确保所有 JPG 文件都是真实人脸，不包含：

   ```
   - 墙面；
   - 衣服图案；
   - 其他人员；
   - 严重模糊画面；
   - 五官被大量裁切的画面。
   ```

3. 当前脚本中的中文姓名会正常写入 labels.json 和 CSV。

   但 cv2.putText 默认不支持中文，因此实时画面中的中文姓名可能无法正确显示。
   如需正确显示中文，可后续使用 Pillow 或 Qt 绘制文字。

4. 人脸样本、识别模型和检录记录均保存在本地，不会主动上传网络。

5. 实际赛事使用前，应取得被采集人员的明确同意，并限制人脸数据目录的
   访问权限。

6. 检录脚本与篮球导播脚本默认使用同一个摄像头节点：

   ```
   /dev/video41
   ```

   两个程序不建议同时打开同一个摄像头。

   当前推荐流程为：

   ```
   完成人脸检录
       ↓
   退出人脸检录程序
       ↓
   启动篮球赛事自动导播程序
   ```

"""


from __future__ import annotations

import argparse
import csv
import json
import os
import re
import select
import sys
import termios
import threading
import time
import tty
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# RK3588 上禁用 OpenCV OpenCL，避免某些 Mali/OpenCL 环境产生额外开销或异常。
# 这项环境变量必须尽量在 import cv2 之前设置。
os.environ.setdefault("OPENCV_OPENCL_RUNTIME", "disabled")

# RK3588 上 OpenCV QT5 后端需要正确的插件路径，否则窗口事件可能异常。
os.environ.setdefault(
    "QT_QPA_PLATFORM_PLUGIN_PATH",
    "/usr/lib/aarch64-linux-gnu/qt5/plugins/platforms",
)

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


class TerminalKeyReader:
    """
    终端按键读取器（非阻塞模式）。

    背景：
        在 Linux / RK3588 环境下，OpenCV QT5 图像窗口可能无法正确获取键盘焦点，
        导致 cv2.waitKey() 读不到按键。此时用户按下的字符会直接进入终端。

    解决方案：
        将终端设置为 cbreak 模式，配合 select() 做非阻塞读取。
        这样终端按键和 OpenCV 窗口按键都会被检查，确保按键一定被捕获。

    用法：
        with TerminalKeyReader() as key_reader:
            while True:
                key = key_reader.read_key()
                if key == 'q':
                    break
    """

    def __init__(self):
        self.enabled = False
        self.old_settings = None

    def __enter__(self):
        if sys.stdin.isatty():
            self.enabled = True
            self.old_settings = termios.tcgetattr(sys.stdin)
            tty.setcbreak(sys.stdin.fileno())
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.enabled and self.old_settings is not None:
            termios.tcsetattr(
                sys.stdin,
                termios.TCSADRAIN,
                self.old_settings,
            )

    def read_key(self):
        """非阻塞读取一个终端按键，没有按键时返回 None。"""
        if not self.enabled:
            return None

        readable, _, _ = select.select([sys.stdin], [], [], 0)
        if readable:
            return sys.stdin.read(1)
        return None


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
    创建 OpenCV LBPH 人脸识别器，并兼容不同 OpenCV Python 绑定形式。

    不同 OpenCV 构建版本可能把同一个 C++ 接口导出为不同 Python 名称：

        形式 1：
            cv2.face.LBPHFaceRecognizer_create(...)

        形式 2：
            cv2.face.LBPHFaceRecognizer.create(...)

        少数旧版本还可能导出为：
            cv2.face_LBPHFaceRecognizer.create(...)
            cv2.face_LBPHFaceRecognizer_create(...)

    因此不能只判断一种名称。这里按常见程度逐个尝试。
    创建参数全部使用位置参数，以减少旧版 Python 绑定不接受关键字参数的问题。
    """
    radius = 1
    neighbors = 8
    grid_x = 8
    grid_y = 8

    if hasattr(cv2, "face") and hasattr(cv2.face, "LBPHFaceRecognizer_create"):
        print("[LBPH] 使用接口: cv2.face.LBPHFaceRecognizer_create")
        return cv2.face.LBPHFaceRecognizer_create(
            radius,
            neighbors,
            grid_x,
            grid_y,
        )

    if hasattr(cv2, "face") and hasattr(cv2.face, "LBPHFaceRecognizer"):
        lbph_class = cv2.face.LBPHFaceRecognizer
        if hasattr(lbph_class, "create"):
            print("[LBPH] 使用接口: cv2.face.LBPHFaceRecognizer.create")
            return lbph_class.create(
                radius,
                neighbors,
                grid_x,
                grid_y,
            )

    if hasattr(cv2, "face_LBPHFaceRecognizer"):
        lbph_class = cv2.face_LBPHFaceRecognizer
        if hasattr(lbph_class, "create"):
            print("[LBPH] 使用接口: cv2.face_LBPHFaceRecognizer.create")
            return lbph_class.create(
                radius,
                neighbors,
                grid_x,
                grid_y,
            )

    if hasattr(cv2, "face_LBPHFaceRecognizer_create"):
        print("[LBPH] 使用接口: cv2.face_LBPHFaceRecognizer_create")
        return cv2.face_LBPHFaceRecognizer_create(
            radius,
            neighbors,
            grid_x,
            grid_y,
        )

    face_members = []
    if hasattr(cv2, "face"):
        face_members = [
            name for name in dir(cv2.face)
            if "LBPH" in name or "FaceRecognizer" in name
        ]

    root_members = [
        name for name in dir(cv2)
        if "LBPH" in name or "FaceRecognizer" in name
    ]

    raise RuntimeError(
        "当前 OpenCV 没有可用的 LBPHFaceRecognizer Python 接口。\n"
        f"OpenCV 版本: {cv2.__version__}\n"
        f"cv2.face 相关成员: {face_members}\n"
        f"cv2 顶层相关成员: {root_members}\n"
        "这通常表示当前 OpenCV 没有完整编译 opencv_contrib 的 face 模块，"
        "或者系统中存在多个 cv2 包冲突。"
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
    scale_factor: float = 1.1,
    min_neighbors: int = 5,
    max_face_size: int = 0,
) -> List[Tuple[int, int, int, int]]:
    """
    在灰度图中检测人脸。

    参数说明：
        scale_factor：
            图像金字塔每层的缩放比例。越接近 1.0，搜索越细致但越慢。

        min_neighbors：
            一个候选框需要获得多少相邻检测支持。数值越大，误检通常越少，
            但过大也会漏检。登记模式默认使用比识别模式更严格的数值。

        min_face_size / max_face_size：
            过滤过小或异常巨大的候选框。
    """
    kwargs = {
        "scaleFactor": float(scale_factor),
        "minNeighbors": int(min_neighbors),
        "flags": cv2.CASCADE_SCALE_IMAGE,
        "minSize": (int(min_face_size), int(min_face_size)),
    }

    if max_face_size > 0:
        kwargs["maxSize"] = (int(max_face_size), int(max_face_size))

    faces = detector.detectMultiScale(gray, **kwargs)
    result = [tuple(int(v) for v in face) for face in faces]
    result.sort(key=lambda item: item[2] * item[3], reverse=True)
    return result


def bbox_iou(
    first: Tuple[int, int, int, int],
    second: Tuple[int, int, int, int],
) -> float:
    """计算两个 x/y/width/height 矩形框的交并比。"""
    ax1, ay1, aw, ah = first
    bx1, by1, bw, bh = second
    ax2, ay2 = ax1 + aw, ay1 + ah
    bx2, by2 = bx1 + bw, by1 + bh

    ix1 = max(ax1, bx1)
    iy1 = max(ay1, by1)
    ix2 = min(ax2, bx2)
    iy2 = min(ay2, by2)

    intersection = max(0, ix2 - ix1) * max(0, iy2 - iy1)
    union = aw * ah + bw * bh - intersection
    return float(intersection / union) if union > 0 else 0.0


def find_optional_eye_cascade() -> Optional[Path]:
    """
    查找 OpenCV 自带的眼睛 Haar 模型。

    眼睛检测不是用来识别身份，而是用于验证“这个候选框更像真人脸”，
    从而过滤墙面纹理、衣服图案等 Haar 人脸误检。
    """
    candidates: List[Path] = []

    if hasattr(cv2, "data") and hasattr(cv2.data, "haarcascades"):
        base = Path(cv2.data.haarcascades)
        candidates.extend(
            [
                base / "haarcascade_eye_tree_eyeglasses.xml",
                base / "haarcascade_eye.xml",
            ]
        )

    for system_base in (
        Path("/usr/share/opencv4/haarcascades"),
        Path("/usr/share/opencv/haarcascades"),
    ):
        candidates.extend(
            [
                system_base / "haarcascade_eye_tree_eyeglasses.xml",
                system_base / "haarcascade_eye.xml",
            ]
        )

    for path in candidates:
        if path.is_file():
            return path

    return None


def load_optional_eye_detector() -> Optional[cv2.CascadeClassifier]:
    """加载眼睛检测器；找不到时返回 None，不影响脚本启动。"""
    path = find_optional_eye_cascade()
    if path is None:
        print("[样本质量] 未找到眼睛 Haar 模型，将跳过眼睛验证。")
        return None

    detector = cv2.CascadeClassifier(str(path))
    if detector.empty():
        print(f"[样本质量] 眼睛 Haar 模型加载失败，将跳过: {path}")
        return None

    print(f"[样本质量] 眼睛 Haar 模型: {path}")
    return detector


def count_detected_eyes(
    eye_detector: Optional[cv2.CascadeClassifier],
    face_gray: np.ndarray,
) -> int:
    """只在脸部上半区域搜索眼睛，降低鼻孔、嘴角等位置的误检。"""
    if eye_detector is None or face_gray.size == 0:
        return 0

    face_height, face_width = face_gray.shape[:2]
    upper_face = face_gray[: max(1, int(face_height * 0.68)), :]
    minimum_eye = max(12, int(min(face_width, face_height) * 0.10))

    eyes = eye_detector.detectMultiScale(
        upper_face,
        scaleFactor=1.1,
        minNeighbors=6,
        flags=cv2.CASCADE_SCALE_IMAGE,
        minSize=(minimum_eye, minimum_eye),
    )
    return int(len(eyes))


def compute_face_quality(face_gray: np.ndarray) -> Tuple[float, float]:
    """
    返回人脸图像的亮度和清晰度。

    brightness：灰度均值，过低表示太暗，过高表示过曝。
    sharpness：Laplacian 方差，越大通常表示边缘越清楚。
    """
    brightness = float(np.mean(face_gray))
    sharpness = float(cv2.Laplacian(face_gray, cv2.CV_64F).var())
    return brightness, sharpness


def mean_face_difference(first: np.ndarray, second: np.ndarray) -> float:
    """计算两张同尺寸灰度人脸的平均绝对像素差，用于过滤近乎重复样本。"""
    difference = cv2.absdiff(first, second)
    return float(np.mean(difference))

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
    采集一位人员的人脸样本，并在保存前执行多级质量筛选。

    与旧版“检测到框就保存”相比，新版必须依次满足：
        1. 人脸位于画面中央的登记区域；
        2. 登记区域中只能检测到一张脸；
        3. 人脸尺寸和长宽比合理；
        4. 亮度和清晰度达标；
        5. 人脸中检测到规定数量的眼睛；
        6. 检测框连续若干帧保持稳定；
        7. 与上一张已保存样本不能过于相似。

    这些门槛会降低采集速度，但能显著减少非人脸、模糊帧和重复帧进入训练集。
    """
    if not args.person_id or not args.name:
        raise ValueError("enroll 模式必须同时提供 --person-id 和 --name。")

    dataset_dir = Path(args.work_dir) / "dataset"
    ensure_directory(dataset_dir)

    safe_id = sanitize_path_component(args.person_id)
    safe_name = sanitize_path_component(args.name)
    person_folder = dataset_dir / f"{safe_id}__{safe_name}"
    ensure_directory(person_folder)

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

    # 若目录已有样本，读取最后一张作为“重复样本比较”的参考。
    last_saved_face: Optional[np.ndarray] = None
    if existing_samples:
        last_saved_face = cv2.imread(str(existing_samples[-1]), cv2.IMREAD_GRAYSCALE)

    print(f"[登记] 人员编号: {args.person_id}")
    print(f"[登记] 姓名: {args.name}")
    print(f"[登记] 样本目录: {person_folder}")
    print(f"[登记] 已有样本: {sample_count}")
    print(f"[登记] 目标样本总数: {args.samples}")
    print(
        f"[登记] 稳定门槛: {args.enroll_stable_frames} 帧, "
        f"IoU >= {args.enroll_stable_iou:.2f}"
    )
    print(
        f"[登记] 质量门槛: sharpness >= {args.min_sharpness:.1f}, "
        f"brightness={args.min_brightness:.0f}~{args.max_brightness:.0f}, "
        f"eyes >= {args.min_eyes}"
    )
    if args.manual_capture:
        print("[登记] 手动保存模式：画面显示 READY 后按 c 保存。")
    else:
        print("[登记] 自动保存模式：满足全部门槛后自动保存。")

    eye_detector = load_optional_eye_detector()

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
    previous_valid_box: Optional[Tuple[int, int, int, int]] = None
    stable_frame_count = 0
    manual_capture_requested = False
    window_name = "Face Enrollment Stable - c capture, q quit"

    try:
        # 终端按键读取器：解决 OpenCV QT5 窗口可能无法获取焦点的问题。
        # 终端按键和窗口按键都会被检查，确保 q/c 一定被捕获。
        term_key_reader = TerminalKeyReader()
        term_key_reader.__enter__()

        while sample_count < args.samples:
            frame_index, frame, _ = camera.get_latest()

            if frame is None or frame_index == last_frame_index:
                # 双通道按键检测：终端按键 + OpenCV 窗口按键
                # RK3588 QT5 后端可能无法获取窗口焦点，所以必须同时读终端
                cv_key = cv2.waitKey(10) & 0xFF
                term_key = term_key_reader.read_key()

                if term_key in ("q", "Q") or cv_key in (ord("q"), 27):
                    print("[登记] 用户提前结束采集。")
                    break
                if term_key in ("c", "C") or cv_key == ord("c"):
                    manual_capture_requested = True
                    print("[登记] 已收到手动保存请求，等待人脸满足全部门槛。")
                continue

            last_frame_index = frame_index
            frame = apply_undistort(frame, calibration)

            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            gray_for_detection = cv2.equalizeHist(gray)
            frame_height, frame_width = gray.shape[:2]

            # 只在画面中央区域做人脸检测。
            # 登记人员应把脸移入该框，这会直接排除大部分背景误检。
            region_width = int(frame_width * args.enroll_region_width_ratio)
            region_height = int(frame_height * args.enroll_region_height_ratio)
            region_x1 = max(0, (frame_width - region_width) // 2)
            region_y1 = max(0, (frame_height - region_height) // 2)
            region_x2 = min(frame_width, region_x1 + region_width)
            region_y2 = min(frame_height, region_y1 + region_height)

            cv2.rectangle(
                frame,
                (region_x1, region_y1),
                (region_x2, region_y2),
                (255, 255, 255),
                2,
            )

            detection_roi = gray_for_detection[
                region_y1:region_y2,
                region_x1:region_x2,
            ]

            local_faces = detect_faces(
                detector,
                detection_roi,
                args.min_face_size,
                scale_factor=args.enroll_scale_factor,
                min_neighbors=args.enroll_min_neighbors,
                max_face_size=args.max_face_size,
            )

            # 把登记区域局部坐标还原到整帧坐标。
            faces = [
                (x + region_x1, y + region_y1, width, height)
                for x, y, width, height in local_faces
            ]

            now = time.time()
            status_text = "Move face into guide"
            detail_text = ""
            valid_box: Optional[Tuple[int, int, int, int]] = None
            normalized_face: Optional[np.ndarray] = None
            brightness = 0.0
            sharpness = 0.0
            eye_count = 0

            if len(faces) == 0:
                status_text = "NO FACE"
            elif len(faces) > 1:
                status_text = "MULTIPLE FACES"
            else:
                x, y, width, height = faces[0]
                valid_box = (x, y, width, height)

                cv2.rectangle(
                    frame,
                    (x, y),
                    (x + width, y + height),
                    (255, 255, 255),
                    3,
                )

                face_area_ratio = (width * height) / float(frame_width * frame_height)
                aspect_ratio = width / float(max(height, 1))
                face_roi = gray[y:y + height, x:x + width]

                if not (args.min_face_area_ratio <= face_area_ratio <= args.max_face_area_ratio):
                    status_text = "FACE SIZE INVALID"
                    valid_box = None
                elif not (args.min_face_aspect <= aspect_ratio <= args.max_face_aspect):
                    status_text = "FACE SHAPE INVALID"
                    valid_box = None
                elif face_roi.size == 0:
                    status_text = "EMPTY FACE ROI"
                    valid_box = None
                else:
                    brightness, sharpness = compute_face_quality(face_roi)
                    eye_count = count_detected_eyes(eye_detector, face_roi)

                    if brightness < args.min_brightness:
                        status_text = "TOO DARK"
                        valid_box = None
                    elif brightness > args.max_brightness:
                        status_text = "TOO BRIGHT"
                        valid_box = None
                    elif sharpness < args.min_sharpness:
                        status_text = "TOO BLURRY"
                        valid_box = None
                    elif eye_detector is not None and eye_count < args.min_eyes:
                        status_text = "EYES NOT CONFIRMED"
                        valid_box = None
                    else:
                        normalized_face = normalize_face(
                            face_roi,
                            (args.face_width, args.face_height),
                        )
                        status_text = "QUALITY OK"

                detail_text = (
                    f"bright={brightness:.0f} sharp={sharpness:.0f} "
                    f"eyes={eye_count}"
                )

            # 连续帧稳定判断。只要中间有一帧质量不合格，就重新累计。
            if valid_box is not None:
                if (
                    previous_valid_box is not None
                    and bbox_iou(previous_valid_box, valid_box) >= args.enroll_stable_iou
                ):
                    stable_frame_count += 1
                else:
                    stable_frame_count = 1

                previous_valid_box = valid_box
            else:
                previous_valid_box = None
                stable_frame_count = 0

            ready = (
                valid_box is not None
                and normalized_face is not None
                and stable_frame_count >= args.enroll_stable_frames
            )

            if ready:
                status_text = "READY - PRESS C" if args.manual_capture else "READY"

                enough_time = now - last_save_time >= args.sample_interval
                capture_triggered = not args.manual_capture or manual_capture_requested

                if enough_time and capture_triggered:
                    sample_difference = float("inf")
                    if last_saved_face is not None:
                        sample_difference = mean_face_difference(
                            normalized_face,
                            last_saved_face,
                        )

                    if sample_difference < args.min_sample_difference:
                        status_text = "MOVE HEAD SLIGHTLY"
                        # 手动请求保留，移动后无需再次按 c。
                    else:
                        sample_count += 1
                        sample_path = person_folder / f"{sample_count:04d}.jpg"

                        if not cv2.imwrite(str(sample_path), normalized_face):
                            raise RuntimeError(f"保存样本失败: {sample_path}")

                        last_saved_face = normalized_face.copy()
                        last_save_time = now
                        manual_capture_requested = False
                        stable_frame_count = 0
                        previous_valid_box = None
                        status_text = f"SAVED {sample_count}/{args.samples}"
                        print(
                            f"[登记] 已保存: {sample_path}, "
                            f"brightness={brightness:.1f}, "
                            f"sharpness={sharpness:.1f}, eyes={eye_count}, "
                            f"difference={sample_difference:.1f}"
                        )

            draw_text(frame, f"ID: {args.person_id}", (30, 40))
            draw_text(frame, f"Samples: {sample_count}/{args.samples}", (30, 75))
            draw_text(
                frame,
                f"Stable: {stable_frame_count}/{args.enroll_stable_frames}",
                (30, 110),
            )
            draw_text(frame, status_text, (30, 145), scale=0.75, thickness=2)
            if detail_text:
                draw_text(frame, detail_text, (30, 180), scale=0.58, thickness=1)
            draw_text(
                frame,
                "Keep one face in guide; q quit; c capture in manual mode",
                (30, 215),
                scale=0.55,
                thickness=1,
            )

            if args.headless:
                # 手动模式需要窗口按 c，因此 headless 下自动退化为自动触发。
                if args.manual_capture:
                    manual_capture_requested = True
                continue

            display = resize_for_display(frame, args.display_scale)
            cv2.imshow(window_name, display)
            cv_key = cv2.waitKey(10) & 0xFF
            term_key = term_key_reader.read_key()

            if term_key in ("q", "Q") or cv_key in (ord("q"), 27):
                print("[登记] 用户提前结束采集。")
                break
            if term_key in ("c", "C") or cv_key == ord("c"):
                manual_capture_requested = True
                print("[登记] 已收到手动保存请求，等待人脸满足全部门槛。")

    finally:
        term_key_reader.__exit__(None, None, None)
        camera.stop()
        cv2.destroyAllWindows()

    print(
        f"[登记] 完成，人员 {args.person_id} 当前共有 "
        f"{sample_count} 张有效样本。"
    )
    print("[下一步] 检查样本后执行 --mode train 重新训练模型。")


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
        # 终端按键读取器：解决 OpenCV QT5 窗口可能无法获取焦点的问题。
        term_key_reader = TerminalKeyReader()
        term_key_reader.__enter__()

        while True:
            frame_index, frame, _ = camera.get_latest()

            if frame is None or frame_index == last_frame_index:
                # 双通道按键检测：终端按键 + OpenCV 窗口按键
                cv_key = cv2.waitKey(10) & 0xFF
                term_key = term_key_reader.read_key()

                if term_key in ("q", "Q") or cv_key in (ord("q"), 27):
                    print("[检录] 用户退出。")
                    break
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
                # headless 模式下只检查终端按键（无 OpenCV 窗口）
                term_key = term_key_reader.read_key()
                if term_key in ("q", "Q"):
                    print("[检录] 用户退出。")
                    break
                continue

            display = resize_for_display(frame, args.display_scale)
            cv2.imshow(window_name, display)
            cv_key = cv2.waitKey(10) & 0xFF
            term_key = term_key_reader.read_key()

            if term_key in ("q", "Q") or cv_key in (ord("q"), 27):
                print("[检录] 用户退出。")
                break

    finally:
        term_key_reader.__exit__(None, None, None)
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

    parser.add_argument(
        "--manual-capture",
        action="store_true",
        help="满足质量和稳定门槛后，按 c 才保存；最稳但采集稍慢",
    )
    parser.add_argument(
        "--enroll-scale-factor",
        type=float,
        default=1.08,
        help="登记阶段 Haar 图像金字塔缩放比例，越接近 1 越细致但越慢",
    )
    parser.add_argument(
        "--enroll-min-neighbors",
        type=int,
        default=9,
        help="登记阶段 Haar 候选支持数，增大可降低误检",
    )
    parser.add_argument(
        "--max-face-size",
        type=int,
        default=700,
        help="登记阶段允许的人脸最大宽高像素，0 表示不限制",
    )
    parser.add_argument(
        "--enroll-stable-frames",
        type=int,
        default=6,
        help="人脸框连续稳定多少帧后才允许保存",
    )
    parser.add_argument(
        "--enroll-stable-iou",
        type=float,
        default=0.65,
        help="相邻有效人脸框达到该 IoU 才视为连续稳定",
    )
    parser.add_argument(
        "--enroll-region-width-ratio",
        type=float,
        default=0.55,
        help="登记检测区域占整帧宽度的比例",
    )
    parser.add_argument(
        "--enroll-region-height-ratio",
        type=float,
        default=0.80,
        help="登记检测区域占整帧高度的比例",
    )
    parser.add_argument(
        "--min-face-area-ratio",
        type=float,
        default=0.012,
        help="人脸框面积占整帧面积的最小比例",
    )
    parser.add_argument(
        "--max-face-area-ratio",
        type=float,
        default=0.30,
        help="人脸框面积占整帧面积的最大比例",
    )
    parser.add_argument(
        "--min-face-aspect",
        type=float,
        default=0.70,
        help="允许的人脸框最小宽高比",
    )
    parser.add_argument(
        "--max-face-aspect",
        type=float,
        default=1.35,
        help="允许的人脸框最大宽高比",
    )
    parser.add_argument(
        "--min-brightness",
        type=float,
        default=45.0,
        help="人脸灰度均值下限",
    )
    parser.add_argument(
        "--max-brightness",
        type=float,
        default=210.0,
        help="人脸灰度均值上限",
    )
    parser.add_argument(
        "--min-sharpness",
        type=float,
        default=80.0,
        help="Laplacian 方差清晰度下限",
    )
    parser.add_argument(
        "--min-eyes",
        type=int,
        default=1,
        help="至少检测到多少只眼睛；设为 0 可关闭此门槛",
    )
    parser.add_argument(
        "--min-sample-difference",
        type=float,
        default=4.0,
        help="与上一张已保存人脸的平均像素差下限，防止重复样本",
    )

    # 人脸检测与统一尺寸参数。
    parser.add_argument(
        "--min-face-size",
        type=int,
        default=140,
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

    if not 1.0 < args.enroll_scale_factor <= 2.0:
        raise ValueError("--enroll-scale-factor 必须在 (1.0, 2.0] 范围内。")

    if args.enroll_min_neighbors <= 0:
        raise ValueError("--enroll-min-neighbors 必须大于 0。")

    if args.max_face_size < 0:
        raise ValueError("--max-face-size 不能小于 0。")

    if args.enroll_stable_frames <= 0:
        raise ValueError("--enroll-stable-frames 必须大于 0。")

    if not 0.0 < args.enroll_stable_iou <= 1.0:
        raise ValueError("--enroll-stable-iou 必须在 (0, 1] 范围内。")

    if not 0.1 <= args.enroll_region_width_ratio <= 1.0:
        raise ValueError("--enroll-region-width-ratio 必须在 [0.1, 1] 范围内。")

    if not 0.1 <= args.enroll_region_height_ratio <= 1.0:
        raise ValueError("--enroll-region-height-ratio 必须在 [0.1, 1] 范围内。")

    if not 0.0 < args.min_face_area_ratio < args.max_face_area_ratio <= 1.0:
        raise ValueError("人脸面积比例参数不合法。")

    if not 0.0 < args.min_face_aspect < args.max_face_aspect:
        raise ValueError("人脸宽高比参数不合法。")

    if not 0.0 <= args.min_brightness < args.max_brightness <= 255.0:
        raise ValueError("亮度范围必须满足 0 <= min < max <= 255。")

    if args.min_sharpness < 0.0:
        raise ValueError("--min-sharpness 不能小于 0。")

    if args.min_eyes < 0:
        raise ValueError("--min-eyes 不能小于 0。")

    if args.min_sample_difference < 0.0:
        raise ValueError("--min-sample-difference 不能小于 0。")

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
