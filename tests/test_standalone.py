r"""
文件作用：验证无旧源码/无 Git 也能运行、可选模块惰性导入、严格配置及输出失败资源释放。
调用/快速测试：.\.venv\Scripts\python.exe -X utf8 -m pytest tests/test_standalone.py -q
输入：临时导出目录、合成视频和测试替身；无需模型，不用替身结果宣称真实推理通过。
输出：pytest 结果及临时产物；失败先查路径、模块导入或 summary 的 FAILED/error。
"""
import ast
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
import yaml

from basketball.config import RunConfig, load_config
from basketball.outputs import SavedVideo
from basketball.records import TrackingRecords

ROOT = Path(__file__).resolve().parents[1]


def clean_env():
    """子进程不继承源码搜索路径，验证导出目录真正可独立导入。"""
    env = os.environ.copy()
    env.pop('PYTHONPATH', None)
    return env


def test_no_old_imports_or_path_injection():
    for path in [ROOT / 'run.py', *(ROOT / 'basketball').rglob('*.py')]:
        tree = ast.parse(path.read_text(encoding='utf-8-sig'))
        for node in ast.walk(tree):
            names = [a.name for a in node.names] if isinstance(node, ast.Import) else [node.module or ''] if isinstance(node, ast.ImportFrom) else []
            assert not any(n.split('.')[0] in {'camera_150', 'rknnlite', 'PyQt5', 'windows_camera_150_client'} for n in names)
        assert 'sys.path.' not in path.read_text(encoding='utf-8-sig')


def test_optional_modules_not_imported_in_clean_process():
    code = "import basketball.pipeline,sys; assert not any(n in sys.modules for n in ['basketball.baseline','basketball.director','basketball.rules.analysis','basketball.rules.motion','camera_150','rknnlite'])"
    result = subprocess.run([sys.executable, '-X', 'utf8', '-c', code], cwd=ROOT,
                            env=clean_env(), capture_output=True, text=True, encoding='utf-8')
    assert result.returncode == 0, result.stderr


def test_export_without_old_sources_or_git(tmp_path):
    exported = tmp_path / '独立 Windows 工程'
    exported.mkdir()
    for name in ('run.py', 'pytest.ini'):
        shutil.copy2(ROOT / name, exported / name)
    for name in ('basketball', 'tests'):
        shutil.copytree(ROOT / name, exported / name, ignore=shutil.ignore_patterns('__pycache__'))
    assert not (exported / '.git').exists() and not (exported / 'camera_150').exists()
    help_result = subprocess.run([sys.executable, '-X', 'utf8', str(exported / 'run.py'), '--help'],
                                 cwd=tmp_path, env=clean_env(), capture_output=True, text=True, encoding='utf-8')
    assert help_result.returncode == 0, help_result.stderr
    # 不递归运行本测试；在导出目录运行有效的行为回归，不调用 git show 或旧源码。
    result = subprocess.run([sys.executable, '-X', 'utf8', '-m', 'pytest', 'tests/test_frozen_regression.py',
                             'tests/test_windows_components.py', 'tests/test_detection_policy.py', 'tests/test_tracker.py', '-q'],
                            cwd=exported, env=clean_env(), capture_output=True, text=True, encoding='utf-8')
    assert result.returncode == 0, result.stdout + result.stderr


def test_nested_template_and_strict_types(tmp_path):
    path = tmp_path / 'local.yaml'
    raw = {'schema_version': 'windows_run_config_v1', 'input': {'source': '比赛.mp4'}, 'model': {'weights': 'best.pt'}}
    path.write_text(yaml.safe_dump(raw), encoding='utf-8')
    config = load_config(['--config', str(path), '--max-frames', '48'])
    assert config.source == tmp_path / '比赛.mp4' and config.max_frames == 48
    assert config.mode == 'track' and not config.director_enabled and not config.baseline_enabled
    raw['tracking'] = {'track_buffer': True}
    path.write_text(yaml.safe_dump(raw), encoding='utf-8')
    with pytest.raises(ValueError, match='track_buffer'):
        load_config(['--config', str(path)])


def test_legacy_flat_config_has_migration_error(tmp_path):
    path = tmp_path / 'old.yaml'
    path.write_text('source: game.mp4\nweights: best.pt\n', encoding='utf-8')
    with pytest.raises(ValueError, match='迁移'):
        load_config(['--config', str(path)])


def test_disabled_baseline_does_not_create_empty_csv(tmp_path):
    with TrackingRecords(tmp_path) as records:
        assert records.baseline_enabled is False
    assert (tmp_path / 'bytetrack_qc.csv').exists()
    assert not (tmp_path / 'smoothtracks_qc.csv').exists()


def test_write_failure_is_reported_and_resources_close(tmp_path, monkeypatch):
    from basketball import pipeline
    source_path = tmp_path / 'input.mp4'
    with SavedVideo(source_path, 30., (160, 90)) as writer:
        for _ in range(3):
            writer.write(np.zeros((90, 160, 3), dtype=np.uint8))
    weights = tmp_path / 'synthetic.pt'
    weights.write_bytes(b'not a model; detector is explicitly replaced in resource-failure test')
    fake = SimpleNamespace(weights=weights, sha256='synthetic', names={7: 'person'}, person_ids=[7],
                           class_ids={'person': [7], 'ball': []}, confidence=.35,
                           last_candidate_counts={'person': 0, 'ball': 0}, last_rejections=[],
                           detect=lambda *args: [])
    monkeypatch.setattr(pipeline, 'YoloDetector', lambda *args, **kwargs: fake)
    original_video_exit = pipeline.SavedVideo.__exit__
    original_source_exit = pipeline.VideoSource.__exit__
    closed = []

    def close_video(self, *args):
        closed.append('video')
        original_video_exit(self, *args)

    def close_source(self, *args):
        closed.append('source')
        original_source_exit(self, *args)

    def fail_write(self, frame):
        raise OSError('simulated disk write failure')

    monkeypatch.setattr(pipeline.SavedVideo, 'write', fail_write)
    monkeypatch.setattr(pipeline.SavedVideo, '__exit__', close_video)
    monkeypatch.setattr(pipeline.VideoSource, '__exit__', close_source)
    with pytest.raises(OSError, match='simulated disk'):
        pipeline.run_pipeline(RunConfig(source=source_path, weights=weights, output_dir=tmp_path / 'out', mode='detect'))
    assert closed == ['video', 'source']
    report = json.loads(next((tmp_path / 'out').glob('*/summary.json')).read_text(encoding='utf-8'))
    assert report['status'] == 'FAILED' and 'simulated disk' in report['error']
