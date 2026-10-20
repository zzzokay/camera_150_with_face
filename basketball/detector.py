r"""
文件作用：本地 YOLO 单次推理、实际类别映射和高低置信候选；不下载权重。
调用入口：根 run.py；本文件是库模块，不直接执行。
输入/输出及边界：见公开类/函数的中文说明；坐标为全幅像素、时间为源秒，ID 是临时编号。
快速测试（PowerShell，项目根目录）：.\.venv\Scripts\python.exe -X utf8 -m pytest tests/test_detection_policy.py tests/test_tracker.py -q
预期输出：pytest 结果；日常运行结果在 configs/local.yaml 指定的输出目录。
排错：缺依赖用同一独立解释器安装 requirements-windows.lock.txt；输入/格式说明见 NEWCOMER_HANDOFF.md。
"""
import hashlib
import math
from dataclasses import asdict, replace
from pathlib import Path

from .contracts import Detection
from .detection_policy import DetectionPolicy, normalize_names, rejection_reason, resolve_class_ids


def validate_weights(path: Path) -> Path:
    """只接受存在的本地 .pt 文件；返回绝对路径，否则在导入 YOLO 前报错。"""
    path = path.expanduser().resolve()
    if path.suffix.lower() != ".pt":
        raise ValueError("Windows 后端需要本地 YOLO .pt；不接受 SAC .pth 或 RKNN .rknn。ONNX 尚未适配")
    if not path.is_file():
        raise FileNotFoundError(f"找不到 YOLO 权重：{path}；请提供真实 .pt，不会自动下载")
    return path


def resolve_person_ids(names: dict | list, aliases: tuple[str, ...]) -> tuple[dict[int, str], list[int]]:
    """从权重真实类别名找人物 ID；匹配不到就报错，绝不默认类别 0。"""
    mapping = normalize_names(names)
    normalized = {name.casefold().strip() for name in aliases}
    ids = [key for key, name in mapping.items() if name.casefold().strip() in normalized]
    if not ids:
        raise ValueError(f"模型类别 {mapping} 中找不到人物别名 {aliases}，请核实权重/配置")
    return mapping, ids


class YoloDetector:
    """一次推理筛选 person/可选 ball；last_rejections 保存本次真实候选排除原因。"""

    def __init__(self, weights: Path, device: str = "cpu", imgsz: int = 640,
                 iou: float = 0.7, policy: DetectionPolicy | None = None,
                 person_tracking_confidence: float | None = None):
        self.weights = validate_weights(weights)
        self.policy = policy or DetectionPolicy()
        if person_tracking_confidence is not None and not 0 < person_tracking_confidence < self.policy.person.confidence:
            raise ValueError('跟踪低阈值必须在 (0, person.confidence) 内')
        self.person_tracking_confidence = person_tracking_confidence
        from ultralytics import YOLO

        self.model = YOLO(str(self.weights), task="detect")
        if self.model.task != "detect":
            raise ValueError(f"需要 detect 检测权重，实际为 {self.model.task}")
        self.names, self.class_ids = resolve_class_ids(self.model.names, self.policy)
        self.person_ids = self.class_ids["person"]
        self.id_to_class = {i: name for name, ids in self.class_ids.items() for i in ids}
        self.device, self.imgsz = device, imgsz
        self.iou = iou
        self.confidence = min(getattr(self.policy, name).confidence for name in self.class_ids if self.class_ids[name])
        if person_tracking_confidence is not None:
            self.confidence = min(self.confidence, person_tracking_confidence)
        self.last_tracking_detections = []
        self.last_rejections = []
        self.last_candidate_counts = {"person": 0, "ball": 0}
        with self.weights.open("rb") as stream:
            self.sha256 = hashlib.file_digest(stream, "sha256").hexdigest()

    def detect(self, image_bgr, coord_system: str) -> list[Detection]:
        """返回筛选后真实观测；低于各类阈值/ROI/尺寸的候选记录原因，异常向上传播。"""
        results = self.model.predict(source=image_bgr, device=self.device, imgsz=self.imgsz,
                                     conf=self.confidence, iou=self.iou, classes=list(self.id_to_class),
                                     verbose=False, save=False, show=False)
        boxes = results[0].boxes
        self.last_rejections = []
        self.last_candidate_counts = {"person": 0, "ball": 0}
        self.last_tracking_detections = []
        detections = []
        if boxes is None:
            return detections
        h, w = image_bgr.shape[:2]
        for row in boxes.data.cpu().numpy():
            x1, y1, x2, y2, confidence, class_id = map(float, row[:6])
            if not all(math.isfinite(v) for v in (x1, y1, x2, y2, confidence, class_id)):
                raise ValueError("YOLO 返回非有限检测数值")
            name = self.id_to_class.get(int(class_id))
            if name is None:
                continue
            self.last_candidate_counts[name] += 1
            bbox = (max(0., min(w - 1., x1)), max(0., min(h - 1., y1)),
                    max(0., min(w - 1., x2)), max(0., min(h - 1., y2)))
            detection = Detection(name, int(class_id), confidence, bbox, coord_system)
            if name == 'person' and self.person_tracking_confidence is not None:
                # 仍使用同一 ROI/尺寸限制；低置信框只供 ByteTrack 续接，G1 接受阈值保持。
                low_rule = replace(self.policy.person, confidence=self.person_tracking_confidence)
                if rejection_reason(detection, low_rule, (w, h)) is None:
                    self.last_tracking_detections.append(detection)
            reason = rejection_reason(detection, getattr(self.policy, name), (w, h))
            if reason:
                self.last_rejections.append({**asdict(detection), "reason": reason})
            else:
                detections.append(detection)
        return sorted(detections, key=lambda d: d.confidence, reverse=True)
