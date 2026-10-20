"""
文件作用：保存无音频本地视频、生成调试图并在关闭后逐帧检查可解码性。
输入：uint8 BGR 帧、FPS、输出目录；输出：MP4/AVI 和实际解码统计。
依赖：OpenCV；调用关系：run -> SavedVideo / draw_overview / verify_video。
注意：每次运行创建唯一目录，不覆盖已有视频；不依赖 h264_rkmpp 或外部 FFmpeg。
运行示例：见 NEWCOMER_HANDOFF.md；MJPG 为显式 AVI 备选，失败不会静默换编码器。
"""
import math
from pathlib import Path

import cv2


class SavedVideo:
    """同步保存全部处理帧；离线模式不丢队列旧帧，保存 FPS 使用源视频 FPS。"""

    def __init__(self, path: Path, fps: float, size: tuple[int, int], codec: str = "mp4v"):
        self.path, self.fps, self.size, self.codec = path, fps, size, codec
        self.count = 0
        self.writer = None
        if path.exists():
            raise FileExistsError(f"拒绝覆盖已有文件：{path}")
        if not math.isfinite(fps) or fps <= 0:
            raise ValueError("保存 FPS 必须为有限正数")
        expected = {"mp4v": ".mp4", "MJPG": ".avi"}
        if codec not in expected or path.suffix.lower() != expected[codec]:
            raise ValueError("mp4v 必须保存为 .mp4，MJPG 必须保存为 .avi")

    def __enter__(self):
        """创建编码器，打不开时提示显式切换 MJPG，不修改用户文件。"""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.writer = cv2.VideoWriter(str(self.path), cv2.VideoWriter_fourcc(*self.codec),
                                      self.fps, self.size)
        if not self.writer.isOpened():
            self.writer.release()
            raise RuntimeError(f"编码器 {self.codec} 无法打开：{self.path}；可尝试 --codec MJPG")
        return self

    def write(self, frame) -> None:
        """保存一帧；尺寸/类型不匹配时立即报错，避免 OpenCV 静默丢帧。"""
        if frame.dtype.name != "uint8" or frame.shape != (self.size[1], self.size[0], 3):
            raise ValueError(f"保存帧必须是 uint8 BGR，尺寸应为 {self.size}")
        self.writer.write(frame)
        self.count += 1

    def __exit__(self, *_):
        """关闭编码器并完成容器尾部索引；之后才能检查解码结果。"""
        if self.writer is not None:
            self.writer.release()


def verify_video(path: Path, expected_frames: int, expected_size: tuple[int, int]) -> dict:
    """实际从头解码至结尾，核对帧数/尺寸；损坏或短写抛 RuntimeError。"""
    cap = cv2.VideoCapture(str(path))
    count = 0
    try:
        if not cap.isOpened():
            raise RuntimeError(f"产物无法打开：{path}")
        fps = float(cap.get(cv2.CAP_PROP_FPS))
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            if (frame.shape[1], frame.shape[0]) != expected_size:
                raise RuntimeError("产物帧尺寸不一致")
            count += 1
    finally:
        cap.release()
    if count != expected_frames or count == 0:
        raise RuntimeError(f"产物帧数错误：实际 {count}，预期 {expected_frames}，文件 {path}")
    return {"path": str(path), "decoded_frames": count, "frame_size": list(expected_size), "fps": fps}


def draw_overview(frame, detections, crop, frame_idx: int, observed: bool, age: int):
    """显示全幅平滑框、裁切范围和观测年龄（源帧）；复用框用橙色并明确标记。"""
    out = frame.copy()
    color = (0, 255, 0) if observed else (0, 165, 255)
    for det in detections:
        x1, y1, x2, y2 = (int(round(v)) for v in det.wide_bbox)
        cv2.rectangle(out, (x1, y1), (x2, y2), color, 2)
        cv2.putText(out, f"person id={det.track_id} {det.score:.2f}", (x1, max(18, y1 - 5)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)
    x1, y1, x2, y2 = crop
    cv2.rectangle(out, (x1, y1), (x2 - 1, y2 - 1), (255, 255, 0), 3)
    status = "NEW INFERENCE" if observed else f"REUSED age={age} source frames"
    cv2.putText(out, f"frame={frame_idx} {status} | old SmoothTracks", (12, 28),
                cv2.FONT_HERSHEY_SIMPLEX, 0.65, color, 2)
    return out
