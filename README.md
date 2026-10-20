# Windows 篮球检测与跟踪

文件作用：提供最简启动、输入准备和结果查看；完整安装/排错见新人交接。

```powershell
.\.venv\Scripts\python.exe -X utf8 .\run.py --config .\configs\local.yaml
```

在项目根目录运行。本机 `local.yaml` 已填写获准使用的录像和桌面 `best.pt`，从录像 **30 秒后**开始。默认进行人物 YOLO + ByteTrack，输出全幅带 ID 视频和 QC；篮球关闭，规则导播与旧关联对照默认关闭。

新机器先按 [新人交接](NEWCOMER_HANDOFF.md) 建立独立 Python 环境、安装锁定依赖，然后复制 `configs/local.example.yaml` 为 `local.yaml`，填写视频和本地 YOLO `.pt` 路径。不要向系统 Python 安装项目依赖。

快速验证只处理起点后的 48 帧：

```powershell
.\.venv\Scripts\python.exe -X utf8 .\run.py --config .\configs\local.yaml --max-frames 48
```

程序结束后打开控制台提示的 `runs/<本次运行>/`：

| 文件 | 查看内容 |
|---|---|
| `overview.mp4` | 全幅人物框、临时 ID、高/低置信匹配阶段和 ROI |
| `bytetrack_qc.csv` | 每次确认匹配的原始观测框、滤波框、ID、源帧号/秒 |
| `tracking_audit.jsonl` | 每处理帧的匹配/丢失信息；不伪造失踪位置 |
| `detections.jsonl` | 真实检测、被排除候选和原因；篮球位置为 null |
| `summary.json` / `run.log` | 实际配置、类别、统计、错误与视频完整解码核验 |

可选功能仍使用同一入口：

```powershell
# 仅检测，不输出轨迹 ID。
.\.venv\Scripts\python.exe -X utf8 .\run.py --config .\configs\local.yaml --mode detect
# 同时开启原规则导播和旧关联对照，额外生成 director.mp4、tracking_comparison.mp4、smoothtracks_qc.csv。
.\.venv\Scripts\python.exe -X utf8 .\run.py --config .\configs\local.yaml --director --baseline
# 检查环境，不加载模型；相机检查不保存画面。
.\.venv\Scripts\python.exe -X utf8 .\run.py --check-env --config .\configs\local.yaml
.\.venv\Scripts\python.exe -X utf8 .\run.py --check-camera --camera 0 --backend dshow
```

- [新人交接、测试与常见错误](NEWCOMER_HANDOFF.md)
- [项目结构与数据流](PROJECT_STRUCTURE.md)
- [Windows 独立工程验收](docs/G2_WINDOWS_ACCEPTANCE_REPORT.md)
- [依赖和代码来源](docs/DEPENDENCIES_AND_SOURCES.md)

本轮清理后 **57 项测试通过**；同一真实录像30秒后1818帧的检测、轨迹及开启可选分支的视频与旧版一致，无旧源码/无Git导出也完成真实模型48帧验证。详细证据与未解决问题见验收报告。

当前仍属于 G2。原 RK3588 工程保留在既有历史分支，Windows 新工程不再运行或兼容那些模块。重构保持原检测/跟踪参数；**临时 ID 不是真实身份，测试通过不等于跟踪质量达标**。独立工程等待用户验收，之后才开始 ByteTrack 质量实验；不自动进入 G3、Homography、TCN 或 ReID。
