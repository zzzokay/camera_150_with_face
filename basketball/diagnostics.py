r"""
文件作用：独立环境、依赖和 Windows 相机诊断，不保存相机图像。
调用入口：根 run.py；本文件是库模块，不直接执行。
输入/输出及边界：见公开类/函数的中文说明；坐标为全幅像素、时间为源秒，ID 是临时编号。
快速测试（PowerShell，项目根目录）：.\.venv\Scripts\python.exe -X utf8 -m pytest tests/test_windows_components.py -q
预期输出：pytest 结果；日常运行结果在 configs/local.yaml 指定的输出目录。
排错：缺依赖用同一独立解释器安装 requirements-windows.lock.txt；输入/格式说明见 NEWCOMER_HANDOFF.md。
"""
import importlib.metadata
import json
import platform
import shutil
import subprocess
import sys


def collect_environment() -> dict:
    """获取真实版本和可用性；缺硬件、命令或包时记录错误，不猜测 GPU 能力。"""
    result = {"platform": platform.platform(), "python": sys.version,
              "executable": sys.executable, "packages": {}, "ffmpeg_executable": shutil.which("ffmpeg")}
    for name in ("torch", "torchvision", "numpy", "opencv-python", "ultralytics", "lap", "PyYAML", "pytest"):
        try:
            result["packages"][name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            result["packages"][name] = "missing"
    try:
        import torch
        result["torch_runtime"] = {"version": torch.__version__, "cuda_available": torch.cuda.is_available(),
                                    "cuda_build": torch.version.cuda}
    except Exception as exc:
        result["torch_error"] = str(exc)
    try:
        import cv2
        result["opencv_version"] = cv2.__version__
        result["opencv_videoio_build"] = [line.strip() for line in cv2.getBuildInformation().splitlines()
                                           if any(key in line for key in ("FFMPEG:", "DirectShow:", "Media Foundation:", "GUI:"))]
    except Exception as exc:
        result["opencv_error"] = str(exc)
    if sys.platform == "win32":
        command = "Get-CimInstance Win32_VideoController | Select-Object Name,DriverVersion | ConvertTo-Json -Compress"
        try:
            process = subprocess.run(["powershell.exe", "-NoProfile", "-Command", command],
                                      capture_output=True, text=True, timeout=20)
            result["video_controllers"] = json.loads(process.stdout) if process.returncode == 0 else process.stderr
        except Exception as exc:
            result["hardware_error"] = str(exc)
    return result


from .sources import VideoSource
import cv2


def check_camera(camera: int, backend: str, preview: bool = False) -> dict:
    """读取3帧验证相机；只保存诊断数值，不写画面，时间是收帧时间。"""
    report = {"camera": camera, "backend": backend, "saved_images": False,
              "preview_requested": preview, "status": "FAILED"}
    try:
        with VideoSource(None, camera, backend, fps=30, width=640, height=360) as source:
            packets = [source.read() for _ in range(3)]
            times = [packet.timestamp_sec for packet in packets]
            if not all(later > earlier for earlier, later in zip(times, times[1:])):
                raise RuntimeError(f"收帧时间未递增：{times}")
            report.update(opened=True, read_frames=3, timestamps_sec=times, reported_fps=source.fps,
                          frame_size=[packets[-1].image_bgr.shape[1], packets[-1].image_bgr.shape[0]],
                          timestamp_basis="capture_monotonic (perf_counter; receipt time)")
            if preview:
                cv2.imshow("Basketball camera probe - no images saved", packets[-1].image_bgr)
                cv2.waitKey(500)
                report["window_visible_api"] = cv2.getWindowProperty("Basketball camera probe - no images saved", cv2.WND_PROP_VISIBLE) > 0
            report["status"] = "COMPLETED"
    except Exception as exc:
        report["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        if preview:
            cv2.destroyAllWindows()
    return report
