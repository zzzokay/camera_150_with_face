r"""
文件作用：Windows 篮球检测/ByteTrack 的统一运行和环境/相机检查入口。
PowerShell（项目根目录）：.\.venv\Scripts\python.exe -X utf8 .\run.py --config .\configs\local.yaml
必备输入：独立 Python 环境、本地 YOLO .pt、视频或相机；复制 local.example.yaml 并填写输入路径。
快速测试：.\.venv\Scripts\python.exe -X utf8 .\run.py --config .\configs\local.yaml --max-frames 48
环境检查：.\.venv\Scripts\python.exe -X utf8 .\run.py --check-env --config .\configs\local.yaml
预期输出：控制台提示唯一 runs 目录；overview.mp4、检测 JSONL、跟踪 CSV/JSONL、summary.json 和 run.log。
常见错误：旧配置按模板迁移；缺模型核对 weights；缺依赖用同一独立解释器安装锁定依赖；编码失败可显式 --codec MJPG。
验收边界：检测/跟踪测试能运行不代表真实身份关联正确；不限制或复用 Track ID，不启用篮球检测。
"""
import json
import logging

from basketball.config import load_config


def main(argv=None) -> int:
    """成功返回 0；配置/模型/保存失败返回 1；用户中断返回 130，并保留未完成报告。"""
    logging.basicConfig(level=logging.INFO, format='%(levelname)s %(message)s')
    try:
        config = load_config(argv)
        if config.check_env or config.check_camera:
            from basketball.diagnostics import check_camera, collect_environment
            if config.check_camera:
                report = check_camera(config.camera, config.backend, config.preview)
                succeeded = report['status'] == 'COMPLETED'
            else:
                report = collect_environment()
                succeeded = not any(v == 'missing' for v in report['packages'].values()) and not report.get('torch_error') and not report.get('opencv_error')
                if config.weights is not None:
                    report['configured_weights'] = {'path': str(config.weights), 'exists': config.weights.is_file(), 'loaded': False}
                    succeeded = succeeded and config.weights.is_file()
            value = json.dumps(report, ensure_ascii=False, indent=2)
            if config.report_path:
                config.report_path.parent.mkdir(parents=True, exist_ok=True)
                with config.report_path.open('x', encoding='utf-8') as stream:
                    stream.write(value + '\n')
            print(value)
            return 0 if succeeded else 1
        from basketball.pipeline import run_pipeline
        path = run_pipeline(config)
        logging.info('Windows 本次运行完成：%s', path)
        return 0
    except KeyboardInterrupt:
        logging.error('用户中断；部分产物不能视为完整验收')
        return 130
    except Exception as exc:
        logging.error('%s: %s', type(exc).__name__, exc)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
