# Windows 检测与跟踪新人交接

文件作用：让新人无需阅读源码即可准备输入、运行、查看结果和排错。运行/环境/验收变化后与 README、结构文档和验收报告同步更新。

## 当前完成与边界

原 Windows 代码放在 RK3588 目录下，预处理、规则导播、绘图和旧对照仍导入旧工程，G2 主循环总是启动导播与旧关联。现在迁移到独立 `basketball/` 包；只保留 Windows 输入、YOLO、人物 ByteTrack、QC 和可选纯规则/对照。不需要 RKNN、LCD、RTSP、音频、检录或技术台。

本轮依据用户“把多余的文件删了”执行独立化清理；当前干净的 `windows/g2-standalone` 分支直接在 `D:\0basketball\project` 整理，便于继续使用原目录。既有历史分支保留；没有清空工作目录或删除个人输入。

重构前测试和同片段基线已建立，180 帧冻结合成回归已在旧代码先运行通过。新自动化、真实模型和独立导出结果以 [本轮验收报告](docs/G2_WINDOWS_ACCEPTANCE_REPORT.md) 为准。**Windows 独立工程验收与跟踪质量验收分开；后者仍未完成。** 篮球关闭，G3/坐标投影/TCN/训练未实施。

清理后57项测试全部通过；真实室内1818帧前后记录/可选视频一致，默认模式和无Git导出48帧也已验证。当前为READY_FOR_REVIEW。旧目录现存标定NPZ备份在 `runs/g2_windows_cleanup_20261020_210634/preserved_assets/`；从新树排除2887个旧路径，实际删除73个旧文件/19个缓存，个人输入与历史保留。

## 从新机器准备环境

安装 Windows Python 3.11（64位，包含 py 启动器）。在项目根目录执行：

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r .\requirements-windows.lock.txt
.\.venv\Scripts\python.exe -m pip check
```

锁文件已明示官方 PyPI 和 PyTorch CPU wheel 源，不修改全局 pip 配置；CPU 实测版本为 Python 3.11.4、torch 2.9.1+cpu、Ultralytics 8.3.225、lap 0.5.12、OpenCV 4.12.0.88。CUDA 未测试，不将此锁文件用于 CUDA 环境。

本项目使用独立 Python 环境，不向系统 Python 安装项目依赖。默认采用 `.venv`，也允许其他满足依赖要求的独立环境。文档和自动化命令优先显式指定解释器；日常开发可以激活环境后使用 `python`。

## 准备输入与最快启动

需要本地 YOLO `.pt` 权重及篮球视频；不会自动下载权重，不能使用 SAC `.pth` 或 RKNN 模型。本机批准权重为 `C:\Users\zenghuiting\Desktop\rk_driceter\best.pt`，实际类别只有 `{0: 'person'}`，没有篮球。

新机器在**尚无 local.yaml 时**执行：

```powershell
Copy-Item .\configs\local.example.yaml .\configs\local.yaml
```

编辑 `input.source` 和 `model.weights`，相对路径以 YAML 目录为准；也可填中文/空格绝对路径。当前室内录像从 30 秒开始、`undistort: none`；已矫正的广角录像用 `already`，`calibration` 必须提供同分辨率 NPZ。镜头矫正不是球场 Homography。

```powershell
.\.venv\Scripts\python.exe -X utf8 .\run.py --config .\configs\local.yaml --max-frames 48
.\.venv\Scripts\python.exe -X utf8 .\run.py --config .\configs\local.yaml
```

本机 `local.yaml` 已填写用户批准的视频和模型；旧私人 `*.local.yaml` 保留为历史，不被新程序读取。`--max-frames 0` 表示到结尾。相机使用 `source: null`、`camera: 0`、`start_seconds: 0` 和合适的 `dshow/msmf/auto` 后端。

日常 `mode: track` 每帧一次 YOLO；`detect` 只检测，允许显式降低推理频率，并在记录中标明复用帧。`--director`/`--baseline` 分别开启导播/旧关联；后者只允许在 track 模式做对照。旧平面配置及旧入口已移出新分支，按统一模板迁移，不会静默按默认参数运行。

## 看什么、怎样验收

默认看 `overview.mp4`，再核对 `summary.json` 的 `status=COMPLETED`、源帧/时间、`inference_calls` 和每个 `outputs.decoded_frames`。文件关闭后程序会从头完整解码验证。输出视频没有音轨，以源名义 FPS 保存，不能保证任意可变帧率录屏的音画时长。

YOLO 提出人物位置和置信度；ByteTrack 用运动预测/重叠先关联高置信框，再用低置信框续接未匹配活动轨迹。低置信不能单独新建轨迹；新高置信框可能待确认，暂时不会有可输出 ID。增大 `match_thresh` 表示放宽第一阶段代价上限，不是提高 IoU 下限；第二阶段阈值在当前库中固定，不能靠一个 YAML 值修改所有阶段。

Track ID 是一次运行、一个 `segment_id` 内的临时轨迹编号，不是姓名/球衣号，也不限制为1～10。原框 `detection.bbox_xyxy` 是真实测量，`bbox_xyxy` 是滤波估计；坐标原点在完整图像左上，x向右、y向下，单位像素。源帧从0计，源时间单位秒；跳过片头后仍保留源帧号和源时间。丢失目标只记 lost ID，不把预测坐标冒充新观测。

例如历史室内源帧723/30.0101秒的一条真实观测约为 `[147.1211,806.7466,214.2195,971.2006]`、置信度 `.776394`、person、raw_full_frame_px。篮球始终 disabled/false/null，不能用人物或上一帧球位置填补。

人工重点查看篮下30–32秒、持球者59–62秒、横向移动73–77秒、场边85–96秒。当前矩形 ROI y=.66–.97 只是录像区域示例，仍可能包含裁判/场边人员；重复框、P218→P425断裂等质量问题未在重构阶段修复。不要凭最大 ID、ID总数或 CSV 行数判断算法优劣。

## 自动测试

普通组件/冻结回归无需模型，真实集成缺输入会明确 skip；不能把 skip 计作真实测试通过。设置已批准的真实输入再运行完整测试：

```powershell
$env:BASKETBALL_TEST_WEIGHTS = 'C:\Users\zenghuiting\Desktop\rk_driceter\best.pt'
$env:BASKETBALL_TEST_VIDEO = 'C:\Users\zenghuiting\Desktop\rk_driceter\usb3_undistorted_20260706_111148_325.mp4'
.\.venv\Scripts\python.exe -X utf8 -m pytest -q
```

测试包括中文路径/编码/源时间、检测契约、ByteTrack两阶段/重置、180帧冻结规则与对照、可选模块、输出失败资源释放、无Git/旧目录导出，以及真实模型的检测/跟踪/开关组合。它们验证工程行为，不等于实际跟踪质量达标。

## 常见错误

| 现象 | 排查与解决 |
|---|---|
| 找不到解释器/包 | 确认在项目根；用 `.venv\Scripts\python.exe -m pip check`；不要对系统 Python 安装 |
| 找不到模型/类别 | 核对 weights 文件与真实 names；仅 .pt；不使用 best_sac，不自动下载替代 |
| 旧 YAML 报错 | 按 local.example.yaml 分组迁移；YAML 相对路径以配置目录解析 |
| 视频打不开/30秒后无帧 | 核对 source 和录像长度；文件 backend 用 auto/ffmpeg；用准确路径，不删文件名中的不可见字符 |
| 编码失败 | 使用 `--codec MJPG` 显式输出 AVI，检查磁盘空间；FAILED/中断目录不算完整证据 |
| 没有导播/对照文件 | 默认关闭；需要时显式 `--director --baseline`，不生成空文件冒充运行 |
| ID跳变/场边目标 | 先看原检测、ROI及高低匹配；属于后续质量实验，不擅自压缩/复用ID |

## 位置、历史与后续

代码和关键数据流见 [结构文档](PROJECT_STRUCTURE.md)，记录字段细节见 [QC说明](docs/G2_TRACKING_QC.md)。本地模型/视频/环境/输出及私人 YAML 均忽略，不提交。
原工程从 `origin/main@5bd9c5a`、G0 `406b64c`、G1 `7f6b9cf`、G2 `cc87e85` 查阅；不能把旧源码从历史重新导入新运行链。回退前先保存个人改动，再在独立目录检出对应历史；不要 hard reset/clean 删除资产。
独立工程验收后才开始固定检测数据、单变量参数与人工身份片段对照；ReID取决于实验结论。当前不进入G3。
