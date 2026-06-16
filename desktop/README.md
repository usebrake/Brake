# Brake Electron App

This is the current user-facing Brake desktop app.

The app is split into two parts:

- `desktop/` is the Electron + React control panel.
- `brake/` is the Python backend package. It owns detection, state, lockouts, recovery, commitment, services, and the local agent.

## Installed Mode

The Windows installer copies the app to:

```text
C:\Program Files\Brake
```

Normal users run `BrakeSetup.exe`. The packaged app includes the built `desktop/dist` UI and does not need Node.js, npm, or the Vite dev server.

## Development Mode

From the repo root:

```powershell
.\start-brake-dev.bat
```

Or manually:

```powershell
cd desktop
npm run dev
```

In development mode, Electron stores local state in `.brake-electron-dev-data/` inside the repo. That keeps it separate from installed state.

## Current Scope

Electron is the primary GUI. The older PyQt files are still present as a legacy/reference layer while Electron is tested, but they are not the UI direction for Brake.
