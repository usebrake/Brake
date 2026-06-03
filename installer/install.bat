@echo off
REM Elevation wrapper. Re-launches as admin if not already.

NET SESSION >NUL 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo Requesting elevation...
    powershell -Command "Start-Process -Verb RunAs -FilePath '%~f0'"
    exit /b 0
)

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0register_service.ps1"
pause
