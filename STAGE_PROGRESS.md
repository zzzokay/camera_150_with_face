# 关卡进度

文件作用：记录实际关卡状态、测试命令、产物、阻塞和用户确认。每次测试/交付后更新；细节见 docs/G0_ACCEPTANCE_REPORT.md，不把规划或组件测试当作端到端验收。

更新日期：2026-10-20（Asia/Shanghai）。当前关卡：**G0 Windows 迁移**。

| 关卡 | 状态 | 说明 |
|---|---|---|
| G0 | READY_FOR_REVIEW | Windows CPU 真实 YOLO → 原规则 → 两路视频保存及完整解码已通过，待用户验收 |
| G1–G7 | TODO | 未开始，未获授权 |

用户确认记录：已要求只执行 G0；已确认使用桌面 rk_driceter/best.pt 和同目录指定广角 MP4。**尚未确认 G0 验收通过，未授权进入 G1。**
随后用户补充 `video/` 中的室内比赛录屏，明确跳过前 30 秒；补充验证已完成，仍未收到 G0 验收确认。

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
用户负责核查输出外观并决定是否验收 G0；Agent 已完成所列自测。**ACCEPTED 只能由用户明确确认，本次仅 READY_FOR_REVIEW。**
范围仍为 G0；后续关卡需用户另行批准，不自动开始。
