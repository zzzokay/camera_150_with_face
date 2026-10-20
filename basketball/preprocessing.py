r"""
文件作用：可选镜头去畸变；不是球场 Homography。
调用入口：根 run.py；本文件是库模块，不直接执行。
输入/输出及边界：见公开类/函数的中文说明；坐标为全幅像素、时间为源秒，ID 是临时编号。
快速测试（PowerShell，项目根目录）：.\.venv\Scripts\python.exe -X utf8 -m pytest tests/test_windows_components.py -q
预期输出：pytest 结果；日常运行结果在 configs/local.yaml 指定的输出目录。
排错：缺依赖用同一独立解释器安装 requirements-windows.lock.txt；输入/格式说明见 NEWCOMER_HANDOFF.md。
"""
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np


@dataclass(frozen=True)
class SingleCameraCalib:
    """镜头参数映射表；尺寸为完整输入像素，不是球场米制。"""
    image_size: tuple[int, int]
    map1: np.ndarray
    map2: np.ndarray


def load_single_camera_calib(path: Path) -> SingleCameraCalib:
    """提取旧 base 的单相机映射；不缩放、不做立体校正、不裁掉 NPZ 的 roi。"""
    if not path.is_file():
        raise FileNotFoundError(f'找不到镜头标定文件：{path}')
    with np.load(path, allow_pickle=False) as data:
        for key in ('camera_matrix', 'dist_coeffs', 'new_camera_matrix', 'image_size'):
            if key not in data.files:
                raise ValueError(f'标定文件缺少字段：{key}')
        flat = np.array(data['image_size']).reshape(-1)
        if flat.size < 2:
            raise ValueError('标定 image_size 至少需要宽高两个数')
        image_size = int(flat[0]), int(flat[1])
        matrix = data['camera_matrix'].astype(np.float64)
        distortion = data['dist_coeffs'].astype(np.float64)
        new_matrix = data['new_camera_matrix'].astype(np.float64)
    if min(image_size) < 2 or matrix.shape != (3, 3) or new_matrix.shape != (3, 3):
        raise ValueError('标定尺寸或相机矩阵格式无效')
    if not all(np.isfinite(v).all() for v in (matrix, distortion, new_matrix)):
        raise ValueError('标定参数必须是有限数值')
    # 保留原 loader 的 R=None、CV_16SC2 和同尺寸整图映射。
    map1, map2 = cv2.initUndistortRectifyMap(matrix, distortion, None, new_matrix, image_size, cv2.CV_16SC2)
    return SingleCameraCalib(image_size, map1, map2)


class FramePreprocessor:
    """none 保留原图；already 按用户声明标记已矫正；calibration 执行原 remap。"""

    def __init__(self, mode: str, calib_file: Path | None = None):
        if mode not in ("none", "already", "calibration"):
            raise ValueError(f"未知去畸变模式：{mode}")
        if (mode == "calibration") != (calib_file is not None):
            raise ValueError("calibration 模式必须且只能提供对应 NPZ")
        self.mode = mode
        self.calib = load_single_camera_calib(calib_file) if calib_file else None
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
