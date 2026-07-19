@echo off
setlocal
cd /d "%~dp0"

set "FFPLAY_EXE=%~dp0ffmpeg\bin\ffplay.exe"

if not exist "%FFPLAY_EXE%" (
    echo [ERROR] ffplay.exe is missing.
    echo Run 00_prepare.bat first.
    pause
    exit /b 1
)

"%FFPLAY_EXE%" -hide_banner -rtsp_transport tcp -nodisp -vn "rtsp://192.168.137.231:8554/director"
pause
