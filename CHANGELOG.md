# 变更记录

文件作用：记录每次变更原因、影响路径、实际验证、兼容风险和回退方法。代码/配置/验证结论变化后更新，和 STAGE_PROGRESS.md、验收报告保持一致。

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
