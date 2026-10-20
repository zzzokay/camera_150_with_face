# 依赖与代码来源

文件作用：记录Windows工程提取范围、第三方依赖和许可证；更改算法/依赖时更新，配合结构与验收报告阅读。

原工程由用户指定：https://github.com/zzzokay/camera_150_with_face 。上游基线5bd9c5a，重构前G2基线cc87e85；未发现项目级LICENSE，本次保留来源记录，不代替原作者授予许可。

| 新模块 | 来源与处理 |
|---|---|
| contracts/sources/detector/policy/tracker/outputs | 原camera_150/windows_pipeline；保留有效行为，解除旧目录依赖 |
| preprocessing | 原base的普通单相机NPZ/remap；独立实现，不带设备/RKNN/OpenCL全局副作用 |
| baseline | 原base的WideDetection/转换/SmoothTracks及G2对照适配器；仅可选旧算法对照 |
| rules/analysis,motion | predict1_weighted/predict1_director实际调用闭包；相同名称按原Python最后定义的实际语义，去掉未调用绘图/采集工具 |
| rendering | G0已提取的纯裁切/比例函数与本地坐标工具；不复制旧入口 |
| records/pipeline | 原记录器合并、可选分支与配置入口重构；旧检测/QC schema保留 |
| tests/fixtures | cc87e85算法在重构前生成的180帧合成结果，无用户视频/身份数据 |

| 依赖 | 来源 / 许可与用途 |
|---|---|
| Ultralytics 8.3.225 | https://github.com/ultralytics/ultralytics ，AGPL-3.0/另有商业授权；YOLO与ByteTrack，仅调用库API，未复制源码 |
| lap 0.5.12 | https://github.com/gatagat/lap ，BSD-2-Clause；线性分配 |
| PyTorch/TorchVision | https://pytorch.org ，BSD类许可；CPU推理 |
| OpenCV Python | https://github.com/opencv/opencv-python ，OpenCV Apache-2.0及wheel内第三方许可；读写/绘图/镜头处理 |
| NumPy/PyYAML/pytest | BSD/MIT/MIT；数组、配置和测试 |
| 用户best.pt及录像 | 用户授权本地测试；模型训练来源/资产授权细节未核实，不提交或公开 |

锁文件为Windows Python3.11 CPU环境，不承诺CUDA兼容。项目不需要外部FFmpeg、Qt、RKNN或Linux音频工具；OpenCV wheel自己的FFMPEG后端提供本地视频编解码。无音轨，mp4v不等于H.264。
原历史仍包含旧上游资产；本次只清理新分支版本树，不改写或宣称净化了全部Git历史。
