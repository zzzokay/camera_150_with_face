"""
文件作用：保存 G2 ByteTrack/旧关联验收 CSV 和逐帧 QC，不是 G3 可训练轨迹规范。
输入：真实帧及匹配观测的 TrackedPerson；输出：两个 CSV 和 tracking_audit.jsonl。
依赖：标准库；调用：run -> TrackingRecords；不写预测失踪框、速度或伪造篮球位置。
状态框与真实检测框分列；仅供本轮关联核验，未来 G3 另冻结数据集/重放接口。
"""
import csv
import json
from contextlib import ExitStack
from dataclasses import asdict
from pathlib import Path


class TrackingRecords:
    """独占创建同步写盘，错误向上传播；每处理帧一行 QC，每匹配观测一行 CSV。"""

    fields = ['schema_version', 'segment_id', 'source_frame_idx', 'timestamp_sec', 'track_id',
              'class_name', 'model_class_id', 'confidence', 'observed', 'track_state', 'association_stage',
              'det_x1', 'det_y1', 'det_x2', 'det_y2', 'track_x1', 'track_y1', 'track_x2', 'track_y2', 'coord_system']

    def __init__(self, directory: Path):
        self.directory = directory
        self.frame_count = self.byte_rows = self.baseline_rows = 0

    def __enter__(self):
        """按 x 模式打开，拒绝覆盖；部分打开失败也关闭已打开文件。"""
        self.stack = ExitStack()
        try:
            self.audit = self.stack.enter_context((self.directory / 'tracking_audit.jsonl').open('x', encoding='utf-8'))
            self.writers = []
            for name in ('bytetrack_qc.csv', 'smoothtracks_qc.csv'):
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
