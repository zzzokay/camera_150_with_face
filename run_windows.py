"""
文件作用：从任意当前目录启动 G0，避免依赖工作目录恰好位于仓库根目录。
输入：CLI/YAML；输出：保存的视频、运行报告及退出码；依赖：windows_pipeline。
调用关系：本文件 -> run.main；示例：见 NEWCOMER_HANDOFF.md。
"""
from camera_150.windows_pipeline.run import main


if __name__ == "__main__":
    raise SystemExit(main())
