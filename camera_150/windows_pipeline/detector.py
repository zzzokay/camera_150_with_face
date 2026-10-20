"""
文件作用：Windows 真实 YOLO 推理及 G1 类别筛选，保留 G0 人物检测接口。
输入：全幅 BGR、DetectionPolicy；输出：真实 Detection 与可解释排除记录。
依赖：Ultralytics/PyTorch；调用：run -> YoloDetector -> 原人物导播适配器。
注意：篮球默认关闭，一帧只推理一次；不补球、不调用 model.track。
运行示例：见 NEWCOMER_HANDOFF.md；本组件不会自动下载权重。
"""
import hashlib
import math
from dataclasses import asdict
from pathlib import Path

from .contracts import Detection
from .detection_policy import ClassPolicy, DetectionPolicy, normalize_names, rejection_reason, resolve_class_ids


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
                 iou: float = 0.7, policy: DetectionPolicy | None = None):
        self.weights = validate_weights(weights)
        self.policy = policy or DetectionPolicy()
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
            reason = rejection_reason(detection, getattr(self.policy, name), (w, h))
            if reason:
                self.last_rejections.append({**asdict(detection), "reason": reason})
            else:
                detections.append(detection)
        return sorted(detections, key=lambda d: d.confidence, reverse=True)


class YoloPersonDetector(YoloDetector):
    """G0 兼容构造器：参数与返回值保持，篮球关闭，不增加区域/尺寸限制。"""

    def __init__(self, weights: Path, device: str = "cpu", imgsz: int = 640,
                 confidence: float = .35, iou: float = .7,
                 person_aliases: tuple[str, ...] = ("person", "player")):
        super().__init__(weights, device, imgsz, iou,
                         DetectionPolicy(person=ClassPolicy(person_aliases, confidence=confidence)))
