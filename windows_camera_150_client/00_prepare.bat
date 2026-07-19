@echo off
setlocal
cd /d "%~dp0"

echo ============================================================
echo camera_150 Windows Viewer - Prepare
echo ============================================================

where python >nul 2>nul
if not errorlevel 1 (
    set "PYTHON_EXE=python"
    goto check_python
)

where py >nul 2>nul
if not errorlevel 1 (
    set "PYTHON_EXE=py -3"
    goto check_python
)

echo [ERROR] Python was not found.
echo Install Python and enable Add Python to PATH.
pause
exit /b 1

:check_python
echo [1/2] Checking the existing Python environment...
%PYTHON_EXE% check_python_env.py
if not errorlevel 1 goto ffmpeg

echo.
echo [WARN] Some Python packages are missing.
echo The script will use the official PyPI index and ignore global pip config.
echo No pip upgrade will be performed.
echo.

%PYTHON_EXE% -m pip install --isolated --disable-pip-version-check --no-cache-dir --index-url https://pypi.org/simple opencv-python pillow PyQt5
if errorlevel 1 (
    echo.
    echo [ERROR] Package installation failed.
    echo Your firewall or security software may be blocking python.exe network access.
    echo Since your old viewer already worked, try 01_start.bat directly first.
    pause
    exit /b 1
)

%PYTHON_EXE% check_python_env.py
if errorlevel 1 (
    echo [ERROR] Python dependencies are still incomplete.
    pause
    exit /b 1
)

:ffmpeg
echo [2/2] Checking local FFmpeg tools...
if exist "ffmpeg\bin\ffplay.exe" if exist "ffmpeg\bin\ffprobe.exe" (
    echo [OK] Local FFmpeg tools already exist.
    goto done
)

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0download_ffmpeg.ps1"
if errorlevel 1 (
    echo.
    echo [WARN] Automatic FFmpeg download failed.
    echo You can manually copy ffplay.exe and ffprobe.exe into:
    echo %~dp0ffmpeg\bin
    pause
    exit /b 1
)

:done
echo.
echo ============================================================
echo [OK] Preparation completed.
echo Run: 01_start.bat
echo ============================================================
pause
exit /b 0
