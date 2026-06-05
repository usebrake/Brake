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

echo Starting Brake...
npm run dev

if errorlevel 1 (
  echo.
  echo Brake failed to start. Leave this window open and share the error above.
  pause
  exit /b 1
)