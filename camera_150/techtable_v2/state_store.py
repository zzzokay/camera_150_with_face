# -*- coding: utf-8 -*-
"""
state_store.py - 篮球技术台 V3 的“比赛规则核心层”
=================================================

设计目标
--------
旧版本中，LCD 按钮和网页按钮各自修改 JSON，导致同一个动作出现两套规则：
例如 LCD 支持撤销，网页端却只写“暂不支持撤销”。随着 24 秒、暂停、
罚球、换人等功能增加，这种写法会越来越难维护。

V3 将规则统一收拢到 GameController：

    LCD UI ─┐
            ├─> GameController.apply_action() ─> game_state.json
    网页 UI ─┘                                  └> events.jsonl

本文件不依赖 PyQt5、OpenCV 或 HTTP，可以独立测试。导播程序只读取
game_state.json，不需要导入技术台 UI，因此技术台和导播保持解耦。

状态机
------
PRE_GAME       赛前
PERIOD_RUNNING 正常比赛进行中
PERIOD_PAUSED  比赛暂停/死球
TIMEOUT        暂停
FREE_THROW     罚球
PERIOD_END     单节结束
OVERTIME       加时赛进行或暂停
GAME_END       全场结束

兼容性
------
保留旧版本常用字段：
    home_score / away_score
    home_fouls / away_fouls
    period / clock_sec_left / clock_running
    selected_player / players / last_event

因此旧 viewer_client.py 仍然可以读取基本比分；新版 scoreboard_overlay.py
会额外显示 24 秒、暂停、球权、BONUS 和比赛阶段。
"""

from __future__ import annotations

import copy
import json
import os
import threading
import time
from typing import Any, Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# 一、比赛状态常量
# ---------------------------------------------------------------------------

PRE_GAME = "PRE_GAME"
PERIOD_RUNNING = "PERIOD_RUNNING"
PERIOD_PAUSED = "PERIOD_PAUSED"
TIMEOUT = "TIMEOUT"
FREE_THROW = "FREE_THROW"
PERIOD_END = "PERIOD_END"
OVERTIME = "OVERTIME"
GAME_END = "GAME_END"

VALID_PHASES = {
    PRE_GAME,
    PERIOD_RUNNING,
    PERIOD_PAUSED,
    TIMEOUT,
    FREE_THROW,
    PERIOD_END,
    OVERTIME,
    GAME_END,
}

DEFAULT_PERIOD_MINUTES = 10
DEFAULT_OVERTIME_MINUTES = 5
DEFAULT_SHOT_CLOCK = 24
DEFAULT_OFFENSIVE_REBOUND_SHOT_CLOCK = 14
PERSONAL_FOUL_LIMIT = 5
TEAM_FOUL_BONUS_LIMIT = 5


def _now_ms() -> int:
    """返回毫秒时间戳，便于客户端判断状态是否更新。"""
    return int(time.time() * 1000)


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return int(default)


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def _team_key(team: str, suffix: str) -> str:
    """把 home/away 转换成 home_score、away_fouls 等字段名。"""
    if team not in ("home", "away"):
        raise ValueError(f"未知队伍：{team}")
    return f"{team}_{suffix}"


def period_label(period: int, regulation_periods: int = 4) -> str:
    """
    返回适合 UI 显示的节次文字。

    1~4  -> 第1节~第4节
    5    -> 加时1
    6    -> 加时2
    """
    period = max(1, int(period))
    regulation_periods = max(1, int(regulation_periods))
    if period <= regulation_periods:
        return f"第{period}节"
    return f"加时{period - regulation_periods}"


def format_clock(seconds_left: float) -> str:
    """把秒数格式化为 MM:SS。"""
    seconds_left = max(0, int(round(seconds_left)))
    return f"{seconds_left // 60:02d}:{seconds_left % 60:02d}"


# ---------------------------------------------------------------------------
# 二、名单和球员数据结构
# ---------------------------------------------------------------------------

def default_roster() -> Dict[str, Any]:
    """没有名单文件时使用的最小示例名单。"""
    return {
        "home_name": "主队",
        "away_name": "客队",
        "players": {
            "home": [
                {"number": "7", "name": "詹嘉裕"},
                {"number": "11", "name": "陈浩年"},
                {"number": "23", "name": "韦泽友"},
            ],
            "away": [
                {"number": "3", "name": "张三"},
                {"number": "8", "name": "李四"},
                {"number": "10", "name": "王五"},
            ],
        },
    }


def normalize_player(player: Dict[str, Any], starter_default: bool = False) -> Dict[str, Any]:
    """
    把旧名单中的简单球员对象升级为 V3 技术统计对象。

    on_court / starter 由 UI 管理；其余统计会在比赛操作时自动累计。
    """
    return {
        "number": str(player.get("number", "")).strip(),
        "name": str(player.get("name", "")).strip(),
        "points": _safe_int(player.get("points", 0)),
        "fouls": _safe_int(player.get("fouls", 0)),
        "ft_made": _safe_int(player.get("ft_made", 0)),
        "ft_attempts": _safe_int(player.get("ft_attempts", 0)),
        "two_made": _safe_int(player.get("two_made", 0)),
        "three_made": _safe_int(player.get("three_made", 0)),
        "rebounds": _safe_int(player.get("rebounds", 0)),
        "assists": _safe_int(player.get("assists", 0)),
        "steals": _safe_int(player.get("steals", 0)),
        "blocks": _safe_int(player.get("blocks", 0)),
        "turnovers": _safe_int(player.get("turnovers", 0)),
        "starter": bool(player.get("starter", starter_default)),
        "on_court": bool(player.get("on_court", starter_default)),
        "fouled_out": bool(
            player.get(
                "fouled_out",
                _safe_int(player.get("fouls", 0)) >= PERSONAL_FOUL_LIMIT,
            )
        ),
    }


def _normalize_team_players(players: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    默认把名单前 5 人设为首发和在场球员。

    少于 5 人时全部在场；已有 starter/on_court 字段时尊重原值。
    """
    normalized: List[Dict[str, Any]] = []
    for index, player in enumerate(players or []):
        explicit = "starter" in player or "on_court" in player
        normalized.append(
            normalize_player(
                player,
                starter_default=(index < 5 and not explicit),
            )
        )
    return normalized


def find_player_index(
    state: Dict[str, Any],
    team: str,
    number: str,
    name: str = "",
) -> int:
    """优先按球衣号查找，找不到时再按姓名查找。"""
    players = state.get("players", {}).get(team, [])
    for index, player in enumerate(players):
        if str(player.get("number", "")) == str(number):
            return index
    if name:
        for index, player in enumerate(players):
            if str(player.get("name", "")) == str(name):
                return index
    return -1


def get_player_text(player: Optional[Dict[str, Any]]) -> str:
    """生成“7号 张三”形式的显示文本。"""
    if not player:
        return "未选择球员"
    number = str(player.get("number", "")).strip()
    name = str(player.get("name", "")).strip()
    if number and name:
        return f"{number}号 {name}"
    return number or name or "未知球员"


# ---------------------------------------------------------------------------
# 三、默认比赛状态和旧状态升级
# ---------------------------------------------------------------------------

def _default_period_stats() -> Dict[str, Dict[str, int]]:
    return {
        "home": {
            "points": 0,
            "fouls": 0,
            "ft_made": 0,
            "ft_attempts": 0,
            "two_made": 0,
            "three_made": 0,
            "rebounds": 0,
            "assists": 0,
            "steals": 0,
            "blocks": 0,
            "turnovers": 0,
        },
        "away": {
            "points": 0,
            "fouls": 0,
            "ft_made": 0,
            "ft_attempts": 0,
            "two_made": 0,
            "three_made": 0,
            "rebounds": 0,
            "assists": 0,
            "steals": 0,
            "blocks": 0,
            "turnovers": 0,
        },
    }


def make_default_state(
    period_minutes: int = DEFAULT_PERIOD_MINUTES,
    roster: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """创建一场全新的 V3 比赛状态。"""
    roster = roster or default_roster()
    period_minutes = max(1, int(period_minutes))

    home_players = _normalize_team_players(
        roster.get("players", {}).get("home", [])
    )
    away_players = _normalize_team_players(
        roster.get("players", {}).get("away", [])
    )

    state = {
        "version": 3,
        "phase": PRE_GAME,
        "home_name": str(roster.get("home_name", "主队")),
        "away_name": str(roster.get("away_name", "客队")),
        "home_score": 0,
        "away_score": 0,
        # 兼容旧字段：表示当前单节球队犯规。
        "home_fouls": 0,
        "away_fouls": 0,
        "regulation_periods": 4,
        "period": 1,
        "period_minutes": period_minutes,
        "overtime_minutes": DEFAULT_OVERTIME_MINUTES,
        "clock_sec_left": period_minutes * 60,
        "clock_running": False,
        "shot_clock_sec": float(DEFAULT_SHOT_CLOCK),
        "shot_clock_running": False,
        "shot_clock_default": DEFAULT_SHOT_CLOCK,
        "shot_clock_offensive_rebound": DEFAULT_OFFENSIVE_REBOUND_SHOT_CLOCK,
        "possession": None,
        # FIBA 风格的手动暂停额度：上半场 2 次、下半场 3 次。
        "timeouts_remaining": {"home": 2, "away": 2},
        "timeout_half_initialized": 1,
        "selected_player": None,
        "free_throw_team": None,
        "players": {
            "home": home_players,
            "away": away_players,
        },
        # period_stats 使用字符串键，JSON 保存后不会发生 int/string 混乱。
        "period_stats": {"1": _default_period_stats()},
        "alerts": [],
        "last_event": "比赛未开始",
        # 给自动导播读取的轻量提示，不包含 UI 对象。
        "director_hint": {
            "mode": "HOLD",
            "reason": PRE_GAME,
            "free_throw_team": None,
        },
        "updated_at_ms": _now_ms(),
    }
    refresh_derived_fields(state)
    return state


def upgrade_state(
    state: Optional[Dict[str, Any]],
    period_minutes: int = DEFAULT_PERIOD_MINUTES,
    roster: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    把 V1/V2 JSON 升级为 V3。

    原字段会尽量保留；新字段使用默认值补齐。这样用户不需要手动删除
    旧 game_state.json。
    """
    base = make_default_state(period_minutes, roster)
    if not isinstance(state, dict):
        return base

    # 先覆盖简单顶层字段。
    for key, value in state.items():
        if key != "players":
            base[key] = copy.deepcopy(value)

    # 球员必须逐个补齐新统计字段。
    old_players = state.get("players", {})
    for team in ("home", "away"):
        source = old_players.get(team)
        if isinstance(source, list):
            base["players"][team] = _normalize_team_players(source)

    if base.get("phase") not in VALID_PHASES:
        base["phase"] = (
            PERIOD_RUNNING
            if bool(base.get("clock_running"))
            else PERIOD_PAUSED
        )

    # 旧版本没有 period_stats，按当前比分建立一个兼容快照。
    if not isinstance(base.get("period_stats"), dict):
        base["period_stats"] = {}
    current_key = str(max(1, _safe_int(base.get("period", 1), 1)))
    base["period_stats"].setdefault(current_key, _default_period_stats())

    base["version"] = 3
    refresh_derived_fields(base)
    return base


def _ensure_period_stats(state: Dict[str, Any]) -> Dict[str, Dict[str, int]]:
    """
    返回当前节统计，并为旧 V2/V3 JSON 补齐后来新增的统计字段。
    """
    key = str(max(1, _safe_int(state.get("period", 1), 1)))
    period_stats = state.setdefault("period_stats", {})
    current = period_stats.setdefault(key, _default_period_stats())

    defaults = _default_period_stats()
    for team in ("home", "away"):
        team_data = current.setdefault(team, {})
        for stat_name, default_value in defaults[team].items():
            team_data.setdefault(stat_name, default_value)
    return current


def _team_full_stats(state: Dict[str, Any], team: str) -> Dict[str, int]:
    """汇总所有节次的球队统计。"""
    total = {
        "points": 0,
        "fouls": 0,
        "ft_made": 0,
        "ft_attempts": 0,
        "two_made": 0,
        "three_made": 0,
        "rebounds": 0,
        "assists": 0,
        "steals": 0,
        "blocks": 0,
        "turnovers": 0,
    }
    for period_data in state.get("period_stats", {}).values():
        team_data = period_data.get(team, {})
        for key in total:
            total[key] += _safe_int(team_data.get(key, 0))
    return total


def build_statistics_snapshot(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    生成网页和 LCD 可直接显示的单节/全场统计。

    这是派生数据，不作为唯一事实来源；基础数据仍保存在 period_stats 和 players。
    """
    current = _ensure_period_stats(state)
    return {
        "current_period": copy.deepcopy(current),
        "full_game": {
            "home": _team_full_stats(state, "home"),
            "away": _team_full_stats(state, "away"),
        },
    }


def refresh_derived_fields(state: Dict[str, Any]) -> None:
    """
    每次状态变化后统一刷新派生字段。

    包括：
        BONUS 状态、球员满犯提醒、统计快照、导播提示等。
    """
    period = max(1, _safe_int(state.get("period", 1), 1))
    regulation_periods = max(
        1,
        _safe_int(state.get("regulation_periods", 4), 4),
    )

    state["period"] = period
    state["home_fouls"] = max(0, _safe_int(state.get("home_fouls", 0)))
    state["away_fouls"] = max(0, _safe_int(state.get("away_fouls", 0)))
    state["clock_sec_left"] = max(
        0.0,
        _safe_float(state.get("clock_sec_left", 0)),
    )
    state["shot_clock_sec"] = max(
        0.0,
        _safe_float(
            state.get("shot_clock_sec", DEFAULT_SHOT_CLOCK),
            DEFAULT_SHOT_CLOCK,
        ),
    )

    state["bonus"] = {
        "home": state["away_fouls"] >= TEAM_FOUL_BONUS_LIMIT,
        "away": state["home_fouls"] >= TEAM_FOUL_BONUS_LIMIT,
    }

    # 个人犯规达到上限时标记 fouled_out。
    foul_out_players = []
    for team in ("home", "away"):
        for player in state.get("players", {}).get(team, []):
            player["fouled_out"] = (
                _safe_int(player.get("fouls", 0)) >= PERSONAL_FOUL_LIMIT
            )
            if player["fouled_out"]:
                foul_out_players.append(
                    {
                        "team": team,
                        "number": str(player.get("number", "")),
                        "name": str(player.get("name", "")),
                    }
                )
    state["fouled_out_players"] = foul_out_players
    state["statistics"] = build_statistics_snapshot(state)

    phase = str(state.get("phase", PRE_GAME))
    clock_running = bool(state.get("clock_running", False))

    if phase == FREE_THROW:
        director_mode = "FREE_THROW"
    elif phase in (TIMEOUT, PERIOD_END, GAME_END, PRE_GAME):
        director_mode = "HOLD"
    elif phase == PERIOD_PAUSED and not clock_running:
        director_mode = "HOLD"
    else:
        director_mode = "NORMAL"

    state["director_hint"] = {
        "mode": director_mode,
        "reason": phase,
        "free_throw_team": state.get("free_throw_team"),
        "period": period,
        "overtime": period > regulation_periods,
    }
    state["updated_at_ms"] = _now_ms()


# ---------------------------------------------------------------------------
# 四、JSON 与事件日志
# ---------------------------------------------------------------------------

def atomic_write_json(path: str, data: Dict[str, Any]) -> None:
    """先写临时文件再原子替换，避免客户端读到半个 JSON。"""
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    temp_path = path + ".tmp"
    with open(temp_path, "w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)
        file.flush()
        os.fsync(file.fileno())
    os.replace(temp_path, path)


def load_json(path: str) -> Optional[Dict[str, Any]]:
    if not path or not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as file:
            return json.load(file)
    except Exception:
        return None


def load_roster(path: Optional[str]) -> Optional[Dict[str, Any]]:
    return load_json(path) if path else None


def save_event(events_path: str, event: Dict[str, Any]) -> None:
    if not events_path:
        return
    os.makedirs(os.path.dirname(os.path.abspath(events_path)), exist_ok=True)
    row = dict(event)
    row.setdefault("created_at_ms", _now_ms())
    with open(events_path, "a", encoding="utf-8") as file:
        file.write(json.dumps(row, ensure_ascii=False) + "\n")


def make_snapshot(state: Dict[str, Any]) -> Dict[str, Any]:
    return copy.deepcopy(state)


# ---------------------------------------------------------------------------
# 五、统一比赛控制器
# ---------------------------------------------------------------------------

class GameController:
    """
    LCD 与网页共享的线程安全比赛控制器。

    所有写操作必须经过 apply_action()。这样：
        - 网页和 LCD 的规则完全一致；
        - 撤销可以覆盖两端操作；
        - JSON、事件日志和导播提示同步更新；
        - HTTP 线程和 Qt 主线程不会同时破坏状态。
    """

    def __init__(
        self,
        state_path: str,
        events_path: str,
        roster: Optional[Dict[str, Any]] = None,
        period_minutes: int = DEFAULT_PERIOD_MINUTES,
        history_limit: int = 200,
    ):
        self.state_path = os.path.abspath(state_path)
        self.events_path = os.path.abspath(events_path)
        self.roster = roster or default_roster()
        self.period_minutes = max(1, int(period_minutes))
        self.history_limit = max(10, int(history_limit))
        self.lock = threading.RLock()
        self.history: List[Dict[str, Any]] = []

        loaded = load_json(self.state_path)
        self.state = upgrade_state(
            loaded,
            period_minutes=self.period_minutes,
            roster=self.roster,
        )
        self._last_saved_second: Optional[Tuple[int, int]] = None
        self.save()

    def get_state(self) -> Dict[str, Any]:
        """返回深拷贝，外部不能绕过控制器直接修改内部状态。"""
        with self.lock:
            return copy.deepcopy(self.state)

    def save(self) -> None:
        with self.lock:
            refresh_derived_fields(self.state)
            atomic_write_json(self.state_path, self.state)

    def _push_history(self) -> None:
        self.history.append(copy.deepcopy(self.state))
        if len(self.history) > self.history_limit:
            self.history.pop(0)

    def _selected_player(self, team: Optional[str] = None) -> Optional[Dict[str, Any]]:
        selected = self.state.get("selected_player")
        if not isinstance(selected, dict):
            return None
        if team is not None and selected.get("team") != team:
            return None
        return selected

    def _player_object(
        self,
        team: str,
        number: str,
        name: str = "",
    ) -> Optional[Dict[str, Any]]:
        index = find_player_index(self.state, team, number, name)
        if index < 0:
            return None
        return self.state["players"][team][index]

    def _set_last_event(self, text: str, alert: Optional[str] = None) -> None:
        self.state["last_event"] = str(text)
        if alert:
            alerts = self.state.setdefault("alerts", [])
            alerts.append(
                {
                    "time_ms": _now_ms(),
                    "text": str(alert),
                }
            )
            # 只保留最近 20 条提醒，避免 JSON 无限增长。
            del alerts[:-20]

    def _log_action(
        self,
        action: str,
        payload: Dict[str, Any],
        source: str,
    ) -> None:
        save_event(
            self.events_path,
            {
                "type": action,
                "source": source,
                "payload": copy.deepcopy(payload),
                "period": self.state.get("period", 1),
                "period_label": period_label(
                    self.state.get("period", 1),
                    self.state.get("regulation_periods", 4),
                ),
                "clock": format_clock(self.state.get("clock_sec_left", 0)),
                "shot_clock": round(
                    _safe_float(self.state.get("shot_clock_sec", 0)),
                    1,
                ),
                "phase": self.state.get("phase"),
                "last_event": self.state.get("last_event"),
            },
        )

    def _reset_period_clocks(self, overtime: bool) -> None:
        minutes = (
            _safe_int(self.state.get("overtime_minutes", 5), 5)
            if overtime
            else _safe_int(
                self.state.get("period_minutes", self.period_minutes),
                self.period_minutes,
            )
        )
        self.state["clock_sec_left"] = max(1, minutes) * 60
        self.state["clock_running"] = False
        self.state["shot_clock_sec"] = float(
            self.state.get("shot_clock_default", DEFAULT_SHOT_CLOCK)
        )
        self.state["shot_clock_running"] = False
        self.state["home_fouls"] = 0
        self.state["away_fouls"] = 0
        self.state["possession"] = None
        self.state["free_throw_team"] = None

    def _ensure_timeout_bank_for_period(self) -> None:
        """
        进入下半场或加时时初始化暂停额度。

        这里使用 FIBA 风格的常见额度：
            上半场 2 次；
            下半场 3 次；
            每个加时 1 次。
        """
        period = _safe_int(self.state.get("period", 1), 1)
        initialized = _safe_int(
            self.state.get("timeout_half_initialized", 1),
            1,
        )
        regulation = _safe_int(
            self.state.get("regulation_periods", 4),
            4,
        )

        if period >= 3 and period <= regulation and initialized < 2:
            self.state["timeouts_remaining"] = {"home": 3, "away": 3}
            self.state["timeout_half_initialized"] = 2
        elif period > regulation:
            self.state["timeouts_remaining"] = {"home": 1, "away": 1}
            self.state["timeout_half_initialized"] = period

    def apply_action(
        self,
        action: str,
        payload: Optional[Dict[str, Any]] = None,
        source: str = "unknown",
    ) -> Dict[str, Any]:
        """
        执行一次比赛动作并返回更新后的状态。

        action 使用字符串而不是直接调用 UI 方法，便于：
            - HTTP POST；
            - LCD 按钮；
            - 后续串口控制器或遥控器；
            - 自动化测试。
        """
        payload = dict(payload or {})
        action = str(action or "").strip()

        with self.lock:
            if not action:
                raise ValueError("action 不能为空")

            if action == "undo":
                if self.history:
                    previous_event = self.state.get("last_event", "上一操作")
                    self.state = self.history.pop()
                    self._set_last_event(f"已撤销：{previous_event}")
                else:
                    self._set_last_event("没有可撤销操作")
                refresh_derived_fields(self.state)
                atomic_write_json(self.state_path, self.state)
                self._log_action(action, payload, source)
                return copy.deepcopy(self.state)

            # 纯选择动作也允许撤销，统一行为更易理解。
            self._push_history()

            if action == "team_names":
                self.state["home_name"] = (
                    str(payload.get("home_name", "")).strip()
                    or self.state.get("home_name", "主队")
                )
                self.state["away_name"] = (
                    str(payload.get("away_name", "")).strip()
                    or self.state.get("away_name", "客队")
                )
                self._set_last_event("已更新队名")

            elif action == "select_player":
                team = str(payload.get("team", ""))
                number = str(payload.get("number", ""))
                name = str(payload.get("name", ""))
                player = self._player_object(team, number, name)
                if player is None:
                    raise ValueError("找不到要选择的球员")
                self.state["selected_player"] = {
                    "team": team,
                    "number": str(player.get("number", "")),
                    "name": str(player.get("name", "")),
                }
                self._set_last_event(
                    f"已选择 {get_player_text(self.state['selected_player'])}"
                )

            elif action == "clear_selected_player":
                self.state["selected_player"] = None
                self._set_last_event("已清除球员选择")

            elif action == "score":
                team = str(payload.get("team", ""))
                value = max(1, min(3, _safe_int(payload.get("value", 1), 1)))
                score_key = _team_key(team, "score")
                self.state[score_key] = _safe_int(
                    self.state.get(score_key, 0)
                ) + value

                period_team = _ensure_period_stats(self.state)[team]
                period_team["points"] += value
                if value == 2:
                    period_team["two_made"] += 1
                elif value == 3:
                    period_team["three_made"] += 1

                selected = self._selected_player(team)
                if selected:
                    player = self._player_object(
                        team,
                        str(selected.get("number", "")),
                        str(selected.get("name", "")),
                    )
                else:
                    player = None

                if player is not None:
                    player["points"] = _safe_int(player.get("points", 0)) + value
                    if value == 2:
                        player["two_made"] = _safe_int(
                            player.get("two_made", 0)
                        ) + 1
                    elif value == 3:
                        player["three_made"] = _safe_int(
                            player.get("three_made", 0)
                        ) + 1
                    event_text = (
                        f"{get_player_text(player)} +{value}，"
                        f"本场{player['points']}分"
                    )
                else:
                    event_text = (
                        f"{self.state.get(team + '_name', team)} +{value}"
                    )

                # 正常进球后默认交换球权并回 24 秒。
                self.state["possession"] = (
                    "away" if team == "home" else "home"
                )
                self.state["shot_clock_sec"] = float(
                    self.state.get(
                        "shot_clock_default",
                        DEFAULT_SHOT_CLOCK,
                    )
                )
                self.state["shot_clock_running"] = bool(
                    self.state.get("clock_running", False)
                )
                self._set_last_event(event_text)

            elif action == "foul":
                team = str(payload.get("team", ""))
                foul_key = _team_key(team, "fouls")
                self.state[foul_key] = _safe_int(
                    self.state.get(foul_key, 0)
                ) + 1
                _ensure_period_stats(self.state)[team]["fouls"] += 1

                selected = self._selected_player(team)
                player = None
                if selected:
                    player = self._player_object(
                        team,
                        str(selected.get("number", "")),
                        str(selected.get("name", "")),
                    )

                alert = None
                if player is not None:
                    player["fouls"] = _safe_int(player.get("fouls", 0)) + 1
                    if player["fouls"] >= PERSONAL_FOUL_LIMIT:
                        player["fouled_out"] = True
                        player["on_court"] = False
                        alert = (
                            f"{get_player_text(player)} 已满 "
                            f"{PERSONAL_FOUL_LIMIT} 次犯规"
                        )
                    event_text = (
                        f"{get_player_text(player)} 第{player['fouls']}犯"
                    )
                else:
                    event_text = (
                        f"{self.state.get(team + '_name', team)} 队犯规 +1"
                    )

                if self.state[foul_key] >= TEAM_FOUL_BONUS_LIMIT:
                    bonus_text = (
                        f"{self.state.get(team + '_name', team)} "
                        "单节犯规已进入罚球状态"
                    )
                    alert = f"{alert}；{bonus_text}" if alert else bonus_text

                self.state["clock_running"] = False
                self.state["shot_clock_running"] = False
                if self.state.get("phase") not in (FREE_THROW, TIMEOUT):
                    self.state["phase"] = PERIOD_PAUSED
                self._set_last_event(event_text, alert=alert)

            elif action == "free_throw":
                team = str(payload.get("team", ""))
                made = bool(payload.get("made", False))
                self.state["phase"] = FREE_THROW
                self.state["free_throw_team"] = team
                self.state["clock_running"] = False
                self.state["shot_clock_running"] = False

                period_team = _ensure_period_stats(self.state)[team]
                period_team["ft_attempts"] += 1
                if made:
                    period_team["ft_made"] += 1
                    period_team["points"] += 1
                    score_key = _team_key(team, "score")
                    self.state[score_key] = _safe_int(
                        self.state.get(score_key, 0)
                    ) + 1

                selected = self._selected_player(team)
                player = None
                if selected:
                    player = self._player_object(
                        team,
                        str(selected.get("number", "")),
                        str(selected.get("name", "")),
                    )
                if player is not None:
                    player["ft_attempts"] = _safe_int(
                        player.get("ft_attempts", 0)
                    ) + 1
                    if made:
                        player["ft_made"] = _safe_int(
                            player.get("ft_made", 0)
                        ) + 1
                        player["points"] = _safe_int(
                            player.get("points", 0)
                        ) + 1
                    who = get_player_text(player)
                else:
                    who = self.state.get(team + "_name", team)

                self._set_last_event(
                    f"{who} 罚球{'命中' if made else '未中'}"
                )

            elif action == "free_throw_end":
                self.state["phase"] = PERIOD_PAUSED
                self.state["free_throw_team"] = None
                self.state["shot_clock_sec"] = float(
                    self.state.get(
                        "shot_clock_default",
                        DEFAULT_SHOT_CLOCK,
                    )
                )
                self._set_last_event("罚球结束，等待发球")

            elif action == "clock_toggle":
                phase = self.state.get("phase")

                # 加时赛保持 OVERTIME 状态，通过 clock_running 区分运行/暂停。
                if phase == OVERTIME:
                    running = not bool(self.state.get("clock_running", False))
                    self.state["clock_running"] = running
                    self.state["shot_clock_running"] = running
                    self._set_last_event(
                        "加时赛开始" if running else "加时赛暂停"
                    )

                elif phase in (PRE_GAME, PERIOD_PAUSED):
                    self.state["clock_running"] = True
                    self.state["shot_clock_running"] = True
                    self.state["phase"] = PERIOD_RUNNING
                    self._set_last_event("比赛时间开始")

                elif phase == PERIOD_RUNNING:
                    self.state["clock_running"] = False
                    self.state["shot_clock_running"] = False
                    self.state["phase"] = PERIOD_PAUSED
                    self._set_last_event("比赛时间暂停")

                else:
                    self._set_last_event(
                        f"当前状态 {self.state.get('phase')} 不能直接开表"
                    )

            elif action == "reset_clock":
                overtime = (
                    _safe_int(self.state.get("period", 1), 1)
                    > _safe_int(self.state.get("regulation_periods", 4), 4)
                )
                self._reset_period_clocks(overtime)
                self.state["phase"] = OVERTIME if overtime else PERIOD_PAUSED
                self._set_last_event("已重置本节时间")

            elif action == "shot_toggle":
                self.state["shot_clock_running"] = not bool(
                    self.state.get("shot_clock_running", False)
                )
                self._set_last_event(
                    "24秒开始"
                    if self.state["shot_clock_running"]
                    else "24秒暂停"
                )

            elif action in ("shot_reset_24", "shot_reset_14"):
                seconds = (
                    _safe_int(
                        self.state.get(
                            "shot_clock_offensive_rebound",
                            DEFAULT_OFFENSIVE_REBOUND_SHOT_CLOCK,
                        ),
                        DEFAULT_OFFENSIVE_REBOUND_SHOT_CLOCK,
                    )
                    if action == "shot_reset_14"
                    else _safe_int(
                        self.state.get(
                            "shot_clock_default",
                            DEFAULT_SHOT_CLOCK,
                        ),
                        DEFAULT_SHOT_CLOCK,
                    )
                )
                self.state["shot_clock_sec"] = float(seconds)
                self.state["shot_clock_running"] = bool(
                    self.state.get("clock_running", False)
                )
                self._set_last_event(f"进攻时间回表 {seconds} 秒")

            elif action == "possession":
                team = payload.get("team")
                if team not in ("home", "away", None, ""):
                    raise ValueError("球权必须是 home、away 或空")
                self.state["possession"] = team or None
                if team:
                    self.state["shot_clock_sec"] = float(
                        self.state.get(
                            "shot_clock_default",
                            DEFAULT_SHOT_CLOCK,
                        )
                    )
                    self.state["shot_clock_running"] = bool(
                        self.state.get("clock_running", False)
                    )
                    self._set_last_event(
                        f"球权：{self.state.get(team + '_name', team)}"
                    )
                else:
                    self._set_last_event("已清除球权")

            elif action == "timeout":
                team = str(payload.get("team", ""))
                remaining = self.state.setdefault(
                    "timeouts_remaining",
                    {"home": 0, "away": 0},
                )
                if _safe_int(remaining.get(team, 0)) <= 0:
                    self._set_last_event(
                        f"{self.state.get(team + '_name', team)} 已无暂停",
                        alert="暂停次数不足",
                    )
                else:
                    remaining[team] = _safe_int(remaining.get(team, 0)) - 1
                    self.state["phase"] = TIMEOUT
                    self.state["clock_running"] = False
                    self.state["shot_clock_running"] = False
                    self._set_last_event(
                        f"{self.state.get(team + '_name', team)} 请求暂停，"
                        f"剩余{remaining[team]}次"
                    )

            elif action == "timeout_end":
                self.state["phase"] = (
                    OVERTIME
                    if self.state.get("period", 1)
                    > self.state.get("regulation_periods", 4)
                    else PERIOD_PAUSED
                )
                self._set_last_event("暂停结束，等待开表")

            elif action == "period_end":
                self.state["phase"] = PERIOD_END
                self.state["clock_running"] = False
                self.state["shot_clock_running"] = False
                self._set_last_event(
                    f"{period_label(self.state.get('period', 1))}结束"
                )

            elif action == "next_period":
                current = _safe_int(self.state.get("period", 1), 1)
                regulation = _safe_int(
                    self.state.get("regulation_periods", 4),
                    4,
                )
                tied = (
                    _safe_int(self.state.get("home_score", 0))
                    == _safe_int(self.state.get("away_score", 0))
                )

                if current < regulation:
                    self.state["period"] = current + 1
                    overtime = False
                elif current >= regulation and tied:
                    self.state["period"] = current + 1
                    overtime = True
                else:
                    self.state["phase"] = GAME_END
                    self.state["clock_running"] = False
                    self.state["shot_clock_running"] = False
                    self._set_last_event("全场比赛结束")
                    overtime = current > regulation

                if self.state.get("phase") != GAME_END:
                    self._reset_period_clocks(overtime)
                    self._ensure_timeout_bank_for_period()
                    _ensure_period_stats(self.state)
                    self.state["phase"] = (
                        OVERTIME if overtime else PERIOD_PAUSED
                    )
                    self._set_last_event(
                        f"进入{period_label(self.state['period'], regulation)}"
                    )

            elif action == "set_period":
                target = max(1, _safe_int(payload.get("period", 1), 1))
                self.state["period"] = target
                overtime = target > _safe_int(
                    self.state.get("regulation_periods", 4),
                    4,
                )
                self._reset_period_clocks(overtime)
                self._ensure_timeout_bank_for_period()
                _ensure_period_stats(self.state)
                self.state["phase"] = OVERTIME if overtime else PERIOD_PAUSED
                self._set_last_event(
                    f"已切换到{period_label(target, self.state.get('regulation_periods', 4))}"
                )

            elif action == "substitution":
                team = str(payload.get("team", ""))
                out_number = str(payload.get("out_number", ""))
                in_number = str(payload.get("in_number", ""))
                outgoing = self._player_object(team, out_number)
                incoming = self._player_object(team, in_number)
                if outgoing is None or incoming is None:
                    raise ValueError("换人失败：找不到换入或换出球员")
                if outgoing is incoming:
                    raise ValueError("换入和换出不能是同一名球员")
                outgoing["on_court"] = False
                incoming["on_court"] = True
                self._set_last_event(
                    f"{self.state.get(team + '_name', team)} 换人："
                    f"{get_player_text(incoming)} 换下 "
                    f"{get_player_text(outgoing)}"
                )

            elif action == "set_on_court":
                team = str(payload.get("team", ""))
                number = str(payload.get("number", ""))
                on_court = bool(payload.get("on_court", True))
                player = self._player_object(team, number)
                if player is None:
                    raise ValueError("找不到球员")
                if on_court and player.get("fouled_out"):
                    raise ValueError("该球员已满犯，不能重新设为在场")
                player["on_court"] = on_court
                self._set_last_event(
                    f"{get_player_text(player)} "
                    f"{'进入场上' if on_court else '离开场上'}"
                )

            elif action == "set_starter":
                team = str(payload.get("team", ""))
                number = str(payload.get("number", ""))
                starter = bool(payload.get("starter", True))
                player = self._player_object(team, number)
                if player is None:
                    raise ValueError("找不到球员")
                player["starter"] = starter
                if starter and not player.get("fouled_out"):
                    player["on_court"] = True
                self._set_last_event(
                    f"{get_player_text(player)} "
                    f"{'设为首发' if starter else '取消首发'}"
                )

            elif action == "player_stat":
                # 给当前选中球员记录篮板、助攻、抢断或盖帽。
                # LCD/网页只需要发送 stat 字符串，不直接接触球员对象。
                team = str(payload.get("team", ""))
                stat = str(payload.get("stat", ""))
                stat_names = {
                    "rebounds": "篮板",
                    "assists": "助攻",
                    "steals": "抢断",
                    "blocks": "盖帽",
                }
                if stat not in stat_names:
                    raise ValueError("stat 必须是 rebounds/assists/steals/blocks")

                selected = self._selected_player(team)
                if not selected:
                    raise ValueError("请先选择同队球员")

                player = self._player_object(
                    team,
                    str(selected.get("number", "")),
                    str(selected.get("name", "")),
                )
                if player is None:
                    raise ValueError("找不到当前选中球员")

                player[stat] = _safe_int(player.get(stat, 0)) + 1
                _ensure_period_stats(self.state)[team][stat] += 1
                self._set_last_event(
                    f"{get_player_text(player)} {stat_names[stat]} +1"
                )

            elif action == "turnover":
                team = str(payload.get("team", ""))
                _ensure_period_stats(self.state)[team]["turnovers"] += 1

                selected = self._selected_player(team)
                if selected:
                    player = self._player_object(
                        team,
                        str(selected.get("number", "")),
                        str(selected.get("name", "")),
                    )
                else:
                    player = None
                if player is not None:
                    player["turnovers"] = _safe_int(
                        player.get("turnovers", 0)
                    ) + 1
                    event_text = f"{get_player_text(player)} 失误"
                else:
                    event_text = (
                        f"{self.state.get(team + '_name', team)} 失误"
                    )

                self.state["possession"] = (
                    "away" if team == "home" else "home"
                )
                self.state["shot_clock_sec"] = float(
                    self.state.get(
                        "shot_clock_default",
                        DEFAULT_SHOT_CLOCK,
                    )
                )
                self._set_last_event(event_text)

            elif action == "game_end":
                self.state["phase"] = GAME_END
                self.state["clock_running"] = False
                self.state["shot_clock_running"] = False
                self._set_last_event("全场比赛结束")

            elif action == "reset_game":
                keep_names = {
                    "home_name": self.state.get("home_name", "主队"),
                    "away_name": self.state.get("away_name", "客队"),
                    "players": {
                        team: [
                            {
                                "number": player.get("number", ""),
                                "name": player.get("name", ""),
                                "starter": player.get("starter", False),
                                "on_court": player.get("starter", False),
                            }
                            for player in self.state.get("players", {}).get(team, [])
                        ]
                        for team in ("home", "away")
                    },
                }
                self.state = make_default_state(
                    period_minutes=self.period_minutes,
                    roster=keep_names,
                )
                self._set_last_event("已重置整场比赛")

            else:
                raise ValueError(f"未知 action：{action}")

            refresh_derived_fields(self.state)
            atomic_write_json(self.state_path, self.state)
            self._log_action(action, payload, source)
            return copy.deepcopy(self.state)

    def tick(self, elapsed_sec: float) -> Dict[str, Any]:
        """
        推进比赛时间和 24 秒。

        Qt 定时器每 100~200 ms 调用一次即可。为了减少 TF 卡写入，
        JSON 只在显示秒数发生变化或计时归零时写盘。
        """
        elapsed = max(0.0, min(1.0, float(elapsed_sec)))
        if elapsed <= 0:
            return self.get_state()

        with self.lock:
            changed = False
            urgent = False

            if bool(self.state.get("clock_running", False)):
                before = _safe_float(self.state.get("clock_sec_left", 0))
                after = max(0.0, before - elapsed)
                self.state["clock_sec_left"] = after
                changed = True
                if after <= 0:
                    self.state["clock_running"] = False
                    self.state["shot_clock_running"] = False
                    self.state["phase"] = PERIOD_END
                    self._set_last_event(
                        f"{period_label(self.state.get('period', 1))}时间到"
                    )
                    urgent = True

            if bool(self.state.get("shot_clock_running", False)):
                before = _safe_float(
                    self.state.get("shot_clock_sec", DEFAULT_SHOT_CLOCK)
                )
                after = max(0.0, before - elapsed)
                self.state["shot_clock_sec"] = after
                changed = True
                if after <= 0:
                    self.state["shot_clock_running"] = False
                    self.state["clock_running"] = False
                    self.state["phase"] = PERIOD_PAUSED
                    offense = self.state.get("possession")
                    if offense in ("home", "away"):
                        _ensure_period_stats(self.state)[offense][
                            "turnovers"
                        ] += 1
                        self.state["possession"] = (
                            "away" if offense == "home" else "home"
                        )
                    self._set_last_event(
                        "24秒违例",
                        alert="24秒进攻时间到",
                    )
                    urgent = True

            if changed:
                refresh_derived_fields(self.state)
                second_key = (
                    int(self.state.get("clock_sec_left", 0)),
                    int(self.state.get("shot_clock_sec", 0)),
                )
                if urgent or second_key != self._last_saved_second:
                    self._last_saved_second = second_key
                    atomic_write_json(self.state_path, self.state)

            return copy.deepcopy(self.state)
