@echo off
setlocal

set "ROOT=%~dp0"
cd /d "%ROOT%"

if not exist "desktop\package.json" (
  echo Brake could not find desktop\package.json.
  echo Make sure you extracted the full GitHub zip before running this file.
  pause
  exit /b 1
)

where npm >nul 2>nul
if errorlevel 1 (
  echo Brake needs Node.js/npm to run from source.
  echo Install Node.js LTS from https://nodejs.org/ then run this file again.
  pause
  exit /b 1
)

cd /d "%ROOT%desktop"

if exist "%ROOT%.brake-source-install" (
  if not exist "node_modules" (
    echo Brake desktop dependencies are missing.
    echo Run installer\install.bat again from the Brake source folder.
    pause
    exit /b 1
  )
  if not exist "dist\index.html" (
    echo Brake desktop build is missing.
    echo Run installer\install.bat again from the Brake source folder.
    pause
    exit /b 1
  )
  set "BRAKE_INSTALLED_SOURCE=1"
  set "BRAKE_NO_DEV_AGENT=1"
  set "BRAKE_DATA_DIR=%ProgramData%\Brake"
  echo Starting Brake...
  npm run start
  exit /b %ERRORLEVEL%
)

if not exist "node_modules" (
  echo Installing Brake desktop dependencies. This only runs the first time.
  npm install
  if errorlevel 1 (
    echo.
    echo Dependency install failed.
    pause
    exit /b 1
  )
)

echo Starting Brake in development mode...
npm run dev

if errorlevel 1 (
  echo.
  echo Brake failed to start. Leave this window open and share the error above.
  pause
  exit /b 1
)