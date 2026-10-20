"""
文件作用：从任意目录运行 G0 环境与模型文件清单检查；不加载任何权重。
输入：--model-dir / --output；输出：JSON；依赖：windows_pipeline.diagnostics。
运行示例：见 NEWCOMER_HANDOFF.md。
"""
from camera_150.windows_pipeline.diagnostics import main


if __name__ == "__main__":
    raise SystemExit(main())
