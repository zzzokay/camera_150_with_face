"""
文件作用：保存 G1 逐帧检测审计 JSONL，区分真实推理、复用帧与未启用的篮球。
输入：VideoFrame、Detection、排除原因；输出：g1_detections_v1，每处理帧一行。
依赖：标准库；调用：run -> DetectionRecords；不是 G3 轨迹表，无速度/身份/球场坐标。
注意：复用帧 detections=[]，无球时 ball_valid=false、位置为 null，不补球。
运行示例：见 NEWCOMER_HANDOFF.md 的 --export-detections。
"""
import json
from dataclasses import asdict
from pathlib import Path

from .contracts import Detection, VideoFrame


class DetectionRecords:
    """独占创建 UTF-8 JSONL，不覆盖旧文件；写入异常使运行失败。"""

    def __init__(self, path: Path):
        self.path = path
        self.stream = None
        self.count = 0

    def __enter__(self):
        """按 x 模式创建文件，拒绝覆盖旧记录。"""
        self.stream = self.path.open("x", encoding="utf-8", newline="\n")
        return self

    def write(self, packet: VideoFrame, coord_system: str, observed: bool,
              detections: list[Detection], rejections: list[dict], ball_enabled: bool,
              last_detect_idx: int) -> None:
        """保存源索引/秒/坐标；仅真实推理能写有效球位置，无候选时不沿用历史球。"""
        actual = detections if observed else []
        balls = [d for d in actual if d.class_name == "ball"]
        record = {
            "schema_version": "g1_detections_v1", "source_frame_idx": packet.source_frame_idx,
            "timestamp_sec": packet.timestamp_sec, "timestamp_basis": packet.timestamp_basis,
            "frame_size_wh": [packet.image_bgr.shape[1], packet.image_bgr.shape[0]],
            "coord_system": coord_system, "inference_performed": observed,
            "detections": [asdict(d) for d in actual], "rejected_detections": rejections if observed else [],
            "reused_from_source_frame_idx": None if observed else last_detect_idx,
            "ball_enabled": ball_enabled, "ball_valid": bool(balls),
            "ball_status": "disabled" if not ball_enabled else ("not_observed" if not observed else ("detected" if balls else "missing")),
            # 多个候选保留全部中心，不能任取其一冒充比赛主球。
            "ball_centers_full_frame_px": [[(d.bbox_xyxy[0] + d.bbox_xyxy[2]) / 2,
                                             (d.bbox_xyxy[1] + d.bbox_xyxy[3]) / 2] for d in balls] or None,
        }
        self.stream.write(json.dumps(record, ensure_ascii=False, allow_nan=False) + "\n")
        self.count += 1

    def __exit__(self, *_):
        """关闭并刷新记录，供独立逐行检查。"""
        if self.stream is not None:
            self.stream.close()
