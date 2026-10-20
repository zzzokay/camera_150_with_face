r"""
文件作用：可选纯规则分析/运镜；仅开启导播时导入。
调用入口：根 run.py；本文件是库模块，不直接执行。
输入/输出及边界：见公开类/函数的中文说明；坐标为全幅像素、时间为源秒，ID 是临时编号。
快速测试（PowerShell，项目根目录）：.\.venv\Scripts\python.exe -X utf8 -m pytest tests/test_frozen_regression.py -q
预期输出：pytest 结果；日常运行结果在 configs/local.yaml 指定的输出目录。
排错：缺依赖用同一独立解释器安装 requirements-windows.lock.txt；输入/格式说明见 NEWCOMER_HANDOFF.md。
"""
