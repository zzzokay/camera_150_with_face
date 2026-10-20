# G2 跟踪接口与验收记录

文件作用：供调参、验收与下一关开发者理解 ByteTrack 输入、时间处理及 QC 文件。接口变化时同步本文、测试和 NEWCOMER_HANDOFF.md；这不是 G3 可训练数据集规范。

## 算法与调用边界

旧 `single_rknn_base.SmoothTracks.update` 按脚底点距离贪心关联，并平滑框；已有临时 ID，并非原来无跟踪。
新 `tracker.PersonByteTracker` 封装安装包中的 `ultralytics.trackers.byte_tracker.BYTETracker`（8.3.225，AGPL-3.0），使用 Kalman 运动预测、框重叠匹配和高/低置信两阶段关联。它不使用球衣外观或人脸，所以多人重叠、快速移动时仍可能换号。

```text
完整 BGR 帧 → 一次 YOLO（最低置信度 .10）
              ├→ 人物 .35 + ROI/尺寸 → G1 检测审计、旧 SmoothTracks 对照
              └→ 人物 .10 + 同一 ROI/尺寸 → ByteTrack
                    ├→ .35 及以上优先匹配/建立轨迹
                    └→ .10–.35 仅续接已有轨迹
                  → TrackedPerson → 原热点/运镜（跳过旧 SmoothTracks）
```

低阈值增加的是同一次 YOLO 保留下来的候选，不再次推理。G1 的 `detections.jsonl` 仍按 .35 接受；其中 `reason=confidence` 的候选可能用于 G2 低置信续接，两者筛选目的不同。ROI/尺寸失败者不会进入人物跟踪。`track_low_thresh` 边界由固定库使用严格 `>` 判断。
只创建一个人物 ByteTrack 实例；ball 不会进入此实例。用户要求篮球暂缓，当前 G2 若配置 ball.enabled=true 会明确报错；没有将人物中心当篮球或声称篮球跟踪已通过。

`TrackedPerson.detection` 是当帧真实观测，保留真实类别编号、置信度及原框；`bbox_xyxy` 是 Kalman 更新后的估计框。两者都在完整输入图像像素空间。当前 `none` 模式为 `raw_full_frame_px`，不谎称已去畸变或球场米制。
`track_id` 为临时编号；用运行目录 + `segment_id` + `track_id` 标识一个轨迹段。它不是球衣号码/球队/实名。库不提供单独的“跟踪置信度”，不制造此字段。

## 时间、缺失与重置

- G2 强制 `detect_interval=1`，每源帧一次真实推理。相同或倒序源帧号/时间直接报错；复用 Detection.observed=false 也不能进入 ByteTrack。
- 库的 Kalman 模型按固定一步时间推进，并非任意 Δt 的连续时间模型。使用源名义 FPS；短 PTS 间隔按 `round(Δt×fps)-1` 次空观测推进，时间间隔超过 .5 秒开启新 segment。本次顺序室内片段没有额外空更新或时间回退。高变帧率、慢速相机仍需另测，不能据本片宣称任意变帧率正确。
- `track_buffer=30` 是 Ultralytics 的 30 FPS 等效缓冲；库转换为 `int(fps/30×30)`。本片 24.032997 FPS 对应 24 步，约 .9986 秒。丢失期间内部保留预测状态，但 CSV/视频不输出失踪预测位置为真实观测；重现时允许续接原 ID，过久则可能新编号。
- 每次 run 新建会话。明显场景切换由低分辨率 HSV 直方图 Bhattacharyya 距离 > .65 触发重置，也同步重置对照和导播状态。它是启发式，闪光、相似镜头、缓慢转场仍可能误判/漏判；支持 `reset()` 显式新场次。
- Ultralytics 使用进程内 ID 计数器；当前支持单个主会话、每次运行独立进程，不承诺同一进程并发多个 tracker 的编号隔离。
- `BYTETracker.update` 的末尾 idx 相对于高/低阶段子集；适配器按阶段还原观测引用，测试用打乱顺序的高/低框验证，不能直接把 idx 当原人物列表索引。

## 参数与调试

`configs/tracking.example.yaml` 记录全部实测参数：high=.35、low=.10、new=.35、match=.8、buffer=30、fuse_score=true、gap=.5 秒、scene=.65。
高阈值必须等于当前 person.confidence；配置会检查两者一致。`match_thresh` 为关联代价上限，不能误读成 IoU 最小值。修改任一阈值后需用同片段复验，不能只用“ID 总数下降”判定效果更好。
G2 的旧算法 ID 对照要求 `smooth > 1e-6`；原算法在 0 时关闭编号，因此 G2 会明确拒绝，G0/G1 仍保留原有关闭行为。
`lap==0.5.12` 已作为明确依赖加入；仅在构建跟踪器时导入 ByteTrack，G0/G1 不需要启动跟踪器。运行前检查 lap 是否存在，避免 Ultralytics 的隐式自动安装。当前锁定 Ultralytics API 版本，升级会明确要求复核。

## QC 文件（g2_tracking_qc_v1）

| 文件 | 一行的含义 |
|---|---|
| `bytetrack_qc.csv` | 一次 ByteTrack 已确认轨迹与真实当前观测的匹配；不是每人每帧必有一行 |
| `smoothtracks_qc.csv` | 同一 YOLO 高阈值人物观测的旧关联结果 |
| `tracking_audit.jsonl` | 每处理帧一行，含两个独立结果、lost_ids、未确认轨迹数、segment/重置原因、球关闭状态 |

CSV 字段：schema_version、segment_id、source_frame_idx、timestamp_sec（源秒数，不从选段归零）、track_id、class_name、model_class_id、confidence（检测置信度）、observed、track_state、association_stage、det_x1/y1/x2/y2、track_x1/y1/x2/y2、coord_system。
`det_*` 是原始检测；`track_*` 是滤波估计。当前所有导出行 observed=true、track_state=tracked；丢失只在逐帧 QC 中列出 ID，不写空中预测框。`association_stage=high/low/legacy_distance`。
视频右侧/overview 为 ByteTrack，H/L 是高/低阶段；左侧旧算法标签 L 是 legacy_distance，不是低置信阶段。青色裁切框统一显示当前 ByteTrack 导播窗口，只对比关联，不在左图运行第二套导播。
暂定同步写盘，写入失败使运行失败；离线不丢帧。本关没有异步数据队列、G3 数据集冻结、独立重放工具、速度或训练标签；CSV 仅用于 G2 的强制 ID 验收。

## 真实首条结果（四舍五入展示）

源帧 723，30.0101 秒，segment=1，person，model_class_id=0，track_id=1，confidence=.77639443，原框/首帧状态框均为 `[147.12109,806.74658,214.21945,971.20056]`，observed=true，association_stage=high，coord_system=raw_full_frame_px。
准确原精度见验收目录 CSV/JSONL，球字段均 disabled/false/null。后续 G3 可消费 TrackedPerson 并另定义可复现轨迹规范，不直接把 QC 当训练真值。
