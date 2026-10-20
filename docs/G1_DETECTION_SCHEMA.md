# G1 检测记录与篮球预留接口

文件作用：说明 g1_detections_v1 的字段、单位、缺失语义和未来篮球接入方法。给配置策略和读取 JSONL 的开发者使用；字段变化时同步本文件与测试。不是 G3 的轨迹/特征数据规范。

## 用户调整后的范围

用户已授权从 G0 进入下一步，并明确篮球检测暂缓，只留接口。本轮做人物筛选、逐帧检测记录和篮球关闭状态；不把“支持球类别映射”写成“已在真实篮球模型上通过”。G2 ByteTrack 尚未开始。

## 模型类别与策略

`YoloDetector` 从真实 `.pt` 的 `model.names` 找类别，标准名只有 `person`、`ball`；原始类别编号仍存入 `model_class_id`。例如单元测试中的 `Player` 可为 7、`Sports Ball` 可为 42，这些只是合成契约测试，不代表真实权重包含它们。实际用户权重只有 `{0: 'person'}`。
策略文件版本 `g1_detection_policy_v1`，两个类别各自有 `enabled`、`aliases`、`confidence`、`min_size_wh`、`max_size_wh`、`roi_polygon`。人物必须启用，篮球默认关闭。启用但权重没有对应类别时立即报错，不能悄悄继续或下载另一个模型。
每帧只做一次 YOLO：推理门槛取所有已启用类别阈值的最小值，之后按各类阈值独立筛选，不会让篮球阈值自动替代人物阈值。

尺寸 `[宽/全帧宽, 高/全帧高]`，例如 `min_size_wh: [0, 0.02]` 在 1080 高输入上要求框高至少 21.6 像素；不是 0.02 米。ROI 是 [0,1] 比例的凸多边形，人物检查框底部中心，球检查框中心。边界点保留，越界、零面积、自交或非凸配置会报错。
室内策略 ROI `[0,.70]–[1,.97]` 只是本次镜头上的画面区域示例，不是球场标定或球员身份。人物脚底可能因遮挡、框抖动、边线移动而进出区域，裁判在区域里也会保留。

未指定 `--detection-policy` 时默认人物阈值/别名仍来自原 `--confidence`、`--person-aliases`，无额外 ROI/尺寸限制；指定文件后，文件明示的同类字段覆盖这两个兼容默认值。实际完整策略写入 summary，不靠猜测优先级复现。

## 逐帧 JSONL

开启 `--export-detections` 后，在唯一运行目录创建 `detections.jsonl`，每个处理帧一行 UTF-8 JSON；同名文件禁止覆盖。结构为：

| 字段 | 含义 |
|---|---|
| `schema_version` | 固定 `g1_detections_v1` |
| `source_frame_idx` | 原视频从 0 起的源帧号，选段不归零 |
| `timestamp_sec` / `timestamp_basis` | 源时间（秒）与时间来源；选段不归零 |
| `frame_size_wh` | 完整输入画面 `[宽,高]`，像素 |
| `coord_system` | none 为 `raw_full_frame_px`；already/calibration 为 `undistorted_full_frame_px` |
| `inference_performed` | 本帧是否真的调用 YOLO |
| `detections` | 仅本帧新推理且通过筛选的框；复用帧为空列表 |
| `rejected_detections` | 本帧真实候选中被排除的框，附 `reason=confidence/size/roi`；复用帧为空 |
| `reused_from_source_frame_idx` | 无新推理时指向最近一次推理帧，否则 null；不把复用框计为新观测 |
| `ball_enabled` | 策略是否启用球；本轮一律 false |
| `ball_valid` | 本帧确有通过筛选的真实球候选才为 true；本轮一律 false |
| `ball_status` | disabled / not_observed / missing / detected，区别关闭、未推理、推理无球和真实候选 |
| `ball_centers_full_frame_px` | 真实球候选中心列表；无球为 null，不沿用上次位置或人物中心 |

每条 Detection 含 `class_name`、`model_class_id`、`confidence`、`bbox_xyxy=[x1,y1,x2,y2]`、`coord_system`、`observed`。存的是全幅像素，不是 1280×720 裁切图坐标；JSONL 中的观测 `observed=true`。导播中间帧仍可复用框，但这些帧只通过 `inference_performed=false` / `reused_from_source_frame_idx` 标明，不复制为新检测。
多个球候选全部保留，不能任取一个就声称找到比赛主球；本轮无真实球模型，球的阈值、尺寸、ROI 和可靠性均待之后实测。

`g1_run_v1` 报告中的 `detection_summary` 按类别统计候选总数、保留数、各排除原因、真实推理帧中有/无该类的帧数。篮球关闭时 `frames_without_detections=null`，不能把“未启用”伪装成模型漏检率；所有累计框数也不等于人数/准确率。

## 下次有篮球权重时

用户提供含真实球类别的 `.pt` 后，在自己的 `.local.yaml` 指向它，复制检测策略到本地文件并设置 `ball.enabled: true`，再用真实视频评估球阈值/尺寸/ROI。缺类别会显式报错；不能用本轮的合成接口测试替代此步骤。球框中心是二维图像位置，空中篮球不能直接当作球场地面点。
当前 JSONL 无 `track_id`、速度、实名或训练标签；后续用户批准 G2/G3 后再独立关联和定义轨迹表，不在当前关卡偷偷导出训练数据。
