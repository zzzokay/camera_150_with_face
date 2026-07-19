#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
stop_all_techtable.py
=====================

一键停止篮球检录、自动导播、RTSP 和技术台相关进程。

优先停止 start_all_techtable.py 写入 PID 文件的进程：
    1. rk_techtable_panel.py
    2. single_rknn_director_view720_network_stream.py
    3. MediaMTX
    4. start_all_techtable.py 工作流 UI

如果 PID 文件丢失，会使用限定的命令行特征进行兜底查找。

运行：
    cd /home/elf/work/camera_150
    python3 stop_all_techtable.py
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import shutil
import signal
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Set


PROJECT_DIR = Path(__file__).resolve().parent
RUNTIME_DIR = PROJECT_DIR / "runtime"
PID_FILE = RUNTIME_DIR / "techtable_processes.json"
LAUNCHER_PID_FILE = RUNTIME_DIR / "start_all_techtable.pid"
ACTIVE_CHECKIN_FILE = RUNTIME_DIR / "active_checkin_session.json"
RTSP_PROBE_FILE = RUNTIME_DIR / "rtsp_probe.json"

STOP_ORDER = ["techtable", "director", "mediamtx"]

# 只有 PID 文件不可用或记录不完整时才使用这些规则。
# 规则尽量限定到本项目文件，避免误杀无关 Python 程序。
FALLBACK_PATTERNS = [
    ("技术台", "techtable_v2/rk_techtable_panel.py"),
    ("RKNN 导播推流", "single_rknn_director_view720_network_stream.py"),
    # FFmpeg 在导播脚本内部使用 start_new_session=True，属于独立进程组；
    # 导播异常退出时必须额外兜底，避免继续占用 hw:1,0 和 RTSP 发布端。
    ("FFmpeg 音视频推流", r"ffmpeg.*rtsp://127\.0\.0\.1:8554/director"),
    ("MediaMTX", "mediamtx_rk3588.yml"),
    ("旧版独立人脸识别", "face_checkin_lbph.*--mode[ =]recognize"),
    ("检录与导播工作流 UI", "start_all_techtable.py"),
]


def read_json(path: Path, default: Any) -> Any:
    try:
        with path.open("r", encoding="utf-8") as file:
            return json.load(file)
    except Exception:
        return default


def is_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def process_command(pid: int) -> str:
    try:
        result = subprocess.run(
            ["ps", "-p", str(pid), "-o", "args="],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            check=False,
        )
        return result.stdout.strip()
    except Exception:
        return ""


def terminate_pids(
    pids: Iterable[int],
    name: str,
    timeout: float = 3.0,
    use_process_group: bool = True,
) -> None:
    unique = sorted({int(pid) for pid in pids if int(pid) > 0 and int(pid) != os.getpid()})
    alive = [pid for pid in unique if is_alive(pid)]
    if not alive:
        print(f"[OK] 未发现运行中的{name}")
        return

    print(f"[STOP] {name}: PID={alive}")
    for pid in alive:
        command = process_command(pid)
        if command:
            print(f"       {pid}: {command}")
        try:
            if use_process_group:
                os.killpg(os.getpgid(pid), signal.SIGTERM)
            else:
                os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        except Exception:
            try:
                os.kill(pid, signal.SIGTERM)
            except Exception as exc:
                print(f"[WARN] PID {pid} SIGTERM 失败：{exc}")

    deadline = time.time() + timeout
    while time.time() < deadline:
        if not any(is_alive(pid) for pid in alive):
            break
        time.sleep(0.1)

    remaining = [pid for pid in alive if is_alive(pid)]
    for pid in remaining:
        print(f"[KILL] PID {pid} 未按时退出，发送 SIGKILL")
        try:
            if use_process_group:
                os.killpg(os.getpgid(pid), signal.SIGKILL)
            else:
                os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        except Exception:
            try:
                os.kill(pid, signal.SIGKILL)
            except Exception as exc:
                print(f"[WARN] PID {pid} SIGKILL 失败：{exc}")


def pgrep(pattern: str) -> List[int]:
    try:
        result = subprocess.run(
            ["pgrep", "-f", pattern],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            check=False,
        )
    except Exception:
        return []

    pids: List[int] = []
    protected = {os.getpid(), os.getppid()}
    for line in result.stdout.splitlines():
        try:
            pid = int(line.strip())
        except ValueError:
            continue
        if pid not in protected:
            pids.append(pid)
    return pids


def stop_from_pid_file() -> Set[int]:
    payload = read_json(PID_FILE, {})
    records: Dict[str, Dict[str, Any]] = payload.get("processes", {}) or {}
    handled: Set[int] = set()

    for name in STOP_ORDER:
        record = records.get(name)
        if not record:
            continue
        try:
            pid = int(record.get("pid", -1))
        except Exception:
            continue
        if pid <= 0:
            continue
        handled.add(pid)
        # 导播退出时还要停止内部 FFmpeg、释放摄像头和 NAU8822，
        # 因此给予更长的优雅退出时间。
        timeout = 8.0 if name == "director" else 3.0
        terminate_pids([pid], name, timeout=timeout)

    return handled


def stop_launcher() -> None:
    payload = read_json(LAUNCHER_PID_FILE, {})
    try:
        launcher_pid = int(payload.get("pid", -1))
    except Exception:
        launcher_pid = -1

    if launcher_pid > 0 and launcher_pid not in (os.getpid(), os.getppid()):
        # UI 本身不一定是独立进程组，不能 killpg，否则可能误伤启动它的终端。
        terminate_pids([launcher_pid], "工作流 UI", use_process_group=False)


def fallback_stop(already_handled: Set[int]) -> None:
    print("\n[兜底检查] 使用受限命令行规则查找残留进程")
    for name, pattern in FALLBACK_PATTERNS:
        pids = [pid for pid in pgrep(pattern) if pid not in already_handled]
        # pgrep 找到的进程不保证由 start_new_session 创建，兜底时只杀 PID。
        terminate_pids(pids, name, use_process_group=False)
        already_handled.update(pids)


def show_port_status() -> None:
    print("\n[端口检查]")
    lsof = shutil.which("lsof")
    if lsof:
        for port, name in ((8554, "RTSP"), (8010, "技术台")):
            print(f"--- {name} {port} ---")
            subprocess.run([lsof, f"-i:{port}"], check=False)
        return

    ss = shutil.which("ss")
    if ss:
        subprocess.run([ss, "-ltnp"], check=False)
    else:
        print("未找到 lsof 或 ss，跳过端口检查。")


def cleanup_pid_files() -> None:
    for path in (PID_FILE, LAUNCHER_PID_FILE):
        try:
            path.unlink()
        except FileNotFoundError:
            pass
        except Exception as exc:
            print(f"[WARN] 无法删除 {path}: {exc}")



def cleanup_transient_checkin_data() -> None:
    """
    删除当前场次的临时检录结果。

    会删除：
        - checkin_session_<match_id>.json；
        - 当天 CSV 中 match_id 等于当前场次的签到行；
        - runtime/active_checkin_session.json；
        - runtime/rtsp_probe.json。

    不会删除：
        - face_checkin/dataset；
        - face_checkin/trainer；
        - labels.json / lbph_model.yml；
        - roster_face_mapping.json；
        - 球员名单。
    """
    marker = read_json(ACTIVE_CHECKIN_FILE, {})
    match_id = str(marker.get("match_id", "")).strip()

    session_text = str(marker.get("session_path", "")).strip()
    if session_text:
        session_path = Path(session_text)
        try:
            session_path.unlink()
            print(f"[CLEAN] 已删除本场检录会话：{session_path}")
        except FileNotFoundError:
            pass
        except Exception as exc:
            print(f"[WARN] 无法删除检录会话 {session_path}: {exc}")

    for csv_text in marker.get("csv_paths", []) or []:
        csv_text = str(csv_text).strip()
        if not csv_text or not match_id:
            continue

        csv_path = Path(csv_text)
        if not csv_path.is_file():
            continue

        try:
            with csv_path.open(
                "r",
                encoding="utf-8-sig",
                newline="",
            ) as file:
                reader = csv.DictReader(file)
                fieldnames = list(reader.fieldnames or [])
                rows = [
                    row for row in reader
                    if str(row.get("match_id", "")).strip() != match_id
                ]

            if not fieldnames:
                csv_path.unlink()
                print(f"[CLEAN] 已删除无效检录 CSV：{csv_path}")
                continue

            if not rows:
                csv_path.unlink()
                print(f"[CLEAN] 已删除本场检录 CSV：{csv_path}")
                continue

            temp_path = csv_path.with_suffix(csv_path.suffix + ".tmp")
            with temp_path.open(
                "w",
                encoding="utf-8-sig",
                newline="",
            ) as file:
                writer = csv.DictWriter(file, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(rows)
            temp_path.replace(csv_path)
            print(
                f"[CLEAN] 已从 {csv_path.name} 删除场次 {match_id} 的检录行"
            )

        except Exception as exc:
            print(f"[WARN] 清理检录 CSV {csv_path} 失败：{exc}")

    for path in (ACTIVE_CHECKIN_FILE, RTSP_PROBE_FILE):
        try:
            path.unlink()
        except FileNotFoundError:
            pass
        except Exception as exc:
            print(f"[WARN] 无法删除 {path}: {exc}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="停止篮球检录、导播、RTSP 和技术台进程")
    parser.add_argument(
        "--no-fallback",
        action="store_true",
        help="只按 PID 文件停止，不使用 pgrep 兜底查找",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    print("=" * 68)
    print("停止篮球检录 / 自动导播 / RTSP / 技术台")
    print(f"工程目录：{PROJECT_DIR}")
    print("=" * 68)

    handled = stop_from_pid_file()

    # 先停止三个后台服务，最后再关闭工作流 UI。
    stop_launcher()

    if not args.no_fallback:
        fallback_stop(handled)

    cleanup_transient_checkin_data()
    cleanup_pid_files()
    show_port_status()

    print("=" * 68)
    print("停止流程完成。")
    print("=" * 68)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
