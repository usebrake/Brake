# Brake Electron App

This is the current user-facing Brake app.

The app is split into two parts:

- `desktop/` is the Electron + React control panel.
- `lockitup/` is still the Python backend package name for now. It owns detection, state, lockouts, recovery, commitment, and the local agent.

The internal Python package name has not been renamed yet because keeping it stable avoids breaking the backend while the product is being finalized.

## Run Locally

From this folder:

```powershell
.\start-brake-dev.bat
```

Or manually:

```powershell
cd desktop
npm run dev
```

In dev mode, Electron stores local state in `.brake-electron-dev-data/` inside this folder. That keeps it separate from installed/production state.

## Current Scope

Electron is the primary GUI now. The older PyQt files are still present as a legacy/reference layer while the backend migration settles, but they are not the UI direction for Brake.
