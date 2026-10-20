r"""
文件作用：保存检测 JSONL 和人物跟踪 QC CSV/JSONL；不写预测失踪框或训练标签。
调用入口：根 run.py；本文件是库模块，不直接执行。
输入/输出及边界：见公开类/函数的中文说明；坐标为全幅像素、时间为源秒，ID 是临时编号。
快速测试（PowerShell，项目根目录）：.\.venv\Scripts\python.exe -X utf8 -m pytest tests/test_detection_policy.py tests/test_tracker.py -q
预期输出：pytest 结果；日常运行结果在 configs/local.yaml 指定的输出目录。
排错：缺依赖用同一独立解释器安装 requirements-windows.lock.txt；输入/格式说明见 NEWCOMER_HANDOFF.md。
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

import csv
from contextlib import ExitStack


class TrackingRecords:
    """独占创建同步写盘，错误向上传播；每处理帧一行 QC，每匹配观测一行 CSV。"""

    fields = ['schema_version', 'segment_id', 'source_frame_idx', 'timestamp_sec', 'track_id',
              'class_name', 'model_class_id', 'confidence', 'observed', 'track_state', 'association_stage',
              'det_x1', 'det_y1', 'det_x2', 'det_y2', 'track_x1', 'track_y1', 'track_x2', 'track_y2', 'coord_system']

    def __init__(self, directory: Path, baseline_enabled: bool = False):
        self.directory = directory
        self.baseline_enabled = baseline_enabled
        self.frame_count = self.byte_rows = self.baseline_rows = 0

    def __enter__(self):
        """按 x 模式打开，拒绝覆盖；部分打开失败也关闭已打开文件。"""
        self.stack = ExitStack()
        try:
            self.audit = self.stack.enter_context((self.directory / 'tracking_audit.jsonl').open('x', encoding='utf-8'))
            self.writers = []
            for name in ('bytetrack_qc.csv', 'smoothtracks_qc.csv'):
                if name == 'smoothtracks_qc.csv' and not self.baseline_enabled:
                    self.writers.append(None)
                    continue
                stream = self.stack.enter_context((self.directory / name).open('x', encoding='utf-8', newline=''))
                writer = csv.DictWriter(stream, fieldnames=self.fields)
                writer.writeheader()
                self.writers.append(writer)
        except BaseException:
            self.stack.close()
            raise
        return self

    def write(self, packet, byte_tracks, baseline_tracks, info):
        """保存当前真实匹配；lost_ids 仅记编号，不将内部预测位置冒充当前观测。"""
        for writer, tracks in zip(self.writers, (byte_tracks, baseline_tracks)):
            if writer is None:
                continue
            for t in tracks:
                d = t.detection
                row = dict(zip(('det_x1', 'det_y1', 'det_x2', 'det_y2'), d.bbox_xyxy))
                row.update(zip(('track_x1', 'track_y1', 'track_x2', 'track_y2'), t.bbox_xyxy))
                row.update(schema_version='g2_tracking_qc_v1', segment_id=t.segment_id,
                           source_frame_idx=packet.source_frame_idx, timestamp_sec=packet.timestamp_sec,
                           track_id=t.track_id, class_name='person', model_class_id=d.model_class_id,
                           confidence=d.confidence, observed=True, track_state='tracked',
                           association_stage=t.association_stage, coord_system=d.coord_system)
                writer.writerow(row)
        self.audit.write(json.dumps({'schema_version': 'g2_tracking_qc_v1',
                                    'source_frame_idx': packet.source_frame_idx, 'timestamp_sec': packet.timestamp_sec,
                                    'inference_performed': True, 'bytetrack': [asdict(t) for t in byte_tracks],
                                    'smoothtracks': [asdict(t) for t in baseline_tracks], 'tracker_info': info,
                                    'ball_enabled': False, 'ball_valid': False, 'ball_status': 'disabled',
                                    'ball_centers_full_frame_px': None}, ensure_ascii=False, allow_nan=False) + '\n')
        self.frame_count += 1
        self.byte_rows += len(byte_tracks)
        self.baseline_rows += len(baseline_tracks)

    def __exit__(self, *_):
        """完整关闭后再独立核对行数。"""
        self.stack.close()
