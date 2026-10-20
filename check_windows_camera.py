"""
文件作用：G0 摄像头打开/读帧/可选预览检查，不加载模型、不保存摄像头画面。
输入：Windows 设备编号、捕获后端；输出：JSON 检查结果，可选保存报告。
依赖：OpenCV、VideoSource；运行：python -X utf8 check_windows_camera.py --camera 0 --preview。
注意：收帧时间不等于传感器曝光时间；预览外观仍需用户现场确认。
"""
import argparse
import json
from pathlib import Path

import cv2

from camera_150.windows_pipeline.sources import VideoSource


def main(argv=None) -> int:
    """读取 3 帧并检查时间递增；可选显示 0.5 秒，报告不包含图像或身份信息。"""
    parser = argparse.ArgumentParser(description="G0 相机检查（不保存画面）")
    parser.add_argument("--camera", type=int, default=0)
    parser.add_argument("--backend", choices=("auto", "dshow", "msmf"), default="dshow")
    parser.add_argument("--preview", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    if args.output and args.output.exists():
        parser.error("报告路径已存在，拒绝覆盖")
    report = {"camera": args.camera, "backend": args.backend, "saved_images": False,
              "preview_requested": args.preview, "status": "FAILED"}
    try:
        with VideoSource(None, args.camera, args.backend, fps=30, width=640, height=360) as source:
            packets = [source.read() for _ in range(3)]
            times = [packet.timestamp_sec for packet in packets]
            if not all(later > earlier for earlier, later in zip(times, times[1:])):
                raise RuntimeError(f"收帧时间未递增：{times}")
            report.update(opened=True, read_frames=3, timestamps_sec=times, reported_fps=source.fps,
                          frame_size=[packets[-1].image_bgr.shape[1], packets[-1].image_bgr.shape[0]],
                          timestamp_basis="capture_monotonic (perf_counter; receipt time)")
            if args.preview:
                cv2.imshow("G0 camera probe - no images saved", packets[-1].image_bgr)
                cv2.waitKey(500)
                report["window_visible_api"] = cv2.getWindowProperty("G0 camera probe - no images saved", cv2.WND_PROP_VISIBLE) > 0
            report["status"] = "COMPLETED"
    except Exception as exc:
        report["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        if args.preview:
            cv2.destroyAllWindows()
    value = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x", encoding="utf-8") as stream:
            stream.write(value + "\n")
    print(value)
    return 0 if report["status"] == "COMPLETED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
