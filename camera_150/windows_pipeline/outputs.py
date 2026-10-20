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
import numpy as np


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


def draw_detection_overview(frame, detections, rejections, crop, frame_idx, observed, age, policy):
    """G1 对照：原始保留框绿/复用橙，排除框紫并写原因；ROI 蓝、规则裁切青。"""
    out = frame.copy()
    h, w = frame.shape[:2]
    for name in ("person", "ball"):
        rule = getattr(policy, name)
        if rule.enabled and rule.roi_polygon:
            points = np.asarray([(round(x * (w - 1)), round(y * (h - 1))) for x, y in rule.roi_polygon], dtype=np.int32)
            cv2.polylines(out, [points], True, (255, 130, 0), 2)
    for d in detections:
        color = (0, 255, 0) if observed else (0, 165, 255)
        if d.class_name == "ball" and observed:
            color = (0, 255, 255)
        x1, y1, x2, y2 = (int(round(v)) for v in d.bbox_xyxy)
        cv2.rectangle(out, (x1, y1), (x2, y2), color, 2)
        cv2.putText(out, f"{d.class_name} {d.confidence:.2f}", (x1, max(18, y1 - 5)), cv2.FONT_HERSHEY_SIMPLEX, .45, color, 1)
    for d in rejections if observed else []:
        x1, y1, x2, y2 = (int(round(v)) for v in d["bbox_xyxy"])
        cv2.rectangle(out, (x1, y1), (x2, y2), (255, 0, 255), 1)
        cv2.putText(out, f"excluded {d['reason']}", (x1, max(18, y1 - 5)), cv2.FONT_HERSHEY_SIMPLEX, .42, (255, 0, 255), 1)
    x1, y1, x2, y2 = crop
    cv2.rectangle(out, (x1, y1), (x2 - 1, y2 - 1), (255, 255, 0), 3)
    status = "NEW INFERENCE" if observed else f"REUSED age={age}"
    cv2.putText(out, f"frame={frame_idx} {status} | person candidates, not identities", (12, 28), cv2.FONT_HERSHEY_SIMPLEX, .6, (0, 255, 255), 2)
    cv2.putText(out, "ball: DISABLED" if not policy.ball.enabled else "ball: real observations only", (12, 55), cv2.FONT_HERSHEY_SIMPLEX, .6, (0, 255, 255), 2)
    return out


def draw_tracking_overview(frame, tracks, crop, frame_idx, timestamp_sec, policy, title='ByteTrack', info=None):
    """G2 画当前匹配观测的 ID/滤波状态框；不画失踪预测，蓝线 ROI，青线导播裁切。"""
    out = frame.copy()
    h, w = out.shape[:2]
    if policy.person.roi_polygon:
        points = np.asarray([(round(x * (w - 1)), round(y * (h - 1))) for x, y in policy.person.roi_polygon], dtype=np.int32)
        cv2.polylines(out, [points], True, (255, 130, 0), 2)
    colors = [(60, 230, 60), (0, 230, 255), (255, 190, 60), (255, 90, 190), (80, 150, 255)]
    for t in tracks:
        x1, y1, x2, y2 = (int(round(v)) for v in t.bbox_xyxy)
        color = colors[t.track_id % len(colors)]
        cv2.rectangle(out, (x1, y1), (x2, y2), color, 2)
        cv2.putText(out, f'P{t.track_id} {t.detection.confidence:.2f} {t.association_stage[0].upper()}',
                    (x1, max(70, y1 - 5)), cv2.FONT_HERSHEY_SIMPLEX, .52, color, 2)
    x1, y1, x2, y2 = crop
    cv2.rectangle(out, (x1, y1), (x2 - 1, y2 - 1), (255, 255, 0), 2)
    cv2.putText(out, f'{title} | source={frame_idx} t={timestamp_sec:.3f}s | temporary person IDs', (12, 28), cv2.FONT_HERSHEY_SIMPLEX, .65, (0, 255, 255), 2)
    segment = info.get('segment_id', 1) if info else 1
    cv2.putText(out, f'segment={segment} matched={len(tracks)} | ball: DISABLED | state boxes are filtered estimates', (12, 55), cv2.FONT_HERSHEY_SIMPLEX, .6, (0, 255, 255), 2)
    return out
