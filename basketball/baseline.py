r"""
文件作用：原脚点距离关联的可选对照；不修改 ByteTrack ID。
调用入口：根 run.py；本文件是库模块，不直接执行。
输入/输出及边界：见公开类/函数的中文说明；坐标为全幅像素、时间为源秒，ID 是临时编号。
快速测试（PowerShell，项目根目录）：.\.venv\Scripts\python.exe -X utf8 -m pytest tests/test_frozen_regression.py -q
预期输出：pytest 结果；日常运行结果在 configs/local.yaml 指定的输出目录。
排错：缺依赖用同一独立解释器安装 requirements-windows.lock.txt；输入/格式说明见 NEWCOMER_HANDOFF.md。
"""
# 来源：single_rknn_base.SmoothTracks 与 G2 对照适配器 @ cc87e85。
import math
from dataclasses import dataclass
from typing import Dict, List, Tuple
import numpy as np
from .tracker import TrackedPerson

@dataclass
class WideDetection:
    """
    为复用原 SmoothTracks 命名保留 WideDetection。

    单路版本中 wide 坐标就是 undistorted 单图坐标，source 固定为 "single"。
    """

    source: str
    score: float
    raw_bbox: Tuple[int, int, int, int]
    rect_bottom: Tuple[float, float]
    wide_bottom: Tuple[float, float]
    wide_bbox: Tuple[float, float, float, float]
    track_id: int = -1

def results_to_single_detections(raw_results: List[Tuple[int, float, Tuple[int, int, int, int]]]) -> List[WideDetection]:
    detections = []
    for _class_id, score, bbox in raw_results:
        x1, y1, x2, y2 = bbox
        bottom = ((x1 + x2) * 0.5, float(y2))
        detections.append(
            WideDetection(
                source="single",
                score=float(score),
                raw_bbox=bbox,
                rect_bottom=(float(bottom[0]), float(bottom[1])),
                wide_bottom=(float(bottom[0]), float(bottom[1])),
                wide_bbox=(float(x1), float(y1), float(x2), float(y2)),
            )
        )
    return detections

class SmoothTracks:
    """原脚底点距离贪心关联及指数平滑，仅用于独立对照。

    在 max_match_dist 像素内选最近候选续接；保留 max_missing 次更新。
    不使用外观、球队或身份信息，交叉时可能接错人；不会覆盖 ByteTrack 编号。
    """

    def __init__(self, smooth: float = 0.65, max_match_dist: float = 180.0, max_missing: int = 15):
        self.smooth = float(np.clip(smooth, 0.0, 0.98))
        self.max_match_dist = float(max_match_dist)
        self.max_missing = int(max_missing)
        self.next_id = 1
        self.tracks: List[Dict] = []

    def update(self, detections: List[WideDetection]) -> List[WideDetection]:
        if self.smooth <= 1e-6:
            for det in detections:
                det.track_id = -1
            return detections

        for tr in self.tracks:
            tr["matched"] = False
            tr["missing"] += 1

        detections_sorted = sorted(detections, key=lambda d: d.wide_bottom[0])
        output = []

        for det in detections_sorted:
            bx, by = det.wide_bottom
            best_track = None
            best_dist = 1e18

            for tr in self.tracks:
                if tr["matched"]:
                    continue
                tx, ty = tr["bottom"]
                dist = ((bx - tx) ** 2 + (by - ty) ** 2) ** 0.5
                if dist < best_dist:
                    best_dist = dist
                    best_track = tr

            if best_track is None or best_dist > self.max_match_dist:
                track_id = self.next_id
                self.next_id += 1
                best_track = {
                    "id": track_id,
                    "bottom": (bx, by),
                    "bbox": det.wide_bbox,
                    "missing": 0,
                    "matched": True,
                }
                self.tracks.append(best_track)
            else:
                sx = self.smooth
                old_bx, old_by = best_track["bottom"]
                new_bx = sx * old_bx + (1.0 - sx) * bx
                new_by = sx * old_by + (1.0 - sx) * by
                old_box = best_track["bbox"]
                new_box = tuple(sx * old_box[i] + (1.0 - sx) * det.wide_bbox[i] for i in range(4))
                best_track["bottom"] = (new_bx, new_by)
                best_track["bbox"] = new_box
                best_track["missing"] = 0
                best_track["matched"] = True

            det.track_id = int(best_track["id"])
            det.wide_bottom = tuple(best_track["bottom"])
            det.wide_bbox = tuple(best_track["bbox"])
            output.append(det)

        self.tracks = [tr for tr in self.tracks if tr["missing"] <= self.max_missing]
        return output

class SmoothTracksBaseline:
    """相同高置信真实观测的独立旧算法对照；不把旧 ID 再关联到 ByteTrack ID。"""

    def __init__(self, smooth=.65, max_match_dist=180., max_missing=15):
        # 原算法 smooth=0 会直接输出 -1；G2 的 ID 对照必须明确拒绝此关闭状态。
        if not math.isfinite(smooth) or smooth <= 1e-6:
            raise ValueError('G2 旧关联 ID 对照要求 smooth > 1e-6；0 会禁用旧 ID')
        self.args = smooth, max_match_dist, max_missing
        self.smoother = SmoothTracks(*self.args)

    def reset(self):
        """与 ByteTrack 同时开启新的场次/镜头段。"""
        self.smoother = SmoothTracks(*self.args)

    def update(self, detections, segment_id=1) -> list[TrackedPerson]:
        """复用原整数框/距离关联；输入只能为本帧真实人物，输出保留原始观测引用。"""
        persons = [d for d in detections if d.class_name == 'person']
        wide = results_to_single_detections([(d.model_class_id, d.confidence, tuple(int(v) for v in d.bbox_xyxy)) for d in persons])
        observations = {id(w): d for w, d in zip(wide, persons)}
        return [TrackedPerson(observations[id(w)], w.track_id, tuple(w.wide_bbox), segment_id, 'legacy_distance')
                for w in self.smoother.update(wide)]
