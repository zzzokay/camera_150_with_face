@echo off
setlocal
cd /d "%~dp0"

set "FFPROBE_EXE=%~dp0ffmpeg\bin\ffprobe.exe"

if not exist "%FFPROBE_EXE%" (
    echo [ERROR] ffprobe.exe is missing.
    echo Run 00_prepare.bat first.
    pause
    exit /b 1
)

"%FFPROBE_EXE%" -v error -rtsp_transport tcp -show_entries stream=index,codec_type,codec_name,sample_rate,channels -of json "rtsp://192.168.137.231:8554/director"

echo.
echo Expected:
echo video codec_name = h264
echo audio codec_name = aac
echo sample_rate = 48000
echo channels = 2
pause
