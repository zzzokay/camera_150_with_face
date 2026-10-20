# G1 验收报告（2026-10-20，用户调整范围）

文件作用：提交本轮人物检测、筛选记录与篮球预留接口的真实证据，说明未完成的双类别能力。测试执行者在代码或结果变化后更新；配合 NEWCOMER_HANDOFF.md、G1_DETECTION_SCHEMA.md 与 STAGE_PROGRESS.md 阅读。

- 当前状态：**READY_FOR_REVIEW / 待用户验收**，仅针对本轮调整范围；不宣称原计划的完整双类别 G1 已通过。
- 用户授权与本关目标：用户在 G0 交付后明确“下一步吧，篮球的检测暂时没有加，你先留着位置”。据此进入 G1，先完成人物策略/检测记录，篮球关闭并预留字段与配置；不因原计划要求球模型而再次要求用户提供权重，也不进入 G2。
- 原有问题与为何修改：原 `YoloPersonDetector` 只做人物检测，缺少逐帧框记录与外部 ROI，检测到的裁判/场边人员可能影响旧导播。G1 增加可解释筛选、类别配置与审计，仍不把 person 等同于上场球员。
- 变更文件及作用：见后文；原 RK3588 文件与 G0 原规则本次未再改动。
- Windows 环境信息：Windows 11 家庭版中文版 10.0.26100、Python 3.11.4、torch 2.9.1+cpu、torchvision 0.24.1+cpu、Ultralytics 8.3.225、OpenCV 4.12.0.88（运行时 4.12.0）、NumPy 2.2.6；独立 `.venv`，无新增包，CUDA/NPU 未测。
- 自动测试：**39 passed in 5.91s，0 失败/跳过**；三项真实模型集成覆盖 G0 起点和 G1 关闭篮球的导出。合成球类别/框只验证接口，不冒充真实篮球推理。
- 实际运行：指定室内录像 30 秒后至结尾，1818 帧、1818 次真实 YOLO；两路视频完整解码，1818 行 JSONL 独立核对。
- 手工检查：六组约 30/45/60/75/90/105.7 秒全幅与导播图，另看排除最多的源帧 1774。失败例保留，见后文。
- 对 RK3588 的影响：本轮无共享源文件改动；旧入口原文与上游一致、算法 AST 和 180 帧合成回归继续通过。未访问 RK3588 真机。
- 根目录文档：README、PROJECT_STRUCTURE、NEWCOMER_HANDOFF、STAGE_PROGRESS、CHANGELOG 已同步；两份用户原规范未改。
- 请用户确认：是否验收本轮调整范围的人物筛选/记录与球接口；篮球真实检出继续暂缓，G2 需要另外授权。

## 实现与配置边界

| 文件 | 本轮作用 |
|---|---|
| `windows_pipeline/detection_policy.py` | 标准 person/ball 名称映射、各类阈值/尺寸/凸多边形 ROI、非法配置检查 |
| `windows_pipeline/detector.py` | `YoloDetector` 一次真实推理后分类型筛选，保留排除原因；`YoloPersonDetector` 保留 G0 构造参数 |
| `windows_pipeline/detection_records.py` | `g1_detections_v1` JSONL，真实/复用帧、球关闭/缺失/观测状态分明 |
| `config.py` / `run.py` | `--detection-policy` / `--export-detections`、按类统计、可选导出，G0 默认仍无额外 ROI |
| `outputs.py` | G1 保留/排除/ROI/裁切叠加；G0 仍使用原平滑 ID 调试图 |
| `contracts.py` | 坐标/时间说明同步；源时间不因选段归零 |
| `configs/detection*.example.yaml` | 通用无 ROI 与本次室内 ROI；两者 ball.enabled=false |
| `configs/g1.indoor.example.yaml` | 文件路径占位、30 秒起点、逐帧推理与检测导出 |
| `tests/test_detection_policy.py` / `test_real_model.py` | 类别/阈值/ROI/无球契约及真实 G1 导出集成 |

人物策略：confidence=0.35，最小框高 0.02×全幅高，最大框高 0.5×全幅高，ROI 顶点 `[0,.70],[1,.70],[1,.97],[0,.97]`，按框底部中心筛选。该区域仅适配这次画面，可能排除远处/边线/遮挡球员，不能当通用校准。
篮球策略：enabled=false，别名 `sports ball/ball/basketball`、独立置信度初值 0.20、尺寸/ROI 接口保留。初值未做真实球验证。将来启用但权重无球类别会报错，不生成替代位置。
人物保留框送入原 `SmoothTracks → analyze_single_view_frame → update_overlay_director_state`；球接口即便未来启用也不会进入原人物导播。这里没有 ByteTrack、球场映射或训练数据标签。

## 模型、视频与真实命令

模型仍是 `C:\Users\zenghuiting\Desktop\rk_driceter\best.pt`，大小 6,243,299 bytes，SHA-256 `d68486dcc883388d1d822a9ab67d9d6c9cd5c6dccf653c63242ecc9e39863db9`，真实 names `{0:'person'}`。
源为用户指定的 `video/2026-04-15重庆客运段安康杯篮球比赛记录_哔哩哔哩_bilibili 和另外 6 个页面 - 个人 - Microsoft​ Edge 2026-10-20 16-53-01.mp4`，源属性/哈希沿用并可对照 [G0 补充报告](G0_ADDITIONAL_VIDEO_VALIDATION.md)；未改写文件。
本轮 `undistort=none`，坐标为 `raw_full_frame_px`，没有将另一相机的 NPZ 用于该录屏。原 G1 清单中的“真实去畸变广角坐标”仍不能据本片宣称完成；already 模式或同镜头标定要在有对应资料时另验。

PowerShell，工作目录 `D:\0basketball\project`：

```powershell
$env:G0_TEST_WEIGHTS = 'C:\Users\zenghuiting\Desktop\rk_driceter\best.pt'
$env:G0_TEST_VIDEO = 'C:\Users\zenghuiting\Desktop\rk_driceter\usb3_undistorted_20260706_111148_325.mp4'
.\.venv\Scripts\python.exe -X utf8 -m pytest -q
```

stdout：`39 passed in 5.91s`，摘要保存 `runs/g1_audit_20261020_171533/automated_test_stdout.txt`。测试的固定真实录像用于回归，不把它说成本次室内场景精度标注。
本机 `g1.indoor.local.yaml` 由示例复制，只把 source 填入上述室内视频绝对路径、weights 填入桌面权重。实际完整运行：

```powershell
$ErrorActionPreference = 'Stop'
.\.venv\Scripts\python.exe -X utf8 .\run_windows.py --config .\configs\g1.indoor.local.yaml 2>&1 | Tee-Object -FilePath .\runs\g1_audit_20261020_171533\real_video_console.txt
```

stdout 含“真实模型类别：{0: 'person'}”“篮球检测：未启用（不生成位置）”和“完整解码核验通过”。本地 YAML 被忽略，通用示例不含个人绝对路径。

## 实际结果与产物

目录：`D:\0basketball\project\runs\g1_20261020_171552_8d53d276`。

| 指标 | 实际值 / 说明 |
|---|---|
| 状态 / 停止 | COMPLETED / source_eof |
| 源范围 | 帧 723–2540；30.0101–105.7088 秒；跳过 723 帧 |
| 处理 / 实际推理 | 1818 帧 / 1818 次；复用帧 0 |
| 人物原始候选 | 20880，已经过 YOLO 0.35 置信度和 NMS，尚未经过新增 ROI |
| 人物保留 / 排除 | 17068 / 3812；本段排除均为 roi，未触发尺寸排除 |
| 有人物 / 无人物推理帧 | 1818 / 0；不代表所有球员都检出，裁判也可能保留 |
| 篮球 | 关闭；候选/保留均 0，未启用不计作漏检帧 |
| 时间戳回退 | 0 |
| 处理 / 含解码核验总耗时 | 106.4542 / 115.5660 秒；含预热，非独立硬件基准 |
| 平均推理 | 31.7540 ms，含首次预热 |

这些是同一轮候选筛选前后统计，不是准确率或唯一人数。G0 仅每 3 帧推理，本轮每帧推理，不能拿两轮框总数直接比较检测能力。
首次控制台日志路径写错产生的重复运行已按已核实的自身 PID 停止，其目录有 `NOT_ACCEPTANCE_EVIDENCE.json`，部分产物不纳入本报告；本报告只计上述完成目录，耗时也不用于性能提升结论。

| 文件 | 验证 |
|---|---|
| `director.mp4` | 1280×720、24.033 FPS、1818 帧、42,616,885 bytes，完整解码通过 |
| `overview.mp4` | 1920×1080、24.033 FPS、1818 帧、132,175,740 bytes，完整解码通过 |
| `detections.jsonl` | 1818 行、5,535,000 bytes，逐行 JSON、源索引连续、时间递增、计数与 summary 一致 |
| `summary.json` / `run.log` | g1_run_v1，真实类别/模型哈希、实际策略、分类统计、视频核验 |
| `record_validation.json` | 独立 JSONL 复核；1818 条球关闭且 ball_valid=false、中心 null |
| `review_contact_sheet_1.jpg` / `_2.jpg` | 六个时间点的检测与导播对照 |
| `overview_frame_1051.jpg` | 源帧 1774，排除最多 7 框的一帧，用于失败边界检查 |
| `visual_review_metadata.json` | 抽查点、候选/排除计数和对应真实源时间 |

两路视频均无音轨，播放约 75.646 秒。源报告 FPS 与 PTS 有小差异，保存为恒定帧率，仍不承诺精确音画同步。

真实首个保留人物（四舍五入展示）：

```json
{
  "source_frame_idx": 723,
  "timestamp_sec": 30.0101,
  "class_name": "person",
  "model_class_id": 0,
  "confidence": 0.77639443,
  "bbox_xyxy": [147.12109, 806.74658, 214.21945, 971.20056],
  "coord_system": "raw_full_frame_px",
  "observed": true,
  "ball_enabled": false,
  "ball_valid": false,
  "ball_centers_full_frame_px": null
}
```

这里为便于阅读把帧级球字段与 Detection 放在同一展示段；真实 JSONL 的层级以 [字段规范](G1_DETECTION_SCHEMA.md) 为准。

## 人工核查、剩余限制与回退

1. 30 秒起点原最高置信的近处裁判框（score≈0.8538、底部 y≈1063.85）被 ROI 排除，近处左右场边人物也有紫色排除框；模型没有因此变成身份识别器。
2. 45/60 秒有横向移动和人物聚集，候选包含重复/遮挡的框；没有真实标注，不能量化 ID 切换或漏检率。G1 叠加的是原始检测框，G0 叠加的是旧平滑轨迹框，两者不能混为同一种测量。
3. 约 60 秒青色裁切仍偏右，左侧人物在窗口外；90/105 秒场内裁判仍可能保留。原规则过渡和球员角色识别问题仍在，没有把筛选框数减少写成运镜质量提升。
4. 源帧 1774 的 7 个排除框包含近处场边与远处候选；远处球员脚点接近 ROI 上边界时存在误排风险，需用户结合场景评估；本轮没有声称被排除者全部是观众。
5. 仅这一室内录像和原固定短片，不覆盖所有场馆/多场完整比赛；目视抽查而非人工连续观看全片。

篮球真实检出、篮球参数有效性、去畸变几何、CUDA/NPU 和 RTSP/音频仍未验证。用户暂缓的球能力以后补验；当前只提交调整范围，不将原计划完整 G1 勾选通过。
本轮 Git 分支 `g1/person-detection-ball-slot`，前一 G0 基线 `406b64c`，代码提交 `73327e9`，文档另行提交。仅本地提交，不推送。需要保持 G0 行为时不传检测策略/导出参数即可；需回到确切 G0 版本，可在独立目录检出 `406b64c`，或保存后续修改后 `git revert <本轮提交号>`，不覆盖用户改动、不删除视频/模型/产物。
下一关只有用户明确授权才开始；当前 JSONL 为检测审计，不包含 ByteTrack、轨迹数据集或训练标签。

**请验收本关；确认后我再执行下一关。**
