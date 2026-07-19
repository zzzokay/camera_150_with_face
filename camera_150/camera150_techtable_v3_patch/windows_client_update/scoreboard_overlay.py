# -*- coding: utf-8 -*-
"""
scoreboard_overlay.py - 技术台 V3 客户端比分条
================================================

该模块只负责“显示”，不修改比赛状态。

兼容：
    - Windows viewer_client.py
    - 旧 V2 JSON
    - 新 V3 JSON

V3 新显示：
    比赛阶段、24 秒、球权、暂停次数、BONUS、加时节次。
"""

from __future__ import annotations

import os
from typing import Any, Dict, Optional, Tuple

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from state_store import format_clock, period_label


FONT_CANDIDATES = [
    "C:/Windows/Fonts/msyh.ttc",
    "C:/Windows/Fonts/simhei.ttf",
    "C:/Windows/Fonts/simsun.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
]


PHASE_TEXT = {
    "PRE_GAME": "赛前",
    "PERIOD_RUNNING": "比赛中",
    "PERIOD_PAUSED": "暂停计时",
    "TIMEOUT": "暂停",
    "FREE_THROW": "罚球",
    "PERIOD_END": "节间",
    "OVERTIME": "加时",
    "GAME_END": "结束",
}


def find_font(user_font: Optional[str] = None) -> Optional[str]:
    if user_font and os.path.exists(user_font):
        return user_font
    for path in FONT_CANDIDATES:
        if os.path.exists(path):
            return path
    return None


def load_font(
    size: int,
    user_font: Optional[str] = None,
) -> ImageFont.ImageFont:
    font_path = find_font(user_font)
    if font_path:
        return ImageFont.truetype(font_path, size=size)
    return ImageFont.load_default()


def _text_size(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.ImageFont,
) -> Tuple[int, int]:
    box = draw.textbbox((0, 0), text, font=font)
    return box[2] - box[0], box[3] - box[1]


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return int(default)


def draw_scoreboard(
    frame_bgr: np.ndarray,
    state: Dict[str, Any],
    font_path: Optional[str] = None,
) -> np.ndarray:
    """
    在 BGR 视频帧上绘制紧凑比分条。

    注意：
        RK3588 LCD 主控端把比分放在视频上方，不调用本函数；
        Windows 观看端仍需要把比分叠加到视频帧，因此使用本函数。
    """
    if frame_bgr is None:
        return frame_bgr

    height, width = frame_bgr.shape[:2]
    image = Image.fromarray(
        cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
    ).convert("RGBA")
    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    # V3 信息比 V2 多，因此顶部使用两行，但总高度仍控制在画面约 14%。
    bar_height = max(86, int(height * 0.14))
    bottom_height = max(34, int(height * 0.055))
    draw.rectangle(
        (0, 0, width, bar_height),
        fill=(0, 0, 0, 170),
    )
    draw.rectangle(
        (0, height - bottom_height, width, height),
        fill=(0, 0, 0, 155),
    )

    score_font = load_font(max(24, int(height * 0.043)), font_path)
    meta_font = load_font(max(17, int(height * 0.027)), font_path)
    small_font = load_font(max(14, int(height * 0.022)), font_path)

    home_name = str(state.get("home_name", "主队"))
    away_name = str(state.get("away_name", "客队"))
    home_score = _safe_int(state.get("home_score", 0))
    away_score = _safe_int(state.get("away_score", 0))
    home_fouls = _safe_int(state.get("home_fouls", 0))
    away_fouls = _safe_int(state.get("away_fouls", 0))
    period = max(1, _safe_int(state.get("period", 1), 1))
    regulation = max(
        1,
        _safe_int(state.get("regulation_periods", 4), 4),
    )
    game_clock = format_clock(float(state.get("clock_sec_left", 0) or 0))
    shot_clock = int(
        np.ceil(float(state.get("shot_clock_sec", 24) or 0))
    )
    phase = str(state.get("phase", ""))
    phase_text = PHASE_TEXT.get(phase, phase or "PAUSE")
    possession = state.get("possession")
    timeouts = state.get("timeouts_remaining", {}) or {}
    bonus = state.get("bonus", {}) or {}

    score_text = (
        f"{home_name}  {home_score} : {away_score}  {away_name}"
    )
    clock_text = (
        f"{period_label(period, regulation)}  {game_clock}"
        f"  24秒 {shot_clock:02d}  {phase_text}"
    )
    possession_text = (
        home_name
        if possession == "home"
        else away_name if possession == "away" else "-"
    )
    detail_text = (
        f"球权 {possession_text}   "
        f"犯规 {home_fouls}/{away_fouls}   "
        f"暂停 {timeouts.get('home', 0)}/{timeouts.get('away', 0)}   "
        f"BONUS {'主' if bonus.get('home') else '-'}"
        f"/{'客' if bonus.get('away') else '-'}"
    )

    draw.text(
        (24, 10),
        score_text,
        font=score_font,
        fill=(255, 255, 255, 255),
    )

    clock_width, _ = _text_size(draw, clock_text, meta_font)
    draw.text(
        (max(24, width - clock_width - 26), 12),
        clock_text,
        font=meta_font,
        fill=(255, 226, 138, 255),
    )

    draw.text(
        (26, bar_height - 31),
        detail_text,
        font=small_font,
        fill=(215, 225, 240, 255),
    )

    last_event = str(state.get("last_event", "") or "")
    if last_event:
        draw.text(
            (24, height - bottom_height + 7),
            f"最近：{last_event}",
            font=small_font,
            fill=(255, 235, 0, 255),
        )

    output = Image.alpha_composite(image, overlay).convert("RGB")
    return cv2.cvtColor(np.asarray(output), cv2.COLOR_RGB2BGR)
