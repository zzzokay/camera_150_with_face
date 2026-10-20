r"""
文件作用：人物 ByteTrack 两阶段关联、时间/镜头重置与原始观测/滤波框区分。
调用入口：根 run.py；本文件是库模块，不直接执行。
输入/输出及边界：见公开类/函数的中文说明；坐标为全幅像素、时间为源秒，ID 是临时编号。
快速测试（PowerShell，项目根目录）：.\.venv\Scripts\python.exe -X utf8 -m pytest tests/test_tracker.py -q
预期输出：pytest 结果；日常运行结果在 configs/local.yaml 指定的输出目录。
排错：缺依赖用同一独立解释器安装 requirements-windows.lock.txt；输入/格式说明见 NEWCOMER_HANDOFF.md。
"""
import math
from dataclasses import asdict, dataclass
from importlib.metadata import version
from importlib.util import find_spec
from types import SimpleNamespace

import cv2
import numpy as np

from .contracts import Detection


@dataclass(frozen=True)
class TrackerConfig:
    """高/低阈值为置信度；buffer 是 30 FPS 等效帧数；gap_reset_seconds 为秒。

    match_thresh 是第一阶段匹配代价上限，越大越宽松，不是 IoU 下限。
    当前固定库的低置信续接/待确认匹配上限分别为 .5/.7，不由此字段控制。
    本轮只迁移原值；不能通过改注释或减少 ID 数量声称关联质量改善。
    """

    track_high_thresh: float = .35
    track_low_thresh: float = .10
    new_track_thresh: float = .35
    track_buffer: int = 30
    match_thresh: float = .8
    fuse_score: bool = True
    gap_reset_seconds: float = .5
    scene_cut_threshold: float = .65




def validate_tracker_config(config: TrackerConfig) -> None:
    """保证两阶段阈值有序；拒绝 NaN/bool/零 buffer，防止静默失去低置信续接。"""
    for name in ('track_high_thresh', 'track_low_thresh', 'new_track_thresh', 'match_thresh', 'scene_cut_threshold'):
        v = getattr(config, name)
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or not 0 < v <= 1:
            raise ValueError(f'{name} 必须在 (0,1]')
    if not config.track_low_thresh < config.track_high_thresh <= config.new_track_thresh:
        raise ValueError('必须 low < high <= new_track_thresh')
    if isinstance(config.track_buffer, bool) or not isinstance(config.track_buffer, int) or config.track_buffer < 1:
        raise ValueError('track_buffer 必须为正整数')
    if not isinstance(config.fuse_score, bool):
        raise ValueError('fuse_score 必须为布尔值')
    if isinstance(config.gap_reset_seconds, bool) or not isinstance(config.gap_reset_seconds, (int, float)) or not math.isfinite(config.gap_reset_seconds) or config.gap_reset_seconds <= 0:
        raise ValueError('gap_reset_seconds 必须为有限正秒数')


@dataclass(frozen=True)
class TrackedPerson:
    """当前帧真实观测及其 ID；bbox_xyxy 为滤波估计，detection.bbox_xyxy 为真实观测。"""

    detection: Detection
    track_id: int
    bbox_xyxy: tuple[float, float, float, float]
    segment_id: int
    association_stage: str


class PersonByteTracker:
    """每视频一个跟踪会话；重复/倒序输入报错，长间隔/明显场景切换开启新 segment。"""

    def __init__(self, config: TrackerConfig, fps: float):
        validate_tracker_config(config)
        if not math.isfinite(fps) or fps <= 0:
            raise ValueError('跟踪 FPS 必须为有限正数')
        if version('ultralytics') != '8.3.225':
            raise RuntimeError('本适配器已验证 ultralytics==8.3.225；升级前须复核输出索引 API')
        if find_spec('lap') is None:
            raise RuntimeError('缺少 lap；请安装 requirements-windows.lock.txt，不允许运行时自动安装')
        from ultralytics.trackers.byte_tracker import BYTETracker
        from ultralytics.engine.results import Boxes

        self.config, self.fps = config, float(fps)
        self.backend = BYTETracker(SimpleNamespace(**asdict(config)), frame_rate=fps)
        self.boxes_type = Boxes
        self.segment_id = 1
        self.previous_idx = self.previous_time = self.previous_hist = None
        self.reset_events = []
        self.total_gap_updates = 0
        self.last_info = {}

    def reset(self, reason: str = 'explicit_new_video') -> None:
        """显式新场次/镜头边界重置；ID 可从 1 重启，必须联合 segment_id 使用。"""
        self.backend.reset()
        self.segment_id += 1
        self.previous_idx = self.previous_time = self.previous_hist = None
        self.reset_events.append({'segment_id': self.segment_id, 'reason': reason})

    def _boxes(self, detections, frame_size):
        width, height = frame_size
        data = np.asarray([[*d.bbox_xyxy, d.confidence, 0] for d in detections], dtype=np.float32).reshape(-1, 6)
        # 独立人物实例只接收 person；内部类别 0 只是 tracker 命名空间，真实模型编号不改变。
        return self.boxes_type(data, (height, width))

    def update(self, detections: list[Detection], frame_idx: int, timestamp_sec: float,
               frame_size: tuple[int, int], image=None) -> list[TrackedPerson]:
        """每个真实推理帧调用一次；时间单位秒，框为全幅像素；不接受复用旧检测。"""
        if not math.isfinite(timestamp_sec) or frame_idx < 0:
            raise ValueError('源帧号/时间非法')
        if self.previous_idx is not None and (frame_idx <= self.previous_idx or timestamp_sec <= self.previous_time):
            raise ValueError('跟踪拒绝重复/倒序源帧或时间；新视频请 reset')
        persons = [d for d in detections if d.class_name == 'person']
        if any(not d.observed for d in persons):
            raise ValueError('复用框不能作为 ByteTrack 新观测')
        if any(not all(math.isfinite(v) for v in (*d.bbox_xyxy, d.confidence)) or d.bbox_xyxy[2] <= d.bbox_xyxy[0] or d.bbox_xyxy[3] <= d.bbox_xyxy[1] or not 0 <= d.confidence <= 1 for d in persons):
            raise ValueError('人物观测必须是有限有效框/置信度')
        reset_reason, distance, histogram = None, None, None
        if image is not None:
            hsv = cv2.cvtColor(cv2.resize(image, (160, 90)), cv2.COLOR_BGR2HSV)
            histogram = cv2.calcHist([hsv], [0, 1, 2], None, [8, 8, 8], [0, 180, 0, 256, 0, 256])
            cv2.normalize(histogram, histogram, norm_type=cv2.NORM_L1)
            if self.previous_hist is not None:
                distance = float(cv2.compareHist(self.previous_hist, histogram, cv2.HISTCMP_BHATTACHARYYA))
                if distance > self.config.scene_cut_threshold:
                    reset_reason = 'scene_cut_histogram'
        delta = timestamp_sec - self.previous_time if self.previous_time is not None else 0.
        if delta > self.config.gap_reset_seconds:
            reset_reason = 'timestamp_gap'
        if reset_reason:
            self.reset(reset_reason)
            self.reset_events[-1].update(source_frame_idx=frame_idx, timestamp_sec=timestamp_sec)
        gap_updates = max(0, round(delta * self.fps) - 1) if not reset_reason else 0
        for _ in range(gap_updates):
            self.backend.update(self._boxes([], frame_size))
        self.total_gap_updates += gap_updates
        boxes = self._boxes(persons, frame_size)
        # 原理：先用 Kalman 预测位置，再按框重叠/置信度代价关联高分框；
        # 未匹配的活动轨迹可用低分框续接。低分框不能独立建轨；新高分框也可能
        # 先等待下一帧确认。以下只将库输出还原到当前真实观测，不二次分配 ID。
        # 8.3.225 的输出 idx 相对于各阶段子集；不能直接索引原人物列表。
        high = [d for d, score in zip(persons, boxes.conf) if score >= self.config.track_high_thresh]
        low = [d for d, score in zip(persons, boxes.conf) if self.config.track_low_thresh < score < self.config.track_high_thresh]
        rows = self.backend.update(boxes)
        result = []
        for row in rows:
            stage = 'high' if row[5] >= self.config.track_high_thresh else 'low'
            candidates = high if stage == 'high' else low
            detection = candidates[int(row[-1])]
            bbox = tuple(float(v) for v in row[:4])
            result.append(TrackedPerson(detection, int(row[4]), bbox, self.segment_id, stage))
        if len({t.track_id for t in result}) != len(result) or any(t.track_id <= 0 for t in result):
            raise RuntimeError('ByteTrack 同一帧返回重复/无效人物 ID')
        self.last_info = {'segment_id': self.segment_id, 'reset_reason': reset_reason,
                          'scene_distance': distance, 'gap_empty_updates': gap_updates,
                          'lost_ids': [int(t.track_id) for t in self.backend.lost_stracks],
                          'unconfirmed_count': sum(not t.is_activated for t in self.backend.tracked_stracks)}
        self.previous_idx, self.previous_time, self.previous_hist = frame_idx, timestamp_sec, histogram
        return result

    def metadata(self) -> dict:
        """保存真实库版本、名义 FPS 与超时；Kalman 每次推进按固定 dt=1，并非连续时间模型。"""
        return {'implementation': 'ultralytics.trackers.byte_tracker.BYTETracker',
                'ultralytics': version('ultralytics'), 'lap': version('lap'), 'config': asdict(self.config),
                'source_fps': self.fps, 'max_time_lost_updates': self.backend.max_time_lost,
                'nominal_lost_seconds': self.backend.max_time_lost / self.fps,
                'time_policy': 'fixed nominal FPS; short PTS gaps advance empty updates; large gaps reset',
                'total_gap_empty_updates': self.total_gap_updates, 'reset_events': self.reset_events}
