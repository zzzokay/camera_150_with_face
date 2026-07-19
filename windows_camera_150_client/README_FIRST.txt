camera_150 Windows Viewer - SYSTEM PYTHON PACKAGE

This package reuses the Python environment that already ran your old
viewer_client.py. It does not create a virtual environment and does not
upgrade pip.

Extract to:

D:\camera_150_client\

Recommended order:

1. Try 01_start.bat directly.
2. If ffplay.exe is missing, run 00_prepare.bat.
3. Use 03_check_rtsp.bat to verify H.264 and AAC.
4. Use 04_audio_only.bat to test only the sound.

Default server:

RTSP : rtsp://192.168.137.231:8554/director
STATE: http://192.168.137.231:8010/state

If Python packages are missing, 00_prepare.bat uses:

--isolated
--index-url https://pypi.org/simple

This ignores the global Tsinghua mirror configuration and does not upgrade pip.
