@echo off
setlocal
cd /d "%~dp0"

where python >nul 2>nul
if not errorlevel 1 (
    python "techtable_v2\viewer_client.py" --rtsp "rtsp://192.168.137.231:8554/director" --state-url "http://192.168.137.231:8010/state" --no-audio
    goto finished
)

where py >nul 2>nul
if not errorlevel 1 (
    py -3 "techtable_v2\viewer_client.py" --rtsp "rtsp://192.168.137.231:8554/director" --state-url "http://192.168.137.231:8010/state" --no-audio
    goto finished
)

echo [ERROR] Python was not found.
pause
exit /b 1

:finished
if errorlevel 1 pause
