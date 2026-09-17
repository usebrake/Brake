const fs = require("node:fs");
const path = require("node:path");

const DEMO_RECOVERY_CODE = "DEMO-RECOVERY-CODE";

function defaultState() {
  return {
    initialized: true,
    enabled: false,
    failSecure: false,
    stateError: "",
    commitmentActive: false,
    committedUntil: null,
    lockoutDurationMinutes: 15,
    detectionSensitivity: "balanced",
    animeDetectionEnabled: false,
    animeDetectionMode: "standard",
    animeModelStatus: "ready",
    recoveryUnlockAfter: null,
    recoveryUnlockPending: false,
    recoveryUnlockDelayMinutes: 15,
    lockoutRecoveryEnabled: true,
    lockoutRecoveryDelayMinutes: 0,
    lockoutRecoveryUsesPer24h: 1,
    shutdownAfterLockout: false,
    password: "demo123",
    recoveryShown: false,
    events: []
  };
}

function option(args, name, fallback = "") {
  const index = args.indexOf(name);
  return index >= 0 && index + 1 < args.length ? String(args[index + 1]) : fallback;
}

function asBoolean(value) {
  return String(value).toLowerCase() === "true";
}

function createDemoBackend(dataDir) {
  const statePath = path.join(dataDir, "state.json");
  let state = load();

  function load() {
    try {
      return { ...defaultState(), ...JSON.parse(fs.readFileSync(statePath, "utf8")) };
    } catch {
      return defaultState();
    }
  }

  function save() {
    fs.mkdirSync(dataDir, { recursive: true });
    fs.writeFileSync(statePath, JSON.stringify(state, null, 2), "utf8");
  }

  function normalizedStatus() {
    if (state.committedUntil && Date.parse(state.committedUntil) <= Date.now()) {
      state.commitmentActive = false;
      state.committedUntil = null;
      save();
    }
    const { password, recoveryShown, events, ...status } = state;
    return status;
  }

  function ok(data = normalizedStatus()) {
    return { ok: true, data };
  }

  function error(code) {
    return { ok: false, error: code };
  }

  function passwordAccepted(args) {
    return option(args, "--password") === state.password;
  }

  function handle(command, args = []) {
    switch (command) {
      case "status":
        return ok();
      case "ensure-recovery": {
        const token = state.recoveryShown ? null : DEMO_RECOVERY_CODE;
        state.recoveryShown = true;
        save();
        return ok({ hasRecovery: true, token });
      }
      case "resume-lockout":
        return ok({ activeLockout: false });
      case "enable": {
        const password = option(args, "--password");
        if (password.length < 6) return error("password_too_short");
        state.password = password;
        state.enabled = true;
        save();
        return ok();
      }
      case "disable":
        if (state.commitmentActive) return error("commitment_active");
        if (!passwordAccepted(args)) return error("wrong_password");
        state.enabled = false;
        state.recoveryUnlockAfter = null;
        state.recoveryUnlockPending = false;
        save();
        return ok();
      case "reset-password": {
        if (option(args, "--recovery-code") !== DEMO_RECOVERY_CODE) {
          return error("wrong_recovery_code");
        }
        const password = option(args, "--new-password");
        if (password.length < 6) return error("password_too_short");
        state.password = password;
        state.failSecure = false;
        state.stateError = "";
        save();
        return ok();
      }
      case "set-duration":
        state.lockoutDurationMinutes = Math.max(1, Math.min(60, Number(option(args, "--minutes", "15")) || 15));
        save();
        return ok();
      case "set-sensitivity":
        state.detectionSensitivity = option(args, "--value", "balanced");
        save();
        return ok();
      case "set-anime-enabled":
        state.animeDetectionEnabled = asBoolean(option(args, "--enabled"));
        save();
        return ok();
      case "set-anime-mode":
        state.animeDetectionMode = option(args, "--value", "standard");
        save();
        return ok();
      case "set-recovery-settings":
        state.recoveryUnlockDelayMinutes = Number(option(args, "--recovery-unlock-delay", "15"));
        state.lockoutRecoveryEnabled = asBoolean(option(args, "--lockout-recovery-enabled", "true"));
        state.lockoutRecoveryDelayMinutes = Number(option(args, "--lockout-recovery-delay", "0"));
        state.lockoutRecoveryUsesPer24h = Number(option(args, "--lockout-recovery-uses", "1"));
        save();
        return ok();
      case "cancel-recovery-unlock":
        state.recoveryUnlockAfter = null;
        state.recoveryUnlockPending = false;
        save();
        return ok();
      case "set-shutdown-after-lockout":
        state.shutdownAfterLockout = asBoolean(option(args, "--enabled"));
        save();
        return ok();
      case "anime-status":
      case "anime-download":
        state.animeModelStatus = "ready";
        save();
        return ok({ animeModelStatus: "ready", modelDir: "Demo mode" });
      case "detection-logs":
        return ok({ events: state.events });
      case "clear-detection-logs":
        state.events = [];
        save();
        return ok({ events: [] });
      case "set-commitment": {
        if (!passwordAccepted(args)) return error("wrong_password");
        const until = option(args, "--until");
        if (!Number.isFinite(Date.parse(until)) || Date.parse(until) <= Date.now()) {
          return error("commitment_must_be_future");
        }
        state.enabled = true;
        state.commitmentActive = true;
        state.committedUntil = new Date(until).toISOString();
        state.recoveryUnlockAfter = null;
        state.recoveryUnlockPending = false;
        save();
        return ok();
      }
      default:
        return error(`unknown_command:${command}`);
    }
  }

  function applyScenario(name) {
    const base = defaultState();
    const inOneHour = new Date(Date.now() + 60 * 60 * 1000).toISOString();
    const inFifteenMinutes = new Date(Date.now() + 15 * 60 * 1000).toISOString();
    if (name === "reset" || name === "protection-off") {
      state = base;
    } else if (name === "protection-on") {
      state = { ...base, enabled: true, recoveryShown: true };
    } else if (name === "commitment") {
      state = {
        ...base,
        enabled: true,
        commitmentActive: true,
        committedUntil: inOneHour,
        recoveryShown: true
      };
    } else if (name === "recovery-pending") {
      state = {
        ...base,
        enabled: true,
        recoveryUnlockPending: true,
        recoveryUnlockAfter: inFifteenMinutes,
        recoveryShown: true
      };
    } else if (name === "repair-required") {
      state = {
        ...base,
        enabled: true,
        failSecure: true,
        stateError: "Demo untrusted state",
        recoveryShown: true
      };
    } else if (name === "sample-logs") {
      state = {
        ...base,
        enabled: true,
        recoveryShown: true,
        events: [
          {
            timestamp: new Date().toISOString(),
            detector: "nudity",
            triggered: true,
            severity: "hard",
            confidence: 0.94,
            label: "Demo detection",
            action: "detected"
          }
        ]
      };
    }
    save();
    return ok();
  }

  function reset() {
    state = defaultState();
    save();
    return ok();
  }

  return { applyScenario, handle, reset, status: normalizedStatus };
}

module.exports = { createDemoBackend, DEMO_RECOVERY_CODE };
