#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
director_game_policy.py - 技术台状态驱动的自动导播策略层
=========================================================

本模块位于“人物分析”和“原导播状态机”之间：

    YOLO/RKNN 人物检测
            ↓
    predict1_weighted.analyze_single_view_frame()
            ↓
    apply_game_state_to_analysis()   ← 读取 game_state.json
            ↓
    predict1_director.update_overlay_director_state()
            ↓
    最终导播画面

这样做的好处：
    1. 不修改原有的人物检测与运镜核心算法；
    2. 技术台只输出 JSON，不依赖导播代码；
    3. 导播只读取轻量状态，不依赖 PyQt5/HTTP；
    4. 关闭策略后，原自动导播行为完全保留。

策略
----
NORMAL
    比赛正常进行，原导播逻辑不变。

HOLD
    赛前、死球、暂停、节间和全场结束时，镜头保持当前区域，
    禁止因场边人员走动而大幅追踪。

FREE_THROW
    罚球时把分析热点平滑引导到对应篮筐区域，同时冻结快速 zoom。
    篮筐左右位置和主队上半场进攻方向可通过命令行配置。

注意
----
本项目是单路 150° 广角摄像头，左右篮筐在矫正画面中的准确位置会因安装
角度不同而变化。默认 0.18 / 0.82 只是起点，应根据现场画面调整。
"""

from __future__ import annotations

import copy
import json
import os
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple


NORMAL = "NORMAL"
HOLD = "HOLD"
FREE_THROW = "FREE_THROW"


@dataclass
class DirectorGamePolicyConfig:
    """技术台状态到导播行为的配置。"""

    enabled: bool = True
    state_file: str = "../techtable_v2/game_state.json"
    refresh_interval: float = 0.20

    # 左右篮筐在矫正后 1920 宽画面中的归一化 X。
    left_basket_x_ratio: float = 0.18
    right_basket_x_ratio: float = 0.82

    # 主队在第 1、2 节进攻哪一侧；下半场自动交换。
    home_first_half_attack: str = "right"

    # 罚球引导区域的大小。它只用于导播判断，不会画到推流中。
    free_throw_region_width_ratio: float = 0.28
    free_throw_region_top_ratio: float = 0.22
    free_throw_region_bottom_ratio: float = 0.96

    # HOLD/FREE_THROW 时冻结 zoom 的帧数。
    freeze_zoom_frames: int = 50

    def validate(self) -> None:
        if self.home_first_half_attack not in ("left", "right"):
            raise ValueError(
                "home_first_half_attack 必须是 left 或 right"
            )
        self.left_basket_x_ratio = min(
            0.48,
            max(0.02, float(self.left_basket_x_ratio)),
        )
        self.right_basket_x_ratio = max(
            0.52,
            min(0.98, float(self.right_basket_x_ratio)),
        )
        self.refresh_interval = max(
            0.05,
            float(self.refresh_interval),
        )


class GameStateReader:
    """
    低开销 JSON 状态读取器。

    主循环每帧调用 get_state() 也不会每帧读盘：
        - refresh_interval 内直接返回缓存；
        - 文件 mtime 未变化时不重新 json.load；
        - JSON 正在原子替换或短暂异常时继续使用上一份有效状态。
    """

    def __init__(self, config: DirectorGamePolicyConfig):
        self.config = config
        self.config.validate()
        self.state_file = os.path.abspath(config.state_file)
        self.last_check_time = 0.0
        self.last_mtime_ns: Optional[int] = None
        self.cached_state: Dict[str, Any] = {
            "phase": "PERIOD_RUNNING",
            "period": 1,
            "clock_running": True,
            "director_hint": {
                "mode": NORMAL,
                "reason": "fallback",
                "free_throw_team": None,
            },
        }
        self.last_error = ""

    def get_state(self) -> Dict[str, Any]:
        now = time.monotonic()
        if (
            now - self.last_check_time
            < self.config.refresh_interval
        ):
            return self.cached_state
        self.last_check_time = now

        try:
            stat = os.stat(self.state_file)
        except FileNotFoundError:
            # 技术台可能比导播晚启动。文件不存在时保持原自动导播。
            return self.cached_state
        except Exception as exc:
            self.last_error = str(exc)
            return self.cached_state

        if self.last_mtime_ns == stat.st_mtime_ns:
            return self.cached_state

        try:
            with open(self.state_file, "r", encoding="utf-8") as file:
                state = json.load(file)
            if not isinstance(state, dict):
                raise ValueError("game_state.json 顶层不是对象")
            self.cached_state = state
            self.last_mtime_ns = stat.st_mtime_ns
            self.last_error = ""
        except Exception as exc:
            # atomic_write_json 已经大幅降低半文件概率；仍保留缓存兜底。
            self.last_error = str(exc)

        return self.cached_state


def _director_mode(game_state: Dict[str, Any]) -> str:
    """
    优先使用技术台生成的 director_hint；旧 JSON 则根据 phase 推断。
    """
    hint = game_state.get("director_hint")
    if isinstance(hint, dict):
        mode = str(hint.get("mode", "")).upper()
        if mode in (NORMAL, HOLD, FREE_THROW):
            return mode

    phase = str(game_state.get("phase", "")).upper()
    if phase == "FREE_THROW":
        return FREE_THROW
    if phase in {
        "PRE_GAME",
        "PERIOD_PAUSED",
        "TIMEOUT",
        "PERIOD_END",
        "GAME_END",
    }:
        return HOLD
    return NORMAL


def _shooting_basket_side(
    team: str,
    period: int,
    config: DirectorGamePolicyConfig,
) -> str:
    """
    根据球队和节次判断罚球目标篮筐在画面左侧还是右侧。

    默认：
        主队第 1、2 节向右进攻；
        客队向左；
        第 3、4 节及加时交换。
    """
    first_half_home = config.home_first_half_attack
    second_half_home = (
        "left" if first_half_home == "right" else "right"
    )

    # 加时延续下半场进攻方向。
    home_side = first_half_home if int(period) <= 2 else second_half_home
    if team == "home":
        return home_side
    return "left" if home_side == "right" else "right"


def free_throw_target_x_ratio(
    game_state: Dict[str, Any],
    config: DirectorGamePolicyConfig,
) -> float:
    """返回当前罚球对应篮筐的归一化 X。"""
    hint = game_state.get("director_hint")
    hint_team = (
        hint.get("free_throw_team")
        if isinstance(hint, dict)
        else None
    )
    team = str(
        game_state.get("free_throw_team")
        or hint_team
        or "home"
    )
    period = int(game_state.get("period", 1) or 1)
    side = _shooting_basket_side(team, period, config)
    return (
        config.left_basket_x_ratio
        if side == "left"
        else config.right_basket_x_ratio
    )


def _hold_analysis(
    analysis: Dict[str, Any],
    director_state: Dict[str, Any],
    frame_w: int,
    frame_h: int,
    config: DirectorGamePolicyConfig,
) -> Dict[str, Any]:
    """
    构造“保持当前镜头”的分析输入。

    不直接硬改最终裁切框，而是把热点放在当前锚点，让原状态机自己减速，
    因此从正常比赛进入暂停时不会产生突跳。
    """
    result = copy.copy(analysis)
    current_anchor = float(
        director_state.get("current_anchor_x", frame_w * 0.5)
    )
    result["predicted_hotspot_x"] = current_anchor
    result["window_focus_x"] = current_anchor
    result["window_focus_y"] = float(
        analysis.get("window_focus_y", frame_h * 0.55)
    )
    result["pan_group"] = []
    result["main_group"] = []
    result["main_region"] = None
    result["density_confidence"] = 1.0
    result["attack_direction"] = 0
    result["triggered_fast_break"] = False
    result["fast_break_active"] = False
    result["hold_after_break_active"] = True

    director_state["zoom_freeze_frames"] = max(
        int(director_state.get("zoom_freeze_frames", 0)),
        int(config.freeze_zoom_frames),
    )
    director_state["current_anchor_v"] = (
        float(director_state.get("current_anchor_v", 0.0)) * 0.25
    )
    return result


def _free_throw_analysis(
    analysis: Dict[str, Any],
    game_state: Dict[str, Any],
    director_state: Dict[str, Any],
    frame_w: int,
    frame_h: int,
    config: DirectorGamePolicyConfig,
) -> Tuple[Dict[str, Any], float]:
    """
    构造罚球镜头分析输入。

    这里只给原状态机一个稳定目标，不直接瞬移裁切框：
        - pan 仍经过原来的迟滞、加速度和阻尼；
        - zoom 暂时冻结；
        - 目标区域落在罚球篮筐附近。
    """
    result = copy.copy(analysis)
    target_ratio = free_throw_target_x_ratio(game_state, config)
    target_x = frame_w * target_ratio
    target_y = frame_h * 0.58

    half_region_w = (
        frame_w * config.free_throw_region_width_ratio * 0.5
    )
    result["predicted_hotspot_x"] = target_x
    result["window_focus_x"] = target_x
    result["window_focus_y"] = target_y

    # 清空人物组，避免罚球线外替补/裁判把窗口选择拉走。
    result["pan_group"] = []
    result["main_group"] = []
    result["main_region"] = [
        max(0.0, target_x - half_region_w),
        frame_h * config.free_throw_region_top_ratio,
        min(float(frame_w), target_x + half_region_w),
        frame_h * config.free_throw_region_bottom_ratio,
    ]
    result["density_confidence"] = 1.0
    result["attack_direction"] = 0
    result["triggered_fast_break"] = False
    result["fast_break_active"] = False
    result["hold_after_break_active"] = False

    director_state["zoom_freeze_frames"] = max(
        int(director_state.get("zoom_freeze_frames", 0)),
        int(config.freeze_zoom_frames),
    )
    return result, target_ratio


def apply_game_state_to_analysis(
    analysis: Dict[str, Any],
    game_state: Dict[str, Any],
    director_state: Dict[str, Any],
    frame_w: int,
    frame_h: int,
    config: DirectorGamePolicyConfig,
) -> Tuple[Dict[str, Any], str]:
    """
    根据技术台状态修改“分析结果”，返回：

        modified_analysis
        policy_text

    policy_text 可叠加到本地调试画面或 profile 日志中。
    """
    if not config.enabled:
        return analysis, "POLICY_OFF"

    mode = _director_mode(game_state)

    if mode == HOLD:
        modified = _hold_analysis(
            analysis,
            director_state,
            frame_w,
            frame_h,
            config,
        )
        reason = str(
            game_state.get("phase")
            or game_state.get("director_hint", {}).get("reason")
            or "HOLD"
        )
        return modified, f"HOLD:{reason}"

    if mode == FREE_THROW:
        modified, target_ratio = _free_throw_analysis(
            analysis,
            game_state,
            director_state,
            frame_w,
            frame_h,
            config,
        )
        team = str(
            game_state.get("free_throw_team")
            or game_state.get("director_hint", {}).get(
                "free_throw_team",
                "?",
            )
        )
        return modified, (
            f"FREE_THROW:{team}@{target_ratio:.2f}"
        )

    return analysis, "NORMAL"
