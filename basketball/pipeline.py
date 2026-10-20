r"""
文件作用：组织 Windows 文件/相机 → 一次 YOLO → 可选 ByteTrack → 记录与可视化。
调用入口：根 run.py；本文件不是独立程序。导播与旧关联默认关闭，开启时才导入。
输入：RunConfig；输出：唯一 runs 子目录、视频、QC、summary/log；不覆盖旧产物。
快速测试：.\.venv\Scripts\python.exe -X utf8 -m pytest tests/test_real_model.py -q
必需输入：设置 BASKETBALL_TEST_WEIGHTS / BASKETBALL_TEST_VIDEO；缺输入时测试标为 skip，不能计作通过。
排错：先查 source/weights，再查 summary 的 error 与 run.log。视频完整解码通过只证明保存正常。
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

from .config import RunConfig, validate_config
from .detector import YoloDetector, validate_weights
from .records import DetectionRecords, TrackingRecords
from .outputs import SavedVideo, draw_detection_overview, draw_tracking_overview, verify_video
from .preprocessing import FramePreprocessor
from .sources import VideoSource


def run_pipeline(config: RunConfig) -> Path:
    """从指定源时间执行真实管线并返回运行目录；起点越界或失败时保留失败报告并抛异常。"""
    # 先检查本地权重，不向 Ultralytics 传入不存在的文件名，防止自动下载。
    validate_config(config)
    validate_weights(config.weights)
    g2 = config.mode == "track"
    if g2 and config.detect_interval != 1:
        raise ValueError('G2 ByteTrack 要求 detect_interval=1，禁止复用检测作新观测')
    prefix = config.mode
    run_dir = config.output_dir / (prefix + datetime.now().strftime("_%Y%m%d_%H%M%S_") + uuid.uuid4().hex[:8])
    run_dir.mkdir(parents=True, exist_ok=False)
    handler = logging.FileHandler(run_dir / "run.log", encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logging.getLogger().addHandler(handler)
    report = {"schema_version": "windows_run_v1", "status": "RUNNING", "config": config.serializable(),
              "command_argv": sys.argv, "processed_frames": 0, "inference_calls": 0,
              "true_person_observations": 0, "frames_reusing_detections": 0,
              "first_detection": None, "outputs": [], "stop_reason": None}
    start = time.perf_counter()
    inference_ms = []
    try:
        policy = config.detection
        tracking_policy = None
        if g2:
            from .tracker import PersonByteTracker
            tracking_policy = config.tracking
            if policy.ball.enabled:
                raise ValueError('本轮 G2 仅验人物跟踪，篮球按用户要求暂缓；请保持 ball.enabled=false')
            if abs(policy.person.confidence - tracking_policy.track_high_thresh) > 1e-8:
                raise ValueError('person.confidence 必须与 track_high_thresh 一致，避免两阶段门槛歧义')
        report["detection_policy"] = policy.serializable()
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
            detector = YoloDetector(config.weights, config.device, config.imgsz, config.iou, policy,
                                    person_tracking_confidence=tracking_policy.track_low_thresh if g2 else None)
            report["model"] = {"path": str(detector.weights), "sha256": detector.sha256,
                                "names": detector.names, "person_class_ids": detector.person_ids,
                                "device": config.device, "canonical_class_ids": detector.class_ids}
            logging.info("真实模型类别：%s；人物类别 ID：%s", detector.names, detector.person_ids)
            logging.info("篮球检测：%s", "启用" if policy.ball.enabled else "未启用（不生成位置）")
            report["detection_summary"] = {
                name: {"enabled": getattr(policy, name).enabled, "candidates": 0, "accepted": 0,
                       "rejected_by_reason": {}, "frames_with_detections": 0,
                       "frames_without_detections": 0 if getattr(policy, name).enabled else None}
                for name in ("person", "ball")
            }
            director = baseline = None
            if config.director_enabled:
                from .director import RuleDirector
                director = RuleDirector(config.view_width, config.view_height)
            tracker = PersonByteTracker(tracking_policy, source.fps) if g2 else None
            if config.baseline_enabled:
                from .baseline import SmoothTracksBaseline
                baseline = SmoothTracksBaseline(config.smooth, config.max_match_dist, config.max_missing)
            report['optional_outputs'] = {'director_enabled': director is not None, 'baseline_enabled': baseline is not None}
            tracking_stats = {'matched_observations': 0, 'high_matches': 0, 'low_matches': 0,
                              'frames_without_confirmed_track': 0, 'baseline_observations': 0}
            seen_ids, baseline_ids = set(), set()
            if g2:
                report['tracker'] = tracker.metadata()
                report['baseline'] = {'enabled': baseline is not None, 'implementation': 'local extracted SmoothTracks' if baseline else None, 'smooth': config.smooth,
                                      'max_match_dist_px': config.max_match_dist, 'max_missing_frames': config.max_missing,
                                      'input_confidence': policy.person.confidence}
                report['model']['yolo_inference_confidence'] = detector.confidence
                logging.info('G2 ByteTrack：高/低阈值 %.2f/%.2f，名义 FPS %.6f，单次推理供两个独立对照',
                             tracking_policy.track_high_thresh, tracking_policy.track_low_thresh, source.fps)
            suffix = ".mp4" if config.codec == "mp4v" else ".avi"
            program = stack.enter_context(SavedVideo(run_dir / ("director" + suffix), source.fps,
                                                       (config.view_width, config.view_height), config.codec)) if director else None
            overview = stack.enter_context(SavedVideo(run_dir / ("overview" + suffix), source.fps,
                                                        (w, h), config.codec)) if config.debug_video else None
            comparison_size = (w, h // 4 * 2)
            comparison = stack.enter_context(SavedVideo(run_dir / ('tracking_comparison' + suffix), source.fps,
                                                        comparison_size, config.codec)) if baseline and config.debug_video else None
            records = stack.enter_context(DetectionRecords(run_dir / "detections.jsonl")) if config.export_detections else None
            tracking_records = stack.enter_context(TrackingRecords(run_dir, baseline_enabled=baseline is not None)) if g2 else None
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
                    report["true_person_observations"] += sum(d.class_name == "person" for d in last_detections)
                    for name in ("person", "ball"):
                        stats = report["detection_summary"][name]
                        count = sum(d.class_name == name for d in last_detections)
                        stats["candidates"] += detector.last_candidate_counts[name]
                        stats["accepted"] += count
                        if stats["enabled"]:
                            stats["frames_with_detections"] += int(count > 0)
                            stats["frames_without_detections"] += int(count == 0)
                        for rejection in detector.last_rejections:
                            if rejection["class_name"] == name:
                                reason = rejection["reason"]
                                stats["rejected_by_reason"][reason] = stats["rejected_by_reason"].get(reason, 0) + 1
                    if last_detections and report["first_detection"] is None:
                        report["first_detection"] = {**asdict(last_detections[0]),
                            "source_frame_idx": packet.source_frame_idx, "timestamp_sec": packet.timestamp_sec}
                else:
                    report["frames_reusing_detections"] += 1
                # 复用的框属于历史观测，不把当前帧标成新的真实检测。
                current_detections = last_detections if observed else [
                    replace(detection, observed=False) for detection in last_detections
                ]
                if records:
                    records.write(packet, preprocessor.coord_system, observed, current_detections,
                                  detector.last_rejections, policy.ball.enabled, last_detect_idx)
                byte_tracks = baseline_tracks = None
                if g2:
                    byte_tracks = tracker.update(detector.last_tracking_detections, packet.source_frame_idx,
                                                 packet.timestamp_sec, (w, h), frame)
                    if tracker.last_info['reset_reason']:
                        if baseline:
                            baseline.reset()
                        if director:
                            director = RuleDirector(config.view_width, config.view_height)
                    baseline_tracks = baseline.update(current_detections, tracker.segment_id) if baseline else []
                    tracking_records.write(packet, byte_tracks, baseline_tracks, tracker.last_info)
                    tracking_stats['matched_observations'] += len(byte_tracks)
                    tracking_stats['high_matches'] += sum(t.association_stage == 'high' for t in byte_tracks)
                    tracking_stats['low_matches'] += sum(t.association_stage == 'low' for t in byte_tracks)
                    tracking_stats['frames_without_confirmed_track'] += int(not byte_tracks)
                    tracking_stats['baseline_observations'] += len(baseline_tracks)
                    seen_ids.update((t.segment_id, t.track_id) for t in byte_tracks)
                    baseline_ids.update((t.segment_id, t.track_id) for t in baseline_tracks)
                if (frame.shape[1], frame.shape[0]) != (w, h):
                    raise ValueError('视频中途分辨率变化，请拆段处理')
                view, crop, info = None, None, None
                if director:
                    view, crop, _, info = director.process(frame, current_detections, tracked_persons=byte_tracks)
                first_crop = crop if first_crop is None else first_crop
                changed_crop_frames += int(crop != first_crop)
                if program:
                    program.write(view)
                debug = None
                if overview or config.preview:
                    if g2:
                        debug = draw_tracking_overview(frame, byte_tracks, crop, packet.source_frame_idx,
                                                       packet.timestamp_sec, policy, info=tracker.last_info)
                        if comparison:
                            old_debug = draw_tracking_overview(frame, baseline_tracks, crop, packet.source_frame_idx,
                                                               packet.timestamp_sec, policy, title='SmoothTracks baseline',
                                                               info=tracker.last_info)
                            panel_size = (w // 2, comparison_size[1])
                            comparison.write(cv2.hconcat([cv2.resize(old_debug, panel_size), cv2.resize(debug, panel_size)]))
                    else:
                        debug = draw_detection_overview(frame, current_detections, detector.last_rejections, crop,
                                                       packet.source_frame_idx, observed,
                                                       packet.source_frame_idx - last_detect_idx, policy)
                if overview:
                    overview.write(debug)
                report["processed_frames"] += 1
                report["last_source_frame_idx"] = packet.source_frame_idx
                report["last_timestamp_sec"] = packet.timestamp_sec
                report["last_crop_full_frame_xyxy"] = crop
                if config.preview:
                    preview_width = min(1280, w)
                    cv2.imshow("Basketball overview - q to stop", cv2.resize(debug, (preview_width, round(h * preview_width / w))))
                    if director:
                        cv2.imshow("Basketball director - q to stop", view)
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
            if records:
                report["detection_records"] = {"path": str(records.path), "rows": records.count,
                                                 "schema_version": "g1_detections_v1"}
            if g2:
                tracking_stats.update(unique_segment_track_ids=len(seen_ids), baseline_unique_segment_track_ids=len(baseline_ids),
                                      qc_frames=tracking_records.frame_count, csv_rows=tracking_records.byte_rows,
                                      baseline_csv_rows=tracking_records.baseline_rows)
                report['tracking_summary'] = tracking_stats
                report['tracker'] = tracker.metadata()
        # 资源已关闭：用真正解码检查保存成功，而不是只判断文件存在。
        for writer in (program, overview, comparison):
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
        report['runtime_project_modules'] = sorted(name for name in sys.modules if name == 'basketball' or name.startswith('basketball.'))
        report['forbidden_runtime_modules'] = sorted(name for name in sys.modules if name.split('.')[0] in {'camera_150', 'windows_camera_150_client', 'rknnlite', 'PyQt5'})
        report["total_wall_sec"] = time.perf_counter() - start
        report["mean_inference_ms_including_warmup"] = sum(inference_ms) / len(inference_ms) if inference_ms else None
        report["inference_times_ms"] = inference_ms
        with (run_dir / "summary.json").open("w", encoding="utf-8") as stream:
            json.dump(report, stream, ensure_ascii=False, indent=2)
        logging.getLogger().removeHandler(handler)
        handler.close()
    return run_dir
