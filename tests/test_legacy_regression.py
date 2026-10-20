"""
文件作用：证明 G0 共享模块只改变依赖加载方式，旧入口和算法保持兼容。
输入：上游固定 Git 版本、当前源码、明确合成的人物框序列；输出：pytest 断言。
依赖：pytest、OpenCV、NumPy、Git；不加载任何模型，不冒充真实视频效果。
运行：python -m pytest tests/test_legacy_regression.py -q。
"""
import ast
import importlib
import subprocess
import sys
from pathlib import Path

import numpy as np

from camera_150.camera_movement_modified import predict1_director as director
from camera_150.camera_movement_modified import predict1_weighted as weighted
from camera_150.camera_movement_modified import single_rknn_base as base
from camera_150.windows_pipeline import rendering
from camera_150.windows_pipeline.contracts import Detection
from camera_150.windows_pipeline.director_adapter import LegacyDirector


ROOT = Path(__file__).resolve().parents[1]
UPSTREAM = "5bd9c5a437536706f51106a5e86fbb2a7ec46906"
LEGACY = "camera_150/camera_movement_modified/"


def upstream(path):
    """只读取已取得的固定上游版本，不使用移动的远端 HEAD。"""
    return subprocess.check_output(["git", "show", f"{UPSTREAM}:{path}"], cwd=ROOT).decode("utf-8")


class IgnoreImportsAndDocs(ast.NodeTransformer):
    """剔除本次允许改变的导入/docstring，保留所有算法表达式、常量与分支。"""

    def visit_Import(self, node):
        return None

    def visit_ImportFrom(self, node):
        return None

    def visit_Expr(self, node):
        return None if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str) else self.generic_visit(node)

    def visit_If(self, node):
        if isinstance(node.test, ast.Name) and node.test.id == "__package__":
            return None
        return self.generic_visit(node)


def test_shared_algorithms_equal_upstream():
    for filename in ("single_rknn_base.py", "predict1_director.py", "predict1_weighted.py"):
        path = LEGACY + filename
        original = IgnoreImportsAndDocs().visit(ast.parse(upstream(path)))
        current = IgnoreImportsAndDocs().visit(ast.parse((ROOT / path).read_text(encoding="utf-8")))
        assert ast.dump(original) == ast.dump(current), filename


def test_original_entrypoints_untouched():
    for filename in ("single_rknn_director_view720_network_stream.py",
                     "single_rknn_director_view720_record_local.py",
                     "single_rknn_director_view1920_record_local.py", "director_game_policy.py", "audio_chain.py"):
        path = LEGACY + filename
        assert (ROOT / path).read_text(encoding="utf-8") == upstream(path)


def test_pure_render_helpers_equal_original():
    original_tree = ast.parse(upstream(LEGACY + "single_rknn_director_view720_record_local.py"))
    current_tree = ast.parse((ROOT / "camera_150/windows_pipeline/rendering.py").read_text(encoding="utf-8"))
    original_functions = {n.name: ast.dump(n) for n in original_tree.body if isinstance(n, ast.FunctionDef)}
    for node in current_tree.body:
        if isinstance(node, ast.FunctionDef):
            assert ast.dump(node) == original_functions[node.name]


def test_no_hardware_or_fake_modules_imported():
    importlib.import_module("camera_150.windows_pipeline.run")
    assert "rknnlite" not in sys.modules
    assert "predict1_yolo" not in sys.modules


def test_legacy_script_style_import():
    code = "import single_rknn_base,predict1_weighted,predict1_director; print('legacy imports OK')"
    result = subprocess.run([sys.executable, "-c", code], cwd=ROOT / LEGACY, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_adapter_matches_manual_original_chain():
    """180 帧合成左右移动、短时无人输入，逐帧核对旧跟踪/状态/裁切及像素。"""
    adapter = LegacyDirector(320, 180)
    smoother = base.SmoothTracks()
    analysis_state = weighted.init_single_view_state()
    state = director.init_overlay_director_state(640)
    frame = np.random.default_rng(20261020).integers(0, 255, (360, 640, 3), dtype=np.uint8)
    for index in range(180):
        center = 120 + (index if index < 90 else 180 - index) * 4
        boxes = [] if 75 <= index < 80 else [(center + k * 12, 145, center + k * 12 + 20, 290) for k in range(-3, 3)]
        detections = [Detection("person", 4, 0.9, box, "undistorted_full_frame_px") for box in boxes]
        image, crop, tracks, info = adapter.process(frame, detections)
        raw = [(4, 0.9, box) for box in boxes]
        expected_tracks = smoother.update(base.results_to_single_detections(raw))
        analysis = weighted.analyze_single_view_frame(rendering.single_detections_to_boxes_info(expected_tracks),
                                                      640, 360, analysis_state)
        expected_info = director.update_overlay_director_state(analysis, 640, 360, 320 / 180, state)
        expected_image, expected_crop = rendering.render_sample_director_view720(frame, expected_info, 320, 180)
        assert crop == expected_crop
        assert info == expected_info
        assert [track.track_id for track in tracks] == [track.track_id for track in expected_tracks]
        assert np.array_equal(image, expected_image)


def test_rknn_core_selection_and_constructor_still_import_real_runtime():
    """未安装 RKNN 的 Windows 上应显式报缺依赖，不能退化为假的检测器。"""
    import pytest

    with pytest.raises(ModuleNotFoundError, match="rknnlite"):
        base.get_core_mask(-1)
    with pytest.raises(ModuleNotFoundError, match="rknnlite"):
        base.PersonDetector("missing.rknn", "labels.txt", 0.35, 0.7)
