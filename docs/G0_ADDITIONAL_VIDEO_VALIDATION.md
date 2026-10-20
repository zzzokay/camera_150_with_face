# G0 补充录像验证（2026-10-20）

文件作用：记录用户补充的室内比赛录屏在跳过前 30 秒后的真实 YOLO、原规则与保存验证。修改片段选择或复测结果后更新；本报告补充 G0_ACCEPTANCE_REPORT.md，不替代首轮广角录像证据，不表示 G0 已获用户验收。

## 范围、变化与输入

当前状态：**READY_FOR_REVIEW，待用户验收**。用户本轮要求换录像验证，并明确“前30秒不要，从30秒后开始”；仍只执行 G0。
原 `run_pipeline` 总是从文件开头运行，新增 `RunConfig.start_seconds` / CLI `--start-seconds`，默认 0 保持原行为。顺序解码到首个源时间不早于 30 秒的帧，再开始 YOLO、旧跟踪/导播和保存；不另存压缩片段，不把平均 FPS 乘 30 当作准确边界。
跳过的帧没有推理、规则状态更新或输出；片段首帧立即真实推理，之后按片段内计数每 3 帧一次，源帧号和时间保持原值。起点超出视频会报错，摄像头不接受该参数。

新增参数位于 `camera_150/windows_pipeline/config.py`，处理位于 `run.py`，通用配置 `configs/windows.example.yaml` 已同步。未修改 RK3588 共享模块、原入口、模型、规则参数或原始录像。
`summary.json` 仍为 `g0_run_v1`，增加可选审计字段 `source.skipped_frames / first_source_frame_idx / first_timestamp_sec`；旧报告可能没有这些字段。

```text
输入：D:\0basketball\project\video\2026-04-15重庆客运段安康杯篮球比赛记录_哔哩哔哩_bilibili 和另外 6 个页面 - 个人 - Microsoft​ Edge 2026-10-20 16-53-01.mp4
文件大小：113,291,682 bytes
SHA-256：4023326edd7e0fa768494356c659cd6f46478ad8d8df844ab49fbe919ecc3816
解码后完整源帧数：2541；1920×1080；OpenCV FFMPEG
报告 FPS：24.03299737159781；按帧数/FPS 估计全长约 105.73 秒
模型：C:\Users\zenghuiting\Desktop\rk_driceter\best.pt
模型 SHA-256：d68486dcc883388d1d822a9ab67d9d6c9cd5c6dccf653c63242ecc9e39863db9
真实类别：{0: 'person'}，没有 ball
```

本片是室内广角比赛录屏；使用 `--undistort none` 保留原画面，不套用另一相机的 NPZ，也不声称已完成镜头标定验证。框的空间标记为 `raw_full_frame_px`，不能与首轮视频的已去畸变坐标直接混用。
环境与首轮一致：Windows 11 / Python 3.11.4 / torch 2.9.1+cpu / Ultralytics 8.3.225 / OpenCV 包 4.12.0.88，`.venv` CPU，无新增依赖。

## 实际 PowerShell 命令

工作目录：`D:\0basketball\project`。预检记录已将用户给定长中文文件名保存至审计 JSON；实际执行：

```powershell
$g0AdditionalVideo = (Get-Content -Encoding UTF8 -Raw .\runs\g0_additional_audit_20261020_165629\source_probe.json | ConvertFrom-Json).source
.\.venv\Scripts\python.exe -X utf8 .\run_windows.py --source $g0AdditionalVideo --weights 'C:\Users\zenghuiting\Desktop\rk_driceter\best.pt' --undistort none --device cpu --detect-interval 3 --start-seconds 30 --max-frames 0 2>&1 | Tee-Object -FilePath .\runs\g0_additional_audit_20261020_165629\real_video_console.txt
```

`max_frames=0` 表示选中起点之后处理到文件结尾，不是处理 0 帧。最快复现不依赖审计 JSON 的文件选择命令见 [NEWCOMER_HANDOFF.md](../NEWCOMER_HANDOFF.md)。

## 实际结果与完整性

| 项目 | 实测值与含义 |
|---|---|
| 状态 / 停止原因 | COMPLETED / source_eof |
| 起点 | 源帧 723，源时间 **30.0101 秒**；跳过 723 帧 |
| 终点 | 源帧 2540，源时间 **105.7088 秒** |
| 处理帧 | **1818**，723–2540，连续且无前 30 秒输出 |
| 真实 YOLO | **606 次**，首个选中帧立即推理 |
| 复用帧 | 1212；observed=false，调试画面显示 REUSED |
| 累计人物候选框 | 6984，跨推理帧累计，不是 6984 个人或准确率 |
| 时间戳回退帧 | 0 |
| 裁切框相对首帧变化帧 | 1808；证明状态更新，不代表导播质量分数 |
| 处理耗时 | 63.6505 秒，含顺序解码跳过、初始化、推理、规则与保存 |
| 总耗时 | 73.9547 秒，含两路输出完整解码核验 |
| 单次推理平均耗时 | 28.2407 ms，含首次预热，不是独立硬件性能基准 |

产物目录：`D:\0basketball\project\runs\g0_20261020_165817_c5a8d96f`。

| 文件 | 已核验内容 |
|---|---|
| `director.mp4` | 1280×720，24.033 FPS，1818 帧，43,346,213 bytes；干净导播，无音轨 |
| `overview.mp4` | 1920×1080，24.033 FPS，1818 帧，156,954,027 bytes；全幅框/临时 ID/青色裁切窗口 |
| `summary.json` / `run.log` | 配置、真实模型哈希/类别、源起止、推理计数、耗时及输出解码统计 |
| `review_contact_sheet_1.jpg` / `_2.jpg` | 六组全幅调试与导播对照，源时间约 30/45/60/75/90/105.7 秒 |
| `overview_frame_*.jpg` / `director_frame_*.jpg` | 输出索引 0、360、720、1080、1440、1817 的原尺寸解码截图 |
| `review_metadata.json` | 对照图准确源帧号/时间、独立源解码帧数、PTS 间隔、产物字节数 |

另一次独立**顺序解码**确认源共 2541 帧、选中部分 1818 帧、首末时间与运行报告一致；未用录屏随机 seek 返回的时间作为准确证据。源选中片段相邻 PTS 约 0.041633–0.041667 秒。
输出使用源报告的 FPS 写恒定帧率视频，播放时长约 **75.646 秒**；源首末 PTS 跨度约 75.6987 秒（不含最后一帧展示时长）。元数据 FPS 与实际 PTS 有小差异，本轮没有重采样音画同步，不能宣称时间完全无偏差。

本轮首条真实输出：

```json
{
  "class_name": "person",
  "model_class_id": 0,
  "confidence": 0.85383528,
  "bbox_xyxy": [764.18921, 865.51556, 844.64612, 1063.85168],
  "coord_system": "raw_full_frame_px",
  "observed": true,
  "source_frame_idx": 723,
  "timestamp_sec": 30.0101
}
```

坐标是完整 1920×1080 画面的左上/右下像素，数值四舍五入显示，原精度在 summary。这个高置信人物框位于近处裁判区域，说明 person 不等于上场球员身份。

## 自动化与目视结果

本轮实际执行（真实权重启用，自动测试仍用首轮固定录像作回归；本片完整测试是上面的独立运行）：

```powershell
$env:G0_TEST_WEIGHTS = 'C:\Users\zenghuiting\Desktop\rk_driceter\best.pt'
$env:G0_TEST_VIDEO = 'C:\Users\zenghuiting\Desktop\rk_driceter\usb3_undistorted_20260706_111148_325.mp4'
.\.venv\Scripts\python.exe -X utf8 -m pytest -q --junitxml .\runs\g0_additional_audit_20261020_165629\pytest.xml
```

**27 passed in 5.46s；0 失败、0 跳过。** 新增起始秒数负数/NaN/无穷/摄像头误用边界，真实模型集成覆盖默认起点和非 3 整数倍的源帧起点，要求片段首帧立即推理、12 帧连续输出、两路完整解码；其余原组件和共享算法回归保持通过。
证据位于 `runs/g0_additional_audit_20261020_165629/pytest.txt`、`pytest.xml`、`source_probe.json`、`real_video_console.txt`。全局测试没有被写成对这场比赛的检测精度评测。

目视抽查六个时间点及完整尺寸的约 60 秒调试图，发现：

1. 模型能在室内比赛画面上检出多名人物；导播输出与青色裁切区对应，窗口在左右两侧活动间移动；不只是在全幅画面上画框。
2. 首帧居中裁切未包含最左侧部分球员；约 60 秒输出中，裁切窗口仍偏右，左侧数名人物在框外。保留了原规则过渡行为，不能把它描述为运镜质量已合格。
3. 裁判、近处场边人员也有 person 框；这是检测到人，不能自动视为真正上场球员。G0 不增加角色分类或新 ROI 调参。
4. 只有人物模型，没有篮球框；本次不能证明持球点/空中球跟随、全场目标关联质量。没有人工真值，不报告 mAP、MOTA、IDF1 或准确率。

两路视频全部逐帧解码通过；人工仅抽查列出的帧，未声称连续人工观看全片。RK3588/CUDA/音频 RTSP 等未测边界仍以主报告为准。当前只完成 G0 补充验证，不进入 G1。

**请验收本关；确认后我再执行下一关。**
