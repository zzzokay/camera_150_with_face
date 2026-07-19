from __future__ import annotations

import importlib
import sys

MODULES = [
    ("cv2", "opencv-python"),
    ("PIL", "pillow"),
    ("PyQt5", "PyQt5"),
]

missing = []
for module_name, package_name in MODULES:
    try:
        module = importlib.import_module(module_name)
        version = getattr(module, "__version__", "installed")
        print(f"[OK] {module_name}: {version}")
    except Exception as exc:
        print(f"[MISSING] {module_name}: {exc}")
        missing.append(package_name)

if missing:
    print("MISSING_PACKAGES=" + ",".join(missing))
    raise SystemExit(2)

print("[OK] Existing Python environment is ready.")
