# -*- coding: utf-8 -*-
"""
rk_techtable_panel.py - RK3588 篮球技术台 V3
=================================================

本文件只负责“界面与网络接口”，比赛规则位于 state_store.py。

结构
----
    GameController
        ├── LCD PyQt5 界面
        ├── 网页 /api/action
        ├── game_state.json
        └── events.jsonl

LCD 和网页不再各写一套加分/犯规/节次逻辑。所有按钮最终都会调用：

    controller.apply_action(action, payload, source)

这样 24 秒、暂停、罚球、加时、换人、撤销和导播提示在两端完全一致。

LCD UI 设计
------------
为了适配 RK3588 板载 LCD：
    - 视频仍占主要区域；
    - 操作区使用 QTabWidget 分页；
    - 按钮默认高度 28~32 px；
    - 字号 11~13 px；
    - 不使用巨型按钮；
    - 导播脚本的本地预览仍由 start_all_techtable.py 固定
      --display-scale 0.35，本技术台不改变该参数。
"""

from __future__ import annotations

import argparse
import html
import json
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, List, Optional, Tuple

# 必须使用 RK3588 系统自带的 Qt5 插件。
#
# 注意：
#   某些带 GUI 的 OpenCV wheel 会在 import cv2 时，把
#   QT_QPA_PLATFORM_PLUGIN_PATH 改成 cv2/qt/plugins。
#   因此这里不仅要在 import cv2 前设置，还必须在 import cv2 后再恢复一次。
os.environ.setdefault("DISPLAY", ":0")

SYSTEM_QT_PLUGIN_DIR = "/usr/lib/aarch64-linux-gnu/qt5/plugins"
SYSTEM_QT_PLATFORM_DIR = os.path.join(
    SYSTEM_QT_PLUGIN_DIR,
    "platforms",
)

os.environ["QT_QPA_PLATFORM"] = "xcb"
os.environ["QT_QPA_PLATFORM_PLUGIN_PATH"] = SYSTEM_QT_PLATFORM_DIR
os.environ["QT_PLUGIN_PATH"] = SYSTEM_QT_PLUGIN_DIR

import cv2
import numpy as np

# OpenCV 导入后再次恢复系统 Qt 路径，避免加载：
# /usr/local/lib/python3.10/dist-packages/cv2/qt/plugins/platforms/libqxcb.so
os.environ["QT_QPA_PLATFORM"] = "xcb"
os.environ["QT_QPA_PLATFORM_PLUGIN_PATH"] = SYSTEM_QT_PLATFORM_DIR
os.environ["QT_PLUGIN_PATH"] = SYSTEM_QT_PLUGIN_DIR

from PyQt5.QtCore import (
    QCoreApplication,
    Qt,
    QThread,
    QTimer,
    pyqtSignal,
)
from PyQt5.QtGui import QImage, QPixmap
from PyQt5.QtWidgets import (
    QApplication,
    QComboBox,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)

from state_store import (
    FREE_THROW,
    GAME_END,
    OVERTIME,
    PERIOD_END,
    PERIOD_PAUSED,
    PERIOD_RUNNING,
    PRE_GAME,
    TIMEOUT,
    GameController,
    default_roster,
    format_clock,
    get_player_text,
    load_roster,
    period_label,
)


# ---------------------------------------------------------------------------
# 一、网页技术台
# ---------------------------------------------------------------------------

INDEX_HTML = r"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>篮球技术台 V3</title>
<style>
:root {
  --bg:#0f172a; --card:#1e293b; --line:#334155; --text:#f8fafc;
  --muted:#94a3b8; --home:#60a5fa; --away:#fb7185; --ok:#4ade80;
  --warn:#facc15; --danger:#f87171;
}
* { box-sizing:border-box; }
body { margin:0; font-family:Arial,"Microsoft YaHei",sans-serif; background:var(--bg); color:var(--text); }
.wrap { max-width:1100px; margin:0 auto; padding:10px; }
.card { background:var(--card); border:1px solid var(--line); border-radius:10px; padding:10px; margin-bottom:9px; }
.scoreline { display:grid; grid-template-columns:1fr auto 1fr; align-items:center; gap:8px; text-align:center; }
.team { font-size:20px; font-weight:800; }
.score { font-size:38px; font-weight:900; }
.meta { display:flex; flex-wrap:wrap; justify-content:center; gap:14px; margin-top:6px; font-size:16px; color:#fde68a; }
.submeta { display:flex; flex-wrap:wrap; justify-content:center; gap:14px; margin-top:5px; font-size:13px; color:#cbd5e1; }
.grid2 { display:grid; grid-template-columns:1fr 1fr; gap:9px; }
.grid3 { display:grid; grid-template-columns:repeat(3,1fr); gap:7px; }
.row { display:flex; flex-wrap:wrap; gap:6px; align-items:center; margin:6px 0; }
h2 { font-size:16px; margin:2px 0 7px; }
button {
  border:0; border-radius:7px; padding:8px 10px; min-height:34px;
  font-size:14px; font-weight:700; cursor:pointer; color:#111827;
}
button:active { transform:scale(.98); }
.home { background:var(--home); }
.away { background:var(--away); }
.ok { background:var(--ok); }
.warn { background:var(--warn); }
.danger { background:var(--danger); }
.neutral { background:#e2e8f0; }
select,input {
  min-height:32px; border-radius:6px; border:1px solid #64748b;
  background:#0f172a; color:white; padding:5px; font-size:13px;
}
.small { font-size:12px; color:var(--muted); }
.alert { color:#fca5a5; font-weight:700; }
table { width:100%; border-collapse:collapse; font-size:12px; }
th,td { border-bottom:1px solid var(--line); padding:5px; text-align:center; }
.oncourt { color:#86efac; font-weight:700; }
.bench { color:#94a3b8; }
@media(max-width:760px) {
  .grid2,.grid3 { grid-template-columns:1fr; }
  .score { font-size:30px; }
  button { flex:1; }
}
</style>
</head>
<body>
<div class="wrap">
  <div class="card">
    <div class="scoreline">
      <div class="team" id="homeName">主队</div>
      <div class="score"><span id="homeScore">0</span> : <span id="awayScore">0</span></div>
      <div class="team" id="awayName">客队</div>
    </div>
    <div class="meta">
      <span id="periodText">第1节</span>
      <span>比赛 <b id="gameClock">10:00</b></span>
      <span>进攻 <b id="shotClock">24</b></span>
      <span id="phase">PRE_GAME</span>
    </div>
    <div class="submeta">
      <span>球权：<b id="possession">-</b></span>
      <span>犯规：<b id="homeFouls">0</b> / <b id="awayFouls">0</b></span>
      <span>暂停：<b id="homeTimeouts">2</b> / <b id="awayTimeouts">2</b></span>
      <span id="bonusText">BONUS -</span>
    </div>
    <div class="submeta" id="lastEvent">比赛未开始</div>
    <div class="submeta alert" id="alertText"></div>
  </div>

  <div class="grid2">
    <div class="card">
      <h2>主队计分与球员</h2>
      <div class="row">
        <select id="homePlayer"></select>
        <button class="home" onclick="selectPlayer('home')">选择球员</button>
      </div>
      <div class="row">
        <button class="home" onclick="act('score',{team:'home',value:1})">+1</button>
        <button class="home" onclick="act('score',{team:'home',value:2})">+2</button>
        <button class="home" onclick="act('score',{team:'home',value:3})">+3</button>
        <button class="warn" onclick="act('foul',{team:'home'})">犯规</button>
      </div>
      <div class="row">
        <button class="ok" onclick="act('free_throw',{team:'home',made:true})">罚中</button>
        <button class="danger" onclick="act('free_throw',{team:'home',made:false})">罚丢</button>
        <button class="neutral" onclick="act('timeout',{team:'home'})">暂停</button>
      </div>
      <div class="row">
        <button class="neutral" onclick="selectedStat('home','rebounds')">篮板</button>
        <button class="neutral" onclick="selectedStat('home','assists')">助攻</button>
        <button class="neutral" onclick="selectedStat('home','steals')">抢断</button>
        <button class="neutral" onclick="selectedStat('home','blocks')">盖帽</button>
        <button class="danger" onclick="selectedTurnover('home')">失误</button>
      </div>
    </div>

    <div class="card">
      <h2>客队计分与球员</h2>
      <div class="row">
        <select id="awayPlayer"></select>
        <button class="away" onclick="selectPlayer('away')">选择球员</button>
      </div>
      <div class="row">
        <button class="away" onclick="act('score',{team:'away',value:1})">+1</button>
        <button class="away" onclick="act('score',{team:'away',value:2})">+2</button>
        <button class="away" onclick="act('score',{team:'away',value:3})">+3</button>
        <button class="warn" onclick="act('foul',{team:'away'})">犯规</button>
      </div>
      <div class="row">
        <button class="ok" onclick="act('free_throw',{team:'away',made:true})">罚中</button>
        <button class="danger" onclick="act('free_throw',{team:'away',made:false})">罚丢</button>
        <button class="neutral" onclick="act('timeout',{team:'away'})">暂停</button>
      </div>
      <div class="row">
        <button class="neutral" onclick="selectedStat('away','rebounds')">篮板</button>
        <button class="neutral" onclick="selectedStat('away','assists')">助攻</button>
        <button class="neutral" onclick="selectedStat('away','steals')">抢断</button>
        <button class="neutral" onclick="selectedStat('away','blocks')">盖帽</button>
        <button class="danger" onclick="selectedTurnover('away')">失误</button>
      </div>
    </div>
  </div>

  <div class="grid2">
    <div class="card">
      <h2>比赛时间 / 24秒 / 球权</h2>
      <div class="row">
        <button class="ok" onclick="act('clock_toggle',{})">比赛开始/暂停</button>
        <button class="neutral" onclick="act('shot_toggle',{})">24秒开始/暂停</button>
        <button class="warn" onclick="act('shot_reset_24',{})">回24</button>
        <button class="warn" onclick="act('shot_reset_14',{})">回14</button>
      </div>
      <div class="row">
        <button class="home" onclick="act('possession',{team:'home'})">主队球权</button>
        <button class="away" onclick="act('possession',{team:'away'})">客队球权</button>
        <button class="neutral" onclick="act('possession',{team:null})">清球权</button>
      </div>
      <div class="row">
        <button class="neutral" onclick="act('timeout_end',{})">暂停结束</button>
        <button class="neutral" onclick="act('free_throw_end',{})">罚球结束</button>
      </div>
    </div>

    <div class="card">
      <h2>节次 / 状态 / 撤销</h2>
      <div class="row">
        <button class="neutral" onclick="act('period_end',{})">本节结束</button>
        <button class="ok" onclick="act('next_period',{})">下一节/加时</button>
        <button class="danger" onclick="act('game_end',{})">全场结束</button>
      </div>
      <div class="row">
        <button class="warn" onclick="act('undo',{})">撤销</button>
        <button class="danger" onclick="confirmReset()">重置整场</button>
      </div>
      <div class="row">
        <input id="periodInput" type="number" min="1" value="1" style="width:70px">
        <button class="neutral" onclick="setPeriod()">指定节次</button>
      </div>
    </div>
  </div>

  <div class="card">
    <h2>换人 / 在场球员</h2>
    <div class="grid2">
      <div>
        <b>主队</b>
        <div class="row">
          <select id="homeOut"></select>
          <span>换下</span>
          <select id="homeIn"></select>
          <button class="home" onclick="substitute('home')">确认换人</button>
        </div>
      </div>
      <div>
        <b>客队</b>
        <div class="row">
          <select id="awayOut"></select>
          <span>换下</span>
          <select id="awayIn"></select>
          <button class="away" onclick="substitute('away')">确认换人</button>
        </div>
      </div>
    </div>
    <div id="lineupTables"></div>
  </div>

  <div class="card">
    <h2>单节与全场统计</h2>
    <div id="stats"></div>
  </div>
</div>

<script>
let state = {};
function fmtClock(sec) {
  sec = Math.max(0, Math.round(Number(sec || 0)));
  return String(Math.floor(sec / 60)).padStart(2,'0') + ':' +
         String(sec % 60).padStart(2,'0');
}
function playerText(p) {
  return `${p.number || ''} ${p.name || ''}`.trim();
}
function fillSelect(id, players, predicate) {
  const el = document.getElementById(id);
  const old = el.value;
  el.innerHTML = '';
  (players || []).filter(predicate || (()=>true)).forEach(p => {
    const o = document.createElement('option');
    o.value = p.number;
    o.textContent = `${playerText(p)} | ${p.points||0}分 ${p.fouls||0}犯${p.on_court?' | 在场':''}`;
    el.appendChild(o);
  });
  if ([...el.options].some(o=>o.value===old)) el.value = old;
}
function renderTeamTable(team) {
  const players = ((state.players || {})[team] || []);
  const rows = players.map(p => `
    <tr>
      <td class="${p.on_court?'oncourt':'bench'}">${p.on_court?'在场':'替补'}</td>
      <td>${playerText(p)}</td>
      <td>${p.points||0}</td><td>${p.fouls||0}</td>
      <td>${p.ft_made||0}/${p.ft_attempts||0}</td>
      <td>${p.rebounds||0}/${p.assists||0}/${p.steals||0}/${p.blocks||0}</td>
      <td>${p.fouled_out?'满犯':''}</td>
    </tr>`).join('');
  return `<table><tr><th>状态</th><th>球员</th><th>分</th><th>犯</th><th>罚球</th><th>板/助/断/帽</th><th>提醒</th></tr>${rows}</table>`;
}
function renderStats() {
  const s = state.statistics || {};
  const current = s.current_period || {};
  const full = s.full_game || {};
  function row(title, d) {
    d = d || {};
    return `<tr><td>${title}</td><td>${d.points||0}</td><td>${d.fouls||0}</td>
      <td>${d.ft_made||0}/${d.ft_attempts||0}</td><td>${d.two_made||0}</td>
      <td>${d.three_made||0}</td><td>${d.rebounds||0}</td>
      <td>${d.assists||0}</td><td>${d.steals||0}</td><td>${d.blocks||0}</td>
      <td>${d.turnovers||0}</td></tr>`;
  }
  document.getElementById('stats').innerHTML =
    `<table><tr><th>范围</th><th>得分</th><th>犯规</th><th>罚球</th><th>2分</th><th>3分</th><th>篮板</th><th>助攻</th><th>抢断</th><th>盖帽</th><th>失误</th></tr>
     ${row('本节主队',current.home)}${row('本节客队',current.away)}
     ${row('全场主队',full.home)}${row('全场客队',full.away)}</table>`;
}
function render(s) {
  state = s;
  homeName.textContent = s.home_name || '主队';
  awayName.textContent = s.away_name || '客队';
  homeScore.textContent = s.home_score || 0;
  awayScore.textContent = s.away_score || 0;
  periodText.textContent = s.period_label || `第${s.period || 1}节`;
  gameClock.textContent = fmtClock(s.clock_sec_left);
  shotClock.textContent = Math.ceil(Number(s.shot_clock_sec || 0));
  phase.textContent = s.phase || '';
  homeFouls.textContent = s.home_fouls || 0;
  awayFouls.textContent = s.away_fouls || 0;
  homeTimeouts.textContent = (s.timeouts_remaining || {}).home ?? 0;
  awayTimeouts.textContent = (s.timeouts_remaining || {}).away ?? 0;
  possession.textContent =
    s.possession === 'home' ? (s.home_name || '主队') :
    s.possession === 'away' ? (s.away_name || '客队') : '-';
  const bonus = s.bonus || {};
  bonusText.textContent = `BONUS 主:${bonus.home?'是':'否'} 客:${bonus.away?'是':'否'}`;
  lastEvent.textContent = s.last_event || '';
  const alerts = s.alerts || [];
  alertText.textContent = alerts.length ? alerts[alerts.length-1].text : '';

  const home = ((s.players || {}).home || []);
  const away = ((s.players || {}).away || []);
  fillSelect('homePlayer', home);
  fillSelect('awayPlayer', away);
  fillSelect('homeOut', home, p=>p.on_court);
  fillSelect('awayOut', away, p=>p.on_court);
  fillSelect('homeIn', home, p=>!p.on_court && !p.fouled_out);
  fillSelect('awayIn', away, p=>!p.on_court && !p.fouled_out);
  lineupTables.innerHTML =
    `<div class="grid2"><div><b>主队阵容</b>${renderTeamTable('home')}</div>
    <div><b>客队阵容</b>${renderTeamTable('away')}</div></div>`;
  renderStats();
}
async function refresh() {
  try {
    const r = await fetch('/state?ts=' + Date.now(), {cache:'no-store'});
    render(await r.json());
  } catch(e) {
    lastEvent.textContent = '状态连接失败：' + e;
  }
}
async function act(action,payload) {
  const r = await fetch('/api/action', {
    method:'POST', headers:{'Content-Type':'application/json'},
    body:JSON.stringify({action,...payload})
  });
  const data = await r.json();
  if (!r.ok) alert(data.error || '操作失败');
  else render(data);
}
function selectPlayer(team) {
  const el = document.getElementById(team + 'Player');
  const players = ((state.players || {})[team] || []);
  const p = players.find(x=>String(x.number)===String(el.value));
  if (p) act('select_player',{team,number:p.number,name:p.name});
}
async function selectedStat(team, stat) {
  const el = document.getElementById(team + 'Player');
  const players = ((state.players || {})[team] || []);
  const p = players.find(x=>String(x.number)===String(el.value));
  if (!p) return;
  await act('select_player',{team,number:p.number,name:p.name});
  await act('player_stat',{team,stat});
}
async function selectedTurnover(team) {
  const el = document.getElementById(team + 'Player');
  const players = ((state.players || {})[team] || []);
  const p = players.find(x=>String(x.number)===String(el.value));
  if (!p) return;
  await act('select_player',{team,number:p.number,name:p.name});
  await act('turnover',{team});
}
function substitute(team) {
  act('substitution',{
    team,
    out_number:document.getElementById(team+'Out').value,
    in_number:document.getElementById(team+'In').value
  });
}
function setPeriod() {
  act('set_period',{period:Number(periodInput.value || 1)});
}
function confirmReset() {
  if (confirm('确定重置整场比赛吗？')) act('reset_game',{});
}
setInterval(refresh,500);
refresh();
</script>
</body>
</html>
"""


class StateHttpServer:
    """
    内置 HTTP 技术台。

    注意：Handler 不直接读写 JSON，而是调用同一个 GameController。
    这保证网页动作和 LCD 动作共享历史栈、规则、事件日志与锁。
    """

    def __init__(
        self,
        controller: GameController,
        host: str = "0.0.0.0",
        port: int = 8010,
    ):
        self.controller = controller
        self.host = str(host)
        self.port = int(port)
        self.httpd: Optional[ThreadingHTTPServer] = None
        self.thread: Optional[threading.Thread] = None
        self.error: Optional[str] = None

    def start(self) -> bool:
        controller = self.controller

        class Handler(BaseHTTPRequestHandler):
            def _send(
                self,
                status: int,
                body: bytes,
                content_type: str = "application/json; charset=utf-8",
            ) -> None:
                self.send_response(status)
                self.send_header("Content-Type", content_type)
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header(
                    "Access-Control-Allow-Methods",
                    "GET,POST,OPTIONS",
                )
                self.send_header(
                    "Access-Control-Allow-Headers",
                    "Content-Type",
                )
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def _json(self, status: int, payload: Dict[str, Any]) -> None:
                body = json.dumps(
                    payload,
                    ensure_ascii=False,
                ).encode("utf-8")
                self._send(status, body)

            def do_OPTIONS(self) -> None:  # noqa: N802
                self._send(204, b"")

            def do_GET(self) -> None:  # noqa: N802
                path = self.path.split("?", 1)[0]
                if path == "/":
                    self._send(
                        200,
                        INDEX_HTML.encode("utf-8"),
                        "text/html; charset=utf-8",
                    )
                    return
                if path == "/health":
                    self._send(200, b"OK", "text/plain; charset=utf-8")
                    return
                if path == "/state":
                    self._json(200, enrich_state_for_clients(controller.get_state()))
                    return
                self._send(404, b"Not Found", "text/plain; charset=utf-8")

            def do_POST(self) -> None:  # noqa: N802
                path = self.path.split("?", 1)[0]
                if path != "/api/action":
                    self._send(404, b"Not Found", "text/plain; charset=utf-8")
                    return
                try:
                    length = int(self.headers.get("Content-Length", "0"))
                    raw = (
                        self.rfile.read(length).decode("utf-8")
                        if length > 0
                        else "{}"
                    )
                    payload = json.loads(raw)
                    action = str(payload.pop("action", "")).strip()
                    state = controller.apply_action(
                        action,
                        payload,
                        source="web",
                    )
                    self._json(200, enrich_state_for_clients(state))
                except Exception as exc:
                    self._json(400, {"error": str(exc)})

            def log_message(self, fmt: str, *args: Any) -> None:
                # HTTP 轮询频率较高，默认关闭访问日志，避免终端刷屏。
                return

        try:
            self.httpd = ThreadingHTTPServer(
                (self.host, self.port),
                Handler,
            )
            self.thread = threading.Thread(
                target=self.httpd.serve_forever,
                name="techtable-http",
                daemon=True,
            )
            self.thread.start()
            return True
        except Exception as exc:
            self.error = str(exc)
            self.httpd = None
            return False

    def stop(self) -> None:
        if self.httpd is None:
            return
        try:
            self.httpd.shutdown()
            self.httpd.server_close()
        except Exception:
            pass
        self.httpd = None


def enrich_state_for_clients(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    添加纯显示字段。

    基础 state 仍使用数值和枚举；客户端无需重复实现节次文本转换。
    """
    result = dict(state)
    result["period_label"] = period_label(
        int(state.get("period", 1) or 1),
        int(state.get("regulation_periods", 4) or 4),
    )
    result["game_clock"] = format_clock(
        float(state.get("clock_sec_left", 0) or 0)
    )
    result["shot_clock_text"] = str(
        int(np.ceil(float(state.get("shot_clock_sec", 0) or 0)))
    )
    return result


# ---------------------------------------------------------------------------
# 二、RTSP 视频线程
# ---------------------------------------------------------------------------

class VideoThread(QThread):
    frame_ready = pyqtSignal(object)
    status_ready = pyqtSignal(str)

    def __init__(
        self,
        rtsp_url: str,
        target_fps: float = 25.0,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self.rtsp_url = str(rtsp_url)
        self.target_fps = max(1.0, float(target_fps))
        self._running = True

    def stop(self) -> None:
        self._running = False
        self.wait(1800)

    def run(self) -> None:
        os.environ.setdefault(
            "OPENCV_FFMPEG_CAPTURE_OPTIONS",
            "rtsp_transport;tcp|max_delay;500000|stimeout;3000000",
        )
        while self._running:
            cap = cv2.VideoCapture(self.rtsp_url, cv2.CAP_FFMPEG)
            try:
                cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            except Exception:
                pass

            if not cap.isOpened():
                self.status_ready.emit("等待 RTSP 视频流")
                cap.release()
                time.sleep(0.8)
                continue

            self.status_ready.emit("RTSP 视频已连接")
            period = 1.0 / self.target_fps
            while self._running:
                started = time.monotonic()
                ok, frame = cap.read()
                if not ok or frame is None:
                    self.status_ready.emit("RTSP 中断，正在重连")
                    break
                self.frame_ready.emit(frame)
                remain = period - (time.monotonic() - started)
                if remain > 0:
                    time.sleep(remain)

            cap.release()
            time.sleep(0.3)


# ---------------------------------------------------------------------------
# 三、LCD 技术台
# ---------------------------------------------------------------------------

class TechTableWindow(QMainWindow):
    def __init__(self, args: argparse.Namespace):
        super().__init__()
        self.args = args
        roster = load_roster(args.roster) or default_roster()

        self.controller = GameController(
            state_path=args.state,
            events_path=args.events,
            roster=roster,
            period_minutes=args.period_minutes,
        )
        self.state = self.controller.get_state()

        self.video_thread: Optional[VideoThread] = None
        self.state_server: Optional[StateHttpServer] = None
        self.last_tick = time.monotonic()

        self._build_ui()
        self._start_video()
        self._start_http()

        # 比赛计时器：100 ms 精度足够技术台显示，同时不会给 Qt 主线程太大压力。
        self.tick_timer = QTimer(self)
        self.tick_timer.timeout.connect(self._on_tick)
        self.tick_timer.start(100)

        # 网页动作发生在 HTTP 线程，LCD 定期读取 controller 的新快照。
        self.refresh_timer = QTimer(self)
        self.refresh_timer.timeout.connect(self._refresh_from_controller)
        self.refresh_timer.start(250)

        self.refresh_ui()

    # ------------------------------ UI 构建 ------------------------------

    def _small_button(
        self,
        text: str,
        danger: bool = False,
        accent: bool = False,
    ) -> QPushButton:
        button = QPushButton(text)
        button.setMinimumHeight(28)
        if danger:
            bg = "#9b2c2c"
            fg = "white"
        elif accent:
            bg = "#1e5aa8"
            fg = "white"
        else:
            bg = "#e7eaf0"
            fg = "#111"
        button.setStyleSheet(
            "QPushButton {"
            f"font-size:12px; font-weight:bold; color:{fg}; background:{bg};"
            "border-radius:5px; padding:3px 6px;"
            "}"
            "QPushButton:pressed {background:#888;}"
        )
        return button

    def _build_ui(self) -> None:
        self.setWindowTitle("RK Basketball TechTable V3")
        self.resize(self.args.window_width, self.args.window_height)

        root = QWidget(self)
        self.setCentralWidget(root)
        root_layout = QHBoxLayout(root)
        root_layout.setContentsMargins(4, 4, 4, 4)
        root_layout.setSpacing(4)

        splitter = QSplitter(Qt.Horizontal)
        root_layout.addWidget(splitter)

        # 左侧：紧凑比分条 + 视频。
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 3, 0)
        left_layout.setSpacing(3)

        top = QWidget()
        top.setStyleSheet("background:#080808; border-radius:4px;")
        top_layout = QGridLayout(top)
        top_layout.setContentsMargins(5, 3, 5, 3)
        top_layout.setSpacing(3)

        self.score_label = QLabel()
        self.score_label.setAlignment(Qt.AlignCenter)
        self.score_label.setMinimumHeight(38)
        self.score_label.setStyleSheet(
            "font-size:22px; font-weight:bold; color:white;"
        )

        self.game_clock_label = QLabel()
        self.game_clock_label.setAlignment(Qt.AlignCenter)
        self.game_clock_label.setStyleSheet(
            "font-size:20px; font-weight:bold; color:#fde68a;"
        )

        self.shot_clock_label = QLabel()
        self.shot_clock_label.setAlignment(Qt.AlignCenter)
        self.shot_clock_label.setMinimumWidth(70)
        self.shot_clock_label.setStyleSheet(
            "font-size:26px; font-weight:bold; color:#f87171;"
        )

        self.meta_label = QLabel()
        self.meta_label.setAlignment(Qt.AlignCenter)
        self.meta_label.setStyleSheet(
            "font-size:11px; color:#cbd5e1;"
        )

        top_layout.addWidget(self.score_label, 0, 0, 1, 3)
        top_layout.addWidget(self.game_clock_label, 1, 0)
        top_layout.addWidget(self.shot_clock_label, 1, 1)
        top_layout.addWidget(self.meta_label, 1, 2)
        left_layout.addWidget(top)

        self.video_label = QLabel("等待视频流")
        self.video_label.setAlignment(Qt.AlignCenter)
        self.video_label.setMinimumSize(560, 315)
        self.video_label.setSizePolicy(
            QSizePolicy.Expanding,
            QSizePolicy.Expanding,
        )
        self.video_label.setStyleSheet(
            "background:#111; color:#ddd; font-size:16px;"
        )
        left_layout.addWidget(self.video_label, stretch=1)

        self.event_label = QLabel()
        self.event_label.setWordWrap(True)
        self.event_label.setStyleSheet(
            "font-size:11px; padding:3px; color:#ffe600; background:#111;"
        )
        left_layout.addWidget(self.event_label)

        self.status_label = QLabel("状态：初始化")
        self.status_label.setStyleSheet("font-size:10px; padding:2px;")
        left_layout.addWidget(self.status_label)
        splitter.addWidget(left)

        # 右侧：分页操作，避免所有按钮挤在一屏。
        self.tabs = QTabWidget()
        self.tabs.setStyleSheet(
            "QTabBar::tab {font-size:11px; padding:5px 8px;}"
            "QGroupBox {font-size:11px; font-weight:bold; margin-top:6px;}"
            "QComboBox,QLineEdit {font-size:11px; min-height:25px;}"
            "QLabel {font-size:11px;}"
        )
        self.tabs.addTab(self._build_score_tab(), "计分")
        self.tabs.addTab(self._build_clock_tab(), "时间")
        self.tabs.addTab(self._build_lineup_tab(), "阵容")
        self.tabs.addTab(self._build_stats_tab(), "统计")
        splitter.addWidget(self.tabs)

        # 右侧只占约 29%，按钮不会被拉得很大。
        splitter.setSizes(
            [
                int(self.args.window_width * 0.71),
                int(self.args.window_width * 0.29),
            ]
        )

    def _build_score_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        player_box = QGroupBox("球员选择")
        player_layout = QGridLayout(player_box)
        player_layout.setContentsMargins(5, 8, 5, 5)
        player_layout.setSpacing(3)

        self.home_player_combo = QComboBox()
        self.away_player_combo = QComboBox()
        select_home = self._small_button("选主队", accent=True)
        select_away = self._small_button("选客队", accent=True)
        clear = self._small_button("清除")
        select_home.clicked.connect(lambda: self._select_combo_player("home"))
        select_away.clicked.connect(lambda: self._select_combo_player("away"))
        clear.clicked.connect(
            lambda: self.do_action("clear_selected_player")
        )

        player_layout.addWidget(QLabel("主"), 0, 0)
        player_layout.addWidget(self.home_player_combo, 0, 1)
        player_layout.addWidget(select_home, 0, 2)
        player_layout.addWidget(QLabel("客"), 1, 0)
        player_layout.addWidget(self.away_player_combo, 1, 1)
        player_layout.addWidget(select_away, 1, 2)
        player_layout.addWidget(clear, 2, 2)
        layout.addWidget(player_box)

        score_box = QGroupBox("得分 / 犯规")
        score_layout = QGridLayout(score_box)
        score_layout.setContentsMargins(5, 8, 5, 5)
        score_layout.setSpacing(3)

        for column, value in enumerate((1, 2, 3)):
            home = self._small_button(f"主+{value}", accent=True)
            away = self._small_button(f"客+{value}", accent=True)
            home.clicked.connect(
                lambda _=False, v=value: self.do_action(
                    "score", {"team": "home", "value": v}
                )
            )
            away.clicked.connect(
                lambda _=False, v=value: self.do_action(
                    "score", {"team": "away", "value": v}
                )
            )
            score_layout.addWidget(home, 0, column)
            score_layout.addWidget(away, 1, column)

        home_foul = self._small_button("主犯规", danger=True)
        away_foul = self._small_button("客犯规", danger=True)
        home_foul.clicked.connect(
            lambda: self.do_action("foul", {"team": "home"})
        )
        away_foul.clicked.connect(
            lambda: self.do_action("foul", {"team": "away"})
        )
        score_layout.addWidget(home_foul, 0, 3)
        score_layout.addWidget(away_foul, 1, 3)
        layout.addWidget(score_box)

        ft_box = QGroupBox("罚球")
        ft_layout = QGridLayout(ft_box)
        ft_layout.setContentsMargins(5, 8, 5, 5)
        ft_layout.setSpacing(3)
        buttons = [
            ("主罚中", "home", True, False),
            ("主罚丢", "home", False, True),
            ("客罚中", "away", True, False),
            ("客罚丢", "away", False, True),
        ]
        for index, (text, team, made, danger) in enumerate(buttons):
            button = self._small_button(text, danger=danger, accent=not danger)
            button.clicked.connect(
                lambda _=False, t=team, m=made: self.do_action(
                    "free_throw",
                    {"team": t, "made": m},
                )
            )
            ft_layout.addWidget(button, index // 2, index % 2)
        end_ft = self._small_button("罚球结束")
        end_ft.clicked.connect(lambda: self.do_action("free_throw_end"))
        ft_layout.addWidget(end_ft, 2, 0, 1, 2)
        layout.addWidget(ft_box)

        stat_box = QGroupBox("当前球员技术统计")
        stat_grid = QGridLayout(stat_box)
        stat_grid.setContentsMargins(5, 8, 5, 5)
        stat_grid.setSpacing(3)
        stat_defs = [
            ("篮板+1", "rebounds"),
            ("助攻+1", "assists"),
            ("抢断+1", "steals"),
            ("盖帽+1", "blocks"),
        ]
        for index, (title, stat_name) in enumerate(stat_defs):
            button = self._small_button(title)
            button.clicked.connect(
                lambda _=False, s=stat_name: self._selected_stat(s)
            )
            stat_grid.addWidget(button, index // 2, index % 2)
        turnover = self._small_button("失误+1", danger=True)
        turnover.clicked.connect(self._selected_turnover)
        stat_grid.addWidget(turnover, 2, 0, 1, 2)
        layout.addWidget(stat_box)

        self.selected_label = QLabel("当前：未选择球员")
        self.selected_label.setWordWrap(True)
        self.selected_label.setStyleSheet(
            "font-size:11px; color:#2563eb; font-weight:bold;"
        )
        layout.addWidget(self.selected_label)

        undo = self._small_button("撤销上一步", danger=True)
        undo.clicked.connect(lambda: self.do_action("undo"))
        layout.addWidget(undo)
        layout.addStretch(1)
        return page

    def _build_clock_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        game_box = QGroupBox("比赛时间")
        grid = QGridLayout(game_box)
        grid.setContentsMargins(5, 8, 5, 5)
        self.clock_toggle_button = self._small_button(
            "开始/暂停",
            accent=True,
        )
        reset_clock = self._small_button("重置本节")
        period_end = self._small_button("本节结束", danger=True)
        next_period = self._small_button("下一节/加时", accent=True)
        self.clock_toggle_button.clicked.connect(
            lambda: self.do_action("clock_toggle")
        )
        reset_clock.clicked.connect(lambda: self.do_action("reset_clock"))
        period_end.clicked.connect(lambda: self.do_action("period_end"))
        next_period.clicked.connect(lambda: self.do_action("next_period"))
        grid.addWidget(self.clock_toggle_button, 0, 0)
        grid.addWidget(reset_clock, 0, 1)
        grid.addWidget(period_end, 1, 0)
        grid.addWidget(next_period, 1, 1)
        layout.addWidget(game_box)

        shot_box = QGroupBox("24秒")
        grid = QGridLayout(shot_box)
        grid.setContentsMargins(5, 8, 5, 5)
        self.shot_toggle_button = self._small_button(
            "开始/暂停",
            accent=True,
        )
        reset24 = self._small_button("回24")
        reset14 = self._small_button("回14")
        self.shot_toggle_button.clicked.connect(
            lambda: self.do_action("shot_toggle")
        )
        reset24.clicked.connect(lambda: self.do_action("shot_reset_24"))
        reset14.clicked.connect(lambda: self.do_action("shot_reset_14"))
        grid.addWidget(self.shot_toggle_button, 0, 0)
        grid.addWidget(reset24, 0, 1)
        grid.addWidget(reset14, 0, 2)
        layout.addWidget(shot_box)

        possession_box = QGroupBox("球权")
        grid = QGridLayout(possession_box)
        grid.setContentsMargins(5, 8, 5, 5)
        home = self._small_button("主队", accent=True)
        away = self._small_button("客队", accent=True)
        clear = self._small_button("清除")
        home.clicked.connect(
            lambda: self.do_action("possession", {"team": "home"})
        )
        away.clicked.connect(
            lambda: self.do_action("possession", {"team": "away"})
        )
        clear.clicked.connect(
            lambda: self.do_action("possession", {"team": None})
        )
        grid.addWidget(home, 0, 0)
        grid.addWidget(away, 0, 1)
        grid.addWidget(clear, 0, 2)
        layout.addWidget(possession_box)

        timeout_box = QGroupBox("暂停")
        grid = QGridLayout(timeout_box)
        grid.setContentsMargins(5, 8, 5, 5)
        home_timeout = self._small_button("主队暂停", danger=True)
        away_timeout = self._small_button("客队暂停", danger=True)
        timeout_end = self._small_button("暂停结束")
        home_timeout.clicked.connect(
            lambda: self.do_action("timeout", {"team": "home"})
        )
        away_timeout.clicked.connect(
            lambda: self.do_action("timeout", {"team": "away"})
        )
        timeout_end.clicked.connect(lambda: self.do_action("timeout_end"))
        grid.addWidget(home_timeout, 0, 0)
        grid.addWidget(away_timeout, 0, 1)
        grid.addWidget(timeout_end, 1, 0, 1, 2)
        layout.addWidget(timeout_box)

        end_game = self._small_button("全场结束", danger=True)
        end_game.clicked.connect(self._confirm_game_end)
        reset_game = self._small_button("重置整场", danger=True)
        reset_game.clicked.connect(self._confirm_reset_game)
        layout.addWidget(end_game)
        layout.addWidget(reset_game)
        layout.addStretch(1)
        return page

    def _build_lineup_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        team_row = QHBoxLayout()
        team_row.addWidget(QLabel("队伍"))
        self.lineup_team_combo = QComboBox()
        self.lineup_team_combo.addItem("主队", "home")
        self.lineup_team_combo.addItem("客队", "away")
        self.lineup_team_combo.currentIndexChanged.connect(
            self._refresh_lineup_combos
        )
        team_row.addWidget(self.lineup_team_combo)
        layout.addLayout(team_row)

        sub_box = QGroupBox("换人")
        form = QFormLayout(sub_box)
        form.setContentsMargins(5, 8, 5, 5)
        self.out_player_combo = QComboBox()
        self.in_player_combo = QComboBox()
        form.addRow("换出", self.out_player_combo)
        form.addRow("换入", self.in_player_combo)
        substitute = self._small_button("确认换人", accent=True)
        substitute.clicked.connect(self._substitute)
        form.addRow(substitute)
        layout.addWidget(sub_box)

        manage_box = QGroupBox("首发 / 在场")
        form = QFormLayout(manage_box)
        form.setContentsMargins(5, 8, 5, 5)
        self.manage_player_combo = QComboBox()
        form.addRow("球员", self.manage_player_combo)
        set_on = self._small_button("设为在场", accent=True)
        set_off = self._small_button("设为替补")
        set_starter = self._small_button("设为首发")
        set_on.clicked.connect(lambda: self._set_on_court(True))
        set_off.clicked.connect(lambda: self._set_on_court(False))
        set_starter.clicked.connect(self._set_starter)
        form.addRow(set_on)
        form.addRow(set_off)
        form.addRow(set_starter)
        layout.addWidget(manage_box)

        self.lineup_label = QLabel()
        self.lineup_label.setWordWrap(True)
        self.lineup_label.setTextFormat(Qt.RichText)
        self.lineup_label.setStyleSheet(
            "font-size:10px; background:#f5f5f5; padding:4px;"
        )
        layout.addWidget(self.lineup_label)
        layout.addStretch(1)
        return page

    def _build_stats_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(4, 4, 4, 4)
        self.stats_label = QLabel()
        self.stats_label.setWordWrap(True)
        self.stats_label.setTextFormat(Qt.RichText)
        self.stats_label.setAlignment(Qt.AlignTop)
        self.stats_label.setStyleSheet(
            "font-size:10px; background:#f8fafc; padding:5px;"
        )
        layout.addWidget(self.stats_label)
        return page

    # ------------------------------ 后台服务 ------------------------------

    def _start_video(self) -> None:
        self.video_thread = VideoThread(
            self.args.rtsp,
            self.args.preview_fps,
            self,
        )
        self.video_thread.frame_ready.connect(self._on_frame)
        self.video_thread.status_ready.connect(
            lambda text: self.status_label.setText(f"状态：{text}")
        )
        self.video_thread.start()

    def _start_http(self) -> None:
        if not self.args.serve_state:
            return
        self.state_server = StateHttpServer(
            self.controller,
            self.args.state_host,
            self.args.state_port,
        )
        if self.state_server.start():
            self.status_label.setText(
                f"状态：网页技术台 http://{self.args.state_host}:"
                f"{self.args.state_port}/"
            )
        else:
            self.status_label.setText(
                f"状态：网页服务失败 {self.state_server.error}"
            )

    def _on_frame(self, frame: np.ndarray) -> None:
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        height, width, channels = rgb.shape
        qimage = QImage(
            rgb.data,
            width,
            height,
            channels * width,
            QImage.Format_RGB888,
        ).copy()
        pixmap = QPixmap.fromImage(qimage).scaled(
            self.video_label.size(),
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation,
        )
        self.video_label.setPixmap(pixmap)

    # ------------------------------ 比赛动作 ------------------------------

    def do_action(
        self,
        action: str,
        payload: Optional[Dict[str, Any]] = None,
    ) -> None:
        try:
            self.state = self.controller.apply_action(
                action,
                payload,
                source="lcd",
            )
            self.refresh_ui()
        except Exception as exc:
            QMessageBox.warning(self, "操作失败", str(exc))

    def _combo_player_data(
        self,
        combo: QComboBox,
    ) -> Optional[Dict[str, str]]:
        data = combo.currentData()
        return dict(data) if isinstance(data, dict) else None

    def _select_combo_player(self, team: str) -> None:
        combo = (
            self.home_player_combo
            if team == "home"
            else self.away_player_combo
        )
        data = self._combo_player_data(combo)
        if data:
            self.do_action("select_player", data)

    def _selected_stat(self, stat_name: str) -> None:
        selected = self.state.get("selected_player")
        if not isinstance(selected, dict):
            QMessageBox.information(self, "技术统计", "请先选择球员。")
            return
        self.do_action(
            "player_stat",
            {
                "team": selected.get("team"),
                "stat": stat_name,
            },
        )

    def _selected_turnover(self) -> None:
        selected = self.state.get("selected_player")
        if not isinstance(selected, dict):
            QMessageBox.information(self, "失误", "请先选择球员。")
            return
        self.do_action(
            "turnover",
            {"team": selected.get("team")},
        )

    def _substitute(self) -> None:
        team = str(self.lineup_team_combo.currentData())
        outgoing = self._combo_player_data(self.out_player_combo)
        incoming = self._combo_player_data(self.in_player_combo)
        if not outgoing or not incoming:
            QMessageBox.information(
                self,
                "换人",
                "需要同时选择换出和换入球员。",
            )
            return
        self.do_action(
            "substitution",
            {
                "team": team,
                "out_number": outgoing["number"],
                "in_number": incoming["number"],
            },
        )

    def _set_on_court(self, on_court: bool) -> None:
        data = self._combo_player_data(self.manage_player_combo)
        if data:
            self.do_action(
                "set_on_court",
                {
                    "team": data["team"],
                    "number": data["number"],
                    "on_court": on_court,
                },
            )

    def _set_starter(self) -> None:
        data = self._combo_player_data(self.manage_player_combo)
        if data:
            self.do_action(
                "set_starter",
                {
                    "team": data["team"],
                    "number": data["number"],
                    "starter": True,
                },
            )

    def _confirm_game_end(self) -> None:
        if QMessageBox.question(
            self,
            "确认",
            "确定结束全场比赛吗？",
        ) == QMessageBox.Yes:
            self.do_action("game_end")

    def _confirm_reset_game(self) -> None:
        if QMessageBox.question(
            self,
            "确认重置",
            "比分、犯规、球员统计和计时都会清零，确定继续吗？",
        ) == QMessageBox.Yes:
            self.do_action("reset_game")

    # ------------------------------ 定时与刷新 ------------------------------

    def _on_tick(self) -> None:
        now = time.monotonic()
        elapsed = now - self.last_tick
        self.last_tick = now
        self.state = self.controller.tick(elapsed)
        self.refresh_ui(lightweight=True)

    def _refresh_from_controller(self) -> None:
        latest = self.controller.get_state()
        if latest.get("updated_at_ms") != self.state.get("updated_at_ms"):
            self.state = latest
            self.refresh_ui()

    @staticmethod
    def _preserve_combo_key(combo: QComboBox) -> str:
        data = combo.currentData()
        if not isinstance(data, dict):
            return ""
        return (
            f"{data.get('team')}|{data.get('number')}|{data.get('name')}"
        )

    @staticmethod
    def _restore_combo_key(combo: QComboBox, key: str) -> None:
        for index in range(combo.count()):
            data = combo.itemData(index)
            if not isinstance(data, dict):
                continue
            current = (
                f"{data.get('team')}|{data.get('number')}|"
                f"{data.get('name')}"
            )
            if current == key:
                combo.setCurrentIndex(index)
                return

    def _fill_player_combo(
        self,
        combo: QComboBox,
        team: str,
        predicate=None,
    ) -> None:
        old_key = self._preserve_combo_key(combo)
        combo.blockSignals(True)
        combo.clear()
        for player in self.state.get("players", {}).get(team, []):
            if predicate and not predicate(player):
                continue
            text = (
                f"{player.get('number', '')} {player.get('name', '')} | "
                f"{player.get('points', 0)}分 {player.get('fouls', 0)}犯"
            )
            if player.get("on_court"):
                text += " | 场上"
            if player.get("fouled_out"):
                text += " | 满犯"
            data = {
                "team": team,
                "number": str(player.get("number", "")),
                "name": str(player.get("name", "")),
            }
            combo.addItem(text, data)
        self._restore_combo_key(combo, old_key)
        combo.blockSignals(False)

    def _refresh_lineup_combos(self) -> None:
        team = str(self.lineup_team_combo.currentData() or "home")
        self._fill_player_combo(
            self.out_player_combo,
            team,
            lambda player: bool(player.get("on_court")),
        )
        self._fill_player_combo(
            self.in_player_combo,
            team,
            lambda player: (
                not bool(player.get("on_court"))
                and not bool(player.get("fouled_out"))
            ),
        )
        self._fill_player_combo(self.manage_player_combo, team)

    def _stats_html(self) -> str:
        statistics = self.state.get("statistics", {})
        current = statistics.get("current_period", {})
        full = statistics.get("full_game", {})

        def line(title: str, data: Dict[str, Any]) -> str:
            return (
                f"<tr><td>{html.escape(title)}</td>"
                f"<td>{data.get('points', 0)}</td>"
                f"<td>{data.get('fouls', 0)}</td>"
                f"<td>{data.get('ft_made', 0)}/"
                f"{data.get('ft_attempts', 0)}</td>"
                f"<td>{data.get('two_made', 0)}</td>"
                f"<td>{data.get('three_made', 0)}</td>"
                f"<td>{data.get('rebounds', 0)}</td>"
                f"<td>{data.get('assists', 0)}</td>"
                f"<td>{data.get('steals', 0)}</td>"
                f"<td>{data.get('blocks', 0)}</td>"
                f"<td>{data.get('turnovers', 0)}</td></tr>"
            )

        table = (
            "<table border='1' cellspacing='0' cellpadding='3'>"
            "<tr><th>范围</th><th>分</th><th>犯</th><th>罚球</th>"
            "<th>2分</th><th>3分</th><th>板</th><th>助</th>"
            "<th>断</th><th>帽</th><th>失误</th></tr>"
            + line("本节主", current.get("home", {}))
            + line("本节客", current.get("away", {}))
            + line("全场主", full.get("home", {}))
            + line("全场客", full.get("away", {}))
            + "</table>"
        )

        players = []
        for team in ("home", "away"):
            for player in self.state.get("players", {}).get(team, []):
                players.append(
                    "<tr>"
                    f"<td>{'主' if team == 'home' else '客'}</td>"
                    f"<td>{html.escape(get_player_text(player))}</td>"
                    f"<td>{player.get('points', 0)}</td>"
                    f"<td>{player.get('fouls', 0)}</td>"
                    f"<td>{player.get('ft_made', 0)}/"
                    f"{player.get('ft_attempts', 0)}</td>"
                    f"<td>{player.get('rebounds', 0)}/"
                    f"{player.get('assists', 0)}/"
                    f"{player.get('steals', 0)}/"
                    f"{player.get('blocks', 0)}</td>"
                    f"<td>{'场上' if player.get('on_court') else '替补'}</td>"
                    "</tr>"
                )
        return (
            table
            + "<br><b>球员统计</b>"
            + "<table border='1' cellspacing='0' cellpadding='3'>"
            + "<tr><th>队</th><th>球员</th><th>分</th><th>犯</th>"
              "<th>罚球</th><th>板/助/断/帽</th><th>状态</th></tr>"
            + "".join(players)
            + "</table>"
        )

    def refresh_ui(self, lightweight: bool = False) -> None:
        state = self.state
        home_name = str(state.get("home_name", "主队"))
        away_name = str(state.get("away_name", "客队"))
        home_score = int(state.get("home_score", 0) or 0)
        away_score = int(state.get("away_score", 0) or 0)
        period = int(state.get("period", 1) or 1)

        self.score_label.setText(
            f"{home_name}  {home_score} : {away_score}  {away_name}"
        )
        self.game_clock_label.setText(
            f"{period_label(period, state.get('regulation_periods', 4))} "
            f"{format_clock(state.get('clock_sec_left', 0))}"
        )
        self.shot_clock_label.setText(
            str(int(np.ceil(float(state.get("shot_clock_sec", 0) or 0))))
        )

        possession = state.get("possession")
        possession_text = (
            home_name
            if possession == "home"
            else away_name if possession == "away" else "-"
        )
        timeouts = state.get("timeouts_remaining", {})
        bonus = state.get("bonus", {})
        self.meta_label.setText(
            f"{state.get('phase', '')} | 球权 {possession_text} | "
            f"犯规 {state.get('home_fouls', 0)}/"
            f"{state.get('away_fouls', 0)} | "
            f"暂停 {timeouts.get('home', 0)}/"
            f"{timeouts.get('away', 0)} | "
            f"BONUS {'主' if bonus.get('home') else '-'}"
            f"/{'客' if bonus.get('away') else '-'}"
        )

        alerts = state.get("alerts", [])
        alert_text = alerts[-1].get("text", "") if alerts else ""
        self.event_label.setText(
            f"最近：{state.get('last_event', '')}"
            + (f"  |  提醒：{alert_text}" if alert_text else "")
        )
        self.selected_label.setText(
            f"当前：{get_player_text(state.get('selected_player'))}"
        )
        self.clock_toggle_button.setText(
            "暂停比赛" if state.get("clock_running") else "开始比赛"
        )
        self.shot_toggle_button.setText(
            "暂停24秒"
            if state.get("shot_clock_running")
            else "开始24秒"
        )

        if lightweight:
            return

        self._fill_player_combo(self.home_player_combo, "home")
        self._fill_player_combo(self.away_player_combo, "away")
        self._refresh_lineup_combos()

        team = str(self.lineup_team_combo.currentData() or "home")
        lineup_lines = []
        for player in state.get("players", {}).get(team, []):
            status = "场上" if player.get("on_court") else "替补"
            if player.get("fouled_out"):
                status = "满犯"
            lineup_lines.append(
                f"{html.escape(get_player_text(player))}：{status}，"
                f"{player.get('points', 0)}分，{player.get('fouls', 0)}犯"
            )
        self.lineup_label.setText("<br>".join(lineup_lines))
        self.stats_label.setText(self._stats_html())

    # ------------------------------ 快捷键 ------------------------------

    def keyPressEvent(self, event) -> None:  # noqa: N802
        key = event.key()
        mapping = {
            Qt.Key_Q: ("score", {"team": "home", "value": 1}),
            Qt.Key_W: ("score", {"team": "home", "value": 2}),
            Qt.Key_E: ("score", {"team": "home", "value": 3}),
            Qt.Key_A: ("score", {"team": "away", "value": 1}),
            Qt.Key_S: ("score", {"team": "away", "value": 2}),
            Qt.Key_D: ("score", {"team": "away", "value": 3}),
            Qt.Key_U: ("undo", {}),
            Qt.Key_Space: ("clock_toggle", {}),
        }
        if key in mapping:
            action, payload = mapping[key]
            self.do_action(action, payload)
        elif key == Qt.Key_F11:
            self.showNormal() if self.isFullScreen() else self.showFullScreen()
        elif key == Qt.Key_Escape and self.isFullScreen():
            self.showNormal()
        else:
            super().keyPressEvent(event)

    def closeEvent(self, event) -> None:  # noqa: N802
        try:
            self.controller.save()
        except Exception:
            pass
        if self.video_thread is not None:
            self.video_thread.stop()
        if self.state_server is not None:
            self.state_server.stop()
        event.accept()


# ---------------------------------------------------------------------------
# 四、启动参数
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="篮球技术台 V3：LCD + 网页统一比赛引擎"
    )
    parser.add_argument(
        "--rtsp",
        default="rtsp://127.0.0.1:8554/director",
        help="导播 RTSP 地址",
    )
    parser.add_argument(
        "--state",
        default=os.path.join(CURRENT_DIR, "game_state.json"),
        help="比赛状态 JSON",
    )
    parser.add_argument(
        "--events",
        default=os.path.join(CURRENT_DIR, "events.jsonl"),
        help="事件日志 JSONL",
    )
    parser.add_argument(
        "--roster",
        default=os.path.join(CURRENT_DIR, "sample_roster.json"),
        help="赛前名单 JSON",
    )
    parser.add_argument(
        "--period-minutes",
        type=int,
        default=10,
        help="常规每节分钟数",
    )
    parser.add_argument(
        "--preview-fps",
        type=float,
        default=25.0,
        help="LCD 视频预览帧率",
    )
    parser.add_argument(
        "--window-width",
        type=int,
        default=1366,
        help="LCD 窗口宽度",
    )
    parser.add_argument(
        "--window-height",
        type=int,
        default=768,
        help="LCD 窗口高度",
    )
    parser.add_argument(
        "--state-host",
        default="0.0.0.0",
        help="网页技术台监听地址",
    )
    parser.add_argument(
        "--state-port",
        type=int,
        default=8010,
        help="网页技术台端口",
    )
    parser.add_argument(
        "--no-serve-state",
        dest="serve_state",
        action="store_false",
        help="关闭内置网页技术台",
    )
    parser.set_defaults(serve_state=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    # 在 QApplication 创建前锁定 Qt 插件搜索路径。
    # 这一步比只设置环境变量更可靠，可以避免 cv2 的 Qt 插件抢占 xcb。
    if os.path.isdir(SYSTEM_QT_PLUGIN_DIR):
        QCoreApplication.setLibraryPaths([SYSTEM_QT_PLUGIN_DIR])

    print("[Qt] DISPLAY =", os.environ.get("DISPLAY"))
    print(
        "[Qt] platform path =",
        os.environ.get("QT_QPA_PLATFORM_PLUGIN_PATH"),
    )
    print("[Qt] library paths =", QCoreApplication.libraryPaths())
    print("[OpenCV] cv2 =", cv2.__file__)

    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    window = TechTableWindow(args)
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
