#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
一次性修改 camera_150_with_face 的启动与停止脚本。

运行：
    cd /home/elf/work/camera_150
    python3 apply_camera150_workflow_patch.py
"""

from __future__ import annotations

import argparse
import ast
import shutil
from pathlib import Path

START_REPLACEMENTS = [('增加场次标记和 RTSP 检测结果路径',
  'PID_FILE = RUNTIME_DIR / "techtable_processes.json"\n'
  'LAUNCHER_PID_FILE = RUNTIME_DIR / "start_all_techtable.pid"\n'
  'STREAM_DIR = Path.home() / "stream_server"\n',
  'PID_FILE = RUNTIME_DIR / "techtable_processes.json"\n'
  'LAUNCHER_PID_FILE = RUNTIME_DIR / "start_all_techtable.pid"\n'
  '\n'
  '# 当前场次的临时检录数据标记。\n'
  '# stop_all_techtable.py 根据它删除本场“已检录”数据，但不会删除人脸样本和模型。\n'
  'ACTIVE_CHECKIN_FILE = RUNTIME_DIR / "active_checkin_session.json"\n'
  '\n'
  '# 启动时 ffprobe 验证 RTSP 音视频轨道后保存的结果。\n'
  'RTSP_PROBE_FILE = RUNTIME_DIR / "rtsp_probe.json"\n'
  '\n'
  'STREAM_DIR = Path.home() / "stream_server"\n'),
 ('加入 RTSP AAC 音轨自动验收',
  '    def start_all(self) -> None:\n        mediamtx_binary = STREAM_DIR / "mediamtx"\n',
  '    def wait_for_rtsp_audio(\n'
  '        self,\n'
  '        url: str,\n'
  '        timeout: float = 18.0,\n'
  '    ) -> Dict[str, Any]:\n'
  '        """\n'
  '        使用 ffprobe 验证 RTSP 真正包含视频轨和音频轨。\n'
  '\n'
  '        OpenCV VideoCapture 只会读取视频，因此“预览连接成功”不能证明音频存在。\n'
  '        这里要求：\n'
  '            - 至少一条 video stream；\n'
  '            - 至少一条 AAC audio stream；\n'
  '            - 音频采样率为 48000 Hz；\n'
  '            - 音频通道数为 2。\n'
  '\n'
  '        验证结果写入 runtime/rtsp_probe.json，便于排查。\n'
  '        """\n'
  '        ffprobe = shutil.which("ffprobe")\n'
  '        if not ffprobe:\n'
  '            raise RuntimeError(\n'
  '                "找不到 ffprobe，无法确认 RTSP 音频是否存在。"\n'
  '                "请确认 ffmpeg/ffprobe 已正确安装。"\n'
  '            )\n'
  '\n'
  '        command = [\n'
  '            ffprobe,\n'
  '            "-v", "error",\n'
  '            "-rtsp_transport", "tcp",\n'
  '            "-show_entries",\n'
  '            "stream=index,codec_type,codec_name,sample_rate,channels",\n'
  '            "-of", "json",\n'
  '            url,\n'
  '        ]\n'
  '\n'
  '        deadline = time.monotonic() + max(1.0, float(timeout))\n'
  '        last_detail = "RTSP 尚未就绪"\n'
  '\n'
  '        while time.monotonic() < deadline:\n'
  '            try:\n'
  '                result = subprocess.run(\n'
  '                    command,\n'
  '                    stdout=subprocess.PIPE,\n'
  '                    stderr=subprocess.PIPE,\n'
  '                    text=True,\n'
  '                    check=False,\n'
  '                    timeout=4.0,\n'
  '                )\n'
  '            except subprocess.TimeoutExpired:\n'
  '                last_detail = "ffprobe 单次检测超时"\n'
  '                time.sleep(0.5)\n'
  '                continue\n'
  '            except Exception as exc:\n'
  '                last_detail = f"ffprobe 执行失败：{exc}"\n'
  '                time.sleep(0.5)\n'
  '                continue\n'
  '\n'
  '            if result.returncode != 0:\n'
  '                last_detail = result.stderr.strip() or f"ffprobe returncode={result.returncode}"\n'
  '                time.sleep(0.5)\n'
  '                continue\n'
  '\n'
  '            try:\n'
  '                payload = json.loads(result.stdout or "{}")\n'
  '            except Exception as exc:\n'
  '                last_detail = f"ffprobe JSON 解析失败：{exc}"\n'
  '                time.sleep(0.5)\n'
  '                continue\n'
  '\n'
  '            streams = payload.get("streams", []) or []\n'
  '            video_streams = [\n'
  '                stream for stream in streams\n'
  '                if str(stream.get("codec_type", "")).lower() == "video"\n'
  '            ]\n'
  '            audio_streams = [\n'
  '                stream for stream in streams\n'
  '                if str(stream.get("codec_type", "")).lower() == "audio"\n'
  '            ]\n'
  '\n'
  '            if not video_streams:\n'
  '                last_detail = f"RTSP 中没有视频轨：{streams}"\n'
  '                time.sleep(0.5)\n'
  '                continue\n'
  '\n'
  '            if not audio_streams:\n'
  '                last_detail = f"RTSP 中没有音频轨：{streams}"\n'
  '                time.sleep(0.5)\n'
  '                continue\n'
  '\n'
  '            audio = audio_streams[0]\n'
  '            codec = str(audio.get("codec_name", "")).lower()\n'
  '            sample_rate_text = str(audio.get("sample_rate", "")).strip()\n'
  '            channels_text = str(audio.get("channels", "")).strip()\n'
  '\n'
  '            if codec != "aac":\n'
  '                raise RuntimeError(\n'
  '                    f"RTSP 已发现音频轨，但编码不是 AAC：{audio}"\n'
  '                )\n'
  '\n'
  '            if sample_rate_text and int(sample_rate_text) != 48000:\n'
  '                raise RuntimeError(\n'
  '                    f"RTSP 音频采样率不是 48000 Hz：{audio}"\n'
  '                )\n'
  '\n'
  '            if channels_text and int(channels_text) != 2:\n'
  '                raise RuntimeError(\n'
  '                    f"RTSP 音频不是双声道：{audio}"\n'
  '                )\n'
  '\n'
  '            verified = {\n'
  '                "verified_at": datetime.now().isoformat(timespec="seconds"),\n'
  '                "url": url,\n'
  '                "video": video_streams[0],\n'
  '                "audio": audio,\n'
  '                "all_streams": streams,\n'
  '            }\n'
  '            atomic_write_json(RTSP_PROBE_FILE, verified)\n'
  '            print(\n'
  '                "[RTSP 验证] 正常："\n'
  '                f"video={video_streams[0].get(\'codec_name\')}，"\n'
  '                f"audio={codec}/{sample_rate_text or \'?\'}Hz/"\n'
  '                f"{channels_text or \'?\'}ch"\n'
  '            )\n'
  '            return verified\n'
  '\n'
  '        raise RuntimeError(\n'
  '            "RTSP 音视频验收失败。\\n"\n'
  '            "要求：H.264 视频 + AAC 48000 Hz 双声道。\\n"\n'
  '            f"最后一次检测结果：{last_detail}\\n"\n'
  '            f"请查看：{LOG_DIR / \'director.log\'} 和 "\n'
  '            "camera_movement_modified/stream_logs/*.ffmpeg.log"\n'
  '        )\n'
  '\n'
  '    def start_all(self) -> None:\n'
  '        mediamtx_binary = STREAM_DIR / "mediamtx"\n'),
 ('启动技术台前验证 RTSP 音视频',
  '            self._start_one("director", *commands["director"], env)\n'
  '            time.sleep(2.0)\n'
  '            self._start_one("techtable", *commands["techtable"], env)\n',
  '            self._start_one("director", *commands["director"], env)\n'
  '\n'
  '            # 必须先确认 RTSP 中既有视频也有 AAC 音频，才能进入正式技术台。\n'
  '            self.wait_for_rtsp_audio(\n'
  '                "rtsp://127.0.0.1:8554/director",\n'
  '                timeout=18.0,\n'
  '            )\n'
  '\n'
  '            self._start_one("techtable", *commands["techtable"], env)\n'),
 ('延长导播与音频链路优雅退出时间',
  '        deadline = time.time() + 3.0\n',
  '        # 导播进程收到 SIGTERM 后需要停止 FFmpeg、释放摄像头和 NAU8822。\n'
  '        # 3 秒可能导致过早 SIGKILL，因此延长到 8 秒。\n'
  '        deadline = time.time() + 8.0\n'),
 ('移除启动器第三页 UI',
  '        self.selection_page = self._build_selection_page()\n'
  '        self.checkin_page = self._build_checkin_page()\n'
  '        self.director_page = self._build_director_page()\n'
  '\n'
  '        self.stack.addWidget(self.selection_page)\n'
  '        self.stack.addWidget(self.checkin_page)\n'
  '        self.stack.addWidget(self.director_page)\n'
  '        self.stack.setCurrentWidget(self.selection_page)\n'
  '\n'
  '        self.process_timer = QTimer(self)\n'
  '        self.process_timer.timeout.connect(self.refresh_process_status)\n'
  '        self.process_timer.start(1000)\n',
  '        # 启动器只显示“人员选择”和“人脸检录”两页。\n'
  '        # 检录完成后直接启动原技术台窗口，不再显示启动器自己的进程管理页。\n'
  '        self.selection_page = self._build_selection_page()\n'
  '        self.checkin_page = self._build_checkin_page()\n'
  '\n'
  '        self.stack.addWidget(self.selection_page)\n'
  '        self.stack.addWidget(self.checkin_page)\n'
  '        self.stack.setCurrentWidget(self.selection_page)\n'),
 ('记录当前场次以便退出后清理检录结果',
  '    def save_session(self) -> None:\n'
  '        if self.session_path is None:\n'
  '            return\n'
  '        selected = self.selected_rows()\n',
  '    def save_session(self) -> None:\n'
  '        if self.session_path is None:\n'
  '            return\n'
  '\n'
  '        # 保存“当前活动场次”标记，停止脚本据此清除本场临时检录结果。\n'
  '        # 这里只删除签到结果，不会删除 face_checkin/dataset、trainer 或映射关系。\n'
  '        current_csv_path = (\n'
  '            FACE_WORK_DIR\n'
  '            / "records"\n'
  '            / f"checkin_{datetime.now().strftime(\'%Y%m%d\')}.csv"\n'
  '        )\n'
  '        active = read_json(ACTIVE_CHECKIN_FILE, {})\n'
  '        csv_paths = {\n'
  '            str(path)\n'
  '            for path in (active.get("csv_paths", []) or [])\n'
  '            if str(path).strip()\n'
  '        }\n'
  '        csv_paths.add(str(current_csv_path))\n'
  '\n'
  '        atomic_write_json(\n'
  '            ACTIVE_CHECKIN_FILE,\n'
  '            {\n'
  '                "match_id": self.match_id,\n'
  '                "session_path": str(self.session_path),\n'
  '                "csv_paths": sorted(csv_paths),\n'
  '                "updated_at": datetime.now().isoformat(timespec="seconds"),\n'
  '            },\n'
  '        )\n'
  '\n'
  '        selected = self.selected_rows()\n'),
 ('检录完成后直接启动原技术台',
  '        self.stack.setCurrentWidget(self.director_page)\n'
  '        QApplication.processEvents()\n'
  '        self.start_director_services()\n',
  '        # 不进入启动器自己的第三页；继续在检录页显示启动进度。\n'
  '        # 服务启动完成后会隐藏本窗口，由原 rk_techtable_panel.py 接管 LCD。\n'
  '        self.enter_director_button.setEnabled(False)\n'
  '        self.checkin_status_label.setText(\n'
  '            "状态：正在启动 MediaMTX、带音频 RTSP 导播和技术台……"\n'
  '        )\n'
  '        QApplication.processEvents()\n'
  '        self.start_director_services()\n'),
 ('启动进度显示在检录页',
  '    def start_director_services(self) -> None:\n'
  '        self.director_video.setText("正在启动 MediaMTX、RKNN 导播和技术台……")\n'
  '        QApplication.processEvents()\n'
  '\n'
  '        # 后台线程启动进程，避免 time.sleep 阻塞 UI\n',
  '    def start_director_services(self) -> None:\n'
  '        self.checkin_status_label.setText(\n'
  '            "状态：正在启动并验证 H.264 + AAC RTSP 流……"\n'
  '        )\n'
  '        QApplication.processEvents()\n'
  '\n'
  '        # 后台线程启动进程并执行 ffprobe 验收，避免阻塞 UI。\n'),
 ('启动成功后隐藏检录窗口并保留后台进程',
  '    def _on_startup_finished(self) -> None:\n'
  '        self.director_started = True\n'
  '        self.start_preview_thread()\n'
  '        self.refresh_process_status()\n'
  '\n'
  '    def _on_startup_error(self, message: str) -> None:\n'
  '        QMessageBox.critical(self, "导播启动失败", message)\n'
  '        self.director_video.setText("导播启动失败，请查看 runtime/logs")\n',
  '    def _on_startup_finished(self) -> None:\n'
  '        self.director_started = True\n'
  '        self.checkin_status_label.setText(\n'
  '            "状态：RTSP 音视频验证通过，技术台已启动。"\n'
  '        )\n'
  '\n'
  '        # 技术台是正式比赛界面；启动器隐藏但保持运行，\n'
  '        # 之后由 stop_all_techtable.py 统一停止全部进程。\n'
  '        self.hide()\n'
  '\n'
  '    def _on_startup_error(self, message: str) -> None:\n'
  '        self.enter_director_button.setEnabled(True)\n'
  '        self.checkin_status_label.setText(\n'
  '            "状态：导播启动失败，请查看 runtime/logs。"\n'
  '        )\n'
  '        QMessageBox.critical(self, "导播启动失败", message)\n'),
 ('隐藏窗口后保持启动器运行',
  '    app = QApplication(sys.argv)\n    app.setStyle("Fusion")\n',
  '    app = QApplication(sys.argv)\n'
  '    # 检录窗口隐藏后仍需保留启动器进程，直到 stop_all_techtable.py 结束它。\n'
  '    app.setQuitOnLastWindowClosed(False)\n'
  '    app.setStyle("Fusion")\n')]

STOP_REPLACEMENTS = [('停止脚本加入 CSV 清理支持', 'import argparse\nimport json\n', 'import argparse\nimport csv\nimport json\n'),
 ('停止脚本加入临时检录数据路径',
  'PID_FILE = RUNTIME_DIR / "techtable_processes.json"\n'
  'LAUNCHER_PID_FILE = RUNTIME_DIR / "start_all_techtable.pid"\n'
  '\n'
  'STOP_ORDER = ["techtable", "director", "mediamtx"]\n',
  'PID_FILE = RUNTIME_DIR / "techtable_processes.json"\n'
  'LAUNCHER_PID_FILE = RUNTIME_DIR / "start_all_techtable.pid"\n'
  'ACTIVE_CHECKIN_FILE = RUNTIME_DIR / "active_checkin_session.json"\n'
  'RTSP_PROBE_FILE = RUNTIME_DIR / "rtsp_probe.json"\n'
  '\n'
  'STOP_ORDER = ["techtable", "director", "mediamtx"]\n'),
 ('兜底结束 FFmpeg 音视频推流进程',
  '    ("RKNN 导播推流", "single_rknn_director_view720_network_stream.py"),\n    ("MediaMTX", "mediamtx_rk3588.yml"),\n',
  '    ("RKNN 导播推流", "single_rknn_director_view720_network_stream.py"),\n'
  '    # FFmpeg 在导播脚本内部使用 start_new_session=True，属于独立进程组；\n'
  '    # 导播异常退出时必须额外兜底，避免继续占用 hw:1,0 和 RTSP 发布端。\n'
  '    ("FFmpeg 音视频推流", r"ffmpeg.*rtsp://127\\.0\\.0\\.1:8554/director"),\n'
  '    ("MediaMTX", "mediamtx_rk3588.yml"),\n'),
 ('停止导播时延长释放音频设备的时间',
  '        handled.add(pid)\n        terminate_pids([pid], name)\n',
  '        handled.add(pid)\n'
  '        # 导播退出时还要停止内部 FFmpeg、释放摄像头和 NAU8822，\n'
  '        # 因此给予更长的优雅退出时间。\n'
  '        timeout = 8.0 if name == "director" else 3.0\n'
  '        terminate_pids([pid], name, timeout=timeout)\n'),
 ('加入退出后检录结果清理',
  'def parse_args() -> argparse.Namespace:\n',
  '\n'
  'def cleanup_transient_checkin_data() -> None:\n'
  '    """\n'
  '    删除当前场次的临时检录结果。\n'
  '\n'
  '    会删除：\n'
  '        - checkin_session_<match_id>.json；\n'
  '        - 当天 CSV 中 match_id 等于当前场次的签到行；\n'
  '        - runtime/active_checkin_session.json；\n'
  '        - runtime/rtsp_probe.json。\n'
  '\n'
  '    不会删除：\n'
  '        - face_checkin/dataset；\n'
  '        - face_checkin/trainer；\n'
  '        - labels.json / lbph_model.yml；\n'
  '        - roster_face_mapping.json；\n'
  '        - 球员名单。\n'
  '    """\n'
  '    marker = read_json(ACTIVE_CHECKIN_FILE, {})\n'
  '    match_id = str(marker.get("match_id", "")).strip()\n'
  '\n'
  '    session_text = str(marker.get("session_path", "")).strip()\n'
  '    if session_text:\n'
  '        session_path = Path(session_text)\n'
  '        try:\n'
  '            session_path.unlink()\n'
  '            print(f"[CLEAN] 已删除本场检录会话：{session_path}")\n'
  '        except FileNotFoundError:\n'
  '            pass\n'
  '        except Exception as exc:\n'
  '            print(f"[WARN] 无法删除检录会话 {session_path}: {exc}")\n'
  '\n'
  '    for csv_text in marker.get("csv_paths", []) or []:\n'
  '        csv_text = str(csv_text).strip()\n'
  '        if not csv_text or not match_id:\n'
  '            continue\n'
  '\n'
  '        csv_path = Path(csv_text)\n'
  '        if not csv_path.is_file():\n'
  '            continue\n'
  '\n'
  '        try:\n'
  '            with csv_path.open(\n'
  '                "r",\n'
  '                encoding="utf-8-sig",\n'
  '                newline="",\n'
  '            ) as file:\n'
  '                reader = csv.DictReader(file)\n'
  '                fieldnames = list(reader.fieldnames or [])\n'
  '                rows = [\n'
  '                    row for row in reader\n'
  '                    if str(row.get("match_id", "")).strip() != match_id\n'
  '                ]\n'
  '\n'
  '            if not fieldnames:\n'
  '                csv_path.unlink()\n'
  '                print(f"[CLEAN] 已删除无效检录 CSV：{csv_path}")\n'
  '                continue\n'
  '\n'
  '            if not rows:\n'
  '                csv_path.unlink()\n'
  '                print(f"[CLEAN] 已删除本场检录 CSV：{csv_path}")\n'
  '                continue\n'
  '\n'
  '            temp_path = csv_path.with_suffix(csv_path.suffix + ".tmp")\n'
  '            with temp_path.open(\n'
  '                "w",\n'
  '                encoding="utf-8-sig",\n'
  '                newline="",\n'
  '            ) as file:\n'
  '                writer = csv.DictWriter(file, fieldnames=fieldnames)\n'
  '                writer.writeheader()\n'
  '                writer.writerows(rows)\n'
  '            temp_path.replace(csv_path)\n'
  '            print(\n'
  '                f"[CLEAN] 已从 {csv_path.name} 删除场次 {match_id} 的检录行"\n'
  '            )\n'
  '\n'
  '        except Exception as exc:\n'
  '            print(f"[WARN] 清理检录 CSV {csv_path} 失败：{exc}")\n'
  '\n'
  '    for path in (ACTIVE_CHECKIN_FILE, RTSP_PROBE_FILE):\n'
  '        try:\n'
  '            path.unlink()\n'
  '        except FileNotFoundError:\n'
  '            pass\n'
  '        except Exception as exc:\n'
  '            print(f"[WARN] 无法删除 {path}: {exc}")\n'
  '\n'
  '\n'
  'def parse_args() -> argparse.Namespace:\n'),
 ('停止全部进程后清理本场检录数据',
  '    cleanup_pid_files()\n    show_port_status()\n',
  '    cleanup_transient_checkin_data()\n    cleanup_pid_files()\n    show_port_status()\n')]


def apply_replacements(text: str, replacements, filename: str) -> str:
    for label, old, new in replacements:
        if new in text:
            print(f"[SKIP] {filename} 已包含：{label}")
            continue
        if old not in text:
            raise RuntimeError(
                f"无法修改 {filename}：没有找到“{label}”的目标代码片段。\n"
                "请确认文件来自 zzzokay/camera_150_with_face 当前 main 分支。"
            )
        print(f"[PATCH] {filename}：{label}")
        text = text.replace(old, new, 1)
    return text


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-dir", default=".")
    args = parser.parse_args()

    project_dir = Path(args.project_dir).expanduser().resolve()
    start_path = project_dir / "start_all_techtable.py"
    stop_path = project_dir / "stop_all_techtable.py"

    for path in (start_path, stop_path):
        if not path.is_file():
            raise FileNotFoundError(f"找不到文件：{path}")

    start_original = start_path.read_text(encoding="utf-8")
    stop_original = stop_path.read_text(encoding="utf-8")

    start_patched = apply_replacements(
        start_original,
        START_REPLACEMENTS,
        start_path.name,
    )
    stop_patched = apply_replacements(
        stop_original,
        STOP_REPLACEMENTS,
        stop_path.name,
    )

    ast.parse(start_patched, filename=str(start_path))
    ast.parse(stop_patched, filename=str(stop_path))

    start_backup = start_path.with_suffix(".py.before_workflow_patch")
    stop_backup = stop_path.with_suffix(".py.before_workflow_patch")

    if not start_backup.exists():
        shutil.copy2(start_path, start_backup)
    if not stop_backup.exists():
        shutil.copy2(stop_path, stop_backup)

    start_path.write_text(start_patched, encoding="utf-8")
    stop_path.write_text(stop_patched, encoding="utf-8")

    print("\n" + "=" * 72)
    print("补丁应用完成")
    print(f"启动脚本：{start_path}")
    print(f"停止脚本：{stop_path}")
    print(f"启动备份：{start_backup}")
    print(f"停止备份：{stop_backup}")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
