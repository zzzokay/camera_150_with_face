@echo off
setlocal
cd /d "%~dp0"

set "RK_IP="
set /p RK_IP=Enter RK3588 IP [192.168.137.231]:
if "%RK_IP%"=="" set "RK_IP=192.168.137.231"

set "VOLUME="
set /p VOLUME=Enter volume 0-100 [100]:
if "%VOLUME%"=="" set "VOLUME=100"

set "FFPLAY_EXE=%~dp0ffmpeg\bin\ffplay.exe"
set "FFPROBE_EXE=%~dp0ffmpeg\bin\ffprobe.exe"

where python >nul 2>nul
if not errorlevel 1 (
    python "techtable_v2\viewer_client.py" --rtsp "rtsp://%RK_IP%:8554/director" --state-url "http://%RK_IP%:8010/state" --ffplay-bin "%FFPLAY_EXE%" --ffprobe-bin "%FFPROBE_EXE%" --volume %VOLUME%
    goto finished
)

where py >nul 2>nul
if not errorlevel 1 (
    py -3 "techtable_v2\viewer_client.py" --rtsp "rtsp://%RK_IP%:8554/director" --state-url "http://%RK_IP%:8010/state" --ffplay-bin "%FFPLAY_EXE%" --ffprobe-bin "%FFPROBE_EXE%" --volume %VOLUME%
    goto finished
)

echo [ERROR] Python was not found.
pause
exit /b 1

:finished
if errorlevel 1 pause
