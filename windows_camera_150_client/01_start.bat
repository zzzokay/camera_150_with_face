@echo off
setlocal
cd /d "%~dp0"

set "FFPLAY_EXE=%~dp0ffmpeg\bin\ffplay.exe"
set "FFPROBE_EXE=%~dp0ffmpeg\bin\ffprobe.exe"

if not exist "%FFPLAY_EXE%" (
    echo [ERROR] ffplay.exe is missing.
    echo Run 00_prepare.bat or copy ffplay.exe into ffmpeg\bin.
    pause
    exit /b 1
)

where python >nul 2>nul
if not errorlevel 1 (
    python "techtable_v2\viewer_client.py" --rtsp "rtsp://192.168.137.231:8554/director" --state-url "http://192.168.137.231:8010/state" --ffplay-bin "%FFPLAY_EXE%" --ffprobe-bin "%FFPROBE_EXE%" --volume 100
    goto finished
)

where py >nul 2>nul
if not errorlevel 1 (
    py -3 "techtable_v2\viewer_client.py" --rtsp "rtsp://192.168.137.231:8554/director" --state-url "http://192.168.137.231:8010/state" --ffplay-bin "%FFPLAY_EXE%" --ffprobe-bin "%FFPROBE_EXE%" --volume 100
    goto finished
)

echo [ERROR] Python was not found.
pause
exit /b 1

:finished
if errorlevel 1 (
    echo.
    echo [ERROR] Viewer exited with an error.
    echo Check: techtable_v2\viewer_audio_ffplay.log
    pause
)
