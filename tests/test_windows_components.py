r"""
文件作用：Windows test_windows_components 的行为测试；合成输入不作为真实比赛精度证据。
调用/快速测试（PowerShell）：.\.venv\Scripts\python.exe -X utf8 -m pytest tests/test_windows_components.py -q
输入：测试内说明的合成数据/临时路径；真实模型测试另需设置 BASKETBALL_TEST_WEIGHTS 与 BASKETBALL_TEST_VIDEO。
预期输出：pytest 结果及临时目录产物；失败查看断言、依赖版本与 NEWCOMER_HANDOFF.md。
"""
from pathlib import Path

import cv2
import numpy as np
import pytest

from basketball.config import load_config
from basketball.detector import resolve_person_ids, validate_weights
from basketball.outputs import SavedVideo, verify_video
from basketball.preprocessing import FramePreprocessor
from basketball.sources import VideoSource


@pytest.mark.parametrize("codec,suffix", [("mp4v", ".mp4"), ("MJPG", ".avi")])
def test_video_codec_unicode_and_timestamps(tmp_path, codec, suffix):
    directory = tmp_path / "中文 空格"
    path = directory / ("彩条" + suffix)
    with SavedVideo(path, 25., (160, 90), codec) as writer:
        for index in range(12):
            writer.write(np.full((90, 160, 3), index * 15, dtype=np.uint8))
    result = verify_video(path, 12, (160, 90))
    assert abs(result["fps"] - 25) < 0.01
    with VideoSource(path) as source:
        packets = []
        while (packet := source.read()) is not None:
            packets.append(packet)
    assert [p.source_frame_idx for p in packets] == list(range(12))
    assert [p.timestamp_sec for p in packets] == pytest.approx(np.arange(12) / 25.)
    assert all(p.timestamp_basis in ("container_pts", "source_frame_idx/fps") for p in packets)


def test_output_rejects_overwrite_and_shape(tmp_path):
    path = tmp_path / "out.mp4"
    with SavedVideo(path, 30., (160, 90)) as writer:
        with pytest.raises(ValueError, match="尺寸"):
            writer.write(np.zeros((90, 158, 3), dtype=np.uint8))
        writer.write(np.zeros((90, 160, 3), dtype=np.uint8))
    with pytest.raises(FileExistsError):
        SavedVideo(path, 30., (160, 90))
    with pytest.raises(RuntimeError, match="帧数"):
        verify_video(path, 2, (160, 90))


def test_config_paths_relative_to_yaml_not_cwd(tmp_path, monkeypatch):
    path = tmp_path / "中文 配置" / "local.yaml"
    path.parent.mkdir()
    path.write_text("schema_version: windows_run_config_v1\ninput:\n  source: game.mp4\n  undistort: already\nmodel:\n  weights: model.pt\noutput:\n  directory: outputs\n", encoding="utf-8")
    monkeypatch.chdir(Path.home())
    config = load_config(["--config", str(path), "--detect-interval", "1"])
    assert config.source == path.parent / "game.mp4"
    assert config.weights == path.parent / "model.pt"
    assert config.output_dir == path.parent / "outputs"
    assert config.detect_interval == 1
    assert config.device == "cpu"


@pytest.mark.parametrize("args", [[], ["--source", "a.mp4", "--camera", "0"],
    ["--source", "a.mp4", "--weights", "a.pt", "--detect-interval", "0"],
    ["--source", "a.mp4", "--weights", "a.pt", "--fps", "nan"],
    ["--source", "a.mp4", "--weights", "a.pt", "--start-seconds", "-1"],
    ["--source", "a.mp4", "--weights", "a.pt", "--start-seconds", "nan"],
    ["--source", "a.mp4", "--weights", "a.pt", "--start-seconds", "inf"],
    ["--camera", "0", "--weights", "a.pt", "--start-seconds", "30"],
    ["--source", "a.mp4", "--weights", "a.pt", "--undistort", "calibration"]])
def test_invalid_config_rejected(args):
    with pytest.raises(ValueError):
        load_config(args)


def test_unknown_yaml_field_rejected(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text("detect_interva: 3", encoding="utf-8")
    with pytest.raises(ValueError, match="未知配置"):
        load_config(["--config", str(path)])


def test_classes_come_from_names():
    names, ids = resolve_person_ids({7: "Player", 2: "basketball"}, ("person", "player"))
    assert names[7] == "Player" and ids == [7]
    with pytest.raises(ValueError, match="找不到人物"):
        resolve_person_ids({0: "basketball"}, ("person", "player"))


def test_no_automatic_weights_download(tmp_path):
    with pytest.raises(FileNotFoundError):
        validate_weights(tmp_path / "yolo11n.pt")
    with pytest.raises(ValueError, match="SAC"):
        validate_weights(tmp_path / "policy.pth")


def test_preprocessing_identity_and_strict_calibration(tmp_path):
    frame = np.zeros((90, 160, 3), dtype=np.uint8)
    for mode in ("none", "already"):
        assert FramePreprocessor(mode).apply(frame) is frame
    assert FramePreprocessor("none").coord_system == "raw_full_frame_px"
    path = tmp_path / "calib.npz"
    matrix = np.array([[100., 0., 80.], [0., 100., 45.], [0., 0., 1.]])
    np.savez(path, camera_matrix=matrix, dist_coeffs=np.zeros(5), new_camera_matrix=matrix,
             image_size=np.array([160, 90]))
    processor = FramePreprocessor("calibration", path)
    assert np.array_equal(processor.apply(frame), frame)
    with pytest.raises(ValueError, match="标定"):
        processor.apply(np.zeros((180, 320, 3), dtype=np.uint8))


def test_empty_or_missing_video_is_not_success(tmp_path):
    with pytest.raises(FileNotFoundError):
        with VideoSource(tmp_path / "missing.mp4"):
            pass
