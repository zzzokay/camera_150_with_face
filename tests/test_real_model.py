"""
文件作用：用用户指定的真实 YOLO 权重和篮球录像执行 G0 自动化集成测试。
输入：G0_TEST_WEIGHTS / G0_TEST_VIDEO 环境变量；输出：pytest 临时目录的真实视频/报告。
依赖：Ultralytics、完整 Windows 管线；缺文件时明确 skip，不用假检测代替。
运行：设置环境变量后 python -m pytest tests/test_real_model.py -q。
"""
import json
import os
from pathlib import Path

import pytest

from camera_150.windows_pipeline.config import RunConfig
from camera_150.windows_pipeline.run import run_pipeline


@pytest.mark.parametrize("start_seconds", [0., 1 / 30.])
def test_actual_yolo_video_to_original_director(tmp_path, start_seconds):
    weights, video = os.environ.get("G0_TEST_WEIGHTS"), os.environ.get("G0_TEST_VIDEO")
    if not weights or not video:
        pytest.skip("未设置真实模型和视频；此 skip 不能计作模型实测通过")
    config = RunConfig(source=Path(video), weights=Path(weights), output_dir=tmp_path,
                        undistort="already", device="cpu", max_frames=12, detect_interval=3,
                        view_width=640, view_height=360, start_seconds=start_seconds)
    run_dir = run_pipeline(config)
    report = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    assert report["status"] == "COMPLETED"
    assert report["processed_frames"] == 12
    assert report["inference_calls"] == 4
    assert report["frames_reusing_detections"] == 8
    assert report["true_person_observations"] > 0
    assert report["first_detection"]["observed"] is True
    assert report["first_detection"]["coord_system"] == "undistorted_full_frame_px"
    assert report["model"]["names"]
    assert report["source"]["first_timestamp_sec"] >= start_seconds
    assert report["source"]["skipped_frames"] == report["source"]["first_source_frame_idx"]
    assert report["last_source_frame_idx"] == report["source"]["first_source_frame_idx"] + 11
    # 本测试录像的首个选中帧确实有人，必须立即实际推理，不能先复用空框。
    assert report["first_detection"]["source_frame_idx"] == report["source"]["first_source_frame_idx"]
    assert all(output["decoded_frames"] == 12 for output in report["outputs"])


def test_actual_g1_person_policy_and_disabled_ball_records(tmp_path):
    """真实人物模型验证 G1 导出；球仍关闭，不把合成契约测试算作真实球推理。"""
    weights, video = os.environ.get("G0_TEST_WEIGHTS"), os.environ.get("G0_TEST_VIDEO")
    if not weights or not video:
        pytest.skip("未设置真实模型和视频")
    policy = Path(__file__).resolve().parents[1] / "configs/detection.example.yaml"
    config = RunConfig(source=Path(video), weights=Path(weights), output_dir=tmp_path,
                       undistort="already", max_frames=6, detect_interval=3,
                       view_width=640, view_height=360, detection_policy=policy, export_detections=True)
    run_dir = run_pipeline(config)
    report = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    rows = [json.loads(line) for line in (run_dir / "detections.jsonl").read_text(encoding="utf-8").splitlines()]
    assert report["schema_version"] == "g1_run_v1"
    assert len(rows) == report["processed_frames"] == 6
    assert sum(r["inference_performed"] for r in rows) == 2
    assert all(r["ball_valid"] is False and r["ball_centers_full_frame_px"] is None for r in rows)
    assert all(not r["detections"] for r in rows if not r["inference_performed"])
    assert report["detection_summary"]["person"]["accepted"] == sum(len(r["detections"]) for r in rows)
    assert report["detection_summary"]["ball"]["frames_without_detections"] is None
