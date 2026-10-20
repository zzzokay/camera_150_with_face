"""
文件作用：定义 G0/G1 的视频帧与真实 YOLO 观测，不是 G3 轨迹导出格式。
输入/输出：BGR uint8 图像、全幅像素框、秒为单位的时间戳。
依赖：dataclasses、NumPy；被 sources / detector / director_adapter 调用。
运行示例：见 NEWCOMER_HANDOFF.md；原人物规则只接收 person，球接口默认关闭。
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
