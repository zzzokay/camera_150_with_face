"""
文件作用：将真实 YOLO 人物观测适配为原 SmoothTracks -> 热点 -> 规则导播输入。
输入：完整 BGR 帧和本轮/复用观测；输出：裁切视频帧、裁切矩形、平滑框、状态。
依赖：原通用模块与 rendering；不加载 RKNN，不替换规则，不引入 ByteTrack。
调用关系：run -> LegacyDirector.process -> 原 analyze/update -> rendering。
注意：临时 track_id 不是真实球员身份；旧关联器多人交叉时可能换号。
运行示例：见 NEWCOMER_HANDOFF.md。
"""
from pathlib import Path

from camera_150.camera_movement_modified import single_rknn_base as base
from camera_150.camera_movement_modified.director_game_policy import (
    DirectorGamePolicyConfig, GameStateReader, apply_game_state_to_analysis,
)
from camera_150.camera_movement_modified.predict1_director import (
    init_overlay_director_state, update_overlay_director_state,
)
from camera_150.camera_movement_modified.predict1_weighted import (
    analyze_single_view_frame, init_single_view_state,
)

from .contracts import Detection
from .rendering import render_sample_director_view720, single_detections_to_boxes_info


class LegacyDirector:
    """每个视频独立维护原规则状态；分辨率变化时拒绝沿用旧坐标。"""

    def __init__(self, width: int, height: int, smooth: float = 0.65,
                 max_match_dist: float = 180., max_missing: int = 15,
                 game_state: Path | None = None):
        self.output_size = width, height
        self.smoother = base.SmoothTracks(smooth, max_match_dist, max_missing)
        self.analysis_state = init_single_view_state()
        self.director_state = None
        self.frame_size = None
        self.policy = DirectorGamePolicyConfig(enabled=game_state is not None,
                                                state_file=str(game_state) if game_state else "")
        self.state_reader = GameStateReader(self.policy) if game_state else None

    def process(self, frame, detections: list[Detection]):
        """推进一帧原规则；返回 (导播图, 全幅裁切框, 旧平滑框, 导播状态)。"""
        h, w = frame.shape[:2]
        if self.frame_size is None:
            self.frame_size = w, h
            self.director_state = init_overlay_director_state(w)
        if self.frame_size != (w, h):
            raise ValueError("视频中途分辨率变化，请拆段处理，避免混用导播坐标")
        # 原 RKNN 返回整数 bbox；在边界处做同样整数化，保留旧规则的输入契约。
        raw = [(d.model_class_id, d.confidence, tuple(int(v) for v in d.bbox_xyxy))
               for d in detections if d.class_name == "person"]
        smoothed = self.smoother.update(base.results_to_single_detections(raw))
        analysis = analyze_single_view_frame(single_detections_to_boxes_info(smoothed),
                                            w, h, self.analysis_state)
        if self.state_reader:
            analysis, _ = apply_game_state_to_analysis(analysis, self.state_reader.get_state(),
                                                       self.director_state, w, h, self.policy)
        info = update_overlay_director_state(analysis, w, h,
                                             self.output_size[0] / self.output_size[1], self.director_state)
        view, crop = render_sample_director_view720(frame, info, *self.output_size)
        return view, crop, smoothed, info
