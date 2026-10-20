# G2 验收报告（2026-10-20，篮球继续暂缓）

文件作用：提交 Windows 人物 ByteTrack 的真实运行、回归和质量边界，供用户决定本关是否验收。结果/参数变化时更新；接口见 G2_TRACKING_QC.md，复现见 NEWCOMER_HANDOFF.md。

## 最新交付：Windows 独立化方案，待确认

- 用户要求先提交方案、确认后重构，独立工程验收后才优化参数；当前仍为 G2，篮球关闭。
- 本轮产物：[G2_WINDOWS_STANDALONE_PLAN.md](G2_WINDOWS_STANDALONE_PLAN.md)。新分支 `windows/g2-standalone` 目前只改文档，旧 G2 基线 `cc87e85` 和历史分支保留；无 Python/YAML/依赖变化，无资产删除。
- 已发现：Windows 预处理、规则导播、渲染工具、旧对照仍依赖原目录；现有 G2 总是启动导播/对照，测试还依赖旧源码与 Git 历史。拟迁移到独立包和根 `run.py`，可选分支默认关闭，先建立固定输入回归。
- 本轮验证：源码/依赖与既有证据复核、文档链接和 Git 差异检查。自动化/真实模型测试本轮未运行（本轮仅方案）；下方 53 项和视频数据均为此前实测，不能计为独立工程通过。
- 状态：**方案等待用户确认；Windows 独立工程尚未实施/验收，跟踪质量仍未达成验收**。确认后按方案提交单独的独立工程验收报告，再等待用户确认；不自动开展调参/ReID。

## 此前 G2 功能实测与质量边界（历史证据）

- 当前状态：**IN_PROGRESS / 用户反馈跟踪效果差，质量待改进、尚未验收**。原人物跟踪、对照与接口功能证据保留；53项测试不代表质量达标。最新诊断与整改顺序见 [G2_QUALITY_REVIEW.md](G2_QUALITY_REVIEW.md)。
- 用户授权：用户在 G1 ROI 调整交付后表示“下一步”，据此接受 G1 调整范围并进入 G2；此前“篮球的检测暂时没有加，你先留着位置”继续生效。G3 未开始。
- 本关目标：独立 ByteTrack 接收一次 YOLO 真实观测，输出人物临时 ID、带 ID 视频和验收 CSV；旧 SmoothTracks 保留独立对照/回退。
- 原有问题与为何修改：旧算法按最近脚点配对，交叉时可能续接错人；.35 前置检测门槛不能给 ByteTrack 提供低置信续接候选。新方案明确区分高/低阈值、真实观测与状态估计。
- 变更文件及作用：新增 `tracker.py`、`tracking_records.py`、两份 G2 示例配置和 `tests/test_tracker.py`；修改 config/detector/run/outputs/director_adapter，使跟踪可选、一次 YOLO 供双对照，G2 导播绕过旧关联。两个 G2 文档说明格式/边界。只改 Windows 文件与依赖/测试/文档。
- Windows 环境：Windows 11 10.0.26100，Python 3.11.4，torch 2.9.1+cpu，Ultralytics 8.3.225，OpenCV 4.12.0.88，NumPy 2.2.6，SciPy 1.17.1，新增 lap 0.5.12（官方 PyPI Windows wheel，约 1.5 MB，仅装 .venv）。`pip check` 无依赖问题，锁定 40 包；未测 CUDA/NPU。
- 自动测试：最终复核 **53 passed in 7.44s，0 失败/跳过**。含旧 39 项、13 项跟踪组件、1 项新增真实模型 G2 集成；日志 `runs/g2_audit_20261020_174355/final_pytest.txt` / `final_pytest.xml`。首次全套 53 passed in 6.33s 的日志仍保留。
- 手工检查：约 30/32/45/60/73.8–76.7/90/105.7 秒及长低置信片段的对照图；具体正反例见后文，非完整逐帧身份标注。
- 对 RK3588 的影响：原目录源文件本轮无改动；旧入口/算法比对、180 帧合成回归以及 G0/G1 真实模型集成仍通过。G2 新增旁路经测试证明不会调用旧关联器，不改变原规则公式。
- 根目录文档：README、PROJECT_STRUCTURE、NEWCOMER_HANDOFF、STAGE_PROGRESS、CHANGELOG 已同步；用户两份规范原文保留。
- 请用户确认：人物 G2 及已列出的跟踪质量限制是否可接受；篮球跟踪仍暂缓，未自动开始 G3。

## 实际命令与输入

PowerShell，项目根目录 `D:\0basketball\project`：

```powershell
.\.venv\Scripts\python.exe -m pip install --index-url https://pypi.org/simple --only-binary=:all: lap==0.5.12
.\.venv\Scripts\python.exe -m pip check
$env:G0_TEST_WEIGHTS = 'C:\Users\zenghuiting\Desktop\rk_driceter\best.pt'
$env:G0_TEST_VIDEO = 'C:\Users\zenghuiting\Desktop\rk_driceter\usb3_undistorted_20260706_111148_325.mp4'
.\.venv\Scripts\python.exe -X utf8 -m pytest -q --junitxml runs/g2_audit_20261020_174355/final_pytest.xml
.\.venv\Scripts\python.exe -X utf8 .\run_windows.py --config .\configs\g2.indoor.local.yaml
```

本机配置由 `g2.indoor.example.yaml` 填写与 G1 相同的真实模型/室内视频路径，跟踪配置指向 `tracking.example.yaml`。本机路径文件被忽略，不提交权重、视频或输出。录像仍跳过前 30 秒，`undistort=none`、CPU、detect_interval=1，ROI 保持 .66–.97。
模型 `best.pt` SHA-256 `d68486dcc883388d1d822a9ab67d9d6c9cd5c6dccf653c63242ecc9e39863db9`，真实 names `{0:'person'}`。室内录屏 SHA-256 `4023326edd7e0fa768494356c659cd6f46478ad8d8df844ab49fbe919ecc3816`，与 G1 一致，文件未改写。完整中文路径见本机配置或 summary；未加载 best_sac。

## 实际结果与产物

完成目录：`D:\0basketball\project\runs\g2_20261020_175136_fc830eed`。

| 指标 | 实际值与含义 |
|---|---|
| 状态/停止 | COMPLETED / source_eof |
| 源帧/时间 | 723–2540；30.0101–105.7088 秒；1818 帧 |
| 真实 YOLO/复用 | 1818 次 / 0 帧；两个对照共用同一批候选 |
| 低门槛原始人物候选 | 43122，YOLO .10+NMS 后；与 G1 的 .35 候选数不能直接比较 |
| .35 人物保留 | 17287，与上一轮 G1 一致 |
| G1 审计排除 | confidence=22242、roi=3593；低置信可能被 G2 续接，ROI 排除不进入跟踪 |
| ByteTrack 匹配观测 | 18778，其中 high=16348、low=2430；不是人数/准确率 |
| 旧关联匹配观测 | 17287；只接收 .35 以上的同批人物框 |
| 不同临时 ID | ByteTrack 274 / 旧关联 160；不等于上场人数，也不能单凭数量判优劣 |
| 全无已确认轨迹帧 | 0；不证明每名球员都被跟住 |
| 重置/时间回退/空推进 | 此顺序片段均为 0；segment=1 共 1818 帧 |
| 处理耗时/含解码总耗时 | 117.7853 / 129.8419 秒；含双图绘制、三路编码/QC，非独立模型性能基准 |
| YOLO 均时 | 28.5402 ms，含首次预热；跟踪 FPS 参数是源名义 24.032997，不是处理吞吐 |

CSV 仅输出已确认匹配，新的高置信框也可能处于待确认阶段而尚未有可输出 ID。最高输出 ID 为 939，很多未确认短轨迹不会输出，不能把最大 ID 当目标数量。

| 文件 | 实际验证 |
|---|---|
| `director.mp4` | 1280×720，24.033 FPS，1818 帧，42,811,729 bytes |
| `overview.mp4` | 1920×1080，24.033 FPS，1818 帧，136,155,029 bytes；ByteTrack ID 与滤波框 |
| `tracking_comparison.mp4` | 1920×540，24.033 FPS，1818 帧，97,471,384 bytes；左旧/右新，非两套导播比较 |
| `bytetrack_qc.csv` | 18778 行观测，不含表头；4,715,550 bytes |
| `smoothtracks_qc.csv` | 17287 行观测，不含表头；4,528,247 bytes |
| `tracking_audit.jsonl` | 1818 行，15,184,706 bytes；逐帧原框/滤波框/ID、球关闭语义 |
| `detections.jsonl` | G1 schema 仍保留，1818 行，11,097,911 bytes |
| `summary.json` / `run.log` | g2_run_v1，真实环境/模型/阈值/FPS/重置/统计 |
| `tracking_validation.json` | 独立核对 CSV/JSONL/原始候选/唯一 ID/源时间/源哈希通过 |
| `case_*.jpg` / `case_metadata.json` | 放大的交叉、短失踪、快速持球移动、场边低置信、横向移动正反例 |

三路视频全部从头完整解码通过；无音轨、CFR 约 75.646 秒。源 PTS 与报告 FPS 略有差异，不承诺任意录屏音画同步或球场几何质量。
独立审计脚本和标准输出在 `runs/g2_audit_20261020_174355/analyze_tracking.py`、`independent_validation.txt`，图像生成脚本 `review_cases.py`；它们是本机验收证据，不是提前实现 G3 重放工具。

## ID 延续、断裂与失败案例

1. `case_lateral_movement.jpg`：同一黑衣持球者在源帧 1774 / 1803 / 1823（73.7962 / 75.0044 / 75.8376 秒）ByteTrack 均为 **P463**；同一原始检测在旧关联中是 **100 → 101 → 92**。画面与原检测逐一核对，说明这个局部片段续接更一致；不外推为全场稳定性指标。
2. `case_moving_ball_handler.jpg`：绿衣持球者在 59.673–60.006 秒 ByteTrack 为 **P218**（先 .298 低置信续接，再 .499 高置信）；60.340 秒没有输出匹配，60.673 秒成为 **P425**。旧方案此处也出现 **61 → 79**。快速运动、检测框变化仍造成碎片；不能声称 ByteTrack 已解决断轨。
3. `case_early_crossing.jpg` / `case_short_missing.jpg`：30–32 秒篮下多人交叉、重叠和重复框；ByteTrack 也有多个 ID 与单个人物重叠。日志显示 ID2 在源帧 767 后缺失两帧、770 重新匹配 ID2；这种“编号重现”只是算法事件，遮挡中是否始终同一人需人工身份标注，不能当自动身份真值。
4. `case_long_low_sideline.jpg`：场边坐着的人员 P792 在源帧 2059–2287、85.6697–95.1685 秒连续 **229 帧**低置信续接（抽查约 .31/.23/.13），证明两阶段通路工作，也暴露扩大 ROI 后场边目标长期保留的副作用；不是新增可靠上场球员。
5. 204 个 ByteTrack 同 ID 观测间隙、1037 个旧 ID 间隙、1206 次同观测的新旧 ID 对应变化仅是自动定位候选事件，**不是**人工 ID Switch/断轨率或算法优劣指标；未作 MOTA/IDF1/准确率计算。274 与 160 的不同 ID 数提示仍有较多碎片，当前只验功能与可追溯质量证据，不宣称性能全面改善。

## 场景切换与其他测试边界

另将已授权室内源帧 723 起 24 帧与桌面广角源帧 0 起 24 帧拼接为明确的 **48 帧受控编辑片**；不是一场连续比赛或身份真值。逐帧来源在 `runs/g2_audit_20261020_174355/controlled_scene_cut_provenance.json`。
实际运行：`.\.venv\Scripts\python.exe -X utf8 .\run_windows.py --config .\runs\g2_audit_20261020_174355\controlled_scene_cut.yaml`。
输出 `runs/g2_audit_20261020_174355/g2_20261020_175231_19acf8b5` 完成 48 次真实 YOLO、48 帧导播完整解码；**在指定源帧 24 / 1.0 秒触发 scene_cut_histogram，segment 1 → 2**，球仍关闭。直方图法不保证所有转场都识别。
组件测试另外验证 15/30/60 FPS 缓冲换算、短缺失/超时、新视频显式 reset、重复/倒序帧拒绝、短 PTS 间隔空更新、长间隔重置、低置信不能独立建轨迹、球类别不能续人物、原导播绕过旧关联，以及检测每帧仅调用一次。最终复核还补入 G2 拒绝 smooth=0 的检查，避免旧对照关闭编号；实拍配置仍为 .65，视频证据不受影响。这些合成条件不作为真实比赛精度证明。

## 已知限制、回退与下游

篮球检测/追踪按用户要求继续暂缓；当前仅保留 disabled/false/null，启用球会报错而不是伪造位置。单目几何、GPU/NPU、摄像头实时跟踪、音频 RTSP、多进程/同进程并发 tracker 未验。当前 ID 碎片较多，重复框与场边人员仍会影响跟踪和原规则裁切；没有连续身份标注或长场次验证。
本关只新增 ID 验收 CSV/QC，没有提前建立 G3 可训练轨迹数据集、重采样、Homography、特征或 TCN。后续 G3 需经用户授权，处理可追溯 schema、记录质量和离线重放，并继续保留上述质量限制。
分支 `g2/bytetrack-person`，代码提交 `5d7eec3`，G1 基线 `7f6b9cf`。不传 `tracking_config`（或继续使用 g1.indoor.local.yaml）即可恢复原 G1 关联/推理门槛；完全回退可在独立目录检出基线，或保存个人修改后 `git revert 5d7eec3` 撤销代码，不删除模型/视频/旧产物。交接文档另行本地提交，不推送。

用户反馈后继续整改 G2，完成质量复测再重新提交验收；当前不进入 G3。
