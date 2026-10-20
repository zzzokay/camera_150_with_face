# 关卡进度

文件作用：记录实际关卡状态、测试命令、产物、阻塞和用户确认。每次测试/交付后更新；细节见 docs/G0_ACCEPTANCE_REPORT.md，不把规划或组件测试当作端到端验收。

更新日期：2026-10-20（Asia/Shanghai）。当前关卡：**G1 人物检测与篮球接口预留（用户调整范围）**。

| 关卡 | 状态 | 说明 |
|---|---|---|
| G0 | ACCEPTED | 用户在补充录像验证后表示“下一步吧”，授权继续 |
| G1 | READY_FOR_REVIEW | 人物筛选/检测记录与篮球关闭接口已自测，待验收；完整双类别能力未验收 |
| G2–G7 | TODO | 未开始，未获授权 |

用户确认记录：G0 使用用户指定的桌面权重与广角录像，之后使用 `video/` 室内录屏、跳过前 30 秒完成补充验证。用户随后明确“下一步吧，篮球的检测暂时没有加，你先留着位置”，据此接受 G0 并授权本次调整范围的 G1；不把篮球双类别能力标作通过，不自动进入 G2。

## 当前 G1 验证

- 最新用户调整：“roi范围的上边界可以再高一点”；室内策略上边界 **0.70 → 0.66**，1080p 中约上移 43 像素，下边界 0.97。仅配置/文档变更，未改原规则或 RK3588 源码。
- 本次相关策略测试 **11 passed in 1.67s，0 失败/跳过**；其余 28 项未重跑（仅此场景参数变化，另做完整真实模型视频对照）。本次日志和核验脚本在 `runs/g1_roi_top_066_20261020_173333/`。
- 最新目录 `runs/g1_20261020_173342_033fabce`：1818 帧/1818 次真实推理，两路 MP4 各完整解码 1818 帧、1818 行 JSONL 全部核验；原始候选与旧轮逐帧一致，**20880 候选、17287 保留、3593 ROI 排除**。179 帧多保留累计 219 框，包含远端场边和重叠候选，不是球员人数或准确率。
- `roi_comparison_frame_1051.jpg` 展示源帧 1774（73.7962 秒）保留 6 → 11 框，另有四个抽查点；`roi_comparison_validation.json` 保存独立核验。新旧 `director.mp4` 哈希相同，本次未改变导播视频；球仍关闭。详细命令/边界见 [G1 报告最新补充](docs/G1_ACCEPTANCE_REPORT.md)。G1 仍待用户验收，G2 未开始。

以下为上边界 0.70 的初版历史证据，当前配置与最新产物以上述补充为准：

- 分支 `g1/person-detection-ball-slot`；本轮只改 Windows 检测/记录/配置/绘图，RK3588 原文件和规则未再改动。
- **39 passed in 5.91s，0 失败/跳过**。实际命令：设置下文真实权重/视频环境变量后运行 `.\.venv\Scripts\python.exe -X utf8 -m pytest -q`；输出摘要在 `runs/g1_audit_20261020_171533/automated_test_stdout.txt`。三个真实模型集成用首轮固定录像回归，室内录像另做完整运行。
- 室内完整验证：`.\.venv\Scripts\python.exe -X utf8 .\run_windows.py --config .\configs\g1.indoor.local.yaml`，`start_seconds=30`、`detect_interval=1`、策略 `detection.indoor.example.yaml`、导出检测记录；完整环境与复现见 [G1 报告](docs/G1_ACCEPTANCE_REPORT.md)。
- 实际源时间 30.0101–105.7088 秒，**1818 帧/1818 次推理**；20880 累计候选、17068 保留、3812 因 ROI 排除，0 帧完全无人物候选不等于所有球员无漏检。
- 目录 `runs/g1_20261020_171552_8d53d276`：两路 MP4 各完整解码 1818 帧；`detections.jsonl` 1818 行逐行检查通过，篮球关闭 1818 帧、位置均 null；独立计数与 summary 一致。
- 人工抽查 30/45/60/75/90/105.7 秒及排除最多的一帧：近处场边人物被排除，场内裁判可能保留；多人遮挡/重复框、规则裁切偏移仍需用户评估，不报告精度或 ID 指标。
- 篮球检出能力、球参数有效性、真实去畸变几何质量均未验收；用户已要求球接口先预留。当前 READY_FOR_REVIEW 仅针对本次调整范围，**不是完整双类别 G1 通过**，没有开始 G2。

## 最新补充验证：30 秒后室内比赛

- 新增 `--start-seconds 30`，默认 0 保持原行为；按源时间顺序跳过，不改旧算法。起点帧立即推理，源索引和时间保留。
- **27 passed in 5.46s，0 失败/跳过**，含两个起点的真实模型集成；命令为下方 pytest 命令，将 JUnit 输出路径替换为 `runs/g0_additional_audit_20261020_165629/pytest.xml`，日志在同目录 `pytest.txt`。
- 真实新录像完整剩余段：源帧 723–2540、源时间 **30.0101–105.7088 秒**、**1818 帧、606 次真实推理、1212 复用帧**；6984 累计候选框不等于人数/准确率。
- 实际运行带 `--undistort none --device cpu --detect-interval 3 --start-seconds 30 --max-frames 0`，完整命令见 [补充报告](docs/G0_ADDITIONAL_VIDEO_VALIDATION.md) 和 [新人交接](NEWCOMER_HANDOFF.md)。
- 目录：`runs/g0_20261020_165817_c5a8d96f`，`director.mp4` / `overview.mp4` 均完整解码 1818 帧；FPS 24.033，播放约 75.646 秒，无音轨。另有 summary、日志、六帧对照和独立源时间核查。
- 边界：室内画面检出裁判/场边人员；约 60 秒窗口偏右、左侧人物被裁出。六个时间点目视核查，未做精度/跟踪指标或整段人工观看；原规则参数未调优，未开始 G1。

## 首轮验证记录（保留历史证据）

PowerShell，工作目录 `D:\0basketball\project`：

```powershell
$env:G0_TEST_WEIGHTS = 'C:\Users\zenghuiting\Desktop\rk_driceter\best.pt'
$env:G0_TEST_VIDEO = 'C:\Users\zenghuiting\Desktop\rk_driceter\usb3_undistorted_20260706_111148_325.mp4'
.\.venv\Scripts\python.exe -X utf8 -m pytest -q --junitxml .\runs\g0_audit\pytest.xml
.\.venv\Scripts\python.exe -X utf8 .\run_windows.py `
  --source 'C:\Users\zenghuiting\Desktop\rk_driceter\usb3_undistorted_20260706_111148_325.mp4' `
  --weights 'C:\Users\zenghuiting\Desktop\rk_driceter\best.pt' `
  --undistort already --device cpu --detect-interval 3 --max-frames 300
```

- 最终 `.venv` 自动化：**22 passed in 4.61s，0 失败、0 跳过**，包含真实模型 12 帧集成；旧算法另有 180 帧合成输入回归。
- 主片段：300 源帧（前 10 秒）、100 次真实推理、200 复用帧、231 个累计人物候选框；不是 231 个人或检测准确率。
- 输出：`runs/g0_20261020_144146_be04f4bc/director.mp4`（1280×720）与 `overview.mp4`（1920×1080），两者 30 FPS、完整解码均为 300 帧。
- 目视核查：第 0、149、299 帧，窗口向左移动；首帧初始居中未包含左侧人物；末帧有重复框和围栏疑似误检，详见报告和 `review_contact_sheet.jpg`。
- 跨当前目录与中文空格输出：真实模型处理 3 帧，两路完整解码通过，目录 `runs/cross_directory 中文/g0_20261020_144312_2c6c6e8d`。
- 摄像头：dshow 0/1 号各读 3 帧、窗口 API 可见、收帧时间递增；未保存画面。1 号实际读帧约每秒一次，不能宣称实时 30 FPS；窗口外观和完整相机推理保存未验收。
- 审计证据：`runs/g0_audit/final_environment.json`、`pytest.txt`、`pytest.xml`、`real_video_console.txt`、`cross_directory_console.txt`、`camera0_final_environment.json`、`camera1_final_environment.json`；主目录另有 `summary.json`、`run.log` 和抽帧对照图。

## 环境、阻塞与确认责任

Python 3.11.4 / torch 2.9.1+cpu / Ultralytics 8.3.225 / OpenCV 4.12.0.88；CPU 路径已验证，完整 39 包版本在 `requirements-windows.lock.txt`。
安装时默认镜像 403、旧 pip 索引解析和下载停滞已解决；最终使用官方源和校验过的官方 wheel，仅安装到 `.venv`，未改全局 pip 配置。
模型与视频均已取得并完成所选片段测试，**当前没有阻塞 G0 自测的问题**。

未验证：RK3588 真机、CUDA/ONNX、msmf、长时摄像头推理录制、原始实拍视频 remap、完整 Qt/技术台/人脸检录/Windows 音频 RTSP；不计作本轮通过项。当前权重只有 person，没有 ball。
G0 已由用户“下一步吧”授权继续；G1 当前只对调整后的范围 READY_FOR_REVIEW。用户负责决定是否验收本轮人物检测/接口，篮球实测仍暂缓；G2 及后续需要另行批准。
