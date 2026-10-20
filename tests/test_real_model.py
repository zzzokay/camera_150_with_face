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


def test_actual_yolo_video_to_original_director(tmp_path):
    weights, video = os.environ.get("G0_TEST_WEIGHTS"), os.environ.get("G0_TEST_VIDEO")
    if not weights or not video:
        pytest.skip("未设置真实模型和视频；此 skip 不能计作模型实测通过")
    config = RunConfig(source=Path(video), weights=Path(weights), output_dir=tmp_path,
                        undistort="already", device="cpu", max_frames=12, detect_interval=3,
                        view_width=640, view_height=360)
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
    assert all(output["decoded_frames"] == 12 for output in report["outputs"])
