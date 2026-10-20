# 变更记录

文件作用：记录每次变更原因、影响路径、实际验证、兼容风险和回退方法。代码/配置/验证结论变化后更新，和 STAGE_PROGRESS.md、验收报告保持一致。

## 2026-10-20 — G2 人物 ByteTrack 与 ID 验收

- 原因/授权：G1 ROI 调整交付后用户表示“下一步”，接受调整范围并授权 G2；篮球暂缓持续生效，不进入 G3。
- 路径：新增 `windows_pipeline/tracker.py`、`tracking_records.py`、G2运行/跟踪示例配置、`tests/test_tracker.py`、G2验收/QC文档；更新 config/detector/director_adapter/run/outputs、真实模型测试、依赖和根目录交接文件。RK3588 文件未改。
- 行为：同次YOLO .10候选供ByteTrack两阶段续接，.35人物供独立旧关联对照；G2导播绕过旧关联，不重复推理/再分ID。原框/估计框分列，lost不输出假观测；重复帧拒绝、间隔/场景/新视频重置。篮球disabled/false/null，启用会报错。
- 环境：只向.venv明确安装官方lap==0.5.12，40包锁定，pip check通过；Ultralytics8.3.225 API固定，GPU未测。
- 验证：最终复核 **53 passed in 7.44s，0失败/跳过**，含拒绝 smooth=0 关闭旧对照编号的参数检查；室内30秒后1818次YOLO，三路视频各完整解码1818帧，QC独立核验；目录 `runs/g2_20261020_175136_fc830eed`，ByteTrack18778条匹配（low2430）、旧17287条。另48帧受控实拍拼接在帧24正确触发段重置。详见 `docs/G2_ACCEPTANCE_REPORT.md`。
- 质量/风险：局部P463稳定而旧ID100→101→92；快速移动P218→P425仍断裂，场边P792低置信229帧保留。不同ID数274/160不是人数或MOTA/IDF1，未证明整体更好；新导播画面可能改变。固定dt/直方图转场启发式、复杂变帧率/相机/NPU仍有限制。
- 回退：分支 `g2/bytetrack-person`，代码提交 `5d7eec3`，G1基线 `7f6b9cf`；继续使用g1本地配置、不传tracking_config可回退原关联；完全撤销代码先保存用户修改再 `git revert 5d7eec3`。仅本地提交，不推送、不提交模型/视频/QC产物。
- 状态：G1调整范围ACCEPTED；人物G2 READY_FOR_REVIEW，篮球真实跟踪暂缓，G3–G7 TODO。

## 2026-10-20 — G1 室内 ROI 上边界提高

- 原因：用户要求上边界再高一点；只将 `configs/detection.indoor.example.yaml` 上边界两处 0.70 改为 0.66，1080p 约上移 43 像素，下边界 0.97；同步 README/结构/交接/进度/验收/schema。检测与导播源码、篮球关闭状态、RK3588 入口均未改。
- 验证：相关策略测试 **11 passed in 1.67s**；相同模型/视频 30 秒后 1818 帧逐帧真实推理，两路视频完整解码。新目录 `runs/g1_20261020_173342_033fabce`；逐帧原始候选完全一致（累计 20880），保留 17068 → 17287、ROI 排除 3812 → 3593，179 帧新增累计 219 个保留框；独立矩形判断/模型与视频哈希/1818 行球关闭语义核验通过。审计在 `runs/g1_roi_top_066_20261020_173333/`；初版 39 项全套结果保留，本次未重跑其余 28 项。
- 风险/边界：扩大区域可纳入远端场边人员和重叠框，不把统计当精度/人数。五个时间点对照核查，未全片人工标注；新旧导播 MP4 哈希相同，原裁切限制仍在。未进入 G2，G1 仍 READY_FOR_REVIEW。
- 回退：将上边界两处 0.66 改回 0.70，或保存个人改动后 `git revert <本次提交号>`。仅本地提交，不推送；不提交模型/视频/审计日志，不覆盖历史产物。

## 2026-10-20 — G1 人物检测与篮球接口预留

- 原因/范围：用户“下一步吧，篮球的检测暂时没有加，你先留着位置”；G0 据此接受，G1 调整为人物筛选/记录与球接口关闭，不宣称完整双类别通过，不进入 G2。
- 路径：新增 `windows_pipeline/detection_policy.py`、`detection_records.py`、三份 G1 示例配置、`tests/test_detection_policy.py` 与 G1 报告/schema；更新 detector/config/run/outputs/contracts 和根目录交接文档。原 RK3588 文件/算法本轮未改。
- 行为：一次真实推理，按真实 names 映射人/球；各类独立阈值/尺寸/ROI；保留原始排除框及原因；可选检测 JSONL 区分真观测与复用；篮球关闭时 valid=false、中心 null。G0 默认人物阈值与无 ROI 行为保留。
- 验证：**39 passed in 5.91s，0 失败/跳过**；室内视频 30 秒后1818帧逐帧推理，20880累计候选、17068保留、3812因ROI排除；两份MP4各完整解码1818帧，JSONL1818行独立计数一致。详情 `docs/G1_ACCEPTANCE_REPORT.md`，完成目录 `runs/g1_20261020_171552_8d53d276`。
- 风险：ROI 不识别身份，近边线/遮挡可能误排，场内裁判可能保留；原导播约60秒裁切偏右仍在。球参数/真实双类别、几何去畸变、GPU/NPU未验。真实框数不是准确率。
- 回退：本地分支 `g1/person-detection-ball-slot`，代码提交 `73327e9`，G0基线 `406b64c`；不传策略/导出保持G0默认，需要完全回退时在独立目录检出G0或保存修改后revert本轮提交。不删除权重/录像，不推送。
- 状态：G1调整范围READY_FOR_REVIEW；球实测按用户要求暂缓，G2未开始。

## 2026-10-20 — G0 补充室内录像与片段起点

- 原因：用户提供另一场比赛录屏，要求前 30 秒不参与验证。
- 影响：`windows_pipeline/config.py` 新增 `start_seconds` / `--start-seconds`；`run.py` 按实际源时间跳过前段，首个选中帧立即推理；示例 YAML、测试、README/结构/交接/进度/验收文档同步。`g0_run_v1` 增加可选源起点/跳过帧审计字段，旧字段含义不变。
- 验证：**27 passed，0 失败/跳过**，含真实模型起点回归；新录像 30.0101–105.7088 秒全部处理，1818 帧、606 次真实 YOLO，两份 MP4 完整解码通过。实际命令/日志/输出在 `docs/G0_ADDITIONAL_VIDEO_VALIDATION.md` 与 `runs/g0_20261020_165817_c5a8d96f`。
- 兼容风险：默认起点 0 行为保持；非零起点重置原规则状态，不预热前 30 秒，初始化阶段可裁掉边缘人物。原录屏 FPS 元数据与 PTS 有小差异，输出 CFR/无音轨，不保证精确音画时长。裁判/场边人物也有检测框；约 60 秒窗口偏右等失败例已记录。
- 回退：仅本地提交，不改 RK3588 共享文件/入口、模型或原录像；若要从头测试设 `--start-seconds 0`，需要撤销新增参数时先保存个人修改再 `git revert <本次提交号>`。测试视频、日志和产物仍被忽略，不推送。
- 状态：G0 READY_FOR_REVIEW，未进入 G1。

## 2026-10-20 — G0 Windows 迁移

- 原因：原工程将 RKNN、V4L2、硬件编码、音频和规则导播绑定，Windows 不能直接运行；当前工作目录原先没有源码或 Git。
- 基线：用户指定上游 `https://github.com/zzzokay/camera_150_with_face`，提交 `5bd9c5a437536706f51106a5e86fbb2a7ec46906`。建立本地 `g0/windows-migration`；稀疏检出应用源码，保留上游其他资产，不推送。
- 影响路径：新增 `camera_150/windows_pipeline/`、`run_windows.py`、`check_windows_environment.py`、`check_windows_camera.py`、`configs/windows.example.yaml`、`requirements-windows*`、`pytest.ini`、`tests/`、`.gitignore` 与根目录交接文档、兼容矩阵和验收报告。README 增加 Windows 导航。
- 共享模块：`single_rknn_base.py` 仅推迟 RKNN 导入；`predict1_director.py` 支持包导入并推迟旧调试绘图依赖。`predict1_weighted.py`、所有 RKNN 主入口、技术台/检录/音频策略未修改。四个纯渲染/转换函数独立到 Windows 模块，测试逐项约束和原函数体一致。
- 新行为：本地真实 YOLO 人物框进入原 SmoothTracks 和规则，顺序读帧，显式镜头处理模式，保存干净导播和全幅调试视频，区分新推理/复用框；每次独立目录，关闭后逐帧核验输出，失败明确报告。
- 相机时间：Windows Python 3.11 的普通 monotonic 在缓冲快速读取时可产生重复时间，改用高精度 perf_counter 记录收帧时刻；不是相机曝光时间。
- 验证：最终隔离 CPU 环境 **22 passed，0 失败/跳过**，含真实 YOLO 集成；真实篮球前 300 帧执行 100 次 YOLO，两路 MP4 各完整解码 300 帧，见 `runs/g0_20261020_144146_be04f4bc`。跨目录中文输出、0/1 号摄像头各读 3 帧及窗口可见 API 已测，详细命令/证据见 `docs/G0_ACCEPTANCE_REPORT.md`。
- 结果边界：权重仅 person；初始居中窗口未包含左侧人物，末帧有人物重复框和围栏疑似误检。保留原规则与阈值，记录失败案例，不把累计候选框数当准确率；1 号摄像头实际约 1 秒读一帧，未验证实时 30 FPS。
- 环境：独立 `.venv`，Python 3.11.4 / torch 2.9.1+cpu / Ultralytics 8.3.225；完整 39 包锁定在 `requirements-windows.lock.txt`。官方 PyPI wheel 校验后安装，`pip check` 通过；未改全局源。
- 兼容风险：Windows 与 RKNN 模型输出/NMS 可能不同；原规则参数按处理帧；mp4v 不是 H.264；VFR/相机实时录制时长、设备 GUI、音频 RTSP、NPU 真机未验收。详见兼容矩阵。
- 回退：RK3588 主入口和原参数保留；可直接按原平台部署，或在独立目录检出原基线。后续如需撤销本轮已提交变更，先保存自己的修改后使用 `git revert <G0提交号>`，不要 hard reset。`.venv`、模型、视频及证据均留在本机且忽略，不由回退脚本删除。
- 提交：代码 `3415582`；交接/实测证据的文档提交由 `git log -1` 查看。全部仅在本地分支，未推送。
- 范围：仅 G0；不修改/加载 `best_sac`，不实施双类别质量改造、ByteTrack、训练数据/TCN/RL。
- 关卡状态：READY_FOR_REVIEW，等待用户验收，尚未 ACCEPTED。
