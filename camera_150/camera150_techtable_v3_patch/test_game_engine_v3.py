#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""技术台 V3 纯逻辑测试，不需要摄像头、PyQt5 或 RKNN。"""

from __future__ import annotations

import tempfile
from pathlib import Path

from state_store import (
    FREE_THROW,
    OVERTIME,
    PERIOD_END,
    PERIOD_PAUSED,
    PERIOD_RUNNING,
    TIMEOUT,
    GameController,
    default_roster,
)


def main() -> int:
    with tempfile.TemporaryDirectory() as temp_dir:
        controller = GameController(
            state_path=str(Path(temp_dir) / "game_state.json"),
            events_path=str(Path(temp_dir) / "events.jsonl"),
            roster=default_roster(),
            period_minutes=10,
        )

        controller.apply_action(
            "select_player",
            {"team": "home", "number": "7", "name": "詹嘉裕"},
            source="test",
        )
        controller.apply_action(
            "score",
            {"team": "home", "value": 3},
            source="test",
        )
        controller.apply_action(
            "player_stat",
            {"team": "home", "stat": "rebounds"},
            source="test",
        )
        state = controller.get_state()
        assert state["home_score"] == 3
        assert state["players"]["home"][0]["points"] == 3
        assert state["players"]["home"][0]["rebounds"] == 1

        for _ in range(5):
            controller.apply_action(
                "foul",
                {"team": "home"},
                source="test",
            )
        state = controller.get_state()
        assert state["players"]["home"][0]["fouled_out"] is True
        assert state["bonus"]["away"] is True

        controller.apply_action(
            "select_player",
            {"team": "away", "number": "3", "name": "张三"},
            source="test",
        )
        controller.apply_action(
            "free_throw",
            {"team": "away", "made": True},
            source="test",
        )
        state = controller.get_state()
        assert state["phase"] == FREE_THROW
        assert state["director_hint"]["mode"] == "FREE_THROW"

        old_timeouts = state["timeouts_remaining"]["away"]
        controller.apply_action(
            "timeout",
            {"team": "away"},
            source="test",
        )
        assert controller.get_state()["phase"] == TIMEOUT
        controller.apply_action("undo", {}, source="test")
        assert (
            controller.get_state()["timeouts_remaining"]["away"]
            == old_timeouts
        )

        controller.state["period"] = 4
        controller.state["home_score"] = 20
        controller.state["away_score"] = 20
        controller.state["phase"] = PERIOD_END
        controller.save()
        controller.apply_action("next_period", {}, source="test")
        state = controller.get_state()
        assert state["period"] == 5
        assert state["phase"] == OVERTIME
        assert int(state["clock_sec_left"]) == 300

        controller.state["phase"] = PERIOD_RUNNING
        controller.state["clock_running"] = True
        controller.state["shot_clock_running"] = True
        controller.state["shot_clock_sec"] = 0.05
        controller.state["possession"] = "home"
        controller.tick(0.1)
        state = controller.get_state()
        assert state["shot_clock_sec"] == 0
        assert state["phase"] == PERIOD_PAUSED
        assert state["possession"] == "away"

    print("技术台 V3 逻辑测试通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
