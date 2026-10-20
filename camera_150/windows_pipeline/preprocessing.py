"""
文件作用：显式控制镜头去畸变，拒绝静默缩放或重复矫正。
输入：完整 BGR 帧、模式、可选原 NPZ；输出：同尺寸完整帧及坐标空间名称。
依赖：OpenCV、原 load_single_camera_calib；调用关系：run -> FramePreprocessor。
注意：镜头去畸变不是球场 Homography，G0 不输出球场米制坐标。
运行示例：见 NEWCOMER_HANDOFF.md。
"""
from pathlib import Path

import cv2

from camera_150.camera_movement_modified.single_rknn_base import load_single_camera_calib


class FramePreprocessor:
    """none 保留原图；already 按用户声明标记已矫正；calibration 执行原 remap。"""

    def __init__(self, mode: str, calib_file: Path | None = None):
        if mode not in ("none", "already", "calibration"):
            raise ValueError(f"未知去畸变模式：{mode}")
        if (mode == "calibration") != (calib_file is not None):
            raise ValueError("calibration 模式必须且只能提供对应 NPZ")
        self.mode = mode
        self.calib = load_single_camera_calib(str(calib_file)) if calib_file else None
        self.coord_system = "raw_full_frame_px" if mode == "none" else "undistorted_full_frame_px"

    def apply(self, frame):
        """处理一帧；NPZ 宽高不匹配时抛 ValueError，防止改变原坐标空间。"""
        if self.calib is None:
            return frame
        actual = (frame.shape[1], frame.shape[0])
        if actual != self.calib.image_size:
            raise ValueError(f"帧尺寸 {actual} 与标定 {self.calib.image_size} 不同；请使用同分辨率标定")
        return cv2.remap(frame, self.calib.map1, self.calib.map2,
                         interpolation=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT)
