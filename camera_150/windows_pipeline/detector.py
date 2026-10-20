"""
文件作用：用真实本地 YOLO .pt 权重进行 Windows 人物检测，输出原广角帧像素框。
输入：BGR 完整帧与推理参数；输出：真实 Detection 列表及权重内 names 类别表。
依赖：Ultralytics/PyTorch；调用关系：run -> YoloPersonDetector -> 原规则适配器。
注意：G0 复用人物导播；双类别质量验收留待 G1。禁止把 SAC .pth 当 YOLO。
运行示例：见 NEWCOMER_HANDOFF.md；本组件不会自动下载权重。
"""
import hashlib
import math
from pathlib import Path

from .contracts import Detection


def validate_weights(path: Path) -> Path:
    """只接受存在的本地 .pt 文件；返回绝对路径，否则在导入 YOLO 前报错。"""
    path = path.expanduser().resolve()
    if path.suffix.lower() != ".pt":
        raise ValueError("G0 后端需要本地 YOLO .pt；不接受 SAC .pth 或 RKNN .rknn。ONNX 尚未适配")
    if not path.is_file():
        raise FileNotFoundError(f"找不到 YOLO 权重：{path}；请提供真实 .pt，不会自动下载")
    return path


def resolve_person_ids(names: dict | list, aliases: tuple[str, ...]) -> tuple[dict[int, str], list[int]]:
    """从权重真实类别名找人物 ID；匹配不到就报错，绝不默认类别 0。"""
    names = dict(enumerate(names)) if isinstance(names, list) else names
    if not isinstance(names, dict) or not names:
        raise ValueError("权重没有有效 names 类别表")
    mapping = {int(k): str(v) for k, v in names.items()}
    normalized = {name.casefold().strip() for name in aliases}
    ids = [key for key, name in mapping.items() if name.casefold().strip() in normalized]
    if not ids:
        raise ValueError(f"模型类别 {mapping} 中找不到人物别名 {aliases}，请核实权重/配置")
    return mapping, ids


class YoloPersonDetector:
    """一帧一次真实 YOLO 推理；不调用 model.track，不引入 G2 跟踪器。"""

    def __init__(self, weights: Path, device: str = "cpu", imgsz: int = 640,
                 confidence: float = 0.35, iou: float = 0.7,
                 person_aliases: tuple[str, ...] = ("person", "player")):
        self.weights = validate_weights(weights)
        from ultralytics import YOLO

        self.model = YOLO(str(self.weights), task="detect")
        if self.model.task != "detect":
            raise ValueError(f"需要 detect 检测权重，实际为 {self.model.task}")
        self.names, self.person_ids = resolve_person_ids(self.model.names, person_aliases)
        self.device, self.imgsz = device, imgsz
        self.confidence, self.iou = confidence, iou
        with self.weights.open("rb") as stream:
            self.sha256 = hashlib.file_digest(stream, "sha256").hexdigest()

    def detect(self, image_bgr, coord_system: str) -> list[Detection]:
        """返回本帧真实人物框（像素）；推理失败向上传播，不能伪装成无人。"""
        results = self.model.predict(source=image_bgr, device=self.device, imgsz=self.imgsz,
                                     conf=self.confidence, iou=self.iou, classes=self.person_ids,
                                     verbose=False, save=False, show=False)
        boxes = results[0].boxes
        detections = []
        if boxes is None:
            return detections
        h, w = image_bgr.shape[:2]
        for row in boxes.data.cpu().numpy():
            x1, y1, x2, y2, confidence, class_id = map(float, row[:6])
            if not all(math.isfinite(v) for v in (x1, y1, x2, y2, confidence, class_id)):
                raise ValueError("YOLO 返回非有限检测数值")
            if int(class_id) not in self.person_ids:
                continue
            bbox = (max(0., min(w - 1., x1)), max(0., min(h - 1., y1)),
                    max(0., min(w - 1., x2)), max(0., min(h - 1., y2)))
            if bbox[2] > bbox[0] and bbox[3] > bbox[1]:
                detections.append(Detection("person", int(class_id), confidence, bbox, coord_system))
        return sorted(detections, key=lambda d: d.confidence, reverse=True)
