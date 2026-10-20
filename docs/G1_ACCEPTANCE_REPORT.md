# G1 验收报告（2026-10-20，用户调整范围）

文件作用：提交本轮人物检测、筛选记录与篮球预留接口的真实证据，说明未完成的双类别能力。测试执行者在代码或结果变化后更新；配合 NEWCOMER_HANDOFF.md、G1_DETECTION_SCHEMA.md 与 STAGE_PROGRESS.md 阅读。

- 当前状态：**ACCEPTED（用户调整范围）**。ROI 调整交付后用户表示“下一步”，据此接受人物/记录/球关闭接口并授权 G2；不宣称原计划完整双类别已通过。以下保留当时实测与待验收过程，最新进度见 STAGE_PROGRESS.md。
- 用户授权与本关目标：用户在 G0 交付后明确“下一步吧，篮球的检测暂时没有加，你先留着位置”。据此进入 G1，先完成人物策略/检测记录，篮球关闭并预留字段与配置；不因原计划要求球模型而再次要求用户提供权重，也不进入 G2。
- 原有问题与为何修改：原 `YoloPersonDetector` 只做人物检测，缺少逐帧框记录与外部 ROI，检测到的裁判/场边人员可能影响旧导播。G1 增加可解释筛选、类别配置与审计，仍不把 person 等同于上场球员。
- 变更文件及作用：见后文；原 RK3588 文件与 G0 原规则本次未再改动。
- Windows 环境信息：Windows 11 家庭版中文版 10.0.26100、Python 3.11.4、torch 2.9.1+cpu、torchvision 0.24.1+cpu、Ultralytics 8.3.225、OpenCV 4.12.0.88（运行时 4.12.0）、NumPy 2.2.6；独立 `.venv`，无新增包，CUDA/NPU 未测。
- 自动测试：初版 **39 passed in 5.91s，0 失败/跳过**；本次仅调整 ROI 配置，重跑相关策略测试 **11 passed in 1.67s**，另做完整真实模型对照。初版三个真实模型集成覆盖 G0 起点和 G1 关闭篮球的导出；合成球类别/框只验证接口。
- 实际运行：指定室内录像 30 秒后至结尾，1818 帧、1818 次真实 YOLO；两路视频完整解码，1818 行 JSONL 独立核对。
- 手工检查：初版六组全幅/导播图；本次另看约 30/60/73.8/90/105.7 秒 ROI 前后对照、源帧 1774 全幅和 60 秒导播。失败例保留，见后文。
- 对 RK3588 的影响：本轮无共享源文件改动；初版旧入口比对、算法 AST 和 180 帧合成回归通过，本次配置调整未重跑这些测试。未访问 RK3588 真机。
- 根目录文档：README、PROJECT_STRUCTURE、NEWCOMER_HANDOFF、STAGE_PROGRESS、CHANGELOG 已同步；两份用户原规范未改。
- 请用户确认：是否验收本轮调整范围的人物筛选/记录与球接口；篮球真实检出继续暂缓，G2 需要另外授权。

## 最新补充验收：ROI 上边界提高到 0.66

用户要求“roi范围的上边界可以再高一点”。原 `detection_policy.rejection_reason` 按人物框底部中心筛选；本次只改 `configs/detection.indoor.example.yaml` 的前两个顶点 y：`0.70 → 0.66`，下边界仍为 0.97。图像 y 从上向下增加，所以 1080p 上边界从 756 移到 712.8 像素，向上约 43 像素。篮球仍关闭，原导播算法与 RK3588 文件未改，未进入 G2。

相同桌面 best.pt、相同室内原视频、同样跳过前 30 秒、CPU/逐帧推理；实际命令（项目根目录 PowerShell）：

```powershell
.\.venv\Scripts\python.exe -X utf8 -m pytest tests\test_detection_policy.py -q
.\.venv\Scripts\python.exe -X utf8 .\run_windows.py --config .\configs\g1.indoor.local.yaml
.\.venv\Scripts\python.exe -X utf8 .\runs\g1_roi_top_066_20261020_173333\compare_roi.py
```

本次 **11 passed in 1.67s，0 失败/跳过**；未重跑其余 28 项，因只有此场景 ROI 参数和文档变化，另以完整真实视频验证。初版 39 项结果保留为历史证据。对照脚本位于本机忽略的审计目录，核对两轮 JSONL、原始候选、独立矩形筛选、源文件/模型 SHA-256 与抽帧，不是新增生产模块。

| 指标 | 原上边界 0.70 | 当前上边界 0.66 |
|---|---|---|
| 完成目录（runs 下） | g1_20261020_171552_8d53d276 | g1_20261020_173342_033fabce |
| 处理 / 真实推理 | 1818 / 1818 | 1818 / 1818 |
| 累计原始人物候选 | 20880 | 20880；逐帧完全一致 |
| 保留 / ROI 排除 | 17068 / 3812 | 17287 / 3593 |
| 源帧 / 时间 | 723–2540 / 30.0101–105.7088 秒 | 完全一致 |
| 球关闭且中心 null | 1818 行 | 1818 行 |

新范围在 179 帧中累计多保留 219 框，原先保留的框全部仍保留。独立计算 0.66–0.97 的矩形脚点筛选与新结果逐帧一致，记录时间严格递增，时间回退 0。该统计是框的累计数量，不是新增 219 名球员或检测准确率。

最新产物目录：`D:\0basketball\project\runs\g1_20261020_173342_033fabce`：

- `overview.mp4`：1920×1080、24.033 FPS、1818 帧、131,644,185 bytes，蓝色上边界已提高。
- `director.mp4`：1280×720、24.033 FPS、1818 帧、42,616,885 bytes。两路均完整解码通过，无音轨。
- `detections.jsonl`：1818 行、5,531,277 bytes；`summary.json` / `run.log` 保存实际策略和完成状态。
- `roi_comparison_frame_1051.jpg`：同一源帧 1774 / 73.7962 秒，上图旧范围、下图新范围，保留框从 6 变为 11；另有输出帧 0/720/1440/1817 对照图。对照图仅为看清边界裁出画面 y=600–1080，不改变模型输入或记录坐标。
- `roi_comparison_validation.json`：独立核验结果；`roi_newly_accepted.json` 列出所有新增保留框与源时间。
- 控制台、策略测试输出、实际命令、核验脚本与视频哈希保存在 `runs/g1_roi_top_066_20261020_173333/`。

目视结论：上边界确实上移；源帧 1774 的远端人物候选被保留，但也包括场边人员和重叠框，不能把新增框全部判为上场球员。近处两个画面底边人物仍因下边界被排除。其他四个抽查点的保留数不变。
这段录像的新旧 `director.mp4` SHA-256 相同（`72f109261f3e223c0e5c7073f8a70d93ef6fc771adf3645da3009dca388c9295`）；本次证实 ROI 与检测记录变化，未产生导播视频变化，约 60 秒裁切偏右的限制仍在。未做全片人工标注或准确率评估。

回退：将室内策略上边界两处 0.66 改回 0.70，即恢复本次对照基线；需撤销整次配置/文档提交时，先保存个人修改再 `git revert <本次提交号>`。模型、录像、历史产物均保留。状态仍为 **READY_FOR_REVIEW**，等待用户确认本轮 G1 调整；球实测暂缓，G2 未开始。

## 初版实现与配置边界（以下保留 0.70 历史基线）

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

初版人物策略：confidence=0.35，最小框高 0.02×全幅高，最大框高 0.5×全幅高，ROI 顶点 `[0,.70],[1,.70],[1,.97],[0,.97]`，按框底部中心筛选；当前上边界已改为 .66，最新结果见上节。该区域仅适配这次画面，可能排除远处/边线/遮挡球员，不能当通用校准。
篮球策略：enabled=false，别名 `sports ball/ball/basketball`、独立置信度初值 0.20、尺寸/ROI 接口保留。初值未做真实球验证。将来启用但权重无球类别会报错，不生成替代位置。
人物保留框送入原 `SmoothTracks → analyze_single_view_frame → update_overlay_director_state`；球接口即便未来启用也不会进入原人物导播。这里没有 ByteTrack、球场映射或训练数据标签。

## 初版模型、视频与真实命令（历史证据）

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

## 初版实际结果与产物（历史证据）

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

## 初版人工核查、剩余限制与回退（历史证据）

1. 30 秒起点原最高置信的近处裁判框（score≈0.8538、底部 y≈1063.85）被 ROI 排除，近处左右场边人物也有紫色排除框；模型没有因此变成身份识别器。
2. 45/60 秒有横向移动和人物聚集，候选包含重复/遮挡的框；没有真实标注，不能量化 ID 切换或漏检率。G1 叠加的是原始检测框，G0 叠加的是旧平滑轨迹框，两者不能混为同一种测量。
3. 约 60 秒青色裁切仍偏右，左侧人物在窗口外；90/105 秒场内裁判仍可能保留。原规则过渡和球员角色识别问题仍在，没有把筛选框数减少写成运镜质量提升。
4. 源帧 1774 的 7 个排除框包含近处场边与远处候选；远处球员脚点接近 ROI 上边界时存在误排风险，需用户结合场景评估；本轮没有声称被排除者全部是观众。
5. 仅这一室内录像和原固定短片，不覆盖所有场馆/多场完整比赛；目视抽查而非人工连续观看全片。

篮球真实检出、篮球参数有效性、去畸变几何、CUDA/NPU 和 RTSP/音频仍未验证。用户暂缓的球能力以后补验；当前只提交调整范围，不将原计划完整 G1 勾选通过。
本轮 Git 分支 `g1/person-detection-ball-slot`，前一 G0 基线 `406b64c`，代码提交 `73327e9`，文档另行提交。仅本地提交，不推送。需要保持 G0 行为时不传检测策略/导出参数即可；需回到确切 G0 版本，可在独立目录检出 `406b64c`，或保存后续修改后 `git revert <本轮提交号>`，不覆盖用户改动、不删除视频/模型/产物。
下一关只有用户明确授权才开始；当前 JSONL 为检测审计，不包含 ByteTrack、轨迹数据集或训练标签。

**请验收本关；确认后我再执行下一关。**
