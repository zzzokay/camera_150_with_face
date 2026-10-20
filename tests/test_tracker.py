"""
文件作用：G2 两阶段关联、缺失/重置/时序、检测单次调用及原导播旁路的组件测试。
输入：明确合成的像素框/场景/YOLO 返回值；输出：pytest 断言，不作为真实球员 ID 精度。
依赖：固定版本 ByteTrack/lap 和 Windows 模块；运行 python -m pytest tests/test_tracker.py -q。
"""
import json
from dataclasses import replace
from types import SimpleNamespace

import numpy as np
import pytest

from camera_150.windows_pipeline.contracts import Detection, VideoFrame
from camera_150.windows_pipeline.tracker import PersonByteTracker, TrackerConfig, load_tracker_config
from camera_150.windows_pipeline.tracking_records import TrackingRecords


def person(x=10., confidence=.9):
    return Detection('person', 7, confidence, (x, 20., x + 20., 80.), 'raw_full_frame_px')


def test_low_stage_keeps_id_and_correct_original_detection_reference():
    tracker = PersonByteTracker(TrackerConfig(), 30.)
    first = tracker.update([person(10), person(100)], 0, 0., (200, 100))
    second = tracker.update([person(101, .2), person(11)], 1, 1 / 30, (200, 100))
    assert [(t.track_id, t.detection.bbox_xyxy[0]) for t in first] == [(1, 10), (2, 100)]
    assert [(t.track_id, t.association_stage, t.detection.bbox_xyxy[0]) for t in second] == [(1, 'high', 11), (2, 'low', 101)]
    assert all(t.detection.model_class_id == 7 for t in second)


def test_low_confidence_alone_cannot_create_track_or_link_ball():
    tracker = PersonByteTracker(TrackerConfig(), 30.)
    ball = replace(person(), class_name='ball', confidence=.99)
    for i in range(3):
        assert tracker.update([person(confidence=.2), ball], i, i / 30, (200, 100)) == []


def test_lost_has_no_exported_position_and_reappears_with_id():
    tracker = PersonByteTracker(TrackerConfig(), 30.)
    original = tracker.update([person()], 0, 0., (200, 100))[0].track_id
    assert tracker.update([], 1, 1 / 30, (200, 100)) == []
    assert tracker.last_info['lost_ids'] == [original]
    assert tracker.update([person(12)], 2, 2 / 30, (200, 100))[0].track_id == original


def test_expired_track_reappearance_requires_new_id():
    tracker = PersonByteTracker(replace(TrackerConfig(), track_buffer=2), 30.)
    original = tracker.update([person()], 0, 0., (200, 100))[0].track_id
    for i in range(1, 5):
        tracker.update([], i, i / 30, (200, 100))
    tracker.update([person()], 5, 5 / 30, (200, 100))
    current = tracker.update([person()], 6, 6 / 30, (200, 100))
    assert current and current[0].track_id != original


def test_duplicate_reverse_and_reused_frame_rejected_before_state_changes():
    tracker = PersonByteTracker(TrackerConfig(), 30.)
    tracker.update([person()], 10, 1., (200, 100))
    for idx, timestamp in [(10, 1.), (9, 1.1), (11, 1.)]:
        with pytest.raises(ValueError, match='重复/倒序'):
            tracker.update([person()], idx, timestamp, (200, 100))
    assert tracker.backend.frame_id == 1
    with pytest.raises(ValueError, match='复用'):
        tracker.update([replace(person(), observed=False)], 11, 1.1, (200, 100))


@pytest.mark.parametrize('fps,expected', [(15., 15), (30., 30), (60., 60)])
def test_buffer_uses_nominal_fps_and_new_video_reset(fps, expected):
    tracker = PersonByteTracker(TrackerConfig(), fps)
    assert tracker.backend.max_time_lost == expected
    assert tracker.update([person()], 0, 0., (200, 100))[0].segment_id == 1
    tracker.reset()
    restarted = tracker.update([person(100)], 0, 0., (200, 100))[0]
    assert (restarted.segment_id, restarted.track_id) == (2, 1)


def test_pts_gap_advances_empty_updates_and_large_gap_starts_new_segment():
    tracker = PersonByteTracker(TrackerConfig(), 30.)
    tracker.update([person()], 0, 0., (200, 100))
    tracker.update([person()], 3, .1, (200, 100))
    assert tracker.last_info['gap_empty_updates'] == 2
    assert tracker.backend.frame_id == 4
    tracker.update([person()], 30, 1., (200, 100))
    assert tracker.segment_id == 2 and tracker.last_info['reset_reason'] == 'timestamp_gap'


def test_obvious_scene_cut_resets_without_cross_scene_id():
    tracker = PersonByteTracker(TrackerConfig(), 30.)
    before = np.full((100, 200, 3), (0, 255, 0), dtype=np.uint8)
    after = np.full((100, 200, 3), (255, 0, 0), dtype=np.uint8)
    tracker.update([person()], 0, 0., (200, 100), before)
    tracks = tracker.update([person(100)], 1, 1 / 30, (200, 100), after)
    assert tracker.last_info['reset_reason'] == 'scene_cut_histogram'
    assert tracks[0].segment_id == 2


def test_detector_once_per_frame_low_candidates_are_not_reused():
    from camera_150.windows_pipeline.detector import YoloDetector
    from camera_150.windows_pipeline.detection_policy import DetectionPolicy
    detector = object.__new__(YoloDetector)
    detector.device, detector.imgsz, detector.confidence, detector.iou = 'cpu', 640, .1, .7
    detector.id_to_class, detector.policy = {7: 'person'}, DetectionPolicy()
    detector.person_tracking_confidence = .1
    calls = []
    class TensorLike:
        def cpu(self): return self
        def numpy(self): return np.array([[10, 20, 30, 80, .2, 7]], dtype=np.float32)
    def predict(**kwargs):
        calls.append(kwargs)
        return [SimpleNamespace(boxes=SimpleNamespace(data=TensorLike()))]
    detector.model = SimpleNamespace(predict=predict)
    image = np.zeros((100, 200, 3), dtype=np.uint8)
    for _ in range(2):
        assert detector.detect(image, 'raw_full_frame_px') == []
        assert len(detector.last_tracking_detections) == 1
    assert len(calls) == 2 and all(call['conf'] == .1 for call in calls)


def test_g2_director_skips_old_association_and_qc_preserves_both_boxes(tmp_path, monkeypatch):
    from camera_150.windows_pipeline.director_adapter import LegacyDirector
    tracker = PersonByteTracker(TrackerConfig(), 30.)
    tracks = tracker.update([person()], 0, 0., (200, 100))
    director = LegacyDirector(160, 90)
    def fail_if_called(*args):
        raise AssertionError('G2 不得再次使用 SmoothTracks 关联')
    monkeypatch.setattr(director.smoother, 'update', fail_if_called)
    image = np.zeros((100, 200, 3), dtype=np.uint8)
    _, _, wide, _ = director.process(image, [person()], tracked_persons=tracks)
    assert wide[0].track_id == tracks[0].track_id
    with TrackingRecords(tmp_path) as writer:
        writer.write(VideoFrame(image, 0, 0., 'container_pts'), tracks, [], tracker.last_info)
    record = json.loads((tmp_path / 'tracking_audit.jsonl').read_text(encoding='utf-8'))
    assert record['bytetrack'][0]['detection']['observed'] is True
    assert record['ball_valid'] is False and record['ball_centers_full_frame_px'] is None


def test_tracking_cli_rejects_inference_reuse_and_bad_thresholds(tmp_path):
    from camera_150.windows_pipeline.config import load_config
    from camera_150.windows_pipeline.tracker import SmoothTracksBaseline
    with pytest.raises(ValueError, match='禁用旧 ID'):
        SmoothTracksBaseline(smooth=0)
    with pytest.raises(ValueError, match='detect_interval'):
        load_config(['--source', 'a.mp4', '--weights', 'a.pt', '--tracking-config', 'tracking.yaml'])
    path = tmp_path / 'bad.yaml'
    path.write_text('schema_version: g2_tracker_config_v1\ntrack_low_thresh: 0.5\n', encoding='utf-8')
    with pytest.raises(ValueError, match='low < high'):
        load_tracker_config(path)
