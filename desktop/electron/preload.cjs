const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("brake", {
  status: () => ipcRenderer.invoke("brake:status"),
  ensureRecovery: () => ipcRenderer.invoke("brake:ensure-recovery"),
  enable: (password) => ipcRenderer.invoke("brake:enable", password),
  disable: (password) => ipcRenderer.invoke("brake:disable", password),
  resetPassword: (payload) => ipcRenderer.invoke("brake:reset-password", payload),
  setDuration: (minutes) => ipcRenderer.invoke("brake:set-duration", minutes),
  setSensitivity: (value) => ipcRenderer.invoke("brake:set-sensitivity", value),
  setSensitivityWithPassword: (payload) => ipcRenderer.invoke("brake:set-sensitivity-with-password", payload),
  setAnimeEnabled: (enabled) => ipcRenderer.invoke("brake:set-anime-enabled", enabled),
  setAnimeEnabledWithPassword: (payload) => ipcRenderer.invoke("brake:set-anime-enabled-with-password", payload),
  setAnimeMode: (value) => ipcRenderer.invoke("brake:set-anime-mode", value),
  setAnimeModeWithPassword: (payload) => ipcRenderer.invoke("brake:set-anime-mode-with-password", payload),
  setRecoverySettings: (payload) => ipcRenderer.invoke("brake:set-recovery-settings", payload),
  setShutdownAfterLockout: (payload) => ipcRenderer.invoke("brake:set-shutdown-after-lockout", payload),
  animeStatus: () => ipcRenderer.invoke("brake:anime-status"),
  downloadAnime: () => ipcRenderer.invoke("brake:anime-download"),
  setCommitment: (payload) => ipcRenderer.invoke("brake:set-commitment", payload),
  testLockout: () => ipcRenderer.invoke("brake:test-lockout"),
  minimize: () => ipcRenderer.send("window:minimize"),
  toggleMaximize: () => ipcRenderer.send("window:toggle-maximize"),
  close: () => ipcRenderer.send("window:close")
});
