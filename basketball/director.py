r"""
文件作用：可选纯规则导播，将人物观测/已有轨迹转换为热点分析、运镜状态和裁切画面。
调用入口：run.py → pipeline，仅 director.enabled=true 时导入；本文件不是独立程序。
输入：完整 BGR 帧、真实人物 Detection 或 ByteTrack 结果；输出：导播帧、全幅像素裁切框和状态。
快速测试：.\.venv\Scripts\python.exe -X utf8 -m pytest tests/test_frozen_regression.py -q
预期输出：180 帧冻结回归通过；实际运行开启导播后额外生成 director.mp4。
排错：分辨率中途变化应拆段；缺文件/模型查根运行配置。本模块不读取技术台或再分配轨迹 ID。
"""
from .rendering import render_sample_director_view720
from .rules.analysis import analyze_single_view_frame, init_single_view_state
from .rules.motion import init_overlay_director_state, update_overlay_director_state


class RuleDirector:
    """每视频独立维护原热点与运镜状态；ByteTrack 输入绕过全部旧关联。"""

    def __init__(self, width: int, height: int):
        self.output_size = width, height
        self.analysis_state = init_single_view_state()
        self.director_state = None
        self.frame_size = None

    def process(self, frame, detections, tracked_persons=None):
        """保留原 G2 整数化边界和规则计算；detect 模式用当前检测，不隐含运行旧跟踪器。"""
        h, w = frame.shape[:2]
        if self.frame_size is None:
            self.frame_size = w, h
            self.director_state = init_overlay_director_state(w)
        if self.frame_size != (w, h):
            raise ValueError('视频中途分辨率变化，请拆段处理，避免混用导播坐标')
        if tracked_persons is None:
            inputs = [(d, d.bbox_xyxy, -1) for d in detections if d.class_name == 'person']
        else:
            inputs = [(t.detection, t.bbox_xyxy, t.track_id) for t in tracked_persons]
        # 旧 G2 适配器先将滤波框截断为整数，再传给纯规则；保留该边界以避免裁切回归。
        boxes = []
        for detection, bbox, track_id in inputs:
            x1, y1, x2, y2 = (float(int(v)) for v in bbox)
            boxes.append(dict(cls_name='person', conf=float(detection.confidence),
                              x1=x1, y1=y1, x2=x2, y2=y2, source='single', track_id=track_id))
        analysis = analyze_single_view_frame(boxes, w, h, self.analysis_state)
        info = update_overlay_director_state(analysis, w, h,
                                             self.output_size[0] / self.output_size[1], self.director_state)
        view, crop = render_sample_director_view720(frame, info, *self.output_size)
        return view, crop, tracked_persons or [], info
