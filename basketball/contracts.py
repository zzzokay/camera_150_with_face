r"""
文件作用：定义源帧、真实检测观测的数据契约；不包含训练数据。
调用入口：根 run.py；本文件是库模块，不直接执行。
输入/输出及边界：见公开类/函数的中文说明；坐标为全幅像素、时间为源秒，ID 是临时编号。
快速测试（PowerShell，项目根目录）：.\.venv\Scripts\python.exe -X utf8 -m pytest tests/test_windows_components.py -q
预期输出：pytest 结果；日常运行结果在 configs/local.yaml 指定的输出目录。
排错：缺依赖用同一独立解释器安装 requirements-windows.lock.txt；输入/格式说明见 NEWCOMER_HANDOFF.md。
"""
from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class VideoFrame:
    """源视频一帧；索引从 0 起，timestamp_sec 为源文件时间（秒），选段不归零。"""

    image_bgr: np.ndarray
    source_frame_idx: int
    timestamp_sec: float
    timestamp_basis: str


@dataclass(frozen=True)
class Detection:
    """一次真实推理的观测；bbox_xyxy 是全幅像素，绝非导播画面或球场米制。"""

    class_name: str
    model_class_id: int
    confidence: float
    bbox_xyxy: tuple[float, float, float, float]
    coord_system: str
    observed: bool = True
