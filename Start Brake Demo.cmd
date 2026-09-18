@echo off
setlocal EnableExtensions

set "BRAKE_DEMO_ROOT=%~dp0"
cd /d "%BRAKE_DEMO_ROOT%"

if not exist "desktop\package.json" (
  echo Brake Demo could not find desktop\package.json.
  pause
  exit /b 1
)

where npm.cmd >nul 2>nul
if errorlevel 1 (
  echo Brake Demo needs Node.js and npm.
  echo Install Node.js LTS, then run this file again.
  pause
  exit /b 1
)

where py.exe >nul 2>nul
if errorlevel 1 (
  echo Brake Demo needs Python for the simulated lockout screen.
  pause
  exit /b 1
)

py -c "import PyQt6, yaml" >nul 2>nul
if errorlevel 1 (
  echo Installing Brake Demo lockout dependencies. This only runs when they are missing.
  py -m pip install --disable-pip-version-check PyQt6 PyYAML
  if errorlevel 1 (
    echo.
    echo Brake Demo could not install PyQt6 and PyYAML.
    pause
    exit /b 1
  )
)

set "BRAKE_DEMO_MODE=1"
set "BRAKE_NO_DEV_AGENT=1"
set "BRAKE_NO_KBD_HOOK=1"
set "BRAKE_PYTHON=py"
set "BRAKE_DATA_DIR=%BRAKE_DEMO_ROOT%.brake-demo-data"

cd /d "%BRAKE_DEMO_ROOT%desktop"

if not exist "node_modules" (
  echo Installing Brake Demo desktop dependencies. This only runs the first time.
  call npm.cmd install
  if errorlevel 1 (
    echo.
    echo Dependency installation failed.
    pause
    exit /b 1
  )
)

echo Starting Brake Demo...
echo Demo password: demo123
echo Demo recovery code: DEMO-RECOVERY-CODE
echo The simulated lockout closes with Esc or Alt+F4.
call npm.cmd run dev

if errorlevel 1 (
  echo.
  echo Brake Demo failed to start. Leave this window open and share the error above.
  pause
  exit /b 1
)
