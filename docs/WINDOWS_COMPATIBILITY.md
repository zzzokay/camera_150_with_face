# G0 平台兼容矩阵与设计依据

文件作用：为开发者和验收者逐项说明真实 RK3588 依赖、Windows 对应方案和验证边界。更换后端、编码器、相机或完成设备实测后更新；配合 PROJECT_STRUCTURE.md 与 G0_ACCEPTANCE_REPORT.md 阅读。

G1 更新：用户授权人物筛选/检测记录与球接口预留，39 项测试通过；G0 默认无额外 ROI，G1 使用可选外部策略与 JSONL，球关闭。当前结果见 [G1_ACCEPTANCE_REPORT.md](G1_ACCEPTANCE_REPORT.md)，真实球模型和 CUDA/NPU 未验，不改变下表的硬件迁移边界。

补充实测：室内比赛录屏按 `--start-seconds 30` 处理至结尾，保留源帧号/时间，两路 1818 帧完整解码；片段起点只用于文件，不更改摄像头接口。27 项测试通过，具体证据与裁切失败例见 [G0_ADDITIONAL_VIDEO_VALIDATION.md](G0_ADDITIONAL_VIDEO_VALIDATION.md)。

## 核实的源码与策略

基线 `5bd9c5a437536706f51106a5e86fbb2a7ec46906`，以下路径均相对项目根。
推荐最小方案：Ultralytics `.pt` + OpenCV 文件/设备读取 + 原规则 + OpenCV 本地编码；不要求外部 FFmpeg、Qt、音频或网络服务。
备选方案是后续按需要增加 ONNX 或 FFmpeg libx264，但本轮不声称这些后端已适配。

| 依赖/原功能 | 实际源码证据 | Windows G0 方案 | 状态/边界 |
|---|---|---|---|
| `rknnlite.api` / NPU / `.rknn` | `single_rknn_base.PersonDetector.__init__/detect`, `get_core_mask` | 新 `YoloPersonDetector` 使用本地 `.pt`；RKNN 延迟导入，只在原硬件检测器创建时加载 | 真实模型结果以验收报告为准；不把 .rknn 转成 .pt |
| 人物类别写死 0 | 原 base `PERSON_CLASS_ID=0`、`labels.txt=person` | 读取实际 `.pt` 的 names，以 person/player 配置别名查 ID | 类别映射单测使用非 0 ID；G0 只传人物，不声称双类别 |
| `/dev/video41` / V4L2 | `single_rknn_base.open_camera`, `LatestFrameCamera` | 文件 Path 优先；摄像头 `--camera N --backend dshow/msmf/auto` | 本机 dshow 0/1 号设备均读 3 帧；窗口 API 可见；msmf/长时推理未测 |
| 最新帧循环可丢/重复帧 | 原 network `run` 每轮 `cam.get_latest()` | 离线顺序读，每源帧处理一次；摄像头同步读 | 文件有源帧号/时间检查；实时低延迟和音画同步未验收 |
| 单目去畸变 | 原 `load_single_camera_calib`, `prepare_frame_for_calib` | 复用原标定/remap，严格检查 NPZ 尺寸；none/already/calibration 明示 | 合成标定组件通过；真实输入按用户声明已矫正，不二次 remap |
| 旧距离关联与 ID | 原 `SmoothTracks.update` | G0/G1 原样复用；G2 使用独立 ByteTrack，旧算法只做对照/回退 | 53项回归/组件/真实模型测试通过；仍有断轨，不等于实名 |
| 原一维热点与 Pan/Zoom | `predict1_weighted.analyze_single_view_frame`, `predict1_director.update_overlay_director_state` | 直接调用原规则；支持脚本与包两种导入 | AST 和 180 帧序列对比；原参数未调优，非 2D 热点或 TCN |
| 绘图模块缺失 | 原 director 顶部引用未随仓库提供的 `predict1_yolo`；旧入口注入绘图兜底 | 此依赖仅在旧调试绘图函数调用时导入；Windows 有真实自己的绘图 | Windows 启动不注入假模块；原绘图调用仍需旧依赖/旧入口提供 |
| 原 720p 渲染 | 原 record 的 `fit_box_to_output_ratio`、`render_sample_director_view720` | 提取四个纯转换/渲染函数，算法体逐一比对 | 原录制入口未修改；复制范围有测试约束 |
| `h264_rkmpp` | 原 `AsyncFFmpegH264Recorder` / `FFmpegNetworkStreamer` 默认编码器 | `mp4v`→MP4，或显式 `MJPG`→AVI；保存后全片逐帧解码 | 编解码组件通过；mp4v 是 MPEG-4 Part 2，不能称 H.264；播放器支持有差异 |
| ALSA `hw:1,0` / AAC | `audio_chain.build_alsa_input_args`, 两个旧入口 | 离线视频不导入音频模块；本轮产物无音轨 | Windows 音频采集/混流未移植，是允许延后项 |
| Wayland / Qt / LCD | 原管理脚本、技术台 UI | 本地默认 headless（无窗口）；可选 OpenCV 预览 | 相机 OpenCV 窗口 API 可见已测；窗口外观待用户确认；Qt/RK3588 LCD 未实测 |
| MediaMTX / RTSP | 原 network、`mediamtx_rk3588.yml`、原 Windows 客户端 | 与离线入口隔离，保留旧应用 | 本轮未部署服务/未验证网络音视频；不影响本地处理 |
| 技术台比赛状态 | 原 `director_game_policy` | 可选 `--game-state` 调用原 NORMAL/HOLD/FREE_THROW 策略，默认不读取状态文件 | 源码保留；状态文件只读，UI/HTTP 端到端未验收 |
| 人脸检录 / LBPH | 原 `face_checkin_lbph*.py` 与 `face_checkin` 资产 | 保留旧逻辑，Windows 本地视频不启动检录 | 完整 Windows 检录未迁移，不是 G0 阻塞 |
| Linux 路径 / 中文文件名 | 原 base 多个 `/home/elf/...` 默认路径 | 新 CLI/配置使用 Path；YAML 相对其所在目录解析 | 中文/空格读写单测通过；不改 RK3588 默认值 |

## 行为保持与已知差异

共享改动只有 base 的 RKNN 延迟导入、director 的包导入与旧绘图延迟导入，加文件用途说明。原热点、跟踪、状态机表达式和阈值没有变化；所有 RKNN 主入口原文保留。
Windows 和 RKNN 模型可能来自不同权重与后处理，不能仅因规则代码一致就宣称框位置一致；本轮无 RK3588 真机，无法做同帧 NPU 对照。
本地输出使用顺序读和源报告 FPS，CPU 慢只增加处理等待时间。保存时按名义 FPS 生成恒定帧率，源 FPS 元数据与实际 PTS 有差异时，时长也有偏差。首轮 30 FPS 视频和补充室内录屏的实际时长分别记录在两份报告中；不声称任意可变帧率音画同步。
摄像头同步处理的实际吞吐可能低于设备标称 FPS，保存容器 FPS 仍是设备报告/指定 FPS，不能据此认定实时录制时长精确。此项与相机实测一起验收；G0 本地视频证据不覆盖该项。
本机相机探测证实了这一点：1 号设备报告约 30 FPS，连续读帧实际间隔约 1 秒；0 号请求 640×360 实际返回 640×480。收帧时间使用高精度 `perf_counter`，不使用在 Windows Python 3.11 中可能给出同值的普通 `monotonic`；它不等于传感器曝光时间。最终报告位于 `runs/g0_audit/camera0_final_environment.json` 和 `camera1_final_environment.json`，不含图像。

原 `filter_playing_persons` 有 ROI 与高度启发式，但无人落在 ROI 时会回退使用其他人物，因此不能保证排除所有观众/裁判。本轮保持原行为，并在可视化中检查失败；检测质量改造须由 G1 授权。
`already` 模式只是明示输入已矫正的假设；图像上仍可能有残余弯曲，本轮没有用球场几何误差证明矫正质量。不得把原相机 NPZ 当作球场 Homography。

## 依赖与许可证来源

| 组件 | 来源 | 许可证/用途 |
|---|---|---|
| Ultralytics 8.3.225 | https://github.com/ultralytics/ultralytics | AGPL-3.0（另有商业授权）；本地人物检测与 G2 ByteTrack，未复制第三方源码 |
| lap 0.5.12 | https://pypi.org/project/lap/ / https://github.com/gatagat/lap | BSD-2-Clause；ByteTrack 线性分配，固定 Windows wheel，明确安装到 .venv |
| PyTorch / TorchVision | https://pytorch.org/ | BSD 类开源许可；CPU 推理 |
| OpenCV Python | https://github.com/opencv/opencv-python | OpenCV Apache-2.0，wheel 含第三方编码组件许可；读写/图像处理 |
| NumPy / PyYAML / pytest | https://numpy.org/ / https://pyyaml.org/ / https://pytest.org/ | BSD / MIT / MIT；计算、配置、测试 |
| 用户 `best.pt` | 用户确认的桌面本地权重 | 训练数据、模型来源/授权细节未核实；不下载/上传/提交此文件 |
| 原工程 | 用户指定 GitHub 仓库 | 未发现项目级 LICENSE；保留原工程与基线来源 |

外部 FFmpeg 可执行程序并非本地视频模式的必要条件；OpenCV wheel 的视频后端能力由环境检查报告给出。
G2 仅支持人物 ByteTrack，篮球按用户要求继续关闭；固定库 API、名义 FPS、场景重置与重复帧边界见 [G2_TRACKING_QC.md](G2_TRACKING_QC.md)。旧 RK3588 源文件在 G2 未变，NPU 真机仍未验收。
当前实测依赖安装在 `.venv`；规范也允许其他满足依赖要求的独立环境，不向系统 Python 安装项目依赖。文档和自动化命令优先显式指定解释器，日常开发可激活后使用 `python`。原环境所用清华镜像曾返回 403，本轮安装命令显式指定官方 PyPI/CPU wheel 源，不修改全局 pip 配置。准确版本与最终运行结果见验收报告。
