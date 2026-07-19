#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
应用篮球技术台 V3 和技术台状态驱动导播策略。
"""

from __future__ import annotations

import argparse
import ast
import shutil
import time
from pathlib import Path

NETWORK_OPS = [('网络导播导入 director_game_policy',
  'from audio_chain import (\n'
  '    AudioConfig,\n'
  '    add_audio_cli_args,\n'
  '    audio_config_from_args,\n'
  '    audio_summary,\n'
  '    build_alsa_input_args,\n'
  '    build_audio_output_args,\n'
  ')\n',
  'from audio_chain import (\n'
  '    AudioConfig,\n'
  '    add_audio_cli_args,\n'
  '    audio_config_from_args,\n'
  '    audio_summary,\n'
  '    build_alsa_input_args,\n'
  '    build_audio_output_args,\n'
  ')\n'
  '\n'
  'from director_game_policy import (\n'
  '    DirectorGamePolicyConfig,\n'
  '    GameStateReader,\n'
  '    apply_game_state_to_analysis,\n'
  ')\n'),
 ('初始化技术台状态读取器',
  '    analysis_state = init_single_view_state()\n'
  '    director_state = init_overlay_director_state(frame_w)\n'
  '    fps_counter = base.FPSCounter()\n',
  '    analysis_state = init_single_view_state()\n'
  '    director_state = init_overlay_director_state(frame_w)\n'
  '    fps_counter = base.FPSCounter()\n'
  '\n'
  '    # -------------------------------------------------------------------------\n'
  '    # 技术台状态驱动的导播策略\n'
  '    # -------------------------------------------------------------------------\n'
  '    # GameStateReader 带缓存和 mtime 检查，不会每帧都读取 JSON。\n'
  '    game_policy_config = DirectorGamePolicyConfig(\n'
  '        enabled=not args.disable_game_policy,\n'
  '        state_file=args.game_state_file,\n'
  '        refresh_interval=args.game_state_refresh,\n'
  '        left_basket_x_ratio=args.left_basket_x_ratio,\n'
  '        right_basket_x_ratio=args.right_basket_x_ratio,\n'
  '        home_first_half_attack=args.home_first_half_attack,\n'
  '        freeze_zoom_frames=args.game_policy_freeze_zoom_frames,\n'
  '    )\n'
  '    game_state_reader = GameStateReader(game_policy_config)\n'
  '    game_policy_text = "NORMAL"\n'),
 ('在原运镜状态机前应用比赛策略',
  '            analysis = analyze_single_view_frame(boxes_info, frame_w, frame_h, analysis_state)\n'
  '            director_info = update_overlay_director_state(\n'
  '                analysis,\n'
  '                frame_w,\n'
  '                frame_h,\n'
  '                out_ratio,\n'
  '                director_state,\n'
  '            )\n',
  '            analysis = analyze_single_view_frame(\n'
  '                boxes_info,\n'
  '                frame_w,\n'
  '                frame_h,\n'
  '                analysis_state,\n'
  '            )\n'
  '\n'
  '            # 在原运镜状态机之前应用比赛阶段策略：\n'
  '            #   NORMAL     原自动导播不变；\n'
  '            #   HOLD       暂停/死球时保持当前区域；\n'
  '            #   FREE_THROW 罚球时平滑引导至对应篮筐。\n'
  '            game_state = game_state_reader.get_state()\n'
  '            analysis, game_policy_text = apply_game_state_to_analysis(\n'
  '                analysis,\n'
  '                game_state,\n'
  '                director_state,\n'
  '                frame_w,\n'
  '                frame_h,\n'
  '                game_policy_config,\n'
  '            )\n'
  '\n'
  '            director_info = update_overlay_director_state(\n'
  '                analysis,\n'
  '                frame_w,\n'
  '                frame_h,\n'
  '                out_ratio,\n'
  '                director_state,\n'
  '            )\n'),
 ('本地调试画面显示比赛策略',
  '                stream_status=streamer.status_text(),\n',
  '                stream_status=(\n'
  '                    f"{streamer.status_text()} | {game_policy_text}"\n'
  '                ),\n'),
 ('增加技术台导播策略命令行参数',
  '    # NAU8822 / ALSA 正式音频链路。\n    add_audio_cli_args(parser, "stream")\n',
  '    # ---------------------------------------------------------------------\n'
  '    # 技术台状态驱动导播\n'
  '    # ---------------------------------------------------------------------\n'
  '    parser.add_argument(\n'
  '        "--game-state-file",\n'
  '        default=str(\n'
  '            SCRIPT_DIR.parent\n'
  '            / "techtable_v2"\n'
  '            / "game_state.json"\n'
  '        ),\n'
  '        help="技术台 game_state.json；导播只读，不会修改该文件",\n'
  '    )\n'
  '    parser.add_argument(\n'
  '        "--disable-game-policy",\n'
  '        action="store_true",\n'
  '        help="关闭技术台状态策略，完全恢复原自动导播逻辑",\n'
  '    )\n'
  '    parser.add_argument(\n'
  '        "--game-state-refresh",\n'
  '        type=float,\n'
  '        default=0.20,\n'
  '        help="技术台状态缓存刷新间隔，单位秒",\n'
  '    )\n'
  '    parser.add_argument(\n'
  '        "--left-basket-x-ratio",\n'
  '        type=float,\n'
  '        default=0.18,\n'
  '        help="矫正画面中左篮筐归一化 X，需要按现场标定",\n'
  '    )\n'
  '    parser.add_argument(\n'
  '        "--right-basket-x-ratio",\n'
  '        type=float,\n'
  '        default=0.82,\n'
  '        help="矫正画面中右篮筐归一化 X，需要按现场标定",\n'
  '    )\n'
  '    parser.add_argument(\n'
  '        "--home-first-half-attack",\n'
  '        choices=["left", "right"],\n'
  '        default="right",\n'
  '        help="主队第1、2节进攻方向；下半场和加时自动交换",\n'
  '    )\n'
  '    parser.add_argument(\n'
  '        "--game-policy-freeze-zoom-frames",\n'
  '        type=int,\n'
  '        default=50,\n'
  '        help="暂停/罚球策略触发后冻结快速 zoom 的帧数",\n'
  '    )\n'
  '\n'
  '    # NAU8822 / ALSA 正式音频链路。\n'
  '    add_audio_cli_args(parser, "stream")\n'),
 ('启动日志显示比赛策略参数',
  '    print(f"stream_audio        : {audio_summary(audio_config_from_args(args, \'stream\'))}")\n'
  '    print(f"stream_overlay      : {args.stream_overlay}")\n',
  '    print(f"stream_audio        : {audio_summary(audio_config_from_args(args, \'stream\'))}")\n'
  '    print(f"game_state_file     : {args.game_state_file}")\n'
  '    print(f"game_policy         : {not args.disable_game_policy}")\n'
  '    print(f"basket_x_ratio      : {args.left_basket_x_ratio:.3f} / {args.right_basket_x_ratio:.3f}")\n'
  '    print(f"home_first_attack   : {args.home_first_half_attack}")\n'
  '    print(f"stream_overlay      : {args.stream_overlay}")\n')]
START_OPS = [('一键启动传入技术台状态与篮筐参数',
  '                    "--render-mode",\n'
  '                    "sample",\n'
  '                    # 板载 LCD 本地 OpenCV 预览缩放比例。\n',
  '                    "--render-mode",\n'
  '                    "sample",\n'
  '                    # 技术台状态只通过 JSON 提供给导播，保持模块解耦。\n'
  '                    "--game-state-file",\n'
  '                    str(GAME_STATE_PATH),\n'
  '                    # 默认主队上半场向画面右侧进攻；现场相反时改为 left。\n'
  '                    "--home-first-half-attack",\n'
  '                    "right",\n'
  '                    # 左右篮筐在矫正画面中的归一化位置，现场可继续微调。\n'
  '                    "--left-basket-x-ratio",\n'
  '                    "0.18",\n'
  '                    "--right-basket-x-ratio",\n'
  '                    "0.82",\n'
  '                    # 板载 LCD 本地 OpenCV 预览缩放比例。\n')]


def apply_ops(text: str, operations, filename: str) -> str:
    for label, old, new in operations:
        if new in text:
            print(f"[SKIP] {filename} 已包含：{label}")
            continue
        if old not in text:
            raise RuntimeError(
                f"无法修改 {filename}：没有找到“{label}”的目标代码。\n"
                "请确认工程来自 camera_150_with_face 当前 main 分支。"
            )
        print(f"[PATCH] {filename}：{label}")
        text = text.replace(old, new, 1)
    return text


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--project-dir",
        default=".",
        help="camera_150 工程根目录",
    )
    args = parser.parse_args()

    package_dir = Path(__file__).resolve().parent
    source_dir = package_dir / "files"
    project_dir = Path(args.project_dir).expanduser().resolve()

    copy_map = {
        source_dir / "techtable_v2" / "state_store.py":
            project_dir / "techtable_v2" / "state_store.py",
        source_dir / "techtable_v2" / "rk_techtable_panel.py":
            project_dir / "techtable_v2" / "rk_techtable_panel.py",
        source_dir / "techtable_v2" / "scoreboard_overlay.py":
            project_dir / "techtable_v2" / "scoreboard_overlay.py",
        source_dir / "camera_movement_modified" / "director_game_policy.py":
            project_dir / "camera_movement_modified" / "director_game_policy.py",
    }

    network_path = (
        project_dir
        / "camera_movement_modified"
        / "single_rknn_director_view720_network_stream.py"
    )
    start_path = project_dir / "start_all_techtable.py"

    required_sources = list(copy_map.keys())
    required_targets = [network_path, start_path]
    missing = [
        str(path)
        for path in required_sources + required_targets
        if not path.is_file()
    ]
    if missing:
        raise FileNotFoundError(
            "缺少以下文件：\n" + "\n".join(missing)
        )

    network_original = network_path.read_text(encoding="utf-8")
    start_original = start_path.read_text(encoding="utf-8")
    network_patched = apply_ops(
        network_original,
        NETWORK_OPS,
        network_path.name,
    )
    start_patched = apply_ops(
        start_original,
        START_OPS,
        start_path.name,
    )

    if '"--display-scale"' not in start_patched or '"0.35"' not in start_patched:
        raise RuntimeError(
            "没有确认到 --display-scale 0.35，为避免 LCD 尺寸失控，停止修改。"
        )

    # 覆盖前统一做语法检查。
    ast.parse(network_patched, filename=str(network_path))
    ast.parse(start_patched, filename=str(start_path))
    for source in required_sources:
        ast.parse(source.read_text(encoding="utf-8"), filename=str(source))

    timestamp = time.strftime("%Y%m%d_%H%M%S")
    backup_dir = project_dir / f"backup_techtable_v3_{timestamp}"
    backup_dir.mkdir(parents=True, exist_ok=False)

    for target in list(copy_map.values()) + required_targets:
        if not target.exists():
            continue
        relative = target.relative_to(project_dir)
        backup = backup_dir / relative
        backup.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(target, backup)

    for source, target in copy_map.items():
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        print(f"[COPY] {target.relative_to(project_dir)}")

    network_path.write_text(network_patched, encoding="utf-8")
    start_path.write_text(start_patched, encoding="utf-8")

    print("\n" + "=" * 76)
    print("篮球技术台 V3 补丁应用完成")
    print(f"工程目录：{project_dir}")
    print(f"备份目录：{backup_dir}")
    print("display-scale：保持 0.35")
    print("=" * 76)
    print("启动：python3 start_all_techtable.py")
    print("停止：python3 stop_all_techtable.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
