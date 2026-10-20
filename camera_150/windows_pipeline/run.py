"""
文件作用：G0 Windows 本地视频/摄像头 -> 真实 YOLO -> 原规则 -> 视频保存的总入口。
输入：RunConfig；输出：唯一运行目录内的导播视频、调试视频、summary.json、run.log。
依赖：各 Windows 组件；RKNN、音频、Qt、RTSP 不进入默认离线流程。
调用关系：run_windows.py -> main -> run_pipeline -> sources/preprocess/detect/director/outputs。
运行示例：见根目录 NEWCOMER_HANDOFF.md；未提供真实模型/视频时以非零状态退出。
"""
import json
import logging
import sys
import time
import uuid
from contextlib import ExitStack
from dataclasses import asdict, replace
from datetime import datetime
from pathlib import Path

import cv2

from .config import RunConfig, load_config
from .detector import YoloPersonDetector, validate_weights
from .director_adapter import LegacyDirector
from .outputs import SavedVideo, draw_overview, verify_video
from .preprocessing import FramePreprocessor
from .sources import VideoSource


def run_pipeline(config: RunConfig) -> Path:
    """从指定源时间执行真实管线并返回运行目录；起点越界或失败时保留失败报告并抛异常。"""
    # 先检查本地权重，不向 Ultralytics 传入不存在的文件名，防止自动下载。
    validate_weights(config.weights)
    run_dir = config.output_dir / (datetime.now().strftime("g0_%Y%m%d_%H%M%S_") + uuid.uuid4().hex[:8])
    run_dir.mkdir(parents=True, exist_ok=False)
    handler = logging.FileHandler(run_dir / "run.log", encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logging.getLogger().addHandler(handler)
    report = {"schema_version": "g0_run_v1", "status": "RUNNING", "config": config.serializable(),
              "command_argv": sys.argv, "processed_frames": 0, "inference_calls": 0,
              "true_person_observations": 0, "frames_reusing_detections": 0,
              "first_detection": None, "outputs": [], "stop_reason": None}
    start = time.perf_counter()
    inference_ms = []
    try:
        preprocessor = FramePreprocessor(config.undistort, config.calib_file)
        logging.info("输出目录：%s", run_dir)
        with ExitStack() as stack:
            source = stack.enter_context(VideoSource(config.source, config.camera, config.backend,
                                                     config.fps, config.camera_width, config.camera_height))
            packet = source.read()
            # 顺序解码跳过片头：以实际时间戳而非平均 FPS 估算边界，兼容录屏的变帧率。
            # 跳过的帧不做 YOLO/规则处理、不写输出，源帧号与源时间保持不变。
            while packet is not None and packet.timestamp_sec < config.start_seconds:
                packet = source.read()
            if packet is None:
                raise ValueError(f"输入在起始时间 {config.start_seconds:g} 秒后没有可解码的视频帧")
            first_frame = preprocessor.apply(packet.image_bgr)
            h, w = first_frame.shape[:2]
            if config.debug_video and (w % 2 or h % 2):
                raise ValueError("广角调试视频要求源宽高为偶数；请用 --no-debug-video 保持原图推理")
            report["source"] = {"fps": source.fps, "frame_size": [w, h],
                                 "metadata_frame_count": source.frame_count, "backend": source.backend_name,
                                 "undistort_declaration": config.undistort,
                                 "skipped_frames": packet.source_frame_idx,
                                 "first_source_frame_idx": packet.source_frame_idx,
                                 "first_timestamp_sec": packet.timestamp_sec}
            logging.info("片段起点：源帧 %d，源时间 %.6f 秒；跳过 %d 帧",
                         packet.source_frame_idx, packet.timestamp_sec, packet.source_frame_idx)
            detector = YoloPersonDetector(config.weights, config.device, config.imgsz,
                                           config.confidence, config.iou, config.person_aliases)
            report["model"] = {"path": str(detector.weights), "sha256": detector.sha256,
                                "names": detector.names, "person_class_ids": detector.person_ids,
                                "device": config.device}
            logging.info("真实模型类别：%s；人物类别 ID：%s", detector.names, detector.person_ids)
            director = LegacyDirector(config.view_width, config.view_height, config.smooth,
                                       config.max_match_dist, config.max_missing, config.game_state)
            suffix = ".mp4" if config.codec == "mp4v" else ".avi"
            program = stack.enter_context(SavedVideo(run_dir / ("director" + suffix), source.fps,
                                                       (config.view_width, config.view_height), config.codec))
            overview = stack.enter_context(SavedVideo(run_dir / ("overview" + suffix), source.fps,
                                                        (w, h), config.codec)) if config.debug_video else None
            last_detections = []
            last_detect_idx = packet.source_frame_idx
            first_crop = None
            changed_crop_frames = 0
            while packet is not None:
                frame = first_frame if report["processed_frames"] == 0 else preprocessor.apply(packet.image_bgr)
                # 每个片段首帧立即推理，防止从非 3 整数倍的源帧开始时先复用空结果。
                observed = report["processed_frames"] % config.detect_interval == 0
                if observed:
                    infer_start = time.perf_counter()
                    last_detections = detector.detect(frame, preprocessor.coord_system)
                    inference_ms.append((time.perf_counter() - infer_start) * 1000)
                    last_detect_idx = packet.source_frame_idx
                    report["inference_calls"] += 1
                    report["true_person_observations"] += len(last_detections)
                    if last_detections and report["first_detection"] is None:
                        report["first_detection"] = {**asdict(last_detections[0]),
                            "source_frame_idx": packet.source_frame_idx, "timestamp_sec": packet.timestamp_sec}
                else:
                    report["frames_reusing_detections"] += 1
                # 复用的框属于历史观测，不把当前帧标成新的真实检测。
                current_detections = last_detections if observed else [
                    replace(detection, observed=False) for detection in last_detections
                ]
                view, crop, smoothed, info = director.process(frame, current_detections)
                first_crop = crop if first_crop is None else first_crop
                changed_crop_frames += int(crop != first_crop)
                program.write(view)
                debug = None
                if overview or config.preview:
                    debug = draw_overview(frame, smoothed, crop, packet.source_frame_idx, observed,
                                          packet.source_frame_idx - last_detect_idx)
                if overview:
                    overview.write(debug)
                report["processed_frames"] += 1
                report["last_source_frame_idx"] = packet.source_frame_idx
                report["last_timestamp_sec"] = packet.timestamp_sec
                report["last_crop_full_frame_xyxy"] = crop
                if config.preview:
                    preview_width = min(1280, w)
                    cv2.imshow("G0 overview - q to stop", cv2.resize(debug, (preview_width, round(h * preview_width / w))))
                    cv2.imshow("G0 director - q to stop", view)
                    if cv2.waitKey(1) & 0xFF in (ord("q"), 27):
                        report["stop_reason"] = "preview_key"
                        break
                if config.max_frames and report["processed_frames"] >= config.max_frames:
                    report["stop_reason"] = "max_frames"
                    break
                if report["processed_frames"] % 30 == 0:
                    logging.info("已处理 %d 帧，真实推理 %d 次，人物观测 %d 个",
                                 report["processed_frames"], report["inference_calls"], report["true_person_observations"])
                packet = source.read()
            if report["stop_reason"] is None:
                report["stop_reason"] = "source_eof"
            report["timestamp_fallback_frames"] = source.fallback_count
            report["crop_changed_from_first_frames"] = changed_crop_frames
            report["processing_wall_sec"] = time.perf_counter() - start
        # 资源已关闭：用真正解码检查保存成功，而不是只判断文件存在。
        for writer in (program, overview):
            if writer:
                report["outputs"].append(verify_video(writer.path, writer.count, writer.size))
        report["status"] = "COMPLETED"
        logging.info("完整解码核验通过：%s", report["outputs"])
    except BaseException as exc:
        report["status"] = "INTERRUPTED" if isinstance(exc, KeyboardInterrupt) else "FAILED"
        report["error"] = f"{type(exc).__name__}: {exc}"
        logging.exception("管线未完成")
        raise
    finally:
        if config.preview:
            cv2.destroyAllWindows()
        report["total_wall_sec"] = time.perf_counter() - start
        report["mean_inference_ms_including_warmup"] = sum(inference_ms) / len(inference_ms) if inference_ms else None
        report["inference_times_ms"] = inference_ms
        with (run_dir / "summary.json").open("w", encoding="utf-8") as stream:
            json.dump(report, stream, ensure_ascii=False, indent=2)
        logging.getLogger().removeHandler(handler)
        handler.close()
    return run_dir


def main(argv=None) -> int:
    """命令行入口；成功返回 0，参数/推理/保存失败返回 1。"""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    try:
        config = load_config(argv)
        path = run_pipeline(config)
        logging.info("G0 本次运行完成：%s", path)
        return 0
    except KeyboardInterrupt:
        logging.error("用户中断；部分产物不能视为完整验收")
        return 130
    except Exception as exc:
        logging.error("%s: %s", type(exc).__name__, exc)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
