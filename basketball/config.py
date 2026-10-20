r"""
文件作用：读取唯一日常 YAML、合并 CLI，并校验 Windows 检测/跟踪运行参数。
调用入口：run.py；本文件是库模块，不直接执行。相对 YAML 路径以其目录为准，CLI 路径以终端目录为准。
输入：windows_run_config_v1 YAML/命令行；输出：RunConfig，含实际生效的检测/跟踪规则。
快速测试：.\.venv\Scripts\python.exe -X utf8 -m pytest tests/test_windows_components.py tests/test_standalone.py -q
预期输出：配置与路径测试通过；实际配置保存在运行 summary.json。
排错：旧 G0/G1/G2 配置请按 configs/local.example.yaml 迁移；未知字段报错，不悄悄使用默认值。
"""
import argparse
import math
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Sequence

import yaml

from .detection_policy import DetectionPolicy, policy_from_mapping, validate_policy
from .tracker import TrackerConfig, validate_tracker_config


@dataclass(frozen=True)
class RunConfig:
    """内部扁平运行参数；对外 YAML 按职责分组，宽高/距离为像素、时间为秒。"""
    source: Path | None = None
    camera: int | None = None
    weights: Path | None = None
    output_dir: Path = Path(__file__).resolve().parents[1] / 'runs'
    mode: str = 'track'
    undistort: str = 'none'
    calib_file: Path | None = None
    backend: str = 'auto'
    fps: float | None = None
    camera_width: int = 1920
    camera_height: int = 1080
    device: str = 'cpu'
    imgsz: int = 640
    iou: float = .7
    detect_interval: int = 1
    smooth: float = .65
    max_match_dist: float = 180.
    max_missing: int = 15
    view_width: int = 1280
    view_height: int = 720
    codec: str = 'mp4v'
    preview: bool = False
    debug_video: bool = True
    export_detections: bool = True
    director_enabled: bool = False
    baseline_enabled: bool = False
    start_seconds: float = 0.
    max_frames: int = 0
    detection: DetectionPolicy = field(default_factory=DetectionPolicy)
    tracking: TrackerConfig = field(default_factory=TrackerConfig)
    check_env: bool = False
    check_camera: bool = False
    report_path: Path | None = None

    def serializable(self) -> dict:
        """返回实际内部参数；路径转为字符串，规则 dataclass 转为具名字段。"""
        return {k: str(v) if isinstance(v, Path) else v for k, v in asdict(self).items()}


# 只做字段映射，不引入另一套配置对象层。外部名称与内部历史字段对应关系固定在这里。
GROUPS = {
    'input': {'source': 'source', 'camera': 'camera', 'backend': 'backend', 'fps': 'fps',
              'width': 'camera_width', 'height': 'camera_height', 'undistort': 'undistort',
              'calib_file': 'calib_file', 'start_seconds': 'start_seconds', 'max_frames': 'max_frames'},
    'model': {'weights': 'weights', 'device': 'device', 'imgsz': 'imgsz', 'iou': 'iou', 'detect_interval': 'detect_interval'},
    'director': {'enabled': 'director_enabled', 'width': 'view_width', 'height': 'view_height'},
    'baseline': {'enabled': 'baseline_enabled', 'smooth': 'smooth', 'max_match_dist': 'max_match_dist', 'max_missing': 'max_missing'},
    'output': {'directory': 'output_dir', 'codec': 'codec', 'preview': 'preview',
               'overview': 'debug_video', 'export_detections': 'export_detections'},
}
PATH_FIELDS = {'source', 'weights', 'output_dir', 'calib_file', 'report_path'}


def load_config(argv: Sequence[str] | None = None) -> RunConfig:
    """无文件也可用 CLI；读取配置不加载模型、不打开相机、不安装依赖。"""
    parser = argparse.ArgumentParser(description='Windows 篮球 YOLO 检测 / ByteTrack 跟踪与视频、QC 导出')
    parser.add_argument('--config', type=Path)
    for name in PATH_FIELDS:
        parser.add_argument('--' + name.replace('_', '-'), type=Path)
    parser.add_argument('--mode', choices=('track', 'detect'))
    parser.add_argument('--undistort', choices=('none', 'already', 'calibration'))
    parser.add_argument('--backend', choices=('auto', 'dshow', 'msmf', 'ffmpeg'))
    parser.add_argument('--codec', choices=('mp4v', 'MJPG'))
    parser.add_argument('--device')
    for name in ('camera', 'imgsz', 'detect_interval', 'max_frames', 'camera_width', 'camera_height'):
        parser.add_argument('--' + name.replace('_', '-'), type=int)
    for name in ('fps', 'iou', 'start_seconds'):
        parser.add_argument('--' + name.replace('_', '-'), type=float)
    for flag, dest in [('preview', 'preview'), ('debug-video', 'debug_video'),
                       ('director', 'director_enabled'), ('baseline', 'baseline_enabled')]:
        parser.add_argument('--' + flag, dest=dest, action=argparse.BooleanOptionalAction, default=None)
    actions = parser.add_mutually_exclusive_group()
    actions.add_argument('--check-env', action='store_true')
    actions.add_argument('--check-camera', action='store_true')
    cli = vars(parser.parse_args(argv))
    config_path = cli.pop('config')
    data = {}
    if config_path:
        config_path = config_path.expanduser().resolve()
        with config_path.open(encoding='utf-8-sig') as stream:
            raw = yaml.safe_load(stream)
        if not isinstance(raw, dict):
            raise ValueError('配置必须是 YAML 字典')
        allowed = set(GROUPS) | {'schema_version', 'mode', 'detection', 'tracking'}
        if set(raw) - allowed:
            raise ValueError(f'未知配置字段：{sorted(set(raw) - allowed)}；请迁移至 configs/local.example.yaml')
        if raw.get('schema_version') != 'windows_run_config_v1':
            raise ValueError('配置版本必须为 windows_run_config_v1；旧配置请按 local.example.yaml 迁移')
        if 'mode' in raw:
            data['mode'] = raw['mode']
        for group, mapping in GROUPS.items():
            values = raw.get(group, {})
            if not isinstance(values, dict) or set(values) - set(mapping):
                raise ValueError(f'未知配置字段或错误格式：{group}')
            for name, value in values.items():
                key = mapping[name]
                if key in PATH_FIELDS and value is not None:
                    value = (config_path.parent / Path(value).expanduser()).resolve()
                data[key] = value
        if 'detection' in raw:
            data['detection'] = policy_from_mapping(raw['detection'])
        if 'tracking' in raw:
            values = raw['tracking']
            if not isinstance(values, dict) or set(values) - set(TrackerConfig.__dataclass_fields__):
                raise ValueError('tracking 配置含未知字段或格式错误')
            data['tracking'] = TrackerConfig(**values)
    for key, value in cli.items():
        if value is not None:
            data[key] = value.expanduser().resolve() if key in PATH_FIELDS else value
    config = RunConfig(**data)
    if config.check_camera and config.camera is None:
        config = replace(config, source=None, camera=0, start_seconds=0.)
    validate_config(config)
    return config


def validate_config(config: RunConfig) -> None:
    """拒绝无效单位/类型、输入歧义与跟踪复用；文件存在性交给对应组件。"""
    diagnostic = config.check_env or config.check_camera
    if not diagnostic and (config.source is None) == (config.camera is None):
        raise ValueError('必须且只能指定 --source 视频路径或 --camera 摄像头编号')
    if not diagnostic and config.weights is None:
        raise ValueError('缺少 --weights：请指定真实 YOLO .pt 权重，不能使用 SAC policy.pth')
    if config.mode not in ('track', 'detect'):
        raise ValueError('mode 必须为 track 或 detect')
    for name in ('start_seconds', 'iou', 'smooth', 'max_match_dist'):
        v = getattr(config, name)
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
            raise ValueError(f'{name} 必须是有限数值')
    if config.start_seconds < 0 or not 0 < config.iou <= 1 or not 0 < config.smooth <= .98 or config.max_match_dist <= 0:
        raise ValueError('start_seconds 非负；iou 在 (0,1]；smooth 在 (0,.98]；关联距离为正')
    for name in ('imgsz', 'detect_interval', 'view_width', 'view_height', 'camera_width', 'camera_height'):
        v = getattr(config, name)
        if isinstance(v, bool) or not isinstance(v, int) or v <= 0:
            raise ValueError(f'{name} 必须为正整数')
    for name in ('max_frames', 'max_missing', 'camera'):
        v = getattr(config, name)
        if v is not None and (isinstance(v, bool) or not isinstance(v, int) or v < 0):
            raise ValueError(f'{name} 必须为非负整数')
    if config.view_width % 2 or config.view_height % 2:
        raise ValueError('导播输出宽高必须为偶数')
    if config.fps is not None and (isinstance(config.fps, bool) or not isinstance(config.fps, (int, float)) or not math.isfinite(config.fps) or config.fps <= 0):
        raise ValueError('fps 必须为有限正数')
    for name in ('preview', 'debug_video', 'export_detections', 'director_enabled', 'baseline_enabled'):
        if not isinstance(getattr(config, name), bool):
            raise ValueError(f'{name} 必须为 true 或 false')
    if config.camera is not None and config.start_seconds:
        raise ValueError('start_seconds 仅用于视频文件')
    if config.undistort not in ('none', 'already', 'calibration') or (config.undistort == 'calibration') != (config.calib_file is not None):
        raise ValueError('仅 undistort=calibration 时必须提供 calib_file，避免二次去畸变')
    if config.backend not in ('auto', 'dshow', 'msmf', 'ffmpeg') or config.codec not in ('mp4v', 'MJPG'):
        raise ValueError('不支持的捕获后端或编码器')
    if config.source is not None and config.backend in ('dshow', 'msmf'):
        raise ValueError('视频文件应使用 auto 或 ffmpeg')
    if config.camera is not None and config.backend == 'ffmpeg':
        raise ValueError('摄像头应使用 auto/dshow/msmf')
    validate_policy(config.detection)
    if config.detection.ball.enabled:
        raise ValueError('篮球模型尚未提供，本轮保持 ball.enabled=false')
    if config.baseline_enabled and config.mode != 'track':
        raise ValueError('旧关联对照仅供 track 模式，与 ByteTrack 比较')
    if config.mode == 'track':
        validate_tracker_config(config.tracking)
        if config.detect_interval != 1:
            raise ValueError('ByteTrack 要求 detect_interval=1；不能把复用检测当新观测')
        if abs(config.detection.person.confidence - config.tracking.track_high_thresh) > 1e-8:
            raise ValueError('person.confidence 必须与 track_high_thresh 一致')
