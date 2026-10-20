# Windows G0 新人交接

文件作用：让新 Agent 或新人无需原作者口头解释就能复现当前阶段。每次环境、命令、模型、接口或验收结论变化后更新；先读本文，再查 PROJECT_STRUCTURE.md、平台兼容矩阵和 G0 验收报告。

## 当前边界与真实性

本轮只做 G0 Windows 迁移，停在用户验收之前。G1–G7 均未开始。
原系统用 RK3588 NPU 检测人物，再根据人物分布和热点平滑移动裁切窗口；文件与函数位置见下文。
本轮将 Windows 检测换成真实 Ultralytics YOLO，保留原距离关联、热点、镜头规则。
最终实测能力、精确统计及尚未验收项见 [G0_ACCEPTANCE_REPORT.md](docs/G0_ACCEPTANCE_REPORT.md)，不得用组件测试或文件存在替代实际推理成功。
本机最终 `.venv` **22 项测试通过、0 失败/跳过**；指定录像前 300 帧（10 秒）完成 100 次真实 YOLO 推理，两路输出各完整解码 300 帧。
实际权重类别只有 `{0: 'person'}`，没有篮球类别；本关不验收双类别检测。

| 能力 | 证据类型与边界 |
|---|---|
| 原算法和旧入口保持 | 静态比对及合成 180 帧序列回归；不是 RK3588 真机测试 |
| 中文/空格路径、MP4/AVI、时间戳、标定尺寸检查 | 真实 Windows 上的组件测试；彩条是合成输入，不能证明篮球检测准确率 |
| YOLO + 原规则 + 保存 | 使用用户确认的真实权重/篮球录像；以验收报告中实际运行数据为准 |
| 摄像头 dshow、OpenCV 窗口 | 本机 0/1 号设备各读 3 帧、收帧时间递增、窗口 API 可见；未保存画面，外观由用户确认；msmf 未测 |
| 音频/RTSP/完整技术台/人脸检录 | 旧源码保留，未移植到新入口，当前视频输出无音轨 |
| 双类别检测质量、ByteTrack、轨迹数据、Homography、TCN | 未实施，需后续逐关批准 |

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
4. `YoloPersonDetector.detect()`：真实 YOLO 输出全幅人物框，读取模型类别名。
5. `LegacyDirector.process()`：转换成原整数框 → 原 `results_to_single_detections()` → 原 `SmoothTracks.update()` → 原 `analyze_single_view_frame()` → 原 `update_overlay_director_state()` → 原 720p 纯裁切函数。
6. `SavedVideo.write()`：保存干净导播和全幅调试画面；关闭后 `verify_video()` 真正解码所有输出帧，检查尺寸和帧数。

原规则的焦点、速度和平滑量按**处理帧**更新；本轮保留参数以便迁移对照，没有把规则的像素/帧变成球场米/秒。
原 `SmoothTracks` 已经有临时编号，并非“原来没有跟踪”；多人交叉时的关联可靠性本轮不升级。
默认不读取技术台；如配置 `game_state`，会只读 JSON 调用原比赛状态策略，完整技术台联动未验收。

## 输入输出和常见机器学习概念

输入是完整 BGR 图像，例如 `[1080,1920,3]`（高、宽、三个颜色通道），不是预先剪成 720p 的导播画面。
输出的一条真实人物框包含 `confidence`（模型对该框的把握）、`bbox_xyxy`（左上和右下像素）、`model_class_id`、`observed=true`；**准确的本轮数值**见验收报告中的 `first_detection`，此处不编造示例观测。
导播输出 `[720,1280,3]` 的视频帧；全幅坐标与裁切后坐标不能混用。

- **YOLO（目标检测模型）**：在每张图中找出人物等目标及其框；它本身不是运镜策略。
- **Track ID（轨迹编号）**：旧跟踪器在同一视频中分配的临时编号，不等于球员姓名/号码；人脸检录身份是另外一层。
- **ROI（感兴趣区域）**：原规则按位置优先保留球场人物的启发式区域，不保证完全排除裁判/观众。
- **热点（hotspot）**：本项目旧规则估计的横向活动中心，单位像素；不是完整二维高斯热点，更不是战术名称。
- **去畸变（undistortion）**：校正镜头造成的弯曲；**Homography（单应性变换）** 则将地面像素投到球场平面，本轮未做。
- **Tensor Shape（张量维度）**：数据数组每个轴的长度；后续 TCN 才会使用 `[B,15,D]`，表示 B 段、每段 15 个历史时间点、每点 D 个数值。
- **TCN（时间卷积网络）**：学习一段时间内运动变化的模型。G0 只准备可运行的视频/观测边界，没有 TCN、训练或未来标签。

原始视频建议 `data/input/`，本地 YOLO 建议 `models/`；轨迹 CSV/JSONL、球场标定、特征与 TCN 权重尚未产生。`summary.json` 是运行证据，不能拿首条框或规则 `predicted_hotspot_x` 当训练真值。

## 验证与五个常见问题

自动化测试：

```powershell
Set-Location 'D:\0basketball\project'
$env:G0_TEST_WEIGHTS = 'C:\Users\zenghuiting\Desktop\rk_driceter\best.pt'
$env:G0_TEST_VIDEO = 'C:\Users\zenghuiting\Desktop\rk_driceter\usb3_undistorted_20260706_111148_325.mp4'
.\.venv\Scripts\python.exe -X utf8 -m pytest -q
```

真实模型测试处理 12 帧，要求确实检出人物且两路视频都能解码；没有设置这两个变量时会 skip，必须报告未运行，不能算带模型测试通过。

| 问题 | 排查顺序与命令 |
|---|---|
| 找不到 YOLO / 错把 SAC 当权重 | `Get-ChildItem -LiteralPath '.\best_sac'`；`Test-Path -LiteralPath 'C:\Users\zenghuiting\Desktop\rk_driceter\best.pt'`；核对 `.pt` 和错误日志，不把 `.pth` 改后缀冒充 |
| 缺包 / Python 用错 | `.\.venv\Scripts\python.exe -m pip check`；运行环境检查脚本，核对 executable 位于 `.venv`，重新按上方命令安装；不要使用原 Linux face_env |
| 能启动但没框 | 查看本次 `summary.json` 的真实 names、人物 ID、真实观测数；确认输入是广角原视频；G0 原规则还用 0.35 人物阈值，不能盲目降低阈值就当效果变好 |
| 视频/标定尺寸不匹配 | `.\.venv\Scripts\python.exe -X utf8 .\run_windows.py --help`；已矫正视频用 already；原始帧用匹配 NPZ 的 calibration，不要重复矫正或静默 resize |
| 保存失败/播放异常/中文乱码 | 查看 `run.log` 和 `outputs` 解码统计；尝试显式 `--codec MJPG`；命令加 `-X utf8`；FPS 无效须显式 `--fps`；只有文件存在不算成功 |

排查原则：先确认路径和环境，再确认帧/尺寸/时间，再确认真实类别和框，最后检查规则裁切和编码。没有人工框真值，本轮不报告 mAP、MOTA、IDF1 或“准确率 100%”。

## 交接、回退与下一关

准确的产物目录、测试输出、环境锁定与真实记录见 [G0 验收报告](docs/G0_ACCEPTANCE_REPORT.md)；当前状态见 [STAGE_PROGRESS.md](STAGE_PROGRESS.md)。
工作基线与修改都在本地 Git，未推送。需要回到原工程时可在另一个独立目录检出原基线，或在干净状态下切回原基线；不要用 hard reset 覆盖自己后续修改。
新版 RK3588 入口仍使用原参数和 `.rknn`。共享算法回归已覆盖导入/规则逻辑，不等于 RK3588 NPU 真机已验证。
G0 通过后，只有用户明确批准才能进入 G1，下一关会复核双类别权重和篮球检出质量；不会在当前关卡自动实施 ByteTrack 或 TCN。
