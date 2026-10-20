r"""
文件作用：Windows test_real_model 的行为测试；合成输入不作为真实比赛精度证据。
调用/快速测试（PowerShell）：.\.venv\Scripts\python.exe -X utf8 -m pytest tests/test_real_model.py -q
输入：测试内说明的合成数据/临时路径；真实模型测试另需设置 BASKETBALL_TEST_WEIGHTS 与 BASKETBALL_TEST_VIDEO。
预期输出：pytest 结果及临时目录产物；失败查看断言、依赖版本与 NEWCOMER_HANDOFF.md。
"""
import json
import os
from pathlib import Path

import pytest

from basketball.config import RunConfig
from basketball.pipeline import run_pipeline


@pytest.mark.parametrize("start_seconds", [0., 1 / 30.])
def test_actual_yolo_video_to_original_director(tmp_path, start_seconds):
    weights, video = os.environ.get("BASKETBALL_TEST_WEIGHTS"), os.environ.get("BASKETBALL_TEST_VIDEO")
    if not weights or not video:
        pytest.skip("未设置真实模型和视频；此 skip 不能计作模型实测通过")
    config = RunConfig(source=Path(video), weights=Path(weights), output_dir=tmp_path,
                        mode='detect', director_enabled=True, undistort="already", device="cpu", max_frames=12, detect_interval=3,
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
    weights, video = os.environ.get("BASKETBALL_TEST_WEIGHTS"), os.environ.get("BASKETBALL_TEST_VIDEO")
    if not weights or not video:
        pytest.skip("未设置真实模型和视频")
    config = RunConfig(source=Path(video), weights=Path(weights), output_dir=tmp_path,
                       mode='detect', undistort="already", max_frames=6, detect_interval=3,
                       view_width=640, view_height=360, export_detections=True)
    run_dir = run_pipeline(config)
    report = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    rows = [json.loads(line) for line in (run_dir / "detections.jsonl").read_text(encoding="utf-8").splitlines()]
    assert report["schema_version"] == "windows_run_v1"
    assert len(rows) == report["processed_frames"] == 6
    assert sum(r["inference_performed"] for r in rows) == 2
    assert all(r["ball_valid"] is False and r["ball_centers_full_frame_px"] is None for r in rows)
    assert all(not r["detections"] for r in rows if not r["inference_performed"])
    assert report["detection_summary"]["person"]["accepted"] == sum(len(r["detections"]) for r in rows)
    assert report["detection_summary"]["ball"]["frames_without_detections"] is None


@pytest.mark.parametrize('director,baseline', [(False, False), (True, False), (False, True), (True, True)])
def test_actual_g2_bytetrack_video_csv_and_legacy_comparison(tmp_path, director, baseline):
    """真实 YOLO 每帧推理，保存可解码 ID 对照、有效 CSV；不把此短测当 ID 精度评估。"""
    weights, video = os.environ.get('BASKETBALL_TEST_WEIGHTS'), os.environ.get('BASKETBALL_TEST_VIDEO')
    if not weights or not video:
        pytest.skip('未设置真实模型和视频')
    root = Path(__file__).resolve().parents[1]
    config = RunConfig(source=Path(video), weights=Path(weights), output_dir=tmp_path,
                       undistort='already', max_frames=8, detect_interval=1,
                       view_width=640, view_height=360, director_enabled=director, baseline_enabled=baseline,
                       export_detections=True)
    run_dir = run_pipeline(config)
    report = json.loads((run_dir / 'summary.json').read_text(encoding='utf-8'))
    rows = [json.loads(line) for line in (run_dir / 'tracking_audit.jsonl').read_text(encoding='utf-8').splitlines()]
    assert report['schema_version'] == 'windows_run_v1'
    assert report['processed_frames'] == report['inference_calls'] == len(rows) == 8
    assert report['frames_reusing_detections'] == 0
    assert len(report['outputs']) == 1 + int(director) + int(baseline)
    assert all(o['decoded_frames'] == 8 for o in report['outputs'])
    assert (run_dir / 'director.mp4').exists() == director
    assert (run_dir / 'smoothtracks_qc.csv').exists() == baseline
    assert (run_dir / 'tracking_comparison.mp4').exists() == baseline
    assert report['forbidden_runtime_modules'] == []
    assert report['tracking_summary']['matched_observations'] > 0
    assert report['tracking_summary']['csv_rows'] == sum(len(r['bytetrack']) for r in rows)
    for row in rows:
        ids = [t['track_id'] for t in row['bytetrack']]
        assert len(ids) == len(set(ids)) and all(i > 0 for i in ids)
        assert row['ball_status'] == 'disabled' and row['ball_centers_full_frame_px'] is None
