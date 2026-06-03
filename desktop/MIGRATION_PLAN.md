# Brake GUI Migration Plan

Goal: replace the PyQt GUI with an Electron/React GUI while keeping the Python
engine stable.

## Rule

Do not rewrite detection, service, watchdog, lockout, uninstall, state, recovery,
or commitment logic while redesigning the GUI. The GUI migration should be visual
first, then integration one bridge method at a time.

## Phase 1 - Visual Shell

Status: started.

- Keep the Electron app in `desktop/`.
- Use mock status data from `electron/main.cjs`.
- Use the Brake design system CSS tokens directly.
- Iterate visually through screenshots.
- Do not connect real enable/disable actions yet.

## Phase 2 - Read-Only Python Bridge

Expose one real read-only method from Electron to Python:

- `status()`

The React UI should show the same values the PyQt UI currently shows, but still
not mutate state.

## Phase 3 - Safe Mutations

Add write actions one at a time:

- `set_duration(minutes)`
- `set_sensitivity(value)`
- `enable(password)`
- `disable(password)`
- `set_commitment(until, password)`
- `test_lockout()`

Each action should call the existing Python controller/service path, not duplicate
business logic in JavaScript.

## Phase 4 - Replace PyQt

Only after the Electron GUI can fully control the app:

- stop using `python -m brake.gui`
- update shortcuts to launch the Electron app
- keep Python service/agent/lockout processes as the backend engine

## Local Commands

```powershell
cd desktop
npm install
npm run dev
```

Build check:

```powershell
npm run build
npm audit
```
