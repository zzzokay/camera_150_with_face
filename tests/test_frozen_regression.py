r"""
文件作用：对照重构前冻结的 180 帧结果，检测 ID、原框/滤波框、旧对照与规则裁切回归。
调用/快速测试：.\.venv\Scripts\python.exe -X utf8 -m pytest tests/test_frozen_regression.py -q
输入：fixtures/g2_before_refactor.json；固定种子的合成像素/人物框，无需模型或录像。
输出：pytest 通过/失败；不写视频，不代表真实比赛跟踪质量。失败先查排序、取整、时间和依赖版本。
"""
import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

from basketball.contracts import Detection
from basketball.director import RuleDirector
from basketball.tracker import PersonByteTracker, TrackerConfig
from basketball.baseline import SmoothTracksBaseline


def assert_frozen(actual, expected):
    """离散状态严格相同，浮点允许 1e-5 绝对误差；像素框单位仍为完整帧像素。"""
    if isinstance(expected, dict):
        assert actual.keys() == expected.keys()
        for key in expected:
            assert_frozen(actual[key], expected[key])
    elif isinstance(expected, list):
        assert len(actual) == len(expected)
        for left, right in zip(actual, expected):
            assert_frozen(left, right)
    elif isinstance(expected, float):
        assert actual == pytest.approx(expected, abs=1e-5, rel=0)
    else:
        assert actual == expected


def test_frozen_tracking_baseline_and_director_sequence():
    """交替打乱候选顺序、低置信续接及短时无人；期望值在旧代码上先生成并运行。"""
    frozen = json.loads((Path(__file__).parent / 'fixtures/g2_before_refactor.json').read_text(encoding='utf-8'))
    image = np.random.default_rng(frozen['seed']).integers(0, 255, (360, 640, 3), dtype=np.uint8)
    tracker = PersonByteTracker(TrackerConfig(), 30.)
    baseline = SmoothTracksBaseline()
    director = RuleDirector(320, 180)
    for expected in frozen['rows']:
        index = expected['index']
        center = 120 + (index if index < 90 else 180 - index) * 4
        detections = [] if 75 <= index < 80 else [
            Detection('person', 4, .2 if (index + k) % 17 == 0 else .9,
                      (center + k * 12, 145, center + k * 12 + 20, 290), 'raw_full_frame_px')
            for k in range(-3, 3)]
        if index % 2:
            detections.reverse()
        high = [d for d in detections if d.confidence >= .35]
        tracks = tracker.update(detections, index, index / 30., (640, 360), image)
        old = baseline.update(high, tracker.segment_id)
        view, crop, _, info = director.process(image, high, tracked_persons=tracks)

        def pack(items):
            return [[t.track_id, t.segment_id, t.association_stage, list(t.detection.bbox_xyxy),
                     list(t.bbox_xyxy), t.detection.confidence] for t in items]

        actual = {'index': index, 'tracks': pack(tracks), 'baseline': pack(old),
                  'tracker_info': tracker.last_info, 'crop': list(crop), 'director_info': info,
                  'view_sha256': hashlib.sha256(view.tobytes()).hexdigest()}
        assert_frozen(actual, expected)
