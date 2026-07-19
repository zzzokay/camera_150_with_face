# camera_150 篮球技术台 V3 + 技术台状态驱动导播

本补丁基于：

```text
https://github.com/zzzokay/camera_150_with_face
```

设计目标是把比赛规则、LCD、网页和自动导播拆成相互独立的层。

---

## 1. 新结构

```text
LCD PyQt5 ───────┐
                  ├── GameController ── game_state.json
网页 /api/action ─┘          │          events.jsonl
                             │
                             └── director_hint
                                      │
                                      ▼
                         director_game_policy.py
                                      │
                                      ▼
                         原 predict1_director.py
```

### 核心原则

1. LCD 和网页不再分别修改 JSON。
2. 两端全部调用同一个 `GameController.apply_action()`。
3. 比赛规则只保存在 `techtable_v2/state_store.py`。
4. 导播只读取 JSON，不依赖 PyQt5、HTTP 或技术台窗口。
5. 原人物检测和原运镜状态机不被重写。
6. `--display-scale` 继续保持 `0.35`。

---

## 2. 已增加功能

### 比赛状态机

```text
PRE_GAME
PERIOD_RUNNING
PERIOD_PAUSED
TIMEOUT
FREE_THROW
PERIOD_END
OVERTIME
GAME_END
```

### 技术台

- 比分；
- 常规节次；
- 无限次加时；
- 比赛时间；
- 24 秒开始/暂停；
- 24 秒回表；
- 14 秒回表；
- 球权；
- 主客队暂停次数；
- 暂停开始/结束；
- 球员得分；
- 球员和球队犯规；
- 个人 5 犯提醒与自动离场；
- 球队单节第 5 犯 BONUS 提醒；
- 罚球命中与罚丢；
- 罚球状态开始/结束；
- 首发球员；
- 在场和替补球员；
- 换人记录；
- 球员篮板、助攻、抢断、盖帽和失误；
- 单节球队统计；
- 全场球队统计；
- 球员统计；
- LCD 与网页统一撤销；
- JSON 状态持久化；
- JSONL 事件日志。

### 自动导播

- `NORMAL`：原人物检测和运镜逻辑完全保留；
- `HOLD`：赛前、暂停、死球、节间和比赛结束时保持当前区域；
- `FREE_THROW`：罚球时平滑引导到对应篮筐；
- 暂停和罚球期间冻结快速 zoom；
- 技术台状态读取带缓存，不会每帧读盘；
- 技术台文件暂时不存在时，自动回退到原导播逻辑。

---

## 3. 文件内容

```text
camera150_techtable_v3_patch/
├── apply_techtable_v3.py
├── test_game_engine_v3.py
├── README.md
├── files/
│   ├── techtable_v2/
│   │   ├── state_store.py
│   │   ├── rk_techtable_panel.py
│   │   └── scoreboard_overlay.py
│   └── camera_movement_modified/
│       └── director_game_policy.py
└── windows_client_update/
    ├── state_store.py
    └── scoreboard_overlay.py
```

---

## 4. 在 RK3588 上应用

先停止旧进程：

```bash
cd /home/elf/work/camera_150
python3 stop_all_techtable.py
```

把整个补丁文件夹复制到：

```text
/home/elf/work/camera_150/camera150_techtable_v3_patch/
```

运行：

```bash
cd /home/elf/work/camera_150

python3 camera150_techtable_v3_patch/apply_techtable_v3.py \
  --project-dir /home/elf/work/camera_150
```

脚本会自动创建类似：

```text
backup_techtable_v3_20260719_235959/
```

的备份目录。

---

## 5. 语法检查

```bash
cd /home/elf/work/camera_150

python3 -m py_compile \
  techtable_v2/state_store.py \
  techtable_v2/rk_techtable_panel.py \
  techtable_v2/scoreboard_overlay.py \
  camera_movement_modified/director_game_policy.py \
  camera_movement_modified/single_rknn_director_view720_network_stream.py \
  start_all_techtable.py \
  stop_all_techtable.py
```

纯逻辑测试：

```bash
cd /home/elf/work/camera_150

PYTHONPATH=techtable_v2 \
python3 camera150_techtable_v3_patch/test_game_engine_v3.py
```

该测试不需要摄像头、RKNN、PyQt5 或 RTSP。

---

## 6. 启动和停止

启动：

```bash
cd /home/elf/work/camera_150
python3 start_all_techtable.py
```

停止：

```bash
cd /home/elf/work/camera_150
python3 stop_all_techtable.py
```

一键启动仍然使用：

```text
--display-scale 0.35
```

音频参数、RTSP 地址和停止脚本 PID 管理不变。

---

## 7. LCD 技术台

LCD 右侧操作区分为四页：

```text
计分
时间
阵容
统计
```

所有按钮高度约 `28~32 px`，字号约 `11~13 px`，不会出现旧版巨型按钮。

### 计分页

- 主客队 +1/+2/+3；
- 选择球员；
- 球员犯规；
- 罚中、罚丢和罚球结束；
- 篮板、助攻、抢断、盖帽、失误；
- 撤销。

### 时间页

- 比赛开始/暂停；
- 24 秒开始/暂停；
- 回 24；
- 回 14；
- 主客队球权；
- 主客队暂停；
- 暂停结束；
- 本节结束；
- 下一节或加时；
- 全场结束；
- 重置整场。

### 阵容页

- 主队/客队切换；
- 选择换入和换出球员；
- 设为在场；
- 设为替补；
- 设为首发。

### 统计页

- 本节球队统计；
- 全场球队统计；
- 球员个人统计。

---

## 8. 网页技术台

浏览器打开：

```text
http://RK3588_IP:8010/
```

例如：

```text
http://192.168.137.231:8010/
```

状态接口仍然是：

```text
http://RK3588_IP:8010/state
```

网页和 LCD 共享同一个控制器，因此：

- 网页加分后 LCD 会刷新；
- LCD 操作后网页会刷新；
- 网页撤销和 LCD 撤销使用同一历史栈；
- 不会再出现两个端口或两套状态源。

---

## 9. 导播状态策略

### 正常比赛

技术台状态：

```text
PERIOD_RUNNING
OVERTIME + clock_running=true
```

导播：

```text
NORMAL
```

完全使用原人物热点、快攻、pan、zoom 和防抖逻辑。

### 暂停、死球和节间

技术台状态：

```text
PRE_GAME
PERIOD_PAUSED
TIMEOUT
PERIOD_END
GAME_END
```

导播：

```text
HOLD
```

镜头以当前锚点作为目标，水平速度衰减，冻结快速 zoom，避免替补席或裁判
走动导致画面大幅移动。

### 罚球

技术台状态：

```text
FREE_THROW
```

导播：

```text
FREE_THROW
```

热点被平滑引导到罚球队伍进攻篮筐。原导播的加速度、阻尼和迟滞仍然生效，
不会瞬间跳转。

---

## 10. 篮筐位置调试

一键启动默认传入：

```text
--left-basket-x-ratio 0.18
--right-basket-x-ratio 0.82
--home-first-half-attack right
```

含义：

- 左篮筐在矫正画面宽度的 18%；
- 右篮筐在矫正画面宽度的 82%；
- 主队第 1、2 节向右侧进攻；
- 第 3、4 节和加时自动交换方向。

### 现场校准方法

1. 启动系统；
2. 在网页或 LCD 选择主队球员；
3. 点击“主罚中”或“主罚丢”；
4. 观察镜头是否落在正确篮筐；
5. 若左右相反，把 `start_all_techtable.py` 中：

```text
"--home-first-half-attack",
"right",
```

改成：

```text
"--home-first-half-attack",
"left",
```

6. 若镜头偏离篮筐，调整：

```text
"--left-basket-x-ratio", "0.18",
"--right-basket-x-ratio", "0.82",
```

例如左篮筐更靠中间：

```text
"--left-basket-x-ratio", "0.22",
```

修改后执行：

```bash
python3 stop_all_techtable.py
python3 start_all_techtable.py
```

---

## 11. 临时关闭技术台导播策略

单独运行导播脚本时增加：

```text
--disable-game-policy
```

即可恢复原有自动导播，不读取比赛状态。

---

## 12. Windows 观看端更新

为了让 Windows 比分条显示：

- 24 秒；
- 球权；
- 暂停次数；
- BONUS；
- 加时；
- 比赛阶段；

把补丁中的：

```text
windows_client_update/state_store.py
windows_client_update/scoreboard_overlay.py
```

复制到：

```text
D:\camera_150_client\techtable_v2\
```

覆盖同名文件。

`viewer_client.py` 和音频播放文件不需要修改。

---

## 13. JSON 关键字段

```json
{
  "version": 3,
  "phase": "PERIOD_RUNNING",
  "period": 1,
  "clock_sec_left": 523.4,
  "shot_clock_sec": 17.2,
  "possession": "home",
  "timeouts_remaining": {
    "home": 2,
    "away": 1
  },
  "bonus": {
    "home": false,
    "away": true
  },
  "free_throw_team": null,
  "director_hint": {
    "mode": "NORMAL",
    "reason": "PERIOD_RUNNING"
  }
}
```

导播只读取：

```text
phase
period
free_throw_team
director_hint
```

其余技术统计变化不会影响运镜性能。

---

## 14. 回滚

停止系统：

```bash
python3 stop_all_techtable.py
```

找到最新备份：

```bash
ls -dt backup_techtable_v3_* | head
```

将备份覆盖回工程。例如：

```bash
BACKUP=$(ls -dt backup_techtable_v3_* | head -n 1)

cp -a "$BACKUP/techtable_v2/." techtable_v2/
cp -a "$BACKUP/camera_movement_modified/." camera_movement_modified/
cp "$BACKUP/start_all_techtable.py" start_all_techtable.py
```

然后重新启动。

---

## 15. 当前规则说明

本版本已经形成可复用的技术台状态机，但仍属于项目级技术台，不是经过赛事
组织认证的专业裁判设备。

暂停额度采用常见 FIBA 风格简化逻辑：

- 上半场每队 2 次；
- 下半场每队 3 次；
- 每个加时每队 1 次。

球队单节第 5 次犯规进入 BONUS；个人第 5 次犯规标记满犯并自动离场。
如你的比赛规则不同，可在 `state_store.py` 顶部常量和
`_ensure_timeout_bank_for_period()` 中调整。
