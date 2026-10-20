# Windows G0/G1/G2 新人交接

文件作用：让新 Agent 或新人无需原作者口头解释就能复现当前阶段。每次环境、命令、模型、接口或验收结论变化后更新；先读本文，再查 PROJECT_STRUCTURE.md、平台兼容矩阵和 G0 验收报告。

## 当前边界与真实性

G0 和 G1 调整范围已由用户“下一步”授权继续。本轮 G2 做人物 ByteTrack，篮球接口继续关闭；G3–G7 未开始，完整双类别检出能力未验收。当前人物跟踪待用户验收，质量限制见最新报告。
原系统用 RK3588 NPU 检测人物，再根据人物分布和热点平滑移动裁切窗口；文件与函数位置见下文。
Windows 检测使用真实 Ultralytics YOLO。G2 使用 ByteTrack 关联并保留原热点/镜头规则，旧距离关联用于独立对照和 G0/G1 回退。
首轮实测见 [G0_ACCEPTANCE_REPORT.md](docs/G0_ACCEPTANCE_REPORT.md)，最新人物检测见 [G1_ACCEPTANCE_REPORT.md](docs/G1_ACCEPTANCE_REPORT.md)，不得用组件测试或文件存在替代实际推理成功。
最新人物跟踪见 [G2_ACCEPTANCE_REPORT.md](docs/G2_ACCEPTANCE_REPORT.md)：**53 项通过**，真实室内片段 1818 次 YOLO、三路视频完整解码、跟踪 CSV/JSONL 独立核验；另做 48 帧受控实拍切换测试。临时 ID 仍有碎片，不宣称整体优于旧方案。
首轮 `.venv` **22 项测试通过、0 失败/跳过**；指定录像前 300 帧（10 秒）完成 100 次真实 YOLO 推理，两路输出各完整解码 300 帧。G0 补充室内录像后新增片段起点参数，当时 **27 项测试通过**，该录像 30 秒后完整处理 1818 帧、606 次真实推理；见 [补充验证报告](docs/G0_ADDITIONAL_VIDEO_VALIDATION.md)。
实际权重类别只有 `{0: 'person'}`，没有篮球类别；按用户要求暂不做篮球实测。G1 初版 **39 项测试通过**；本次 ROI 调整重跑相关 **11 项通过**，室内录像 30 秒后 **1818 帧/1818 次真实推理**、两路完整解码、1818 行检测记录均已核验，详见 [G1 验收报告](docs/G1_ACCEPTANCE_REPORT.md)。

| 能力 | 证据类型与边界 |
|---|---|
| 原算法和旧入口保持 | 静态比对及合成 180 帧序列回归；不是 RK3588 真机测试 |
| 中文/空格路径、MP4/AVI、时间戳、标定尺寸检查 | 真实 Windows 上的组件测试；彩条是合成输入，不能证明篮球检测准确率 |
| YOLO + 原规则 + 保存 | 使用用户确认的真实权重/篮球录像；以验收报告中实际运行数据为准 |
| 摄像头 dshow、OpenCV 窗口 | 本机 0/1 号设备各读 3 帧、收帧时间递增、窗口 API 可见；未保存画面，外观由用户确认；msmf 未测 |
| 音频/RTSP/完整技术台/人脸检录 | 旧源码保留，未移植到新入口，当前视频输出无音轨 |
| 人物 ROI/尺寸筛选、检测 JSONL | G1 已用室内录像实测；ROI 不等于球员身份分类 |
| 篮球接口、双类别质量 | 类别/参数/无球字段已留接口，篮球关闭，真实球模型有效性未测 |
| 人物 ByteTrack 与旧 ID 对照 | G2 实测，原框/状态框分离；存在断轨和场边目标，不等于实名/号码 |
| G3 可训练轨迹/重放、Homography、TCN | 未实施；G2 CSV 仅为本关 ID 验收，需逐关批准 |

## 当前 G2 最快上手

以前 `SmoothTracks.update` 按脚点最近距离续接编号，交叉时可能配错人。**ByteTrack（多目标跟踪算法）** 先用高置信框匹配，剩余目标再用低置信框续接；结合运动预测，仍不看球衣外观/真实身份。原 `.35` 检测门槛会丢掉这些弱框，因此 G2 将同一次 YOLO 的推理门槛设为 `.10`，再按 `.35/.10` 分阶段筛选，ROI 仍为 .66–.97。

```powershell
Set-Location 'D:\0basketball\project'
.\.venv\Scripts\python.exe -m pip install --index-url https://pypi.org/simple --only-binary=:all: lap==0.5.12
.\.venv\Scripts\python.exe -X utf8 .\run_windows.py --config .\configs\g2.indoor.local.yaml
```

本机配置已填同一室内视频和桌面 best.pt，源前30秒不参与处理。新机器复制 `configs/g2.indoor.example.yaml` 为 `.local.yaml`，填写自己的真实 source/weights；跟踪配置指向 `tracking.example.yaml`。全新环境按下方依赖安装步骤准备，当前完整锁定40包。`detect_interval` 必须为1，缺 lap/错误库版本/篮球启用会明确报错，不自动下载新权重。
数据流：视频/预处理 → 一次 YOLO → 人物高低候选 → `PersonByteTracker.update` → `LegacyDirector.process(tracked_persons=...)` 跳过旧关联 → 原热点/运镜 → 保存。相同高置信观测另供 `SmoothTracksBaseline` 做独立对照；不会用旧编号再次修改 ByteTrack 编号。

最新实际目录 `D:\0basketball\project\runs\g2_20261020_175136_fc830eed`：先看 `tracking_comparison.mp4`（左旧/右新），再看 `overview.mp4`（全幅 ByteTrack ID）和干净 `director.mp4`。三路各1818帧、24.033 FPS、无音轨。青色框均为当前 ByteTrack 导播范围；左图只对照 ID，不是另一套导播。右侧 H/L 表示高/低阶段；左侧 L 是 legacy_distance。
`bytetrack_qc.csv` 为18778条确认观测，`smoothtracks_qc.csv` 为17287条；逐帧 QC 在 `tracking_audit.jsonl`。例如源帧723/30.0101秒，segment=1、person、track_id=1、confidence≈.776394、原框≈[147.1211,806.7466,214.2195,971.2006]，raw_full_frame_px；球仍 disabled/false/null。原框是观测，另存的 track框是滤波估计，不能当成每个像素都是真实测量。

怎么判断：先核对 summary 的 COMPLETED、inference_calls=1818、三个 outputs.decoded_frames=1818；再确认 CSV ID 为正且同帧不重复、源时间和原图对应。`tracking_validation.json` 已独立核查本次记录，带 ID 不等于身份正确。`case_lateral_movement.jpg` 中局部 P463 稳定，`case_moving_ball_handler.jpg` 中 P218→P425 断裂，`case_long_low_sideline.jpg` 中场边 P792 持续保留；不能只看正例。
本轮不同 ID 数 ByteTrack274/旧160，不能声称全场更稳定。没有人工真值，不报告 MOTA/IDF1。若不通过，先查检测/ROI，再看高低门槛/源 FPS/重置，最后查遮挡关联；具体语义见 [G2_TRACKING_QC.md](docs/G2_TRACKING_QC.md)。
与下一关关系：G3 经批准后消费 `TrackedPerson` 并定义可训练轨迹/重放规范；当前仅 QC，不生成速度/标签，不提前做 G3。回退可直接运行原 `g1.indoor.local.yaml`（无 tracking_config）；每视频新建跟踪会话，重复帧拒绝，复杂变帧率/转场仍有边界。

## G1 最快上手（保留对照与回退）

原 G0 `YoloPersonDetector` 返回人物框，没有逐帧审计。G1 用 `YoloDetector` 读取真实类别表，只做一次推理，再按各类阈值、相对尺寸和 ROI 筛选；人物送入原导播，排除候选保留原因，球关闭时不产生位置。旧类保留为兼容构造器。
**ROI（感兴趣区域）** 是画面上允许保留目标的位置。本次示例按人物框底部中心检查 y 比例 0.66–0.97；按用户要求将上边界从 0.70 提高到 0.66，在 1080p 中约向上移动 43 像素。图像 y 越小越靠上，因此是减小数值来扩大远端范围；仍无法辨别场内裁判/场边人员，也可能排除靠近边线的人，不能推广成所有视频通用配置。

现有本机配置已经实际执行：

```powershell
Set-Location 'D:\0basketball\project'
.\.venv\Scripts\python.exe -X utf8 .\run_windows.py --config .\configs\g1.indoor.local.yaml
```

本机配置复制自 `configs/g1.indoor.example.yaml`，仅填入用户指定室内视频和桌面 best.pt 的绝对路径；新机器先复制为 `.local.yaml` 并填写自己的真实文件，所有 YAML 相对路径仍以配置所在目录解析。`detection_policy: detection.indoor.example.yaml` 引用本次镜头专用策略；通用无 ROI 策略是 `detection.example.yaml`。
G1 历史结果：`D:\0basketball\project\runs\g1_20261020_173342_033fabce`。先看 `overview.mp4`：绿框保留、紫框排除并注明原因、蓝框 ROI、青框原规则裁切，左上明确 `ball: DISABLED`。G1 绿框为当前真实检测，和 G0 的平滑临时 ID 框含义不同。`director.mp4` 仍是干净 720p；两路均无音轨。`roi_comparison_frame_1051.jpg` 展示源帧 1774 的前后范围：远端新增保留框也含场边/重叠候选；本段新旧导播视频哈希相同，不代表运镜改善。

`detections.jsonl` 每帧一行，保存全幅框、类别、置信度、时间和排除原因；本轮每帧真实推理，不复制旧框当新检测。例：首个保留人物 confidence≈0.776394、xyxy≈[147.1211,806.7466,214.2195,971.2006]，源帧 723 / 30.0101 秒，`raw_full_frame_px`；同帧 `ball_enabled=false`、`ball_valid=false`、`ball_centers_full_frame_px=null`。实际原精度在文件中。
最新统计为 20880 累计候选、17287 保留、3593 ROI 排除；旧上边界 0.70 时保留 17068 / 排除 3812。逐帧原始候选一致，新范围在 179 帧多保留累计 219 框；不是人数或准确率，0 个完全无人物的推理帧也不证明每名球员都被检测。
本次相关测试 `.\.venv\Scripts\python.exe -X utf8 -m pytest tests\test_detection_policy.py -q` 为 **11 passed in 1.67s**；完整 1818 次真实推理、两路解码、逐行对照核验通过。初版 39 项是历史全套结果，本次未重跑全部，详见 [验收报告最新补充](docs/G1_ACCEPTANCE_REPORT.md)。恢复旧范围可将策略上边界两处 0.66 改回 0.70。

完整字段/单位/复用帧/球接口接入步骤见 [G1_DETECTION_SCHEMA.md](docs/G1_DETECTION_SCHEMA.md)。下次获准接入真实篮球权重时，可在 G1 检测路径改本地策略 `ball.enabled: true` 并指向含球类别的权重；缺类别会报错，不能仅改开关就认为模型会找球。当前 G2 明确拒绝启用篮球，需另行实现并验收球跟踪。球参数 0.20 等仅是待验证初值。
本节 G1 JSONL 仍是检测审计，没有轨迹 ID、速度或训练标签；G2 已在独立 QC 中保存关联结果。G1 调整范围已接受，本轮等待 G2 验收，G3 数据规范/重放不提前实施。

## 从全新 Windows 建立环境

安装 Python 3.11（64 位，安装时启用 Python Launcher），安装 Git。以下是在项目根目录执行的 **PowerShell** 命令。
现有工作目录是 `D:\0basketball\project`；新机器把这行替换为自己的工程目录。
不需要激活环境，也不需要修改 PowerShell 执行策略；一直显式调用 `.venv` 里的 Python。

```powershell
Set-Location 'D:\0basketball\project'
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --index-url https://pypi.org/simple pip==25.3
.\.venv\Scripts\python.exe -m pip install --index-url https://download.pytorch.org/whl/cpu --extra-index-url https://pypi.org/simple torch==2.9.1+cpu torchvision==0.24.1+cpu
.\.venv\Scripts\python.exe -m pip install --index-url https://pypi.org/simple -r .\requirements-windows.txt
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -X utf8 .\check_windows_environment.py --model-dir .\best_sac
```

首次安装会下载 CPU PyTorch 等包，约数百 MB。显式源只作用于这些命令，不修改系统 pip 配置。
旧 pip 23.1.2 在仅使用 CPU 索引解析 `typing-extensions` 时出现过元数据问题；本机默认清华镜像还返回过 403，故上面先从官方 PyPI 固定安装 pip 25.3，并为 CPU wheel 命令同时提供官方 PyPI 依赖源。
最终完整依赖版本锁定在 `requirements-windows.lock.txt`；CPU 环境可按相同两源执行 `pip install -r requirements-windows.lock.txt`，其中 `+cpu` wheel 需要 PyTorch CPU 索引。直接依赖清单用于理解所需组件，lock 用于重建实测环境。

GPU 是可选项：本机虽有 RTX 4060 Laptop GPU，本轮安装的是 CPU wheel，并用 `--device cpu` 验证。
**CUDA（NVIDIA GPU 计算运行时）** 需要驱动与 wheel 匹配，不能仅因为机器有显卡就把 `device` 写成 `cuda`。
如之后需要 GPU，可在另一虚拟环境按 PyTorch 官方 https://pytorch.org/get-started/locally/ 选择相匹配的 torch/torchvision CUDA wheel，再装同一直接依赖文件并运行 `torch.cuda.is_available()`；这条 GPU 路径本轮未测试，不能标为已支持加速。

## 模型与视频准备

`best_sac/` 中的 `policy.pth`、`actor.optimizer.pth` 等是强化学习策略/优化器文件，不能当作 YOLO。仅检查过文件清单，没有加载或修改。
用户已确认本轮使用：

```text
YOLO：C:\Users\zenghuiting\Desktop\rk_driceter\best.pt
录像：C:\Users\zenghuiting\Desktop\rk_driceter\usb3_undistorted_20260706_111148_325.mp4
```

该录像已实际读取：1920×1080、30 FPS、4236 帧，约 141.2 秒；首帧是室外篮球场和两名人员。
`--undistort already` 表示按用户确认和文件来源把它当作已去畸变输入，不会再 remap。尚未重新验证残余畸变。
权重/视频可留在原位置，不必拷贝，更不应提交 Git。新机器将命令中的两个绝对路径替换为自己的真实文件。
`YoloPersonDetector` 从实际权重读取 `names`，按 `person_aliases` 查人物 ID；不是默认类别 0。最终真实类别表、文件 SHA-256（内容指纹）见验收报告与每次运行的 `summary.json`。
G0 只把人物传入原规则，即使权重有其他类别也不代表已完成 G1。只接受本地 `.pt`；不存在就报错，不自动下载示例模型。ONNX 目前没有适配。

## 最快上手：真实模型和视频

以下只处理前 300 帧（10 秒），用 CPU、每 3 帧做一次推理，输出仍是 30 FPS。CPU 推理慢会让处理花更久，不会把输出 10 秒自动压成 3 秒。

```powershell
Set-Location 'D:\0basketball\project'
.\.venv\Scripts\python.exe -X utf8 .\run_windows.py `
  --source 'C:\Users\zenghuiting\Desktop\rk_driceter\usb3_undistorted_20260706_111148_325.mp4' `
  --weights 'C:\Users\zenghuiting\Desktop\rk_driceter\best.pt' `
  --undistort already --device cpu --detect-interval 3 --max-frames 300
```

成功会打印真实模型类别、处理帧数和“完整解码核验通过”，并生成 `runs/g0_日期_时间_随机后缀/`：

- `director.mp4`：1280×720 的干净规则导播裁切画面，没有检测框和音轨。
- `overview.mp4`：1920×1080 全幅调试画面，人物框、临时编号和青色裁切窗口；绿色标记新推理，橙色标记复用结果。
- `summary.json`：`status=COMPLETED`、`processed_frames=300`、`inference_calls=100`、`frames_reusing_detections=200`，两份视频逐帧解码均为 300 帧。
- `run.log`：本次运行日志。模型框/推理异常会报错并留下 `FAILED` 报告，不能当成功。

上面三个计数是此命令的预期；真实检测次数、实际耗时与产物路径必须以本轮报告为准，不能写成模型准确率。
本次已生成的结果位于 `D:\0basketball\project\runs\g0_20261020_144146_be04f4bc`：可先查看其中 `review_contact_sheet.jpg`，再播放 `director.mp4` 和 `overview.mp4`。
本次 100 次真实推理共输出 231 个累计人物候选框，包含重复/误检，不代表 231 个人。首帧居中裁切暂排除左侧人物；第 149、299 帧窗口已移向左侧，末帧仍有重复人物框和围栏疑似误检；这些质量局限保留在报告中。
双击视频或在 Codex 中打开核查：调试图框应落在人身上，裁切框应逐步朝人物活动区移动，导播图应对应青框覆盖的区域。规则缓慢过渡是原设计，不能只看第一帧就判断没有动作。

完整处理原文件时将 `--max-frames 300` 改成 `--max-frames 0`。`--preview` 开启两个 OpenCV 窗口，按 q/Esc 停止；本轮默认无窗口，交互预览需用户实机确认。
`mp4v` 是 MPEG-4 Part 2，并不是 H.264；若本机播放器打不开，可以显式添加 `--codec MJPG` 输出 AVI。两种编码器的中文路径编解码均有组件测试；无需安装外部 FFmpeg。

相机打开/读帧检查命令（只显示短暂窗口，不保存画面）：

```powershell
.\.venv\Scripts\python.exe -X utf8 .\check_windows_camera.py --camera 0 --preview
```

本机实际检测到 `EV Camera Device`、`USB2.0 HD UVC WebCam`。0 号请求 640×360 后实际返回 640×480，1 号返回 640×360，说明相机可能不接受请求尺寸。两者均能打开并读帧，报告 FPS 约 30；1 号的实际读帧间隔约 1 秒，不能据设备报告的 FPS 宣称实时 30 FPS。完整摄像头 YOLO/保存与长时间实时性未在本轮验收。

## 补充室内录像：跳过前 30 秒

新增 `--start-seconds 30` 只用于文件，按源时间顺序解码跳过前段；不另存压缩输入，源帧号/时间保持不变，首个选中帧马上推理。`max_frames` 只计选中后的帧，0 表示处理剩余全部。默认 `start_seconds=0` 保持从头运行。
输入与首轮相机不同，使用 `--undistort none`，不能把另一相机的 NPZ 套过来。输出坐标是 `raw_full_frame_px`，并非去畸变或球场米制坐标。
本机已核对下面文件选择唯一匹配用户给定的长中文名；同一模型/CLI 参数的实际运行见补充报告，复现可执行：

```powershell
Set-Location 'D:\0basketball\project'
$g0ReplayVideos = @(Get-ChildItem -LiteralPath .\video -Filter '2026-04-15*16-53-01.mp4' -File)
if ($g0ReplayVideos.Count -ne 1) { throw '必须唯一匹配用户指定的比赛录像' }
.\.venv\Scripts\python.exe -X utf8 .\run_windows.py `
  --source $g0ReplayVideos[0].FullName `
  --weights 'C:\Users\zenghuiting\Desktop\rk_driceter\best.pt' `
  --undistort none --device cpu --detect-interval 3 --start-seconds 30 --max-frames 0
```

实际从源帧 723（30.0101 秒）处理到 2540（105.7088 秒），共 1818 帧。结果：`D:\0basketball\project\runs\g0_20261020_165817_c5a8d96f`；两份 MP4 都能完整解码，约 75.646 秒，无音轨。
先查看 `review_contact_sheet_1.jpg` / `_2.jpg` 再播放两路视频。调试图里裁判/场边人员同样有 person 框；约 60 秒窗口偏右，左侧数人被裁出，不能把工程运行成功当作运镜质量已合格。源报告 FPS 与实际 PTS 有小差异，输出为恒定帧率，不保证音画精确同步。

## 配置文件和任意当前目录

复制 `configs/windows.example.yaml` 为 Git 忽略的 `configs/windows.local.yaml`，只在本地填写模型/视频路径。
YAML 内相对路径以 YAML 文件所在目录解析，CLI 相对路径以调用者目录解析。
从其他目录启动时用绝对入口路径和绝对配置路径。本机已在 `D:\0basketball` 执行以下命令，使用本地配置中的上述真实文件，覆盖为 3 帧：

```powershell
& 'D:\0basketball\project\.venv\Scripts\python.exe' -X utf8 `
  'D:\0basketball\project\run_windows.py' `
  --config 'D:\0basketball\project\configs\windows.local.yaml' --max-frames 3
```

成功输出 `runs/cross_directory 中文/g0_20261020_144312_2c6c6e8d`，真实推理 1 次，两路各完整解码 3 帧；本机 YAML 的输出设置是 `output_dir: ../runs/cross_directory 中文`。新机器替换工程绝对目录，并先填写自己的 `.local.yaml`。
相机模式同样是待实机验证的接口示例：不用文件配置，指定 `--camera 0 --backend dshow --weights '<YOLO绝对路径.pt>' --undistort none --max-frames 90 --preview`。
相机编号/实际 FPS/分辨率须现场核对；如果使用 `calibration`，还必须提供同尺寸、同相机的 `--calib-file`。

## 调用顺序和旧/新接口

1. `run_windows.main()` → `load_config()`：读配置，解析中文路径，默认 CPU。
2. `VideoSource.read()`：文件逐帧读取，给源帧号与秒；避免旧摄像头“最新帧”方式在离线时丢/重复帧。
3. `FramePreprocessor.apply()`：按 none/already/calibration 处理；标定尺寸不符直接报错，避免偷偷改变坐标空间。
4. `YoloDetector.detect()`：真实 YOLO 读取模型类别名，按策略输出全幅人物/可选球框；G0 兼容类名 `YoloPersonDetector` 保留。仅人物进入旧导播，G1 可另写检测审计。
5. G0/G1 `LegacyDirector.process()`：转换成原整数框 → 原 `results_to_single_detections()` → 原 `SmoothTracks.update()` → 原热点/运镜/720p 纯裁切。G2 先由独立 ByteTrack 关联，再传 tracked_persons 直接进入原热点/运镜，跳过旧关联；另存独立旧算法 ID 对照。
6. `SavedVideo.write()`：保存干净导播和全幅调试画面；关闭后 `verify_video()` 真正解码所有输出帧，检查尺寸和帧数。

原规则的焦点、速度和平滑量按**处理帧**更新；本轮保留参数以便迁移对照，没有把规则的像素/帧变成球场米/秒。
原 `SmoothTracks` 已经有临时编号，并非“原来没有跟踪”；G2 新支路已升级 ByteTrack，旧类保留原样，当前真实测试仍有换号/断轨。
默认不读取技术台；如配置 `game_state`，会只读 JSON 调用原比赛状态策略，完整技术台联动未验收。

## 输入输出和常见机器学习概念

输入是完整 BGR 图像，例如 `[1080,1920,3]`（高、宽、三个颜色通道），不是预先剪成 720p 的导播画面。
输出的一条真实人物框包含 `confidence`（模型对该框的把握）、`bbox_xyxy`（左上和右下像素）、`model_class_id`、`observed=true`；**准确的本轮数值**见验收报告中的 `first_detection`，此处不编造示例观测。
导播输出 `[720,1280,3]` 的视频帧；全幅坐标与裁切后坐标不能混用。

- **YOLO（目标检测模型）**：在每张图中找出人物等目标及其框；它本身不是运镜策略。
- **Track ID（轨迹编号）**：跟踪器在同一视频段中分配的临时编号，不等于球员姓名/号码；人脸检录身份是另外一层，G2 还需联合 segment_id 区分重置后的同号。
- **ROI（感兴趣区域）**：原规则按位置优先保留球场人物的启发式区域，不保证完全排除裁判/观众。
- **热点（hotspot）**：本项目旧规则估计的横向活动中心，单位像素；不是完整二维高斯热点，更不是战术名称。
- **去畸变（undistortion）**：校正镜头造成的弯曲；**Homography（单应性变换）** 则将地面像素投到球场平面，本轮未做。
- **Tensor Shape（张量维度）**：数据数组每个轴的长度；后续 TCN 才会使用 `[B,15,D]`，表示 B 段、每段 15 个历史时间点、每点 D 个数值。
- **TCN（时间卷积网络）**：学习一段时间内运动变化的模型。G0 只准备可运行的视频/观测边界，没有 TCN、训练或未来标签。

原始视频建议 `data/input/`，本地 YOLO 建议 `models/`；G2 验收 CSV/JSONL 已写到本次 runs 目录，G3 可训练轨迹/重放、球场标定、特征与 TCN 权重尚未产生。`summary.json` 是运行证据，不能拿首条框或规则 `predicted_hotspot_x` 当训练真值。

## 验证与五个常见问题

自动化测试：

```powershell
Set-Location 'D:\0basketball\project'
$env:G0_TEST_WEIGHTS = 'C:\Users\zenghuiting\Desktop\rk_driceter\best.pt'
$env:G0_TEST_VIDEO = 'C:\Users\zenghuiting\Desktop\rk_driceter\usb3_undistorted_20260706_111148_325.mp4'
.\.venv\Scripts\python.exe -X utf8 -m pytest -q
```

真实模型测试对每个起点各处理 12 帧，要求首个选中帧立即真实推理、确实检出人物且两路视频都能解码；没有设置这两个变量时会 skip，必须报告未运行，不能算带模型测试通过。

| 问题 | 排查顺序与命令 |
|---|---|
| 找不到 YOLO / 错把 SAC 当权重 | `Get-ChildItem -LiteralPath '.\best_sac'`；`Test-Path -LiteralPath 'C:\Users\zenghuiting\Desktop\rk_driceter\best.pt'`；核对 `.pt` 和错误日志，不把 `.pth` 改后缀冒充 |
| 缺包 / Python 用错 | `.\.venv\Scripts\python.exe -m pip check`；运行环境检查脚本，核对 executable 位于 `.venv`，重新按上方命令安装；不要使用原 Linux face_env |
| 能启动但没框 | 查看本次 `summary.json` 的真实 names、人物 ID、真实观测数；确认输入是广角原视频；G0 原规则还用 0.35 人物阈值，不能盲目降低阈值就当效果变好 |
| 视频/标定尺寸不匹配 | `.\.venv\Scripts\python.exe -X utf8 .\run_windows.py --help`；已矫正视频用 already；原始帧用匹配 NPZ 的 calibration，不要重复矫正或静默 resize |
| 保存失败/播放异常/中文乱码 | 查看 `run.log` 和 `outputs` 解码统计；尝试显式 `--codec MJPG`；命令加 `-X utf8`；FPS 无效须显式 `--fps`；只有文件存在不算成功 |

排查原则：先确认路径和环境，再确认帧/尺寸/时间，再确认真实类别和框，最后检查规则裁切和编码。没有人工框真值，本轮不报告 mAP、MOTA、IDF1 或“准确率 100%”。

## 交接、回退与下一关

当前产物、测试输出与真实记录见 [G2 验收报告](docs/G2_ACCEPTANCE_REPORT.md)；检测/迁移历史保留在 G1/G0 报告，当前状态见 [STAGE_PROGRESS.md](STAGE_PROGRESS.md)。
工作基线与修改都在本地 Git，未推送。需要回到原工程时可在另一个独立目录检出原基线，或在干净状态下切回原基线；不要用 hard reset 覆盖自己后续修改。
新版 RK3588 入口仍使用原参数和 `.rknn`。共享算法回归已覆盖导入/规则逻辑，不等于 RK3588 NPU 真机已验证。
用户已接受 G1 调整范围并授权 G2；篮球实测暂缓并预留接口。当前等待人物 G2 验收，G3–G7 仍需后续明确批准。
