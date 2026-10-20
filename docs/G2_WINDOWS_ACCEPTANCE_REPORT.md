# G2 Windows 独立工程验收报告

文件作用：提交 Windows 独立化、文件清理和行为回归证据，供用户验收；不是跟踪质量达标报告。当前分支 `windows/g2-standalone`，状态 **READY_FOR_REVIEW，等待用户验收**。整体 G2 质量仍为 IN_PROGRESS。

## 本次结果与范围

用户收到独立化方案后要求“把多余的文件删了”。已在现有 Windows 专用分支完成必要的提取、清理与验证，继续使用 `D:\0basketball\project`，没有另建工作树或移动历史分支。根入口为 `run.py`，Windows 源码为 `basketball/`，无需原 RK3588 目录或 `.git` 即可运行。

旧代码把 Windows 预处理、规则导播、绘图及旧关联绑定在 `camera_150/`，简单删除会导致导入失败。因此先建立回归，再将实际调用的纯逻辑提取到新包：YOLO 提供当帧人物观测，ByteTrack 进行高低置信关联；可选导播把已有轨迹转换为热点和裁切；可选旧对照独立计算距离关联。关闭可选分支时不导入、不构造，也不产生对应空文件。

保留了人物检测/跟踪、文件/Windows 相机输入接口、镜头预处理、可视化、轨迹和检测记录。统一分组配置，增加中文用途/运行/测试说明，更新 README、新人交接、结构、规范、阶段状态及来源文档。没有安装依赖、调整模型/检测/ByteTrack 参数、压缩或强制复用 ID；没有实施 ReID、G3、Homography、TCN 或训练。篮球继续 disabled/false/null。

## 清理清单与保护

| 操作 | 实际结果 |
|---|---|
| 从新分支版本树排除旧路径 | 2887 个；包含稀疏检出中未落盘的旧环境、旧资产和二进制，不能把此数当成磁盘删除数 |
| 磁盘上实际删除的旧跟踪文件 | 73 个；按清单逐文件删除，没有递归清空工程 |
| 删除旧目录派生 Python 缓存 | 19 个；清理空目录，无意外残留 |
| 自动审批拦截的缓存删除 | 根 `__pycache__` 中 `run_windows.cpython-311.pyc`、`check_windows_environment.cpython-311.pyc` 两个旧入口缓存仍保留；删除被工具以“blocked by policy”拒绝，没有继续尝试绕过；不参与新入口运行，且被Git忽略 |
| 移出的模块 | 全部 `camera_150/`（含旧 Windows 包）、RTSP 客户端、旧三个根入口、六份旧示例配置、依赖旧源码/Git 的硬件回归测试 |
| 迁移后的功能 | `basketball/`；规则为 `director.py` + `rules/`，对照为 `baseline.py`，均默认关闭 |
| 现存镜头标定文件 | 先备份到本轮证据目录 `preserved_assets/camera_usb3_calib.npz`，再移出旧目录；备份前后 SHA-256 一致 |
| 个人资产 | `.venv`、`best_sac`、`models`、`video`、旧 `runs` 和私人 `*.local.yaml` 保留；未加载 best_sac 模型 |

标定备份 SHA-256：`2535be1ca31d0ecbe17aa58c3484e1b25c6a86362bce6feaa973c6eff0beb145`。日常只需 `configs/local.example.yaml`；本机新 `local.yaml` 已写入批准输入并被 Git 忽略，旧私人配置只作历史保留，不被新程序读取。

历史引用清理前后保持：

| 分支/引用 | 提交 |
|---|---|
| origin/main | 5bd9c5a437536706f51106a5e86fbb2a7ec46906 |
| g0/windows-migration | 406b64c995a95406d9608f1f1d8c4f2b3ae732be |
| g1/person-detection-ball-slot | 7f6b9cf3f2d942602f52cebf096bc1296647a56b |
| g2/bytetrack-person | cc87e85b69ddabab7664769822c431bb65ba07f4 |

没有重写 Git 历史、删除历史分支或推送本次代码。原历史仍含旧上游资产，不宣称整个仓库历史已清洗。原工程可从上述引用查阅；当前删除仅体现在 Windows 新版本树。上表两个缓存是明确列出的清理残留，不把它们计入已删除数量。

## 环境、输入与固定参数

实际独立解释器：`D:\0basketball\project\.venv\Scripts\python.exe`；Windows build 26100，Python 3.11.4，torch 2.9.1+cpu，torchvision 0.24.1+cpu，Ultralytics 8.3.225，lap 0.5.12，OpenCV Python 4.12.0.88，NumPy 2.2.6。`pip check` 返回 `No broken requirements found.`。没有向系统 Python 安装依赖。存在 NVIDIA 设备不代表 CUDA 已验证；当前 torch 为 CPU 版。

输入均为用户明确批准的原文件：

| 输入 | 路径/声明 | SHA-256 |
|---|---|---|
| YOLO | `C:\Users\zenghuiting\Desktop\rk_driceter\best.pt`；实际 names 只有 `{0: 'person'}` | d68486dcc883388d1d822a9ab67d9d6c9cd5c6dccf653c63242ecc9e39863db9 |
| 室内录像 | `D:\0basketball\project\video\2026-04-15重庆客运段安康杯篮球比赛记录_哔哩哔哩_bilibili 和另外 6 个页面 - 个人 - Microsoft​ Edge 2026-10-20 16-53-01.mp4`；none，不作镜头矫正 | 4023326edd7e0fa768494356c659cd6f46478ad8d8df844ab49fbe919ecc3816 |
| 自动集成测试录像 | 桌面 rk_driceter 下 `usb3_undistorted_20260706_111148_325.mp4`；already，避免重复矫正 | 原文件用于短测；完整前后对照使用上行室内录像 |

室内路径包含不可见字符，以 `configs/local.yaml` 中的实际路径为准。处理源帧 **723–2540**，源时间 **30.0101–105.7088 秒**，共 **1818 帧**；跳过的片头不参加推理，时间/帧号不归零。源名义 FPS 为 24.032997，完整帧 1920×1080。

本轮固定 imgsz=640、NMS IoU=.7、人物接受=.35、跟踪 low=.10/high=.35/new=.35、match=.8、buffer=30、fuse_score=true、gap=.5 秒、scene=.65；原矩形 ROI y=.66–.97。可选旧对照 smooth=.65、180像素、15次缺失。上述数值沿用基线，没有进行质量优化或尺寸对照实验。

## 回归与真实运行证据

统一证据根目录：`D:\0basketball\project\runs\g2_windows_cleanup_20261020_210634`，简记为下表 `<证据>`。产物被 Git 忽略，未提交用户模型、录像或 QC 数据。

| 验证 | 实际结果 | 证据 |
|---|---|---|
| 重构前完整测试 | 53 passed in 8.41s，0失败/跳过 | before_pytest.txt / .xml |
| 新增冻结回归先跑旧实现 | 180帧合成序列，旧实现先通过；随后在新实现通过 | tests/fixtures/g2_before_refactor.json；test_frozen_regression.py |
| 清理后完整测试 | **57 passed in 14.50s，0失败/跳过**；其中7例真实模型集成，覆盖 detect/track 及导播/对照四组合 | after_pytest.txt / .xml |
| 同片段前后，开启导播/对照 | 两次各1818次真实 YOLO；4份检测/QC记录逐字节一致；3路视频各1818帧逐帧解码像素一致 | parity_report.json；compare_runs.py / compare_runs_console.txt |
| 默认关闭导播/对照 | 1818次真实 YOLO、overview完整解码1818帧；检测JSONL/ByteTrack CSV逐字节一致，逐帧主跟踪审计一致 | after_default_console.txt；default_and_export_report.json |
| 无旧源码、无.git导出 | 导出副本从自身run.py运行真实模型48帧，视频完整解码48帧；检测/逐帧轨迹与默认运行前48帧一致 | standalone_export/；export_real_model_console.txt；default_and_export_report.json |
| 独立自动测试 | 57项中包含导出副本组件/冻结回归、路径注入检查、可选模块惰性导入、写盘失败资源释放/FAILED报告 | tests/test_standalone.py；after_pytest.xml |
| 输入与资产 | 模型/室内录像哈希和基线一致；标定备份一致、历史引用未改 | manifest.json；cleanup_report.json；default_and_export_report.json |
| 环境 | CPU环境检查完成；pip check通过 | environment.json / environment_console.txt |

真实完整对照：

- 重构前：`<证据>\before\g2_20261020_210706_febfc91b`。
- 新版开启可选分支：`<证据>\after_with_options\track_20261020_212135_11dbf815`。
- 新版默认：`<证据>\after_default\track_20261020_213227_40887eb9`。
- 独立导出真实短测：`<证据>\standalone_export\runs\track_20261020_213449_8dab7c39`。

前后均有17287条达到人物接受门槛的观测、18778条ByteTrack确认匹配（high16348、low2430）；开启旧对照时有17287条旧关联输出。274个运行内不同轨迹段ID仅用于一致性复核，不是人数或质量指标。所有处理帧的球字段均disabled/false/null，逐帧ID正数且不重复。

默认运行只有overview、检测/跟踪记录及summary/log，没有director/comparison/旧CSV。summary的 `runtime_project_modules` 不含director、baseline或rules，`forbidden_runtime_modules=[]`；静态检查无旧目录import或sys.path注入。无Git导出继续使用现有独立解释器和外部批准输入，这验证源码独立，不代表复制了完整Python环境或模型。

保留原检测schema `g1_detections_v1`、QC `g2_tracking_qc_v1`；总报告改为 `windows_run_v1`。旧平面YAML/旧入口不再支持，必须按新模板迁移；不覆盖历史产物或静默解释成默认值。

## 人工核查与未解决问题

已查看本次同参数输出的固定源帧735、1451、1774、2200，分别对应篮下交叉、持球者断裂、横向移动与场边目标；图片为 `<证据>\case_*.jpg` 和 `manual_review_contact_sheet.jpg`。另核对逐帧审计；这不是全片逐人身份标注。

- 源帧735/30.51秒，篮下人物仍有重叠/局部重复框。
- 源帧1451/60.3396秒，中心持球者缺少确认ID；检测仍约.371，P218在lost。新记录与旧记录完全相同，不能把问题只归于漏检。日志中P425最早在源帧1453/60.4229秒输出；此前诊断展示的1459/60.6729秒是后续抽样画面，并非首次输出。
- 源帧1774/73.7962秒可见临时编号输出；单帧可见编号不能证明整个交叉过程身份正确。
- 源帧2200/91.544秒仍有场边目标，历史P792低置信长续接未消除。ROI脚点过滤不识别场上球员身份。

功能回归相同也保留了原有质量缺陷，**不能把57项测试通过、视频能播放或较少ID当成质量达标**。尚未做960完整评估、640/960/1280固定检测对照、真实球场多边形、单变量ByteTrack参数调整或ReID实验；没有MOTA/IDF1身份真值结论。

未测：CUDA、新版相机长时推理/实时性、任意变帧率、几何矫正精度、篮球模型。历史G0相机短读不能代替新版长时验收。输出无音轨、按源名义FPS保存，mp4v不是H.264。CPU运行耗时受同时验证任务影响，本轮不作性能提升结论。

## 用户运行与验收

在 `D:\0basketball\project` 的 PowerShell 直接运行：

```powershell
# 快速验证；去掉 --max-frames 48 则处理从30秒到结尾。
.\.venv\Scripts\python.exe -X utf8 .\run.py --config .\configs\local.yaml --max-frames 48
# 需要原规则/旧算法对照时显式开启。
.\.venv\Scripts\python.exe -X utf8 .\run.py --config .\configs\local.yaml --director --baseline
# 环境检查不加载模型。
.\.venv\Scripts\python.exe -X utf8 .\run.py --check-env --config .\configs\local.yaml
```

完整自动测试复现：

```powershell
$env:BASKETBALL_TEST_WEIGHTS = 'C:\Users\zenghuiting\Desktop\rk_driceter\best.pt'
$env:BASKETBALL_TEST_VIDEO = 'C:\Users\zenghuiting\Desktop\rk_driceter\usb3_undistorted_20260706_111148_325.mp4'
.\.venv\Scripts\python.exe -X utf8 -m pytest -q
.\.venv\Scripts\python.exe -m pip check
```

本轮完整新版命令为默认启动及 `--director --baseline`，分别另加 `--output-dir` 指向上述after目录；导出验证在standalone_export中清除PYTHONPATH，用原独立解释器绝对路径执行该副本run.py、该副本local.yaml和`--max-frames 48`。旧基线命令保留在before_console/summary中，不能在清理后的新树使用旧入口。

查看控制台提示目录的overview.mp4，再看summary的COMPLETED、1818/48帧计数和源起点；可用现有完整产物直接复核。新人安装/排错见 [NEWCOMER_HANDOFF](../NEWCOMER_HANDOFF.md)，模块与数据流见 [PROJECT_STRUCTURE](../PROJECT_STRUCTURE.md)。

若需查看/回退旧版，先保存自己的改动，在另一个目录检出指定历史引用；不要对当前含个人资产的目录执行hard reset或git clean。本轮全部源码/文档随Windows分支本地提交，可从Git查阅；私人产物不随提交。

**本次只提交Windows独立工程验收，等待用户确认；确认通过后才开展G2跟踪质量实验。**
