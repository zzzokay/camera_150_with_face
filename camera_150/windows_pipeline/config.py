"""
文件作用：合并 G0/G1 YAML/CLI 配置，校验范围和 Windows 路径。
输入：命令行列表和可选 YAML；输出：RunConfig；错误配置抛出 ValueError。
依赖：pathlib、argparse、PyYAML；调用关系：run.main -> load_config。
注意：YAML 内相对路径以 YAML 所在目录为基准，CLI 路径以调用者目录为基准。
运行示例：python run_windows.py --help。
"""
import argparse
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Sequence

import yaml


@dataclass(frozen=True)
class RunConfig:
    """G0 参数；宽高为像素，start_seconds 为源时间秒数，max_frames=0 表示读到结尾。"""

    source: Path | None = None
    camera: int | None = None
    weights: Path | None = None
    output_dir: Path = Path(__file__).resolve().parents[2] / "runs"
    undistort: str = "none"
    calib_file: Path | None = None
    backend: str = "auto"
    fps: float | None = None
    camera_width: int = 1920
    camera_height: int = 1080
    device: str = "cpu"
    imgsz: int = 640
    confidence: float = 0.35
    iou: float = 0.7
    person_aliases: tuple[str, ...] = ("person", "player")
    detect_interval: int = 3
    smooth: float = 0.65
    max_match_dist: float = 180.0
    max_missing: int = 15
    view_width: int = 1280
    view_height: int = 720
    codec: str = "mp4v"
    preview: bool = False
    debug_video: bool = True
    start_seconds: float = 0.0
    max_frames: int = 0
    game_state: Path | None = None
    detection_policy: Path | None = None
    export_detections: bool = False

    def serializable(self) -> dict:
        """返回可写入运行报告的配置；路径保持可追溯绝对值。"""
        return {k: str(v) if isinstance(v, Path) else v for k, v in asdict(self).items()}


PATH_FIELDS = ("source", "weights", "output_dir", "calib_file", "game_state", "detection_policy")


def load_config(argv: Sequence[str] | None = None) -> RunConfig:
    """读取配置并校验；不打开摄像头、不下载或加载模型。"""
    parser = argparse.ArgumentParser(description="Windows YOLO -> 原规则导播 -> 视频/可选 G1 检测记录")
    parser.add_argument("--config", type=Path)
    for name in PATH_FIELDS:
        parser.add_argument("--" + name.replace("_", "-"), type=Path)
    for name in ("camera", "imgsz", "detect_interval", "max_missing", "view_width", "view_height",
                 "max_frames", "camera_width", "camera_height"):
        parser.add_argument("--" + name.replace("_", "-"), type=int)
    for name in ("fps", "confidence", "iou", "smooth", "max_match_dist", "start_seconds"):
        parser.add_argument("--" + name.replace("_", "-"), type=float)
    parser.add_argument("--undistort", choices=("none", "already", "calibration"))
    parser.add_argument("--backend", choices=("auto", "dshow", "msmf", "ffmpeg"))
    parser.add_argument("--device")
    parser.add_argument("--codec", choices=("mp4v", "MJPG"))
    parser.add_argument("--person-aliases", nargs="+")
    for name in ("preview", "debug_video", "export_detections"):
        parser.add_argument("--" + name.replace("_", "-"), action=argparse.BooleanOptionalAction, default=None)
    cli = vars(parser.parse_args(argv))
    config_path = cli.pop("config")
    data = {}
    if config_path:
        config_path = config_path.expanduser().resolve()
        with config_path.open(encoding="utf-8-sig") as stream:
            data = yaml.safe_load(stream) or {}
        if not isinstance(data, dict):
            raise ValueError("YAML 顶层必须是参数字典")
        unknown = set(data) - set(RunConfig.__dataclass_fields__)
        if unknown:
            raise ValueError(f"未知配置参数：{sorted(unknown)}")
        for name in PATH_FIELDS:
            if data.get(name) is not None:
                path = Path(data[name]).expanduser()
                data[name] = (config_path.parent / path).resolve()
    for name, value in cli.items():
        if value is not None:
            data[name] = value.expanduser().resolve() if name in PATH_FIELDS else value
    if "person_aliases" in data:
        if not isinstance(data["person_aliases"], (list, tuple)):
            raise ValueError("person_aliases 必须是名称列表，例如 [person, player]")
        data["person_aliases"] = tuple(str(v).strip().casefold() for v in data["person_aliases"])
    config = RunConfig(**data)
    validate_config(config)
    return config


def validate_config(config: RunConfig) -> None:
    """检查互斥输入及数值范围；文件存在性留给对应组件报告。"""
    import math

    if (config.source is None) == (config.camera is None):
        raise ValueError("必须且只能指定 --source 视频路径或 --camera 摄像头编号")
    if config.camera is not None and config.camera < 0:
        raise ValueError("camera 必须是非负编号")
    if not math.isfinite(config.start_seconds) or config.start_seconds < 0:
        raise ValueError("start_seconds 必须是有限非负秒数")
    if config.camera is not None and config.start_seconds:
        raise ValueError("start_seconds 仅用于视频文件，不用于摄像头")
    if config.weights is None:
        raise ValueError("缺少 --weights：请指定真实 YOLO .pt 权重，不能使用 SAC policy.pth")
    if config.undistort not in ("none", "already", "calibration"):
        raise ValueError("undistort 必须为 none / already / calibration")
    if (config.undistort == "calibration") != (config.calib_file is not None):
        raise ValueError("仅 undistort=calibration 时必须提供 calib_file，避免误用/二次去畸变")
    if config.backend not in ("auto", "dshow", "msmf", "ffmpeg") or config.codec not in ("mp4v", "MJPG"):
        raise ValueError("不支持的捕获后端或编码器")
    if config.source is not None and config.backend in ("dshow", "msmf"):
        raise ValueError("视频文件应使用 auto 或 ffmpeg，dshow/msmf 用于摄像头")
    if config.camera is not None and config.backend == "ffmpeg":
        raise ValueError("摄像头编号应使用 auto/dshow/msmf")
    for name in ("confidence", "iou", "smooth", "max_match_dist"):
        if not math.isfinite(getattr(config, name)):
            raise ValueError(f"{name} 必须是有限数值")
    if not 0 < config.confidence <= 1 or not 0 < config.iou <= 1 or not 0 <= config.smooth <= 0.98:
        raise ValueError("confidence/iou 必须在 (0,1]，smooth 在 [0,0.98]")
    if config.max_match_dist <= 0 or config.max_missing < 0 or not config.person_aliases:
        raise ValueError("跟踪距离必须为正，max_missing 非负，person_aliases 非空")
    for name in ("imgsz", "detect_interval", "view_width", "view_height", "camera_width", "camera_height"):
        if getattr(config, name) <= 0:
            raise ValueError(f"{name} 必须为正整数")
    if config.view_width % 2 or config.view_height % 2 or config.max_frames < 0:
        raise ValueError("输出宽高必须为偶数，max_frames 必须非负")
    if config.fps is not None and (not math.isfinite(config.fps) or config.fps <= 0):
        raise ValueError("fps 必须是有限正数；视频文件仅在 FPS 元数据无效时使用它")
    if any(not isinstance(getattr(config, name), bool) for name in ("preview", "debug_video", "export_detections")):
        raise ValueError("preview/debug_video/export_detections 必须为 true 或 false")
