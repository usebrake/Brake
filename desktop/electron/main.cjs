const { app, BrowserWindow, ipcMain, Menu, Tray, nativeImage } = require("electron");
const { execFile, spawn } = require("node:child_process");
const path = require("node:path");

const isSourceInstalled = process.env.BRAKE_INSTALLED_SOURCE === "1";
const isDev = !app.isPackaged && !isSourceInstalled;
const repoRoot = path.resolve(__dirname, "../..");
const installRoot = app.isPackaged ? path.dirname(process.execPath) : repoRoot;
const pythonExe = process.env.BRAKE_PYTHON || process.env.PYTHON || "python";
const bridgeExe = app.isPackaged ? path.join(installRoot, "BrakeBridge.exe") : "";
const appUserModelId = "com.usebrake.Brake";
let backendQueue = Promise.resolve();
let mainWindow = null;
let tray = null;
let devAgent = null;
let isQuitting = false;

app.setName("Brake");

if (process.platform === "win32") {
  app.setAppUserModelId(appUserModelId);
}

if (!app.requestSingleInstanceLock()) {
  app.exit(0);
}

app.on("second-instance", () => {
  showWindow();
});

function appIcon() {
  const base = path.join(__dirname, "../src/assets");
  const image = nativeImage.createFromPath(path.join(base, "brake-ring-256.png"));
  image.addRepresentation({
    scaleFactor: 1,
    width: 16,
    height: 16,
    buffer: nativeImage.createFromPath(path.join(base, "brake-ring-16.png")).toPNG()
  });
  image.addRepresentation({
    scaleFactor: 1,
    width: 32,
    height: 32,
    buffer: nativeImage.createFromPath(path.join(base, "brake-ring-32.png")).toPNG()
  });
  image.addRepresentation({
    scaleFactor: 1,
    width: 48,
    height: 48,
    buffer: nativeImage.createFromPath(path.join(base, "brake-ring-48.png")).toPNG()
  });
  return image;
}

function backend(command, args = [], timeoutMs = 5000) {
  const env = backendEnv();
  const exe = app.isPackaged ? bridgeExe : pythonExe;
  const exeArgs = app.isPackaged
    ? [command, ...args]
    : ["-m", "brake.desktop_bridge", command, ...args];

  return new Promise((resolve) => {
    execFile(
      exe,
      exeArgs,
      {
        cwd: installRoot,
        env,
        windowsHide: true,
        timeout: timeoutMs
      },
      (error, stdout, stderr) => {
        if (stdout.trim()) {
          try {
            resolve(JSON.parse(stdout.trim()));
            return;
          } catch {
            // Fall through to the regular error handling below.
          }
        }
        if (error) {
          resolve({
            ok: false,
            error: stderr.trim() || error.message || "backend_unavailable"
          });
          return;
        }
        resolve({ ok: false, error: "bad_backend_response" });
      }
    );
  });
}

function backendEnv() {
  const env = { ...process.env };
  if (app.isPackaged) {
    const programData = process.env.ProgramData || "C:\\ProgramData";
    env.BRAKE_DATA_DIR = process.env.BRAKE_DATA_DIR || path.join(programData, "Brake");
    delete env.BRAKE_DESKTOP_DEV;
    delete env.PYTHONPATH;
  } else {
    env.PYTHONPATH = [repoRoot, process.env.PYTHONPATH].filter(Boolean).join(path.delimiter);
  }
  if (isSourceInstalled) {
    const programData = process.env.ProgramData || "C:\\ProgramData";
    env.BRAKE_DATA_DIR = process.env.BRAKE_DATA_DIR || path.join(programData, "Brake");
    delete env.BRAKE_DESKTOP_DEV;
  } else if (isDev) {
    env.BRAKE_DESKTOP_DEV = "1";
    env.BRAKE_DATA_DIR = process.env.BRAKE_DATA_DIR || path.join(repoRoot, ".brake-electron-dev-data");
  }
  return env;
}

function startDevAgent() {
  if (!isDev || process.env.BRAKE_NO_DEV_AGENT === "1" || devAgent) return;
  // --parent-pid: the agent exits if this Electron process dies, so a
  // force-killed Electron cannot leave an orphaned agent scanning.
  devAgent = spawn(
      pythonExe,
      ["-m", "brake.agent", "--parent-pid", String(process.pid)],
      {
        cwd: repoRoot,
        env: backendEnv(),
        windowsHide: true,
        detached: false,
        stdio: "ignore"
      }
  );
  devAgent.on("exit", () => {
    devAgent = null;
  });
}

function queuedBackend(command, args = [], timeoutMs = 5000) {
  const next = backendQueue.then(() => backend(command, args, timeoutMs));
  backendQueue = next.catch(() => undefined);
  return next;
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 980,
    height: 680,
    minWidth: 860,
    minHeight: 600,
    title: "Brake",
    backgroundColor: "#0b0e14",
    frame: false,
    thickFrame: false,
    show: false,
    autoHideMenuBar: true,
    icon: appIcon(),
    webPreferences: {
      preload: path.join(__dirname, "preload.cjs"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: false
    }
  });

  Menu.setApplicationMenu(null);

  mainWindow.on("close", (event) => {
    if (isQuitting) return;
    event.preventDefault();
    mainWindow.hide();
  });

  mainWindow.once("ready-to-show", () => {
    mainWindow.show();
  });

  if (isDev) {
    mainWindow.loadURL("http://127.0.0.1:5173");
  } else {
    mainWindow.loadFile(path.join(__dirname, "../dist/index.html"));
  }
}

function showWindow() {
  if (!mainWindow) {
    createWindow();
    return;
  }
  mainWindow.show();
  if (mainWindow.isMinimized()) mainWindow.restore();
  mainWindow.focus();
}

function createTray() {
  tray = new Tray(appIcon());
  tray.setToolTip("Brake");
  tray.setContextMenu(Menu.buildFromTemplate([
    { label: "Show Brake", click: showWindow },
    { type: "separator" },
    {
      label: "Quit Brake",
      click: () => {
        isQuitting = true;
        app.quit();
      }
    }
  ]));
  tray.on("double-click", showWindow);
}

app.whenReady().then(async () => {
  if (isDev) {
    await queuedBackend("status");
  }
  startDevAgent();
  await queuedBackend("resume-lockout");
  createTray();

  ipcMain.handle("brake:status", async () => queuedBackend("status"));
  ipcMain.handle("brake:ensure-recovery", async () => queuedBackend("ensure-recovery"));
  ipcMain.handle("brake:enable", async (_event, password) => (
    queuedBackend("enable", ["--password", String(password)])
  ));
  ipcMain.handle("brake:disable", async (_event, password) => (
    queuedBackend("disable", ["--password", String(password)])
  ));
  ipcMain.handle("brake:reset-password", async (_event, payload) => (
    queuedBackend("reset-password", [
      "--recovery-code", String(payload?.recoveryCode || ""),
      "--new-password", String(payload?.newPassword || "")
    ])
  ));
  ipcMain.handle("brake:set-duration", async (_event, minutes) => (
    queuedBackend("set-duration", ["--minutes", String(minutes)])
  ));
  ipcMain.handle("brake:set-sensitivity", async (_event, value) => (
    queuedBackend("set-sensitivity", ["--value", String(value)])
  ));
  ipcMain.handle("brake:set-sensitivity-with-password", async (_event, payload) => (
    queuedBackend("set-sensitivity", [
      "--value", String(payload?.value || ""),
      "--password", String(payload?.password || "")
    ])
  ));
  ipcMain.handle("brake:set-anime-enabled", async (_event, enabled) => (
    queuedBackend("set-anime-enabled", ["--enabled", enabled ? "true" : "false"])
  ));
  ipcMain.handle("brake:set-anime-enabled-with-password", async (_event, payload) => (
    queuedBackend("set-anime-enabled", [
      "--enabled", payload?.enabled ? "true" : "false",
      "--password", String(payload?.password || "")
    ])
  ));
  ipcMain.handle("brake:set-anime-mode", async (_event, value) => (
    queuedBackend("set-anime-mode", ["--value", String(value)])
  ));
  ipcMain.handle("brake:set-anime-mode-with-password", async (_event, payload) => (
    queuedBackend("set-anime-mode", [
      "--value", String(payload?.value || ""),
      "--password", String(payload?.password || "")
    ])
  ));
  ipcMain.handle("brake:set-recovery-settings", async (_event, payload) => (
    queuedBackend("set-recovery-settings", [
      "--recovery-unlock-delay", String(payload?.recoveryUnlockDelayMinutes || ""),
      "--lockout-recovery-enabled", payload?.lockoutRecoveryEnabled ? "true" : "false",
      "--lockout-recovery-delay", String(payload?.lockoutRecoveryDelayMinutes || ""),
      "--password", String(payload?.password || "")
    ])
  ));
  ipcMain.handle("brake:set-shutdown-after-lockout", async (_event, payload) => (
    queuedBackend("set-shutdown-after-lockout", [
      "--enabled", payload?.enabled ? "true" : "false",
      "--password", String(payload?.password || "")
    ])
  ));
  ipcMain.handle("brake:anime-status", async () => (
    queuedBackend("anime-status")
  ));
  ipcMain.handle("brake:anime-download", async () => (
    queuedBackend("anime-download", [], 30 * 60 * 1000)
  ));
  ipcMain.handle("brake:detection-logs", async () => (
    queuedBackend("detection-logs", ["--limit", "100"])
  ));
  ipcMain.handle("brake:clear-detection-logs", async () => (
    queuedBackend("clear-detection-logs")
  ));
  ipcMain.handle("brake:set-commitment", async (_event, payload) => (
    queuedBackend("set-commitment", [
      "--until", String(payload?.until || ""),
      "--password", String(payload?.password || "")
    ])
  ));
  ipcMain.handle("brake:test-lockout", async () => (
    queuedBackend("test-lockout", ["--seconds", "10"])
  ));

  ipcMain.on("window:minimize", (event) => {
    BrowserWindow.fromWebContents(event.sender)?.minimize();
  });

  ipcMain.on("window:toggle-maximize", (event) => {
    const win = BrowserWindow.fromWebContents(event.sender);
    if (!win) return;
    if (win.isMaximized()) {
      win.unmaximize();
    } else {
      win.maximize();
    }
  });

  ipcMain.on("window:close", (event) => {
    BrowserWindow.fromWebContents(event.sender)?.close();
  });

  createWindow();

  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow();
    }
  });
});

app.on("window-all-closed", () => {
  // Keep the tray process alive. The background service/agent owns protection.
});

app.on("before-quit", () => {
  isQuitting = true;
  if (devAgent) {
    devAgent.kill();
    devAgent = null;
  }
});
