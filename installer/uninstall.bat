@echo off
NET SESSION >NUL 2>&1
if %ERRORLEVEL% NEQ 0 (
    powershell -Command "Start-Process -Verb RunAs -FilePath '%~f0'"
    exit /b 0
)
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0unregister_service.ps1"
pause
