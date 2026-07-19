@echo off
setlocal

where python >nul 2>nul
if not errorlevel 1 (
    echo python
    exit /b 0
)

where py >nul 2>nul
if not errorlevel 1 (
    echo py -3
    exit /b 0
)

exit /b 1
