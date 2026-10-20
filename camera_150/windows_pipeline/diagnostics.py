"""
文件作用：记录本机 Windows/Python/依赖/硬件及模型文件清单，不加载任何权重。
输入：可选模型目录；输出：JSON 可序列化环境报告，缺依赖明确标为 missing。
依赖：标准库，探测时可选导入 torch/cv2；调用关系：check_windows_environment.py / run。
运行示例：见 NEWCOMER_HANDOFF.md；文件清单不反序列化 .pth/.pt。
"""
import argparse
import importlib.metadata
import json
import platform
import shutil
import subprocess
import sys
from pathlib import Path


def collect_environment(model_dir: Path | None = None) -> dict:
    """获取真实版本和可用性；缺硬件、命令或包时记录错误，不猜测 GPU 能力。"""
    result = {"platform": platform.platform(), "python": sys.version,
              "executable": sys.executable, "packages": {}, "ffmpeg_executable": shutil.which("ffmpeg")}
    for name in ("torch", "torchvision", "numpy", "opencv-python", "ultralytics", "PyYAML", "pytest"):
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
    if model_dir:
        if not model_dir.is_dir():
            result["model_inventory_error"] = f"目录不存在：{model_dir}"
        else:
            files = sorted(path for path in model_dir.rglob("*") if path.is_file())
            result["model_inventory"] = [{"path": str(path.relative_to(model_dir)), "bytes": path.stat().st_size,
                                           "suffix": path.suffix} for path in files]
            result["yolo_candidates"] = [str(path) for path in files if path.suffix.lower() in (".pt", ".onnx")]
    return result


def main(argv=None) -> int:
    """输出 JSON；--output 拒绝覆盖，返回 0 仅表示检查执行完，不表示 G0 通过。"""
    parser = argparse.ArgumentParser(description="G0 环境/模型清单检查（不加载模型）")
    parser.add_argument("--model-dir", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    report = collect_environment(args.model_dir)
    value = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x", encoding="utf-8") as stream:
            stream.write(value + "\n")
    print(value)
    return 0
