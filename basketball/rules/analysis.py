r"""
文件作用：基于人物分布的旧热点/战团分析；从原纯算法提取，参数不变。
调用入口：根 run.py；本文件是库模块，不直接执行。
输入/输出及边界：见公开类/函数的中文说明；坐标为全幅像素、时间为源秒，ID 是临时编号。
快速测试（PowerShell，项目根目录）：.\.venv\Scripts\python.exe -X utf8 -m pytest tests/test_frozen_regression.py -q
预期输出：pytest 结果；日常运行结果在 configs/local.yaml 指定的输出目录。
排错：缺依赖用同一独立解释器安装 requirements-windows.lock.txt；输入/格式说明见 NEWCOMER_HANDOFF.md。
"""
# 来源：predict1_weighted.py @ cc87e85；保留实际调用闭包。
import math

PERSON_NAMES = {"person", "player"}  # 被当作“人物目标”的类别名称集合。

BALL_NAMES = {"sports ball", "ball"}  # 被当作“篮球目标”的类别名称集合。

PERSON_MIN_CONF = 0.35  # 人物框最低置信度；调高更干净，调低更容易保人。

BALL_MIN_CONF = 0.28  # 球框最低置信度；球很小，通常阈值要低于人物。

WINDOW_LEFT = "Left"  # 左窗口名称常量。

WINDOW_CENTER = "Center"  # 中窗口名称常量。

WINDOW_RIGHT = "Right"  # 右窗口名称常量。

MOVE_STATIONARY = "Stationary"  # MOVE 文本里表示当前保持不动。

ZOOM_IN = "Zoom In"  # zoom 状态：继续拉近。

ZOOM_OUT = "Zoom Out"  # zoom 状态：继续拉远。

ZOOM_HOLD = "Hold"  # zoom 状态：保持当前景别。

COURT_ROI = (0.04, 0.24, 0.96, 0.98)  # 球场有效区域 ROI，格式为 (左, 上, 右, 下) 的比例坐标。

BASE_CAMERA_SCALE = 1.32  # 默认景别倍率；值越大，相当于镜头越“拉近”。

MAX_CAMERA_SCALE = 1.92  # 最大允许景别倍率，防止过度放大。

FOCUS_X_ALPHA = 0.10  # 横向焦点平滑系数；越大越跟手，越小越稳。

FOCUS_Y_ALPHA = 0.08  # 纵向焦点平滑系数；通常比横向更保守。

FOCUS_X_DEAD_ZONE = 0.008  # 横向死区；小范围抖动直接忽略。

FOCUS_Y_DEAD_ZONE = 0.030  # 纵向死区；减少上下小跳动。

VERTICAL_HOME_Y_RATIO = 0.64  # 默认纵向构图中心位置，越大越靠下。

VERTICAL_FOLLOW_BLEND = 0.18  # 纵向跟随混合比例；控制对人物纵向移动的响应。

VERTICAL_MIN_RATIO = 0.58  # 纵向构图允许的最低位置比例。

VERTICAL_MAX_RATIO = 0.72  # 纵向构图允许的最高位置比例。

MAIN_REGION_ALPHA = 0.14  # 主战区平滑系数；平滑主战区范围。

LOCK_REGION_ALPHA = 0.18  # 锁定区域平滑系数；控制主战区锁的松紧。

LOCK_FOCUS_ALPHA = 0.14  # 锁定焦点平滑系数；控制焦点锁的松紧。

BATTLE_SWITCH_SCORE_RATIO = 1.22  # 候选战团要超过当前战团多少分才允许切换。

BATTLE_SWITCH_STABLE_FRAMES = 8  # 战团切换前需要连续稳定多少帧。

BATTLE_LOCK_MIN_IOU = 0.10  # 锁定战团时，区域重叠低于该值更容易解锁。

BATTLE_LOCK_MAX_FOCUS_DISTANCE = 0.22  # 锁定战团时，焦点距离超过该值更容易切换。

WINDOW_MIN_DWELL_FRAMES = 18  # 进入左右窗口前，当前窗口至少要停留的帧数。

WINDOW_SWITCH_COOLDOWN_FRAMES = 10  # 窗口切换后冷却帧数，避免连续来回跳。

WINDOW_ENTER_BIAS = 0.62  # 从中间切向左右时，需要达到的偏置阈值。

WINDOW_SIDE_STABLE_FRAMES = 8  # 从中间切到左右前，需要侧边判断稳定多少帧。

WINDOW_CENTER_RETURN_STABLE_FRAMES = 5  # 从左右回中前，需要中心判断稳定多少帧。

WINDOW_SIDE_TO_SIDE_STABLE_FRAMES = 10  # 左右直接互切时，需要额外稳定多少帧。

WINDOW_GUIDE_BLEND = 0.28  # 普通情况下，窗口导向对目标锚点的混合权重。

WINDOW_FAST_BREAK_GUIDE_BLEND = 0.10  # 快攻时窗口导向的混合权重，较低以免过度拉扯。

WINDOW_LEFT_BOX = (0.00, 0.34, 0.55, 1.00)  # 左窗口范围，格式为 (左, 上, 右, 下)。

WINDOW_RIGHT_BOX = (0.45, 0.36, 1.00, 1.00)  # 右窗口范围，格式为 (左, 上, 右, 下)。

WINDOW_CENTER_BOX = (0.25, 0.36, 0.75, 1.00)  # 中窗口范围，格式为 (左, 上, 右, 下)。

WINDOW_TRACK_LINE_Y_RATIO = 0.30  # 红色参考线高度比例，越小越靠上。

WINDOW_TRACK_BOX_HEIGHT_RATIO = 0.70  # 绿色导播框基础高度比例。

WINDOW_TRACK_BOX_SIDE_HEIGHT_RATIO = 0.65  # 绿色导播框在左右静止时的目标高度比例。

WINDOW_SCORE_HOLD_BONUS = 0.18  # 当前窗口在打分时的额外加成，减少轻微抖动切窗。

MOVE_PROGRESS_MAX_STEP = 0.010  # MOVE 正向推进时每帧最多前进多少。

BOX_DISPLAY_SMOOTH_ALPHA = 0.22  # 导播框显示层平滑系数；越大越跟手，越小越稳。

PAN_SETTLE_RATIO = 0.008  # 认为 pan 已基本到位的距离比例阈值。

PAN_ANCHOR_ACCEL = 0.055  # 镜头锚点追目标时的基础加速度。

PAN_ANCHOR_DAMPING = 0.86  # 镜头锚点速度阻尼；越小收得越快。

PAN_ANCHOR_MAX_VELOCITY = 0.014  # 镜头锚点允许的最大速度比例。

PAN_ANCHOR_MAX_ACCEL = 0.0028  # 镜头锚点允许的最大加速度比例。

PAN_REVERSAL_DAMPING = 0.42  # 目标方向反转时，对当前速度的额外阻尼。

PAN_TARGET_ALPHA = 0.16  # 目标锚点平滑系数；控制目标位置变化是否太突兀。

PAN_TARGET_MAX_STEP = 0.009  # 目标锚点每帧最大位移比例，防止目标跳跃。

PAN_TARGET_DEAD_ZONE = 0.010  # 目标锚点死区，小变动直接忽略。

PAN_DENSITY_GAIN = 2.45  # 热点偏离中心后，转成 pan 偏置时的放大倍率。

PAN_TREND_GAIN = 0.48  # 偏置变化趋势的放大倍率，用于增强方向性。

PAN_TREND_LIMIT = 0.08  # 趋势项上限，防止趋势过强导致过冲。

PAN_DENSITY_TARGET_ALPHA = 0.34  # 普通状态下，偏置追踪的平滑系数。

PAN_CENTER_DEAD_BIAS = 0.10  # 认为“接近中心”的偏置死区阈值。

PAN_CENTER_RETURN_ALPHA = 0.10  # 从侧边回中时的平滑系数。

PAN_SIDE_BIAS_LIMIT = 0.72  # 侧边偏置最大值，防止导播框贴边。

PAN_SMALL_GROUP_FULL_SIZE = 8  # 人数达到该值后，不再因人数少而缩小偏置。

PAN_SMALL_GROUP_MIN_SCALE = 0.60  # 人少时偏置最小缩放比例，减少误判带来的大动作。

PAN_SIDE_HOLD_DECAY_FRAMES = 60  # 长时间停在侧边后，开始衰减侧边偏置的帧数。

PAN_SIDE_HOLD_DECAY_SCALE = 0.78  # 长时间停在侧边后，侧边偏置的衰减比例。

HOTSPOT_EMA_ALPHA = 0.28  # 热点位置 EMA 平滑系数。

HOTSPOT_VELOCITY_ALPHA = 0.18  # 热点速度平滑系数。

HOTSPOT_LEAD_FRAMES = 5  # 普通情况下，热点预测向前看多少帧。

HOTSPOT_MIN_MOVE_RATIO = 0.0018  # 低于该位移比例的变化直接认为没动。

HOTSPOT_ATTACK_EDGE_BLEND = 0.18  # 进攻边缘位置参与热点计算的混合权重。

HOTSPOT_BALL_BLEND = 0.10  # 球位置参与热点计算的混合权重。

FAST_BREAK_SPEED_RATIO = 0.018  # 热点速度超过该比例时，判为快攻候选。

FAST_BREAK_JUMP_RATIO = 0.10  # 热点位置突跳超过该比例时，判为快攻候选。

FAST_BREAK_FRAMES = 18  # 快攻状态持续的基础帧数。

FAST_BREAK_LEAD_FRAMES = 24  # 快攻时热点预测向前看多少帧。

FAST_BREAK_TARGET_ALPHA = 0.72  # 快攻时目标偏置追踪系数，显著高于普通状态。

FAST_BREAK_TARGET_MAX_STEP = 0.035  # 快攻时目标锚点每帧最大位移比例。

FAST_BREAK_ANCHOR_ACCEL = 0.145  # 快攻时镜头锚点加速度。

FAST_BREAK_MAX_VELOCITY = 0.040  # 快攻时镜头锚点最大速度。

FAST_BREAK_MAX_ACCEL = 0.010  # 快攻时镜头锚点最大加速度。

FAST_BREAK_ZOOM_FREEZE_FRAMES = 30  # 快攻触发后冻结 zoom 的帧数。

POST_BREAK_HOLD_FRAMES = 32  # 快攻结束后，保持当前方向别急着回中的帧数。

ARRIVAL_HOLD_FRAMES = 10  # 刚追到新热点后，驻留保持的帧数。

ARRIVAL_HOLD_DISTANCE_RATIO = 0.014  # 认为“已到达热点附近”的距离比例阈值。

ARRIVAL_HOLD_DIRECTION_TOLERANCE = 0.10  # 驻留中判定方向反转的容忍阈值。

ARRIVAL_HOLD_BLEND = 0.82  # 驻留保持时，对驻留锚点的混合强度。

LANDING_HOLD_FRAMES = 8  # 镜头真正落位后，再额外稳住的帧数。

LANDING_HOLD_DISTANCE_RATIO = 0.009  # 认为“镜头已落位”的距离比例阈值。

LANDING_HOLD_BLEND = 0.80  # 落位保持时，对落位锚点的混合强度。

LEAD_SPACE_RATIO_NORMAL = 0.10  # 普通移动时，沿进攻方向预留的空间比例。

LEAD_SPACE_RATIO_FAST = 0.18  # 快攻时，沿进攻方向预留的空间比例。

RECENTER_FAST_BIAS = 0.08  # 偏置进入该范围后，开始认为可以尝试快速回中。

RECENTER_FAST_ALPHA = 0.10  # 快速回中时的平滑系数。

PAN_FREEZE_FRAMES_AFTER_SWITCH = 12  # 窗口切换后冻结 pan 的帧数。

ZOOM_AFTER_PAN_SETTLE_FRAMES = 18  # pan 稳定多少帧后才允许 zoom。

ZOOM_REGION_STABLE_FRAMES = 18  # zoom 区域稳定多少帧后才允许 zoom。

ZOOM_ALPHA = 0.10  # zoom 值平滑系数。

ZOOM_TARGET_DEAD_BAND = 0.12  # zoom 目标变化小于该带宽时不动作。

ZOOM_COOLDOWN_FRAMES = 72  # zoom 触发后的冷却帧数。

ZOOM_COMMIT_FRAMES = 32  # zoom 决策提交后，保持该目标的帧数。

ZOOM_TARGET_STEP = 0.12  # zoom 目标量化步长。

ZOOM_REGION_PAD_X = 0.050  # zoom 目标区域横向外扩边距。

ZOOM_REGION_PAD_Y = 0.070  # zoom 目标区域纵向外扩边距。

MIN_BATTLE_GROUP_SIZE = 5  # 主战团人数过少时，至少补到多少人。

PAN_GROUP_MIN_SIZE = 6  # 横向热点组理想的最少人数。

def clamp(value, low, high):
    return max(low, min(high, value))

def smooth_value(prev_v, new_v, alpha=0.12):
    if prev_v is None:
        return new_v
    return alpha * new_v + (1 - alpha) * prev_v

def smoothstep01(progress):
    p = clamp(progress, 0.0, 1.0)
    return p * p * (3.0 - 2.0 * p)

def box_center(box):
    return (box["x1"] + box["x2"]) / 2.0, (box["y1"] + box["y2"]) / 2.0

def box_size(box):
    return max(1.0, box["x2"] - box["x1"]), max(1.0, box["y2"] - box["y1"])

def union_region(boxes):
    if not boxes:
        return None
    return [
        min(b["x1"] for b in boxes),
        min(b["y1"] for b in boxes),
        max(b["x2"] for b in boxes),
        max(b["y2"] for b in boxes),
    ]

def region_center(region):
    if region is None:
        return None, None
    x1, y1, x2, y2 = region
    return (x1 + x2) / 2.0, (y1 + y2) / 2.0

def region_iou(region_a, region_b):
    if region_a is None or region_b is None:
        return 0.0

    ax1, ay1, ax2, ay2 = region_a
    bx1, by1, bx2, by2 = region_b

    ix1 = max(ax1, bx1)
    iy1 = max(ay1, by1)
    ix2 = min(ax2, bx2)
    iy2 = min(ay2, by2)

    inter_w = max(0.0, ix2 - ix1)
    inter_h = max(0.0, iy2 - iy1)
    inter_area = inter_w * inter_h

    area_a = max(0.0, ax2 - ax1) * max(0.0, ay2 - ay1)
    area_b = max(0.0, bx2 - bx1) * max(0.0, by2 - by1)
    union_area = area_a + area_b - inter_area

    if union_area <= 0:
        return 0.0
    return inter_area / union_area

def focus_distance_ratio(focus_a, focus_b, img_w, img_h):
    if focus_a is None or focus_b is None:
        return 1.0

    ax, ay = focus_a
    bx, by = focus_b
    dx = (ax - bx) / max(1.0, img_w)
    dy = (ay - by) / max(1.0, img_h)
    return math.sqrt(dx * dx + dy * dy)

def smooth_region(prev_region, new_region, alpha=0.10):
    if new_region is None:
        return prev_region
    if prev_region is None:
        return new_region

    return [
        smooth_value(prev_region[0], new_region[0], alpha),
        smooth_value(prev_region[1], new_region[1], alpha),
        smooth_value(prev_region[2], new_region[2], alpha),
        smooth_value(prev_region[3], new_region[3], alpha),
    ]

def region_change_ratio(prev_region, new_region, img_w, img_h):
    if prev_region is None or new_region is None:
        return 1.0

    prev_cx, prev_cy = region_center(prev_region)
    new_cx, new_cy = region_center(new_region)
    center_shift = abs(new_cx - prev_cx) / max(1.0, img_w) + abs(new_cy - prev_cy) / max(1.0, img_h)

    prev_w = max(1.0, prev_region[2] - prev_region[0])
    prev_h = max(1.0, prev_region[3] - prev_region[1])
    new_w = max(1.0, new_region[2] - new_region[0])
    new_h = max(1.0, new_region[3] - new_region[1])
    size_change = abs(new_w - prev_w) / max(1.0, img_w) + abs(new_h - prev_h) / max(1.0, img_h)

    return center_shift + size_change

def smooth_focus_pair(prev_focus, new_focus, alpha=0.10):
    if new_focus is None or new_focus[0] is None:
        return prev_focus
    if prev_focus is None:
        return new_focus

    return (
        smooth_value(prev_focus[0], new_focus[0], alpha),
        smooth_value(prev_focus[1], new_focus[1], alpha),
    )

def smooth_focus_axis(prev_v, new_v, frame_size, alpha, dead_zone_ratio):
    if prev_v is None:
        return new_v
    if abs(new_v - prev_v) <= frame_size * dead_zone_ratio:
        return prev_v
    return smooth_value(prev_v, new_v, alpha)

def stabilize_vertical_focus(focus_y, img_h):
    home_y = img_h * VERTICAL_HOME_Y_RATIO
    follow_y = home_y + (focus_y - home_y) * VERTICAL_FOLLOW_BLEND
    return clamp(
        follow_y,
        img_h * VERTICAL_MIN_RATIO,
        img_h * VERTICAL_MAX_RATIO
    )

def inside_court_roi(box, img_w, img_h):
    rx1, ry1, rx2, ry2 = COURT_ROI
    roi_x1 = rx1 * img_w
    roi_y1 = ry1 * img_h
    roi_x2 = rx2 * img_w
    roi_y2 = ry2 * img_h

    cx, cy = box_center(box)
    return roi_x1 <= cx <= roi_x2 and roi_y1 <= cy <= roi_y2

def get_person_boxes(boxes_info, person_names=PERSON_NAMES, min_conf=0.35):
    return [
        b for b in boxes_info
        if b["cls_name"] in person_names and b["conf"] >= min_conf
    ]

def get_ball_boxes(boxes_info, ball_names=BALL_NAMES, min_conf=0.18):
    return [
        b for b in boxes_info
        if b["cls_name"] in ball_names and b["conf"] >= min_conf
    ]

def ball_focus_x(balls, img_w, img_h):
    court_balls = [b for b in balls if inside_court_roi(b, img_w, img_h)]
    candidates = court_balls if court_balls else balls
    if not candidates:
        return None

    def ball_score(ball):
        w, h = box_size(ball)
        return ball["conf"] * max(1.0, w * h)

    ball = max(candidates, key=ball_score)
    cx, _ = box_center(ball)
    return cx

def filter_playing_persons(persons, img_w, img_h):
    in_roi = [p for p in persons if inside_court_roi(p, img_w, img_h)]
    candidates = in_roi if in_roi else persons

    if len(candidates) <= 2:
        return candidates

    heights = sorted(box_size(p)[1] for p in candidates)
    median_h = heights[len(heights) // 2]
    min_h = max(img_h * 0.026, median_h * 0.35)

    filtered = []
    for p in candidates:
        cx, cy = box_center(p)
        _, h = box_size(p)

        if h < min_h:
            continue
        if cx < img_w * 0.04 or cx > img_w * 0.96:
            continue
        if cy < img_h * 0.30 or cy > img_h * 0.96:
            continue

        filtered.append(p)

    return filtered if len(filtered) >= 2 else candidates

def court_activity_weight(person, img_w=None, img_h=None):
    if img_w is None or img_h is None:
        return 1.0

    cx, cy = box_center(person)
    rx = cx / max(1.0, img_w)
    ry = cy / max(1.0, img_h)
    weight = 1.0

    if rx < 0.08 or rx > 0.92:
        weight *= 0.28
    elif rx < 0.13 or rx > 0.87:
        weight *= 0.58

    if ry < 0.36 or ry > 0.91:
        weight *= 0.26
    elif ry < 0.43 or ry > 0.86:
        weight *= 0.58

    return weight

def person_focus_weight(person, img_w=None, img_h=None):
    w, h = box_size(person)
    area_boost = min(2.2, (w * h) / 4500.0)
    height_boost = min(2.5, h / 120.0)
    return person["conf"] * (1.0 + 0.35 * area_boost + 0.45 * height_boost) * court_activity_weight(person, img_w, img_h)

def weighted_focus(persons, img_w=None, img_h=None):
    if not persons:
        return None, None

    total_w = 0.0
    sum_x = 0.0
    sum_y = 0.0

    for p in persons:
        cx, cy = box_center(p)
        w = person_focus_weight(p, img_w, img_h)
        total_w += w
        sum_x += cx * w
        sum_y += cy * w

    if total_w <= 0:
        return None, None

    return sum_x / total_w, sum_y / total_w

def density_cluster_focus(persons, img_w, img_h):
    if not persons:
        return None, None, 0.0

    centers = [(box_center(p), p) for p in persons]
    radius_x = img_w * 0.20
    radius_y = img_h * 0.20
    scored = []

    for (cx, cy), p in centers:
        local_density = 0.0
        for (ox, oy), other in centers:
            dx = (ox - cx) / max(1.0, radius_x)
            dy = (oy - cy) / max(1.0, radius_y)
            proximity = max(0.0, 1.0 - dx * dx - dy * dy)
            local_density += proximity * person_focus_weight(other, img_w, img_h)

        scored.append((local_density * person_focus_weight(p, img_w, img_h), cx, cy))

    scored.sort(reverse=True, key=lambda item: item[0])
    top_count = max(4, min(len(scored), 6))
    top = scored[:top_count]
    total = sum(score for score, _, _ in top)

    if total <= 0:
        focus_x, focus_y = weighted_focus(persons, img_w, img_h)
        return focus_x, focus_y, 0.0

    focus_x = sum(cx * score for score, cx, _ in top) / total
    focus_y = sum(cy * score for score, _, cy in top) / total
    confidence = clamp(0.45 + total / max(1.0, len(persons) * 2.0), 0.45, 1.0)

    return focus_x, focus_y, confidence

def attack_edge_x(persons, img_w, img_h, direction):
    if not persons or direction == 0:
        return None

    scored = []
    for p in persons:
        cx, _ = box_center(p)
        position_score = cx / max(1.0, img_w) if direction > 0 else 1.0 - cx / max(1.0, img_w)
        score = position_score * person_focus_weight(p, img_w, img_h)
        scored.append((score, cx))

    scored.sort(reverse=True, key=lambda item: item[0])
    top = scored[:max(1, min(3, len(scored)))]
    total = sum(score for score, _ in top)
    if total <= 0:
        return None

    return sum(cx * score for score, cx in top) / total

def score_density_group(group, img_w, img_h):
    if not group:
        return -1.0

    region = union_region(group)
    rx1, ry1, rx2, ry2 = region
    region_area_ratio = ((rx2 - rx1) * (ry2 - ry1)) / max(1.0, img_w * img_h)
    weight_sum = sum(person_focus_weight(p, img_w, img_h) for p in group)
    return weight_sum * (1.0 + 0.35 * len(group)) / (0.08 + region_area_ratio)

def tighten_density_group(group, img_w, img_h):
    focus_x, focus_y = weighted_focus(group, img_w, img_h)
    if focus_x is None:
        return group

    tight_group = []
    for p in group:
        cx, cy = box_center(p)
        if abs(cx - focus_x) <= img_w * 0.28 and abs(cy - focus_y) <= img_h * 0.28:
            tight_group.append(p)

    return tight_group if len(tight_group) >= 3 else group

def refine_main_group(group, img_w, img_h):
    if len(group) <= 2:
        return group

    focus_x, focus_y = weighted_focus(group, img_w, img_h)
    if focus_x is None:
        return group

    refined = []
    for p in group:
        cx, cy = box_center(p)
        activity = court_activity_weight(p, img_w, img_h)
        close_to_play = abs(cx - focus_x) <= img_w * 0.27 and abs(cy - focus_y) <= img_h * 0.26
        likely_on_court = activity >= 0.45 and abs(cx - focus_x) <= img_w * 0.34 and abs(cy - focus_y) <= img_h * 0.30

        if close_to_play or likely_on_court:
            refined.append(p)

    return refined if len(refined) >= 3 else group

def expand_sparse_group(group, persons, img_w, img_h, target_focus=None, min_group_size=3):
    target_size = min(min_group_size, len(persons))
    if len(group) >= target_size or len(persons) <= len(group):
        return group

    focus_x, focus_y = weighted_focus(group, img_w, img_h)
    if focus_x is None and target_focus is not None:
        focus_x, focus_y = target_focus
    if focus_x is None:
        return group

    selected = list(group)
    selected_ids = {id(p) for p in selected}
    nearby = []

    for p in persons:
        if id(p) in selected_ids:
            continue

        activity = court_activity_weight(p, img_w, img_h)
        if activity < 0.20:
            continue

        cx, cy = box_center(p)
        dx = abs(cx - focus_x) / max(1.0, img_w)
        dy = abs(cy - focus_y) / max(1.0, img_h)
        distance = math.sqrt(dx * dx + dy * dy)

        if dx <= 0.42 and dy <= 0.34:
            nearby.append((distance / max(0.20, activity), p))

    for _, p in sorted(nearby, key=lambda item: item[0]):
        selected.append(p)
        if len(selected) >= target_size:
            break

    return selected

def previous_region_group(persons, previous_region, previous_focus, img_w, img_h):
    if not persons or previous_region is None:
        return []

    px1, py1, px2, py2 = previous_region
    expand_x = img_w * 0.08
    expand_y = img_h * 0.08
    px1 -= expand_x
    px2 += expand_x
    py1 -= expand_y
    py2 += expand_y

    prev_x, prev_y = previous_focus if previous_focus is not None else region_center(previous_region)
    group = []

    for p in persons:
        cx, cy = box_center(p)
        in_expanded_region = px1 <= cx <= px2 and py1 <= cy <= py2
        near_previous_focus = (
            prev_x is not None
            and abs(cx - prev_x) <= img_w * 0.32
            and abs(cy - prev_y) <= img_h * 0.32
        )

        if in_expanded_region or near_previous_focus:
            group.append(p)

    return tighten_density_group(group, img_w, img_h) if len(group) >= 2 else []

def build_density_candidates(persons, img_w, img_h, previous_region=None, previous_focus=None):
    if not persons:
        return []

    candidates = []
    seen = set()
    radius_x = img_w * 0.24
    radius_y = img_h * 0.24
    centers = [(box_center(p), p) for p in persons]

    prev_group = previous_region_group(persons, previous_region, previous_focus, img_w, img_h)
    if prev_group:
        candidates.append(prev_group)
        seen.add(tuple(sorted(id(p) for p in prev_group)))

    for (seed_x, seed_y), _ in centers:
        group = []
        for (cx, cy), p in centers:
            dx = (cx - seed_x) / radius_x
            dy = (cy - seed_y) / radius_y
            if dx * dx + dy * dy <= 1.0:
                group.append(p)

        if not group:
            continue

        group = tighten_density_group(group, img_w, img_h)
        key = tuple(sorted(id(p) for p in group))
        if key in seen:
            continue

        seen.add(key)
        candidates.append(group)

    return candidates

def continuity_bonus(group, img_w, img_h, previous_region=None, previous_focus=None):
    if previous_region is None and previous_focus is None:
        return 1.0

    region = union_region(group)
    focus_x, focus_y = weighted_focus(group, img_w, img_h)
    if focus_x is None:
        focus_x, focus_y = region_center(region)

    bonus = 1.0

    if previous_region is not None:
        bonus += 0.55 * region_iou(region, previous_region)

    if previous_focus is not None and focus_x is not None:
        prev_x, prev_y = previous_focus
        norm_dx = (focus_x - prev_x) / max(1.0, img_w * 0.35)
        norm_dy = (focus_y - prev_y) / max(1.0, img_h * 0.35)
        distance = math.sqrt(norm_dx * norm_dx + norm_dy * norm_dy)
        proximity = clamp(1.0 - distance, 0.0, 1.0)
        bonus += 0.45 * proximity

    return bonus

def best_scored_group(candidates, img_w, img_h, previous_region=None, previous_focus=None):
    best_group = []
    best_score = -1.0

    for group in candidates:
        score = score_density_group(group, img_w, img_h)
        score *= continuity_bonus(group, img_w, img_h, previous_region, previous_focus)

        if score > best_score:
            best_score = score
            best_group = group

    return best_group, best_score

def is_same_battle_group(group, locked_region, locked_focus, img_w, img_h):
    if not group or locked_region is None:
        return False

    region = union_region(group)
    focus = weighted_focus(group, img_w, img_h)
    iou = region_iou(region, locked_region)
    distance = focus_distance_ratio(focus, locked_focus, img_w, img_h)

    return iou >= BATTLE_LOCK_MIN_IOU or distance <= BATTLE_LOCK_MAX_FOCUS_DISTANCE

def select_density_group_locked(
    persons,
    img_w,
    img_h,
    locked_region=None,
    locked_focus=None,
    switch_count=0
):
    if not persons:
        return [], 0

    candidates = build_density_candidates(persons, img_w, img_h, locked_region, locked_focus)
    if not candidates:
        return persons, 0

    best_group, best_score = best_scored_group(candidates, img_w, img_h, locked_region, locked_focus)
    if not best_group:
        return persons, 0

    if locked_region is None:
        return refine_main_group(best_group, img_w, img_h), 0

    locked_candidates = [
        group for group in candidates
        if is_same_battle_group(group, locked_region, locked_focus, img_w, img_h)
    ]

    if not locked_candidates:
        switch_count += 1
        fallback_group = previous_region_group(persons, locked_region, locked_focus, img_w, img_h)
        if switch_count >= max(3, BATTLE_SWITCH_STABLE_FRAMES // 2):
            return refine_main_group(best_group, img_w, img_h), 0
        if fallback_group:
            return refine_main_group(fallback_group, img_w, img_h), switch_count
        return refine_main_group(best_group, img_w, img_h), switch_count

    locked_group, locked_score = best_scored_group(locked_candidates, img_w, img_h, locked_region, locked_focus)

    if is_same_battle_group(best_group, locked_region, locked_focus, img_w, img_h):
        return refine_main_group(best_group, img_w, img_h), 0

    if best_score >= locked_score * BATTLE_SWITCH_SCORE_RATIO:
        switch_count += 1
        if switch_count >= BATTLE_SWITCH_STABLE_FRAMES:
            return refine_main_group(best_group, img_w, img_h), 0
        return refine_main_group(locked_group, img_w, img_h), switch_count

    return refine_main_group(locked_group, img_w, img_h), 0

def select_current_density_group(persons, img_w, img_h):
    if not persons:
        return []

    candidates = build_density_candidates(persons, img_w, img_h)
    if not candidates:
        return persons

    best_group, _ = best_scored_group(candidates, img_w, img_h)
    if not best_group:
        return persons

    best_group = refine_main_group(best_group, img_w, img_h)
    best_group = expand_sparse_group(best_group, persons, img_w, img_h, min_group_size=PAN_GROUP_MIN_SIZE)
    return best_group

def battle_hotspot_center(main_group, main_region, img_w, img_h, ball_x=None, attack_direction=0):
    density_x, _, density_confidence = density_cluster_focus(main_group, img_w, img_h)
    region_x, _ = region_center(main_region)
    weighted_x, _ = weighted_focus(main_group, img_w, img_h)

    xs = [x for x in (density_x, region_x, weighted_x) if x is not None]
    if not xs:
        return None, 0.0

    if density_x is None:
        density_x = sum(xs) / len(xs)
    if region_x is None:
        region_x = density_x
    if weighted_x is None:
        weighted_x = density_x

    hotspot_x = density_x * 0.84 + region_x * 0.10 + weighted_x * 0.06

    edge_x = attack_edge_x(main_group, img_w, img_h, direction=attack_direction)
    if edge_x is not None:
        hotspot_x = hotspot_x * (1.0 - HOTSPOT_ATTACK_EDGE_BLEND) + edge_x * HOTSPOT_ATTACK_EDGE_BLEND

    if ball_x is not None:
        hotspot_x = hotspot_x * (1.0 - HOTSPOT_BALL_BLEND) + ball_x * HOTSPOT_BALL_BLEND

    group_size_confidence = clamp(len(main_group) / 6.0, 0.35, 1.0)
    confidence = clamp(0.78 * density_confidence + 0.22 * group_size_confidence, 0.45, 1.0)
    if ball_x is not None:
        confidence = clamp(confidence + 0.08, 0.45, 1.0)

    return hotspot_x, confidence

def init_single_view_state():
    return {
        # prev_focus_x / prev_focus_y：上一帧平滑后的焦点。
        "prev_focus_x": None,
        "prev_focus_y": None,
        # prev_main_region / prev_main_focus：上一帧主战区及其焦点。
        "prev_main_region": None,
        "prev_main_focus": None,
        # battle_region_lock / battle_focus_lock：主战区锁定区域及其焦点。
        "battle_region_lock": None,
        "battle_focus_lock": None,
        # battle_switch_count：主战区切换累计稳定计数。
        "battle_switch_count": 0,
        # smooth_hotspot_x：平滑后的热点横坐标。
        # prev_hotspot_x：上一帧原始热点横坐标。
        # hotspot_velocity_x：热点横向速度。
        "smooth_hotspot_x": None,
        "prev_hotspot_x": None,
        "hotspot_velocity_x": 0.0,
        # fast_break_frames：快攻状态剩余帧数。
        # post_break_hold_frames：快攻结束后继续保方向的剩余帧数。
        "fast_break_frames": 0,
        "post_break_hold_frames": 0,
    }

def analyze_single_view_frame(boxes_info, frame_w, frame_h, state):
    """把全幅像素人物框汇总为原一维热点与运动信息，原地更新每视频状态。

    属于可选规则导播：按历史阈值筛框、聚合横向位置并平滑热点，供运镜决策。
    不进行身份识别或球场投影；本轮保持原公式与输入顺序，冻结回归核对结果。
    """
    # persons：经过类别筛选和阈值过滤的人物框。
    # balls：经过类别筛选和阈值过滤的球框。
    # current_ball_x：当前帧球的横向焦点位置。
    # detections_count：当前帧人物框数量，用于调试显示。
    persons = get_person_boxes(boxes_info, min_conf=PERSON_MIN_CONF)
    persons = filter_playing_persons(persons, frame_w, frame_h)
    balls = get_ball_boxes(boxes_info, min_conf=BALL_MIN_CONF)
    current_ball_x = ball_focus_x(balls, frame_w, frame_h)
    detections_count = len(persons)

    # main_group：当前主战团人物集合。
    # pan_group：用于计算横向热点的人物集合。
    main_group, state["battle_switch_count"] = select_density_group_locked(
        persons,
        frame_w,
        frame_h,
        locked_region=state["battle_region_lock"],
        locked_focus=state["battle_focus_lock"],
        switch_count=state["battle_switch_count"],
    )
    main_group = expand_sparse_group(
        main_group,
        persons,
        frame_w,
        frame_h,
        target_focus=state["battle_focus_lock"],
        min_group_size=MIN_BATTLE_GROUP_SIZE,
    )
    pan_group = select_current_density_group(persons, frame_w, frame_h)
    if not pan_group:
        pan_group = main_group

    # raw_main_region：当前主战团的原始外接矩形。
    # raw_focus_x / raw_focus_y：当前主战团的原始加权焦点。
    raw_main_region = union_region(main_group)
    raw_focus_x, raw_focus_y = weighted_focus(main_group, frame_w, frame_h)

    state["battle_region_lock"] = smooth_region(
        state["battle_region_lock"],
        raw_main_region,
        alpha=LOCK_REGION_ALPHA,
    )
    state["battle_focus_lock"] = smooth_focus_pair(
        state["battle_focus_lock"],
        (raw_focus_x, raw_focus_y),
        alpha=LOCK_FOCUS_ALPHA,
    )

    main_region = smooth_region(state["prev_main_region"], state["battle_region_lock"], alpha=MAIN_REGION_ALPHA)
    focus_x, focus_y = state["battle_focus_lock"] if state["battle_focus_lock"] is not None else (raw_focus_x, raw_focus_y)

    if focus_x is None:
        focus_x = state["prev_main_focus"][0] if state["prev_main_focus"] is not None else frame_w * 0.50
    if focus_y is None:
        focus_y = state["prev_main_focus"][1] if state["prev_main_focus"] is not None else frame_h * VERTICAL_HOME_Y_RATIO

    if main_region is not None:
        region_focus_x, region_focus_y = region_center(main_region)
        focus_x = focus_x * 0.66 + region_focus_x * 0.34
        focus_y = focus_y * 0.72 + region_focus_y * 0.28

        if current_ball_x is not None:
            region_w = max(1.0, main_region[2] - main_region[0])
            if abs(current_ball_x - region_focus_x) > max(region_w * 0.90, frame_w * 0.18):
                current_ball_x = None

    focus_y = stabilize_vertical_focus(focus_y, frame_h)
    focus_x = smooth_focus_axis(state["prev_focus_x"], focus_x, frame_w, FOCUS_X_ALPHA, FOCUS_X_DEAD_ZONE)
    focus_y = smooth_focus_axis(state["prev_focus_y"], focus_y, frame_h, FOCUS_Y_ALPHA, FOCUS_Y_DEAD_ZONE)

    state["prev_focus_x"] = focus_x
    state["prev_focus_y"] = focus_y
    state["prev_main_focus"] = (focus_x, focus_y)
    state["prev_main_region"] = main_region

    # attack_direction：热点移动方向；1 表示向右推进，-1 表示向左推进，0 表示方向不明显。
    attack_direction = (
        1 if state["hotspot_velocity_x"] > frame_w * HOTSPOT_MIN_MOVE_RATIO
        else -1 if state["hotspot_velocity_x"] < -frame_w * HOTSPOT_MIN_MOVE_RATIO
        else 0
    )

    # hotspot_x：当前帧推断出的原始热点位置。
    # density_confidence：热点推断的可靠度。
    hotspot_x, density_confidence = battle_hotspot_center(
        pan_group,
        union_region(pan_group),
        frame_w,
        frame_h,
        ball_x=current_ball_x,
        attack_direction=attack_direction,
    )
    if hotspot_x is None:
        hotspot_x = frame_w * 0.50

    triggered_fast_break = False
    if state["smooth_hotspot_x"] is None:
        state["smooth_hotspot_x"] = hotspot_x
        state["prev_hotspot_x"] = hotspot_x
        state["hotspot_velocity_x"] = 0.0
    else:
        # instant_velocity_x：原始热点相对上一帧的瞬时速度。
        instant_velocity_x = hotspot_x - state["prev_hotspot_x"]
        if abs(instant_velocity_x) <= frame_w * HOTSPOT_MIN_MOVE_RATIO:
            instant_velocity_x = 0.0

        triggered_fast_break = (
            abs(instant_velocity_x) >= frame_w * FAST_BREAK_SPEED_RATIO
            or abs(hotspot_x - state["smooth_hotspot_x"]) >= frame_w * FAST_BREAK_JUMP_RATIO
        )

        if triggered_fast_break:
            state["fast_break_frames"] = FAST_BREAK_FRAMES
            state["post_break_hold_frames"] = POST_BREAK_HOLD_FRAMES

        if state["fast_break_frames"] > 0:
            state["fast_break_frames"] -= 1
        elif state["post_break_hold_frames"] > 0:
            state["post_break_hold_frames"] -= 1

        state["hotspot_velocity_x"] = smooth_value(
            state["hotspot_velocity_x"],
            instant_velocity_x,
            alpha=HOTSPOT_VELOCITY_ALPHA,
        )
        hotspot_alpha = FAST_BREAK_TARGET_ALPHA if state["fast_break_frames"] > 0 else HOTSPOT_EMA_ALPHA
        state["smooth_hotspot_x"] = smooth_value(
            state["smooth_hotspot_x"],
            hotspot_x,
            alpha=hotspot_alpha,
        )
        state["prev_hotspot_x"] = hotspot_x

    # fast_break_active：当前是否处于快攻状态。
    # hold_after_break_active：当前是否处于“快攻后别急着回中”的保持状态。
    fast_break_active = state["fast_break_frames"] > 0
    hold_after_break_active = state["post_break_hold_frames"] > 0

    # lead_frames：热点预测提前量，快攻时显著增大。
    # predicted_hotspot_x：结合热点速度后，预测出的未来热点位置。
    lead_frames = FAST_BREAK_LEAD_FRAMES if fast_break_active else HOTSPOT_LEAD_FRAMES
    predicted_hotspot_x = clamp(
        state["smooth_hotspot_x"] + state["hotspot_velocity_x"] * lead_frames,
        frame_w * 0.10,
        frame_w * 0.90,
    )

    return {
        "persons": persons,
        "balls": balls,
        "current_ball_x": current_ball_x,
        "detections_count": detections_count,
        "main_group": main_group,
        "pan_group": pan_group,
        "main_region": main_region,
        "focus_x": focus_x,
        "focus_y": focus_y,
        "window_focus_x": predicted_hotspot_x * 0.35 + state["smooth_hotspot_x"] * 0.65,
        "window_focus_y": focus_y,
        "hotspot_x": hotspot_x,
        "smooth_hotspot_x": state["smooth_hotspot_x"],
        "predicted_hotspot_x": predicted_hotspot_x,
        "hotspot_velocity_x": state["hotspot_velocity_x"],
        "density_confidence": density_confidence,
        "attack_direction": attack_direction,
        "fast_break_active": fast_break_active,
        "hold_after_break_active": hold_after_break_active,
        "triggered_fast_break": triggered_fast_break,
    }
