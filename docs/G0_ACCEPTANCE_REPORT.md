# G0 验收报告（2026-10-20）

文件作用：向用户提交 Windows G0 的真实验收证据、变更边界与未验证项。由本关测试执行者在代码或验证结果变化后更新；复现步骤见 NEWCOMER_HANDOFF.md，逐项状态见 STAGE_PROGRESS.md。

补充验证：用户随后指定另一室内比赛录屏并要求跳过前 30 秒；已完成源时间 30.0101–105.7088 秒共 1818 帧、606 次真实 YOLO，两路完整解码；新增片段起点参数后 **27 项测试通过**。详见 [G0_ADDITIONAL_VIDEO_VALIDATION.md](G0_ADDITIONAL_VIDEO_VALIDATION.md)。下文保留首轮 300 帧及 22 项测试的原始记录。

- 当前状态：**待用户验收 / READY_FOR_REVIEW**。用户尚未验收；G1 及后续未开始。
- 本关目标：真实 Windows 本地篮球视频 → 真实 YOLO 人物推理 → 原 SmoothTracks 和规则导播 → 本地保存；去除新入口对 RKNN、Linux 设备、音频与硬件编码的启动依赖。
- 原有问题与为何修改：`single_rknn_base.PersonDetector` 使用 RKNNLite，原 `open_camera` 使用 V4L2；旧录制/推流入口还绑定 RK3588 编码器、ALSA 和显示环境。Windows 需要独立入口和推理后端。旧 `SmoothTracks` 已有临时 ID，本轮复用，不宣称原来没有跟踪。
- 变更文件及作用：见下表。原三个 RKNN 录制/推流入口、`predict1_weighted.py`、技术台、检录、音频/比赛状态策略均未修改。
- Windows 环境信息：Windows 11 家庭版中文版，构建 10.0.26100，64 位；Python 3.11.4；torch 2.9.1+cpu、torchvision 0.24.1+cpu、Ultralytics 8.3.225、OpenCV 包 4.12.0.88（运行时 4.12.0）、NumPy 2.2.6、PyYAML 6.0.3、pytest 8.4.2。存在 Intel UHD Graphics 与 NVIDIA RTX 4060 Laptop GPU，本轮 CUDA 不可用/未使用。外部 ffmpeg 不在 PATH；OpenCV 内置 FFMPEG 后端可用。
- 实际运行命令：下文 PowerShell 命令与本地日志对应，均在真实 Windows 上执行。
- 产物与路径：主要证据目录为 `D:\0basketball\project\runs\g0_20261020_144146_be04f4bc`；另有审计目录、跨目录试跑和 pytest 临时产物，详见下文。
- 自动测试：**22 项通过、0 项失败、0 项跳过**，耗时 4.61 秒；包括真实权重/篮球录像集成测试。初始系统环境曾运行 21 项组件/回归，最终结论采用独立 `.venv` 的 22 项。CUDA/NPU 设备测试不在这 22 项中，未运行原因见未验证项。
- 手工检查：已目视检查输出第 0、149、299 帧及对应全幅调试图；确认框位于主要人物区域、导播输出对应青色窗口、窗口向左移动。发现重复框、疑似误检及初始裁切未包含左侧人物的问题，保留并记录，不报告检测准确率。
- 对 RK3588 的影响：共享模块只调整依赖导入方式；算法 AST 与固定上游一致；180 帧合成序列逐帧核对跟踪、状态、裁切及像素一致。没有 RK3588 真机，因此 NPU/音视频链路兼容性仍为未实测。
- 已知问题 / 未验证内容：见最后一节。模型仅有 person；未进行双类别质量验收、ByteTrack 或任何训练。
- 根目录更新的文档：README.md、PROJECT_STRUCTURE.md、NEWCOMER_HANDOFF.md、STAGE_PROGRESS.md、CHANGELOG.md；用户两份工程规范原文保留，SHA-256 与用户提供文件一致。
- 请用户确认：是否验收 G0；后续关卡需另行明确授权。本次交付停止在 G0。

## 变更文件与数据流

| 文件/目录 | 作用与修改范围 |
|---|---|
| `camera_150/windows_pipeline/` | 分离配置、帧/框类型、视频源、可选去畸变、YOLO 人物检测、旧导播适配、视频输出和环境诊断 |
| `run_windows.py` | Windows 总入口，支持绝对路径从其他当前目录启动 |
| `check_windows_environment.py` | 版本/硬件/模型文件清单，不反序列化 SAC |
| `check_windows_camera.py` | 设备打开、读 3 帧、时间递增和短暂预览检查，不保存摄像头图像 |
| 原 `single_rknn_base.py` | RKNN 导入推迟到 `PersonDetector.__init__` / `get_core_mask`，原算法不变 |
| 原 `predict1_director.py` | 支持包导入；旧调试绘图依赖按需导入，状态机不变 |
| `windows_pipeline/rendering.py` | 原录制入口四个纯转换/渲染函数的隔离副本；测试约束函数体一致，原录制脚本未改 |
| `configs/windows.example.yaml` | 可移植配置，路径相对 YAML 自身目录；本机 `.local.yaml` 被忽略 |
| `requirements-windows.txt` / `.lock.txt` | 固定直接依赖 / 实测完整 CPU 环境 39 个包 |
| `tests/` / `pytest.ini` | 组件、旧算法回归、真实模型集成测试，避免收集上游设备/虚拟环境代码 |
| `.gitignore` 与根目录文档 | 忽略模型/视频/环境/运行证据，维护真实结构、复现、进度和回退 |

调用链：`run_windows.main → VideoSource.read → FramePreprocessor.apply → YoloPersonDetector.detect → LegacyDirector.process → 原 SmoothTracks → 原 analyze_single_view_frame → 原 update_overlay_director_state → 纯裁切渲染 → SavedVideo → verify_video`。
图像输入为 `[1080,1920,3]` BGR uint8；导播输出为 `[720,1280,3]`。框和裁切矩形仍使用完整广角图像像素，不是球场米制。

## 模型与输入真实性

用户在本聊天明确确认使用两个桌面文件：

```text
模型：C:\Users\zenghuiting\Desktop\rk_driceter\best.pt
模型大小：6,243,299 bytes
模型 SHA-256：d68486dcc883388d1d822a9ab67d9d6c9cd5c6dccf653c63242ecc9e39863db9
实际 model.names：{0: 'person'}
视频：C:\Users\zenghuiting\Desktop\rk_driceter\usb3_undistorted_20260706_111148_325.mp4
实际输入：1920×1080，30 FPS，4236 帧，约 141.2 秒
本轮主验收范围：源帧 0–299，共 300 帧（10 秒）
```

按来源与用户确认，输入声明为 `already` 去畸变，实际不再 remap；本轮未重新验证残余镜头畸变。原视频和权重未改写。
`best_sac/` 仅列出文件和查看 ZIP 条目/环境说明，未反序列化其张量、未运行 SAC；其中没有 `.pt/.onnx/.rknn` YOLO 文件。
所用 YOLO 真实类别表只有人物，不能把本轮写成篮球检测或 G1 通过。

## 实际命令与输出摘要

### 1. 环境与依赖

PowerShell，工作目录 `D:\0basketball\project`：

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --index-url https://pypi.org/simple pip==25.3
.\.venv\Scripts\python.exe -m pip install --index-url https://download.pytorch.org/whl/cpu --extra-index-url https://pypi.org/simple torch==2.9.1+cpu torchvision==0.24.1+cpu
.\.venv\Scripts\python.exe -X utf8 .\runs\g0_audit\download_official_wheels.py
.\.venv\Scripts\python.exe -m pip install --no-index --find-links .\runs\g0_wheelhouse_20261020 -r .\requirements-windows.txt
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -X utf8 .\check_windows_environment.py --model-dir .\best_sac --output .\runs\g0_audit\final_environment.json
```

实际 stdout 摘要：`Verified wheels: 28 MB: 159.1 seconds: 96.7`；`Successfully installed ... ultralytics-8.3.225`；`No broken requirements found.`。
最初默认清华镜像返回 403，仅用 CPU 索引的旧 pip 还遇到 typing-extensions 元数据问题；原标准 pip 下载后在 OpenCV 包处长时间等待，因此中止了该次安装进程。
最终从**同一官方 PyPI**直接取得已解析的 28 个 wheel，对照 PyPI JSON 的 SHA-256 全部校验后离线安装；来源/大小/哈希在 `runs/g0_wheelhouse_20261020/manifest.json`。未改全局 pip 源。
完成后还实际执行 `.venv\Scripts\python.exe -m pip install --index-url https://pypi.org/simple -r requirements-windows.txt`，显示全部已满足并返回 0。
全新机器的标准联网安装路径见交接文档；本轮未使用第二台全新电脑复现。

### 2. 自动化测试（真实模型已启用）

```powershell
$env:G0_TEST_WEIGHTS = 'C:\Users\zenghuiting\Desktop\rk_driceter\best.pt'
$env:G0_TEST_VIDEO = 'C:\Users\zenghuiting\Desktop\rk_driceter\usb3_undistorted_20260706_111148_325.mp4'
.\.venv\Scripts\python.exe -X utf8 -m pytest -q --junitxml .\runs\g0_audit\pytest.xml
```

stdout：`22 passed in 4.61s`；原始输出 `runs/g0_audit/pytest.txt`，机器可读证据 `pytest.xml`。
真实模型集成用 12 帧，实际执行 4 次推理，要求人物框观测数大于 0、8 帧为复用、两路视频均能完整解码。它没有替换成 mock 检测器。
其余 21 项覆盖原共享算法/入口回归、180 帧合成输入旧新对齐、中文空格路径、两种编码器、时间戳、标定尺寸、真实类别名映射及错误配置。合成输入只验证工程接口。

### 3. CPU 篮球片段导播

```powershell
.\.venv\Scripts\python.exe -X utf8 .\run_windows.py `
  --source 'C:\Users\zenghuiting\Desktop\rk_driceter\usb3_undistorted_20260706_111148_325.mp4' `
  --weights 'C:\Users\zenghuiting\Desktop\rk_driceter\best.pt' `
  --undistort already --device cpu --detect-interval 3 --max-frames 300
```

stdout 含 `真实模型类别：{0: 'person'}` 和 `完整解码核验通过`；完整控制台保存为 `runs/g0_audit/real_video_console.txt`。

| 指标 | 实际值 | 含义 |
|---|---:|---|
| 处理源帧 | 300 | 0–299，完整处理所选 10 秒片段，未声称处理整段 4236 帧 |
| 真实 YOLO 调用 | 100 | 每 3 帧一次，首次为源帧 0 |
| 推理产生的人物候选框累计数 | 231 | 跨帧框数之和，含误检/重复候选；不是 231 个人，也不是准确率 |
| 复用上一轮结果的帧 | 200 | 内存中 observed=false；调试视频标橙色 REUSED 与年龄 |
| 时间戳回退帧 | 0 | 本段容器时间戳有效，最终 9.9667 秒 |
| 裁切框相对首帧发生变化的帧 | 290 | 证明裁切状态实际在更新，不等于导播质量分数 |
| 处理耗时 | 11.3154 秒 | 含初始化、推理、规则、保存，未含最后全片复查 |
| 总耗时 | 12.9367 秒 | 包括两路视频完整解码核验 |
| 平均一次推理 | 29.1503 ms | 包括首次预热；不是独立硬件/实时性能基准 |

本轮首条**真实模型输出**（按显示需要四舍五入；原精度见 summary）：

```json
{
  "class_name": "person",
  "model_class_id": 0,
  "confidence": 0.75336236,
  "bbox_xyxy": [116.44494, 594.07220, 180.37442, 751.53613],
  "coord_system": "undistorted_full_frame_px",
  "observed": true,
  "source_frame_idx": 0,
  "timestamp_sec": 0.0
}
```

### 4. 跨当前目录 + YAML + 中文空格输出

工作目录特意设为 `D:\0basketball`。本机配置 `configs/windows.local.yaml` 指定上述真实输入/权重、`output_dir: ../runs/cross_directory 中文` 和 `max_frames: 300`；命令行覆盖为 3 帧以验证路径。

```powershell
& 'D:\0basketball\project\.venv\Scripts\python.exe' -X utf8 `
  'D:\0basketball\project\run_windows.py' `
  --config 'D:\0basketball\project\configs\windows.local.yaml' --max-frames 3
```

成功目录 `runs/cross_directory 中文/g0_20261020_144312_2c6c6e8d`，真实推理 1 次，两路视频均解码 3 帧。日志 `runs/g0_audit/cross_directory_console.txt`。本机配置不提交，通用示例不含开发者绝对路径。

### 5. 摄像头打开与预览 API

```powershell
.\.venv\Scripts\python.exe -X utf8 .\check_windows_camera.py --camera 0 --preview --output .\runs\g0_audit\camera0_final_environment.json
.\.venv\Scripts\python.exe -X utf8 .\check_windows_camera.py --camera 1 --preview --output .\runs\g0_audit\camera1_final_environment.json
```

两个设备均为 `COMPLETED`，每路读取 3 帧，`window_visible_api=true`，不保存画面。
0 号实际 640×480，收帧时间 `[0, 0.052548, 0.180453]` 秒；1 号实际 640×360，时间 `[0, 1.000044, 2.000160]` 秒，两者报告约 30 FPS。
1 号实际间隔接近 1 秒，不能宣称相机实时 30 FPS；这只是 API 打开/读帧/窗口检查，窗口外观和完整相机 YOLO/录制仍待用户实机确认。
最初普通 monotonic 时钟在 0 号缓冲读取时出现重复时间；已改为 perf_counter，并以以上实际递增结果验证。它记录收帧时刻，非硬件曝光时间。

## 产物、查看方式与人工核查

主要目录：`D:\0basketball\project\runs\g0_20261020_144146_be04f4bc`。

| 文件 | 实际产物 |
|---|---|
| `director.mp4` | 9,981,118 bytes；1280×720，30 FPS，300 帧；干净规则裁切，MPEG-4 Part 2，无音轨 |
| `overview.mp4` | 19,013,430 bytes；1920×1080，30 FPS，300 帧；原全幅平滑框、临时 ID、青色裁切窗口、新观测/复用标记 |
| `summary.json` / `run.log` | COMPLETED、真实类别/权重哈希、全部参数、帧/推理计数、推理耗时、输出解码统计 |
| `review_contact_sheet.jpg` | 源帧 0、149、299，左为全幅调试，右为对应导播输出 |
| `overview_frame_*.jpg` / `director_frame_*.jpg` | 三个时间点的原尺寸解码截图 |

可双击 MP4 播放或在 Codex 文件面板打开；外观可先查看对照图。整个输出已逐帧解码，目视检查只抽查上述三帧，未声称人工连续审看全片或所有播放器均兼容。

观察结果：

1. 第 0 帧初始化为居中裁切，左侧人物暂在裁切区外；第 149、299 帧窗口已向左侧活动区域移动，导播输出中主要两人可见。这是本轮保持的原初始化/过渡行为，需由用户判断能否接受。
2. 第 299 帧右侧同一人物出现两个重叠候选框（临时 id=6 与 id=8），围栏附近出现疑似误检（id=7）。这些是当前模型/后处理与旧关联器的局限；没有通过调参或删除失败帧隐藏它们。
3. 第 149、299 帧显示 REUSED age=2，明确来自前次推理，不是新的真实观测。
4. 没有人工真值，不报告 mAP、MOTA、IDF1 或检测准确率；临时 ID 不等于实名身份。

## 兼容、回退与未验证项

- 原工程基线：`5bd9c5a437536706f51106a5e86fbb2a7ec46906`；本地代码提交：`3415582`；最终文档/环境锁定提交可用 `git log -1` 查看。分支 `g0/windows-migration`，未推送。
- 原共享算法 AST 与基线一致；原 RKNN 三入口及音频、技术台/检录源码差异检查未发现改动。可在另一目录检出基线回退；不要覆盖自己的后续未提交修改。完整矩阵见 WINDOWS_COMPATIBILITY.md。
- 新增/更新文档和配置都具有文件作用说明。模型、原视频、.venv、wheel 缓存、日志和截图不提交；上游原有私人/环境资产仅保留在原版本树，未作为本轮新增资产。
- 尚未测试：RK3588 真机 NPU、CUDA、ONNX、相机 msmf 后端、长时间相机推理保存/实时音画时长、完整 Qt/技术台、人脸检录与 Windows 音频 RTSP。
- 原镜头 NPZ 的真实原始视频去畸变未在本片段执行；对应 remap 与尺寸边界仅做了合成组件测试；已去畸变输入避免二次矫正。
- 只验证选定 10 秒实际录像，不代表多人完整比赛、交叉遮挡、快速运动全场景质量合格；本轮保持旧规则阈值，不升级算法。
- 本关产物为 Windows 运行入口和清晰的全幅人物观测边界，后续 G1 可复核新的 person+ball 权重与检测质量；ByteTrack、轨迹、球场坐标、特征、TCN 均需后续逐关批准。

**请验收本关；确认后我再执行下一关。**
