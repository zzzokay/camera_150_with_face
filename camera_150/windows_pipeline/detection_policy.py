"""
文件作用：定义 G1 人物/篮球类别、阈值、尺寸及 ROI 筛选，默认保留 G0 人物行为。
输入：可选 YAML、真实模型 names、Detection；输出：标准类别 ID 和排除原因。
坐标：尺寸/ROI 是全幅 [0,1] 比例，人物用框底部中心，篮球用框中心。
依赖：PyYAML/OpenCV；调用：run/detector。ROI 不识别身份，篮球默认关闭。
运行示例：见 NEWCOMER_HANDOFF.md 的 G1 入口。
"""
import math
from dataclasses import asdict, dataclass, replace
from pathlib import Path

import cv2
import numpy as np
import yaml

from .contracts import Detection


def finite_number(value) -> bool:
    """仅接受有限数字，排除 YAML 字符串、null 和作为整数子类的 bool。"""
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


@dataclass(frozen=True)
class ClassPolicy:
    """单类规则；宽高为全幅比例，ROI=None 不做区域筛选。"""

    aliases: tuple[str, ...]
    enabled: bool = True
    confidence: float = 0.35
    min_size_wh: tuple[float, float] = (0., 0.)
    max_size_wh: tuple[float, float] = (1., 1.)
    roi_polygon: tuple[tuple[float, float], ...] | None = None


@dataclass(frozen=True)
class DetectionPolicy:
    """标准名 person/ball；disabled 的篮球即使在模型中存在也不启用。"""

    person: ClassPolicy = ClassPolicy(("person", "player"))
    ball: ClassPolicy = ClassPolicy(("sports ball", "ball", "basketball"), False, 0.20)

    def serializable(self) -> dict:
        """输出实际配置，供报告复现，不代表模型有效性。"""
        return {"schema_version": "g1_detection_policy_v1", **asdict(self)}


def validate_policy(policy: DetectionPolicy) -> None:
    """拒绝非法范围、歧义别名及非凸/零面积 ROI；边界点算保留。"""
    aliases_seen = set()
    for name in ("person", "ball"):
        rule = getattr(policy, name)
        if not isinstance(rule.enabled, bool) or (name == "person" and not rule.enabled):
            raise ValueError("person 必须启用，enabled 必须为布尔值")
        if not isinstance(rule.aliases, (tuple, list)) or not rule.aliases or any(not isinstance(a, str) or not a.strip() for a in rule.aliases):
            raise ValueError(f"{name}.aliases 必须为非空名称列表")
        aliases = {a.strip().casefold() for a in rule.aliases}
        if aliases & aliases_seen:
            raise ValueError("person 与 ball 的别名不能重叠")
        aliases_seen |= aliases
        if not finite_number(rule.confidence) or not 0 < rule.confidence <= 1:
            raise ValueError(f"{name}.confidence 必须在 (0,1]")
        for pair in (rule.min_size_wh, rule.max_size_wh):
            if not isinstance(pair, (tuple, list)) or len(pair) != 2 or any(not finite_number(v) or not 0 <= v <= 1 for v in pair):
                raise ValueError(f"{name} 尺寸必须是两个 [0,1] 比例")
        if any(low > high for low, high in zip(rule.min_size_wh, rule.max_size_wh)):
            raise ValueError(f"{name} 最小尺寸不能大于最大尺寸")
        if rule.roi_polygon is not None:
            points = rule.roi_polygon
            if not isinstance(points, (tuple, list)) or len(points) < 3 or any(not isinstance(p, (tuple, list)) or len(p) != 2 or any(not finite_number(v) or not 0 <= v <= 1 for v in p) for p in points):
                raise ValueError(f"{name}.roi_polygon 至少含三个 [x,y] 比例点")
            contour = np.asarray(points, dtype=np.float32)
            if not cv2.isContourConvex(contour) or abs(cv2.contourArea(contour)) < 1e-8:
                raise ValueError(f"{name}.roi_polygon 必须是按边界顺序排列的非零面积凸多边形")


def load_detection_policy(path: Path | None, confidence: float = .35,
                          person_aliases: tuple[str, ...] = ("person", "player")) -> DetectionPolicy:
    """无文件时复用 G0 阈值/别名；文件只覆盖明示字段，未知字段报错。"""
    policy = DetectionPolicy(person=ClassPolicy(person_aliases, confidence=confidence))
    if path is not None:
        with path.open(encoding="utf-8-sig") as stream:
            data = yaml.safe_load(stream)
        if not isinstance(data, dict) or set(data) - {"schema_version", "person", "ball"}:
            raise ValueError("检测策略必须为字典且只含 schema_version/person/ball")
        if data.get("schema_version") != "g1_detection_policy_v1":
            raise ValueError("检测策略 schema_version 必须为 g1_detection_policy_v1")
        rules = {}
        for name in ("person", "ball"):
            overrides = data.get(name, {})
            if not isinstance(overrides, dict) or set(overrides) - set(ClassPolicy.__dataclass_fields__):
                raise ValueError(f"{name} 检测策略含未知字段或不是字典")
            overrides = dict(overrides)
            for key in ("aliases", "min_size_wh", "max_size_wh", "roi_polygon"):
                if key in overrides and overrides[key] is not None:
                    if not isinstance(overrides[key], (list, tuple)):
                        raise ValueError(f"{name}.{key} 必须是列表")
                    overrides[key] = tuple(tuple(p) if isinstance(p, (tuple, list)) else p for p in overrides[key]) if key == "roi_polygon" else tuple(overrides[key])
            rules[name] = replace(getattr(policy, name), **overrides)
        policy = DetectionPolicy(**rules)
    validate_policy(policy)
    return policy


def normalize_names(names: dict | list) -> dict[int, str]:
    """读取模型类别表，不假定人物/篮球对应固定编号。"""
    names = dict(enumerate(names)) if isinstance(names, list) else names
    if not isinstance(names, dict) or not names:
        raise ValueError("权重没有有效 names 类别表")
    return {int(k): str(v) for k, v in names.items()}


def resolve_class_ids(names: dict | list, policy: DetectionPolicy) -> tuple[dict[int, str], dict[str, list[int]]]:
    """仅启用配置允许且模型确实含有的类别；请求不存在的球类立即报错。"""
    validate_policy(policy)
    mapping = normalize_names(names)
    ids = {}
    for name in ("person", "ball"):
        rule = getattr(policy, name)
        aliases = {a.strip().casefold() for a in rule.aliases}
        ids[name] = [i for i, label in mapping.items() if label.strip().casefold() in aliases] if rule.enabled else []
        if rule.enabled and not ids[name]:
            raise ValueError(f"模型类别 {mapping} 中找不到 {name} 别名 {rule.aliases}；篮球未加入时请保持 ball.enabled=false")
    return mapping, ids


def rejection_reason(detection: Detection, rule: ClassPolicy, frame_size: tuple[int, int]) -> str | None:
    """按置信度、尺寸、ROI 返回首个排除原因；坐标为完整帧像素。"""
    if not rule.enabled:
        return "disabled"
    if detection.confidence < rule.confidence:
        return "confidence"
    width, height = frame_size
    x1, y1, x2, y2 = detection.bbox_xyxy
    ratios = ((x2 - x1) / width, (y2 - y1) / height)
    if min(ratios) <= 0 or any(v < lo or v > hi for v, lo, hi in zip(ratios, rule.min_size_wh, rule.max_size_wh)):
        return "size"
    if rule.roi_polygon is not None:
        point = ((x1 + x2) / (2 * width), (y2 if detection.class_name == "person" else (y1 + y2) / 2) / height)
        if cv2.pointPolygonTest(np.asarray(rule.roi_polygon, dtype=np.float32), point, False) < 0:
            return "roi"
    return None
