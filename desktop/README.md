# Brake Electron App

This is the current user-facing Brake desktop app.

The app is split into two parts:

- `desktop/` is the Electron + React control panel.
- `brake/` is the Python backend package. It owns detection, state, lockouts, recovery, commitment, services, and the local agent.

## Installed Source Mode

The GitHub source-beta installer copies the app to:

```text
C:\Program Files\Brake
```

During install, it runs `npm install` and `npm run build`. The Start Menu shortcut then runs Electron against the built `desktop/dist` UI. It does not need the Vite dev server for normal installed use.

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