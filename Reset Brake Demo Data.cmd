@echo off
setlocal EnableExtensions

set "BRAKE_DEMO_DATA=%~dp0.brake-demo-data"
if not exist "%BRAKE_DEMO_DATA%" (
  echo Brake Demo is already reset.
  pause
  exit /b 0
)

echo Close Brake Demo before resetting it.
choice /C YN /N /M "Reset all local Brake Demo settings and scenarios? [Y/N] "
if errorlevel 2 exit /b 0

rmdir /S /Q "%BRAKE_DEMO_DATA%"
echo Brake Demo data was reset.
pause
