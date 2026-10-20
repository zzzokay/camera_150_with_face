r"""
文件作用：Windows test_detection_policy 的行为测试；合成输入不作为真实比赛精度证据。
调用/快速测试（PowerShell）：.\.venv\Scripts\python.exe -X utf8 -m pytest tests/test_detection_policy.py -q
输入：测试内说明的合成数据/临时路径；真实模型测试另需设置 BASKETBALL_TEST_WEIGHTS 与 BASKETBALL_TEST_VIDEO。
预期输出：pytest 结果及临时目录产物；失败查看断言、依赖版本与 NEWCOMER_HANDOFF.md。
"""
import json
from dataclasses import replace

import numpy as np
import pytest

from basketball.contracts import Detection, VideoFrame
from basketball.detection_policy import (
    ClassPolicy, DetectionPolicy, policy_from_mapping, rejection_reason, resolve_class_ids, validate_policy,
)
from basketball.records import DetectionRecords


def test_names_disabled_ball_and_missing_requested_class():
    names = {7: "Player", 42: "Sports Ball"}
    policy = DetectionPolicy()
    assert resolve_class_ids(names, policy)[1] == {"person": [7], "ball": []}
    enabled = replace(policy, ball=replace(policy.ball, enabled=True))
    assert resolve_class_ids(names, enabled)[1] == {"person": [7], "ball": [42]}
    with pytest.raises(ValueError, match="ball"):
        resolve_class_ids({7: "Player"}, enabled)


def test_per_class_threshold_size_and_anchor():
    """同一框底部在 ROI 而中心不在：人物保留、球排除，坐标空间不会暗换。"""
    roi = ((0., .7), (1., .7), (1., 1.), (0., 1.))
    person = ClassPolicy(("player",), confidence=.5, roi_polygon=roi)
    ball = ClassPolicy(("ball",), confidence=.2, roi_polygon=roi)
    d = Detection("person", 7, .6, (40., 20., 60., 80.), "raw_full_frame_px")
    assert rejection_reason(d, person, (100, 100)) is None
    assert rejection_reason(replace(d, class_name="ball"), ball, (100, 100)) == "roi"
    assert rejection_reason(replace(d, confidence=.3), person, (100, 100)) == "confidence"
    assert rejection_reason(replace(d, class_name="ball", confidence=.3, bbox_xyxy=(40., 75., 50., 85.)), ball, (100, 100)) is None
    assert rejection_reason(d, replace(person, max_size_wh=(1., .5)), (100, 100)) == "size"


@pytest.mark.parametrize("change", [
    {"confidence": float("nan")}, {"aliases": None}, {"min_size_wh": None},
    {"min_size_wh": (.5, .5), "max_size_wh": (.2, .2)},
    {"roi_polygon": ((0., 0.), (1., 1.), (1., 0.), (0., 1.))},
    {"roi_polygon": (1, 2, 3)}, {"aliases": ("ball",)},
])
def test_invalid_policy_rejected(change):
    with pytest.raises(ValueError):
        validate_policy(replace(DetectionPolicy(), person=replace(DetectionPolicy().person, **change)))


def test_yaml_unknown_field_and_defaults(tmp_path):
    with pytest.raises(ValueError, match="未知"):
        policy_from_mapping({'person': {'confdence': .2}})
    policy = policy_from_mapping({'person': {'confidence': .44, 'aliases': ['human']}})
    assert policy.person.confidence == .44 and policy.person.aliases == ("human",)
    assert policy.ball.enabled is False


def test_records_missing_ball_and_reused_frames_do_not_invent_positions(tmp_path):
    path = tmp_path / "detections.jsonl"
    packet = VideoFrame(np.zeros((100, 100, 3), dtype=np.uint8), 10, 1., "container_pts")
    ball = Detection("ball", 42, .8, (10., 20., 20., 30.), "raw_full_frame_px")
    with DetectionRecords(path) as writer:
        writer.write(packet, "raw_full_frame_px", True, [], [], False, 10)
        writer.write(replace(packet, source_frame_idx=11, timestamp_sec=1.1), "raw_full_frame_px", True, [ball], [], True, 11)
        writer.write(replace(packet, source_frame_idx=12, timestamp_sec=1.2), "raw_full_frame_px", False, [ball], [], True, 11)
        writer.write(replace(packet, source_frame_idx=13, timestamp_sec=1.3), "raw_full_frame_px", True, [], [], True, 13)
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert [r["ball_status"] for r in rows] == ["disabled", "detected", "not_observed", "missing"]
    assert [r["ball_valid"] for r in rows] == [False, True, False, False]
    assert rows[1]["ball_centers_full_frame_px"] == [[15., 25.]]
    assert rows[2]["detections"] == [] and rows[2]["ball_centers_full_frame_px"] is None
    assert rows[2]["reused_from_source_frame_idx"] == 11
    with pytest.raises(FileExistsError):
        with DetectionRecords(path):
            pass
