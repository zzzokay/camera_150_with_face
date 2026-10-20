r"""
文件作用：纯规则裁切与坐标工具；不依赖设备或旧工程。
调用入口：根 run.py；本文件是库模块，不直接执行。
输入/输出及边界：见公开类/函数的中文说明；坐标为全幅像素、时间为源秒，ID 是临时编号。
快速测试（PowerShell，项目根目录）：.\.venv\Scripts\python.exe -X utf8 -m pytest tests/test_windows_components.py -q
预期输出：pytest 结果；日常运行结果在 configs/local.yaml 指定的输出目录。
排错：缺依赖用同一独立解释器安装 requirements-windows.lock.txt；输入/格式说明见 NEWCOMER_HANDOFF.md。
"""
from typing import Tuple

import cv2
import numpy as np

def box_rect_to_pixels(box_rect, out_w, out_h):
    """将旧规则浮点框取整并限制在完整帧内；沿用原边界语义。"""
    x1, y1, x2, y2 = box_rect
    ix1 = clamp_int(int(round(x1)), 0, out_w - 2)
    ix2 = clamp_int(int(round(x2)), ix1 + 1, out_w - 1)
    iy1 = clamp_int(int(round(y1)), 0, out_h - 2)
    iy2 = clamp_int(int(round(y2)), iy1 + 1, out_h - 1)
    return ix1, iy1, ix2, iy2


def clamp_int(value: int, low: int, high: int) -> int:
    """把整数限制在 [low, high] 范围内。"""
    return int(max(low, min(high, value)))

def fit_box_to_output_ratio(
    box_rect: Tuple[float, float, float, float],
    frame_w: int,
    frame_h: int,
    out_ratio: float,
) -> Tuple[int, int, int, int]:
    """
    以样本导播框为运动轨迹，但强制裁切窗口匹配输出比例。

    样本里的绿色导播框宽高比不是固定 16:9。
    这里保留它的横向运动、停顿、左右切换和底部锚定效果，
    再把裁切框调整成 1280x720 需要的 16:9，避免输出两侧黑边。
    """
    x1, y1, x2, y2 = box_rect_to_pixels(box_rect, frame_w, frame_h)

    base_w = max(2.0, float(x2 - x1))
    base_h = max(2.0, float(y2 - y1))
    center_x = (float(x1) + float(x2)) * 0.5

    # 保持样本框的下边界锚定，让画面整体偏向球场下半部。
    bottom_y = float(y2)

    # 先以样本框宽度为基准，计算 16:9 高度。
    target_w = base_w
    target_h = target_w / max(1e-6, out_ratio)

    # 如果这样算出来的高度比样本框还矮，就改为以高度为基准扩宽。
    # 这样 1080p -> 720p 时，景别更接近样本运镜。
    if target_h < base_h:
        target_h = base_h
        target_w = target_h * out_ratio

    # 不允许裁切窗口超过源画幅。
    if target_w > frame_w:
        target_w = float(frame_w)
        target_h = target_w / max(1e-6, out_ratio)
    if target_h > frame_h:
        target_h = float(frame_h)
        target_w = target_h * out_ratio

    target_w = max(2.0, min(float(frame_w), target_w))
    target_h = max(2.0, min(float(frame_h), target_h))

    left = center_x - target_w * 0.5
    top = bottom_y - target_h

    left = max(0.0, min(left, frame_w - target_w))
    top = max(0.0, min(top, frame_h - target_h))

    ix1 = clamp_int(round(left), 0, frame_w - 2)
    iy1 = clamp_int(round(top), 0, frame_h - 2)
    ix2 = clamp_int(round(left + target_w), ix1 + 2, frame_w)
    iy2 = clamp_int(round(top + target_h), iy1 + 2, frame_h)

    # 四舍五入后再修一次比例，尽量保持 16:9。
    final_w = ix2 - ix1
    final_h = iy2 - iy1
    wanted_w = int(round(final_h * out_ratio))
    if wanted_w <= frame_w and abs(wanted_w - final_w) > 2:
        cx = (ix1 + ix2) * 0.5
        ix1 = clamp_int(round(cx - wanted_w * 0.5), 0, frame_w - wanted_w)
        ix2 = ix1 + wanted_w

    return ix1, iy1, ix2, iy2

def render_sample_director_view720(
    frame: np.ndarray,
    director_info: dict,
    view_w: int,
    view_h: int,
) -> Tuple[np.ndarray, Tuple[int, int, int, int]]:
    """
    按“运镜样本”的导播框做裁切，再输出固定 720p 画幅。

    这和旧版 render_single_view_crop 的区别：
        - 不再直接用 current_anchor_x + scale_value 自己算裁切框；
        - 改用 update_overlay_director_state 生成的 display_box_rect；
        - 运镜的左右窗口、过渡速度、驻留和回中节奏与样本代码一致。
    """
    frame_h, frame_w = frame.shape[:2]
    out_ratio = view_w / max(1.0, view_h)

    box_rect = director_info.get("display_box_rect")
    if box_rect is None:
        box_h = frame_h * 0.70
        box_w = box_h * out_ratio
        box_rect = (
            frame_w * 0.5 - box_w * 0.5,
            frame_h - box_h,
            frame_w * 0.5 + box_w * 0.5,
            frame_h,
        )

    x1, y1, x2, y2 = fit_box_to_output_ratio(box_rect, frame_w, frame_h, out_ratio)
    crop = frame[y1:y2, x1:x2]
    if crop.size == 0:
        view = cv2.resize(frame, (view_w, view_h), interpolation=cv2.INTER_LINEAR)
        return view, (0, 0, frame_w, frame_h)

    view = cv2.resize(crop, (view_w, view_h), interpolation=cv2.INTER_LINEAR)
    return view, (int(x1), int(y1), int(x2), int(y2))
