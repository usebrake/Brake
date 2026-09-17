# Brake Demo

Brake Demo runs the production desktop interface against local mock state. It does not connect to BrakeService, start the detection agent, install startup entries, write to the installed Brake data directory, block keyboard input, or request Windows shutdown.

## Start

Double-click `Start Brake Demo.cmd` from the repository root. The first launch installs desktop dependencies if they are missing. Later launches start the Vite and Electron development environment directly, so React UI changes update without rebuilding an installer.

Demo credentials:

- Password: `demo123`
- Recovery code: `DEMO-RECOVERY-CODE`

The app tray menu contains demo scenarios for protection, commitment, recovery, repair, detection logs, and the simulated lockout. The simulated lockout uses the production lockout window but never persists state, installs a keyboard hook, or shuts down Windows. Press `Esc` or `Alt+F4` to leave it immediately.

## Reset

Close Brake Demo, then double-click `Reset Brake Demo Data.cmd`. Demo state lives only in `.brake-demo-data` inside this worktree.

The installed Brake application and its live state are separate and remain active while Brake Demo is open.
