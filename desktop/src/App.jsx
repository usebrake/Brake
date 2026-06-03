import {
  Activity,
  Clock,
  Download,
  Info,
  Gauge,
  Maximize,
  Minus,
  Plus,
  Power,
  ScanEye,
  ShieldCheck,
  ShieldOff,
  X
} from "lucide-react";
import React from "react";
import { useEffect, useRef, useState } from "react";

const fallbackStatus = {
  initialized: true,
  enabled: false,
  commitmentActive: false,
  committedUntil: null,
  lockoutDurationMinutes: 3,
  detectionSensitivity: "balanced",
  animeDetectionEnabled: false,
  animeDetectionMode: "standard",
  animeModelStatus: "not_installed",
  recoveryUnlockAfter: null,
  recoveryUnlockPending: false
};
const MIN_PASSWORD_LENGTH = 6;
const SENSITIVITY_RANK = { light: 0, balanced: 1, strict: 2 };
const ANIME_MODE_RANK = { standard: 0, strict: 1 };

function BrakeMark({ tone = "gold" }) {
  return (
    <span className={`brake-mark ${tone}`} aria-hidden="true">
      <span />
      <span />
    </span>
  );
}

function Button({ variant = "secondary", icon: Icon, children, onClick, disabled = false }) {
  return (
    <button className={`btn ${variant}`} onClick={onClick} disabled={disabled}>
      {Icon ? <Icon size={16} strokeWidth={2.2} /> : null}
      <span>{children}</span>
    </button>
  );
}

function Badge({ state, children }) {
  return <span className={`badge ${state || ""}`}>{children}</span>;
}

function formatCommitmentLeft(committedUntil, now) {
  if (!committedUntil) return "";
  const end = new Date(committedUntil).getTime();
  const remainingMs = end - now;
  if (!Number.isFinite(end) || remainingMs <= 0) return "ending soon";

  const totalMinutes = Math.ceil(remainingMs / 60000);
  if (totalMinutes < 60) {
    return `${totalMinutes} ${totalMinutes === 1 ? "minute" : "minutes"} left`;
  }

  const totalHours = Math.ceil(totalMinutes / 60);
  if (totalHours < 24) {
    return `${totalHours} ${totalHours === 1 ? "hour" : "hours"} left`;
  }

  const totalDays = Math.ceil(totalHours / 24);
  return `${totalDays} ${totalDays === 1 ? "day" : "days"} left`;
}

function formatRecoveryUnlockLeft(unlockAfter, now) {
  if (!unlockAfter) return "";
  const end = new Date(unlockAfter).getTime();
  const remainingMs = end - now;
  if (!Number.isFinite(end) || remainingMs <= 0) return "ending soon";
  const totalMinutes = Math.ceil(remainingMs / 60000);
  return `${totalMinutes} ${totalMinutes === 1 ? "minute" : "minutes"} left`;
}

function animeStatusCopy(status) {
  const labels = {
    ready: "Ready",
    not_installed: "Not installed",
    missing_dependencies: "Missing Python packages",
    installing: "Installing"
  };
  return labels[status] || "Not installed";
}

function StatusPanel({ status, now }) {
  const committed = status.commitmentActive;
  const enabled = status.enabled;
  const recoveryLeft = status.recoveryUnlockPending ? formatRecoveryUnlockLeft(status.recoveryUnlockAfter, now) : "";
  const state = committed ? "committed" : enabled ? "protected" : "off";
  const commitmentLeft = committed ? formatCommitmentLeft(status.committedUntil, now) : "";

  return (
    <section className={`status-panel ${state}`}>
      <div className="status-rail" />
      <div className="status-icon">
        {enabled || committed ? (
          <ShieldCheck size={28} />
        ) : (
          <Power size={27} />
        )}
      </div>
      <div className="status-copy">
        <div className="eyebrow">{recoveryLeft ? "RECOVERY COOLDOWN" : committed ? "COMMITTED" : enabled ? "PROTECTED" : "OFF"}</div>
        <h2>{recoveryLeft ? "Emergency unlock pending" : committed ? "Commitment active" : enabled ? "You're covered" : "Protection is off"}</h2>
        <p>
          {recoveryLeft
            ? "Recovery code accepted. Brake will turn protection off after the cooldown."
            : committed
            ? "Password cannot turn protection off until the commitment ends."
            : enabled
              ? "Brake is watching your screen. Local only."
              : "Brake is not watching right now."}
        </p>
        {commitmentLeft ? <p className="status-meta">{commitmentLeft}</p> : null}
        {recoveryLeft ? <p className="status-meta">{recoveryLeft}</p> : null}
      </div>
      <Badge state={state}>{recoveryLeft ? recoveryLeft : committed ? commitmentLeft || "Locked in" : enabled ? "Active" : "Idle"}</Badge>
    </section>
  );
}

function Card({ icon: Icon, title, subtitle, children }) {
  return (
    <section className="card">
      <header className="card-head">
        {Icon ? (
          <span className="lead-icon">
            <Icon size={17} />
          </span>
        ) : null}
        <div>
          <h3>{title}</h3>
          {subtitle ? <p>{subtitle}</p> : null}
        </div>
      </header>
      <div className="card-body">{children}</div>
    </section>
  );
}

function SettingRow({ title, description, aside }) {
  return (
    <div className="setting-row">
      <div>
        <div className="setting-title">{title}</div>
        {description ? <div className="setting-description">{description}</div> : null}
      </div>
      <div className="setting-aside">{aside}</div>
    </div>
  );
}

function SensitivityOption({ active, title, description, onClick, disabled = false, note = "" }) {
  return (
    <button className={`radio-row ${active ? "active" : ""}`} onClick={onClick} disabled={disabled}>
      <span className="radio-dot" />
      <div>
        <div className="setting-title">{title}</div>
        <div className="setting-description">{description}</div>
        {note ? <div className="setting-note">{note}</div> : null}
      </div>
    </button>
  );
}

function Modal({ title, children, onClose }) {
  return (
    <div className="modal-scrim" role="presentation" onMouseDown={onClose}>
      <section className="modal" role="dialog" aria-modal="true" aria-label={title} onMouseDown={(event) => event.stopPropagation()}>
        <header className="modal-head">
          <span className="lead-icon">
            <Info size={17} />
          </span>
          <div>
            <h2>{title}</h2>
            <p>Local screen accountability with calm friction.</p>
          </div>
          <button className="icon-button" aria-label="Close" onClick={onClose}>
            <X size={18} />
          </button>
        </header>
        <div className="modal-body">{children}</div>
      </section>
    </div>
  );
}

function PasswordModal({ mode, durationMinutes, commitmentActive, error, onCancel, onSubmit, onRecoverPassword }) {
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const enabling = mode === "enable";

  const submit = (event) => {
    event.preventDefault();
    if (enabling && password.length < MIN_PASSWORD_LENGTH) {
      onSubmit(password, "Password must be at least 6 characters.");
      return;
    }
    if (enabling && password !== confirmPassword) {
      onSubmit(password, "Passwords do not match.");
      return;
    }
    onSubmit(password, "");
  };

  return (
    <Modal title={enabling ? "Turn on protection" : "Turn off protection"} onClose={onCancel}>
      <form className="password-form" onSubmit={submit}>
        <p>
          {enabling
            ? "You'll set a new password for this session. Past passwords no longer work."
            : commitmentActive
              ? "Commitment is active. Your regular password cannot turn protection off right now. Entering your recovery code starts a 10-minute emergency cooldown before Brake turns off."
              : "Enter the current password to turn protection off. If you enter your recovery code instead, Brake starts a 10-minute emergency cooldown before turning off."}
        </p>
        {enabling ? (
          <p>
            Explicit content triggers a <strong>{durationMinutes}-minute</strong> lockout, then Windows shuts down.
            After restart, a five-minute strict watch starts. Incidental nudity gets a short warning first.
          </p>
        ) : null}
        <label className="field">
          <span>{enabling ? "New password" : "Password"}</span>
          <input
            autoFocus
            type="password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
          />
        </label>
        {enabling ? (
          <label className="field">
            <span>Confirm password</span>
            <input
              type="password"
              value={confirmPassword}
              onChange={(event) => setConfirmPassword(event.target.value)}
            />
          </label>
        ) : null}
        {!enabling ? (
          <button className="link-button form-link" type="button" onClick={onRecoverPassword}>
            Forgot password? Use recovery code
          </button>
        ) : null}
        {error ? <p className="form-error">{error}</p> : null}
        <div className="modal-actions">
          <button className="btn secondary" type="button" onClick={onCancel}>Cancel</button>
          <button className="btn primary" type="submit">
            {enabling ? "Turn on" : "Turn off"}
          </button>
        </div>
      </form>
    </Modal>
  );
}

function ResetPasswordModal({ error, onCancel, onSubmit }) {
  const [recoveryCode, setRecoveryCode] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");

  const submit = (event) => {
    event.preventDefault();
    if (!recoveryCode.trim()) {
      onSubmit(null, "Enter your recovery code.");
      return;
    }
    if (newPassword.length < MIN_PASSWORD_LENGTH) {
      onSubmit(null, "Password must be at least 6 characters.");
      return;
    }
    if (newPassword !== confirmPassword) {
      onSubmit(null, "Passwords do not match.");
      return;
    }
    onSubmit({ recoveryCode: recoveryCode.trim(), newPassword }, "");
  };

  return (
    <Modal title="Reset password" onClose={onCancel}>
      <form className="password-form" onSubmit={submit}>
        <p>
          Use your recovery code to set a new protection password. This keeps protection and any active commitment exactly as they are.
        </p>
        <label className="field">
          <span>Recovery code</span>
          <input
            autoFocus
            type="password"
            value={recoveryCode}
            onChange={(event) => setRecoveryCode(event.target.value)}
          />
        </label>
        <label className="field">
          <span>New password</span>
          <input
            type="password"
            value={newPassword}
            onChange={(event) => setNewPassword(event.target.value)}
          />
        </label>
        <label className="field">
          <span>Confirm password</span>
          <input
            type="password"
            value={confirmPassword}
            onChange={(event) => setConfirmPassword(event.target.value)}
          />
        </label>
        {error ? <p className="form-error">{error}</p> : null}
        <div className="modal-actions">
          <button className="btn secondary" type="button" onClick={onCancel}>Cancel</button>
          <button className="btn primary" type="submit">Reset password</button>
        </div>
      </form>
    </Modal>
  );
}

function ConfirmModal({ title, body, confirmLabel = "Confirm", warning = "", onCancel, onConfirm }) {
  return (
    <Modal title={title} onClose={onCancel}>
      <div className="password-form">
        <p>{body}</p>
        {warning ? <p className="form-warning">{warning}</p> : null}
        <div className="modal-actions">
          <button className="btn secondary" type="button" onClick={onCancel}>Cancel</button>
          <button className="btn primary" type="button" onClick={onConfirm}>{confirmLabel}</button>
        </div>
      </div>
    </Modal>
  );
}

function SettingsPasswordModal({ title, body, error, onCancel, onSubmit }) {
  const [password, setPassword] = useState("");

  const submit = (event) => {
    event.preventDefault();
    if (!password) {
      onSubmit("", "Enter your password.");
      return;
    }
    onSubmit(password, "");
  };

  return (
    <Modal title={title} onClose={onCancel}>
      <form className="password-form" onSubmit={submit}>
        <p>{body}</p>
        <label className="field">
          <span>Password</span>
          <input
            autoFocus
            type="password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
          />
        </label>
        {error ? <p className="form-error">{error}</p> : null}
        <div className="modal-actions">
          <button className="btn secondary" type="button" onClick={onCancel}>Cancel</button>
          <button className="btn primary" type="submit">Apply change</button>
        </div>
      </form>
    </Modal>
  );
}

function CommitmentModal({ error, onCancel, onSubmit }) {
  const [amount, setAmount] = useState(3);
  const [unit, setUnit] = useState("days");
  const [password, setPassword] = useState("");

  const submit = (event) => {
    event.preventDefault();
    if (!password) {
      onSubmit(null, "Enter your password.");
      return;
    }
    const safeAmount = Math.max(1, Math.min(365, Number(amount) || 1));
    const millis = safeAmount * (unit === "hours" ? 60 * 60 * 1000 : 24 * 60 * 60 * 1000);
    const until = new Date(Date.now() + millis).toISOString().replace("Z", "+00:00");
    onSubmit({ until, password }, "");
  };

  return (
    <Modal title="Lock in a commitment" onClose={onCancel}>
      <form className="password-form" onSubmit={submit}>
        <p>
          While a commitment is active, your password cannot turn protection off.
          You can still make settings stricter, but not looser.
        </p>
        <div className="inline-fields">
          <label className="field compact">
            <span>Lock in for</span>
            <input
              min="1"
              max="365"
              type="number"
              value={amount}
              onChange={(event) => setAmount(event.target.value)}
            />
          </label>
          <label className="field compact">
            <span>Unit</span>
            <select value={unit} onChange={(event) => setUnit(event.target.value)}>
              <option value="days">days</option>
              <option value="hours">hours</option>
            </select>
          </label>
        </div>
        <label className="field">
          <span>Password</span>
          <input
            autoFocus
            type="password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
          />
        </label>
        {error ? <p className="form-error">{error}</p> : null}
        <div className="modal-actions">
          <button className="btn secondary" type="button" onClick={onCancel}>Cancel</button>
          <button className="btn primary" type="submit">Lock it in</button>
        </div>
      </form>
    </Modal>
  );
}

function RecoveryModal({ token, regenerated = false, onClose }) {
  const [copied, setCopied] = useState(false);

  const copy = () => {
    navigator.clipboard?.writeText(token).then(() => setCopied(true));
  };

  return (
    <Modal title={regenerated ? "New recovery code" : "Save your recovery code"} onClose={onClose}>
      <div className="password-form">
        <p>
          This code can reset your password immediately. It can also start a 10-minute emergency cooldown to turn Brake off if you get stuck behind a commitment.
          You will not see this exact code again.
        </p>
        <p>
          Do not save it somewhere easy to reach on this computer. Write it on paper, take a photo on your phone, or give it to someone you trust.
          If you want the strongest commitment, you can choose not to copy it, but then a forgotten password may require a full reset.
        </p>
        <label className="field">
          <span>Recovery code</span>
          <input readOnly value={token} onFocus={(event) => event.target.select()} />
        </label>
        <p className="form-warning">Anyone with this code can reset your password or schedule emergency disable on this machine. Treat it like a password, but keep it away from impulse access.</p>
        <div className="modal-actions">
          <button className="btn secondary" type="button" onClick={copy}>
            {copied ? "Copied" : "Copy"}
          </button>
          <button className="btn primary" type="button" onClick={onClose}>I understand</button>
        </div>
      </div>
    </Modal>
  );
}

function GuideSection({ title, children }) {
  return (
    <section className="guide-section">
      <h3>{title}</h3>
      <div>{children}</div>
    </section>
  );
}

function GuideModal({ tab, status, onClose }) {
  const duration = Number(status.lockoutDurationMinutes) || 1;
  const title = tab === "anime"
    ? "How Anime works"
    : tab === "detection"
      ? "How Detection works"
      : "How Overview works";

  return (
    <Modal title={title} onClose={onClose}>
      {tab === "overview" ? (
        <div className="guide">
          <GuideSection title="What Brake does">
            <p>Brake watches your screen locally. Screenshots are checked on this computer and are not uploaded, saved, or sent anywhere.</p>
          </GuideSection>
          <GuideSection title="When protection is on">
            <p>Clear explicit content triggers your full lockout. With your current setting, that lockout lasts {duration} {duration === 1 ? "minute" : "minutes"}.</p>
            <p>When that full lockout ends, Windows shuts down. After restart, Brake starts a short strict-watch window to prevent immediately reopening the same content.</p>
          </GuideSection>
          <GuideSection title="Commitment">
            <p>A commitment locks your settings in. Your normal password cannot turn protection off until the commitment ends.</p>
            <p>During commitment, you can make Brake stricter, but you cannot make it easier to bypass. The recovery code can reset a forgotten password, or start a 10-minute emergency cooldown before protection turns off.</p>
          </GuideSection>
        </div>
      ) : tab === "detection" ? (
        <div className="guide">
          <GuideSection title="Photo and video detection">
            <p>Detection uses the main nudity detector for real photos, videos, streams, and browser content.</p>
            <p>Exposed genitals or anus are treated as hard explicit content. Those trigger the full lockout and shutdown flow.</p>
          </GuideSection>
          <GuideSection title="Sensitivity levels">
            <p><strong>Light:</strong> only clear explicit content triggers. Incidental nudity is ignored as much as possible.</p>
            <p><strong>Balanced:</strong> best default. Clear explicit content still locks. Partial nudity gets a short warning pause instead of a shutdown.</p>
            <p><strong>Strict:</strong> more aggressive for partial nudity, but it asks for matching scans first so one random false hit is filtered out.</p>
          </GuideSection>
          <GuideSection title="Changing sensitivity">
            <p>Making detection stricter asks for confirmation. If commitment is active, you cannot lower it again until commitment ends.</p>
            <p>If protection is on without commitment, lowering sensitivity requires your password.</p>
          </GuideSection>
        </div>
      ) : (
        <div className="guide">
          <GuideSection title="Illustrated detection">
            <p>Anime detection is optional because it uses a separate local model. Once downloaded, it runs on this computer only.</p>
            <p>The model labels images as normal or NSFW. It does not identify exact body parts like the main photo detector.</p>
          </GuideSection>
          <GuideSection title="Anime modes">
            <p><strong>Not strict:</strong> illustrated NSFW causes a short pause only. It does not start the shutdown flow.</p>
            <p><strong>Strict:</strong> very high-confidence illustrated NSFW can trigger the full lockout. Lower-confidence hits still use the short pause.</p>
          </GuideSection>
          <GuideSection title="Locking anime settings">
            <p>Turning anime detection on during commitment locks it on until the commitment ends.</p>
            <p>If protection is on without commitment, turning anime detection off or lowering anime strictness requires your password.</p>
          </GuideSection>
        </div>
      )}
    </Modal>
  );
}

function WindowChrome() {
  return (
    <div className="window-chrome">
      <div className="drag-region" />
      <div className="window-controls">
        <button aria-label="Minimize" onClick={() => window.brake?.minimize?.()}>
          <Minus size={15} />
        </button>
        <button aria-label="Maximize" onClick={() => window.brake?.toggleMaximize?.()}>
          <Maximize size={13} />
        </button>
        <button className="close" aria-label="Close" onClick={() => window.brake?.close?.()}>
          <X size={15} />
        </button>
      </div>
    </div>
  );
}

export default function App() {
  const [tab, setTab] = useState("overview");
  const [status, setStatus] = useState(fallbackStatus);
  const [showInfo, setShowInfo] = useState(false);
  const [notice, setNotice] = useState("");
  const [passwordPrompt, setPasswordPrompt] = useState(null);
  const [resetPasswordPrompt, setResetPasswordPrompt] = useState(null);
  const [commitmentPrompt, setCommitmentPrompt] = useState(null);
  const [recoveryPrompt, setRecoveryPrompt] = useState(null);
  const [confirmPrompt, setConfirmPrompt] = useState(null);
  const [settingsPasswordPrompt, setSettingsPasswordPrompt] = useState(null);
  const [animeInstalling, setAnimeInstalling] = useState(false);
  const [now, setNow] = useState(Date.now());
  const durationSaveTimer = useRef(null);
  const sensitivitySaveTimer = useRef(null);
  const pendingDuration = useRef(false);
  const pendingSensitivity = useRef(false);
  const durationPreserveUntil = useRef(0);
  const sensitivityPreserveUntil = useRef(0);
  const durationDraft = useRef(fallbackStatus.lockoutDurationMinutes);

  useEffect(() => {
    let alive = true;
    const refresh = () => {
      window.brake?.status?.().then((response) => {
        if (!alive || !response) return;
        if (response.ok) {
          mergeBackendStatus(response.data);
        } else {
          setNotice(response.error || "Backend is not available yet.");
        }
      });
    };
    refresh();
    window.brake?.ensureRecovery?.().then((response) => {
      if (!alive || !response?.ok || !response.data?.token) return;
      setRecoveryPrompt({ token: response.data.token, regenerated: false });
    });
    const timer = window.setInterval(refresh, 2500);
    const clockTimer = window.setInterval(() => setNow(Date.now()), 30000);
    return () => {
      alive = false;
      window.clearInterval(timer);
      window.clearInterval(clockTimer);
      window.clearTimeout(durationSaveTimer.current);
      window.clearTimeout(sensitivitySaveTimer.current);
    };
  }, []);

  const protectedTone = status.commitmentActive ? "amber" : status.enabled ? "teal" : "gold";
  const mergeBackendStatus = (data) => {
    setStatus((current) => {
      const now = Date.now();
      const keepDuration = pendingDuration.current || now < durationPreserveUntil.current;
      const keepSensitivity = pendingSensitivity.current || now < sensitivityPreserveUntil.current;
      const nextDuration = keepDuration ? current.lockoutDurationMinutes : data.lockoutDurationMinutes;
      durationDraft.current = Number(nextDuration) || fallbackStatus.lockoutDurationMinutes;
      return {
        ...fallbackStatus,
        ...data,
        lockoutDurationMinutes: nextDuration,
        ...(animeInstalling ? { animeModelStatus: "installing" } : {}),
        ...(keepSensitivity ? { detectionSensitivity: current.detectionSensitivity } : {})
      };
    });
  };
  const applyBackendResponse = (response) => {
    if (!response?.ok) {
      setNotice(humanError(response?.error || "That change was not accepted."));
      return false;
    }
    mergeBackendStatus(response.data);
    setNotice("");
    return true;
  };
  const saveDurationSoon = (minutes) => {
    pendingDuration.current = true;
    durationPreserveUntil.current = Date.now() + 1200;
    window.clearTimeout(durationSaveTimer.current);
    durationSaveTimer.current = window.setTimeout(() => {
      window.brake?.setDuration?.(minutes).then((response) => {
        if (response?.ok) {
          pendingDuration.current = false;
          durationPreserveUntil.current = Date.now() + 700;
        } else {
          pendingDuration.current = false;
          durationPreserveUntil.current = 0;
        }
        applyBackendResponse(response);
      });
    }, 180);
  };
  const saveSensitivitySoon = (value) => {
    pendingSensitivity.current = true;
    sensitivityPreserveUntil.current = Date.now() + 1200;
    window.clearTimeout(sensitivitySaveTimer.current);
    sensitivitySaveTimer.current = window.setTimeout(() => {
      window.brake?.setSensitivity?.(value).then((response) => {
        if (response?.ok) {
          pendingSensitivity.current = false;
          sensitivityPreserveUntil.current = Date.now() + 700;
        } else {
          pendingSensitivity.current = false;
          sensitivityPreserveUntil.current = 0;
        }
        applyBackendResponse(response);
      });
    }, 180);
  };
  const toggleProtection = () => {
    setPasswordPrompt({ mode: status.enabled ? "disable" : "enable", error: "" });
  };
  const submitProtectionPassword = (password, localError = "") => {
    const mode = passwordPrompt?.mode;
    if (!mode) return;
    if (localError) {
      setPasswordPrompt((current) => ({ ...current, error: localError }));
      return;
    }
    const call = mode === "enable" ? window.brake?.enable : window.brake?.disable;
    call?.(password).then((response) => {
      if (response?.ok) {
        applyBackendResponse(response);
        setPasswordPrompt(null);
        if (mode === "enable") {
          setNotice("Protection is on.");
        } else if (response.data?.recoveryUnlockPending) {
          setNotice("Recovery code accepted. Protection will turn off after the 10-minute cooldown.");
        } else {
          setNotice("Protection is off.");
        }
        return;
      }
      setPasswordPrompt((current) => ({
        ...current,
        error: humanError(response?.error || "That password was not accepted.")
      }));
    });
  };
  const submitPasswordReset = (payload, localError = "") => {
    if (localError) {
      setResetPasswordPrompt((current) => ({ ...current, error: localError }));
      return;
    }
    window.brake?.resetPassword?.(payload).then((response) => {
      if (response?.ok) {
        applyBackendResponse(response);
        setResetPasswordPrompt(null);
        setPasswordPrompt(null);
        setNotice("Password reset. Use your new password from now on.");
        return;
      }
      setResetPasswordPrompt((current) => ({
        ...current,
        error: humanError(response?.error || "Password reset failed.")
      }));
    });
  };
  const toggleCommitment = () => {
    if (status.commitmentActive) {
      setNotice("Commitment is active. Use Turn off protection with your recovery code for emergency override.");
      return;
    }
    setCommitmentPrompt({ error: "" });
  };
  const submitCommitment = (payload, localError = "") => {
    if (localError) {
      setCommitmentPrompt((current) => ({ ...current, error: localError }));
      return;
    }
    window.brake?.setCommitment?.(payload).then((response) => {
      if (response?.ok) {
        applyBackendResponse(response);
        setCommitmentPrompt(null);
        setNotice("Commitment is locked in.");
        return;
      }
      setCommitmentPrompt((current) => ({
        ...current,
        error: humanError(response?.error || "Commitment was not accepted.")
      }));
    });
  };
  const changeDuration = (delta) => {
    const next = Math.max(1, Math.min(60, (Number(durationDraft.current) || 1) + delta));
    durationDraft.current = next;
    setStatus((current) => ({ ...current, lockoutDurationMinutes: next }));
    saveDurationSoon(next);
  };
  const changeDurationInput = (value) => {
    if (value === "") {
      durationPreserveUntil.current = Date.now() + 1200;
      setStatus((current) => ({ ...current, lockoutDurationMinutes: "" }));
      return;
    }
    const parsed = Number.parseInt(value, 10);
    if (Number.isNaN(parsed)) return;
    const next = Math.max(1, Math.min(60, parsed));
    durationDraft.current = next;
    setStatus((current) => ({
      ...current,
      lockoutDurationMinutes: next
    }));
    saveDurationSoon(next);
  };
  const normalizeDurationInput = () => {
    const next = Math.max(1, Math.min(60, Number(status.lockoutDurationMinutes) || 1));
    durationDraft.current = next;
    setStatus((current) => ({ ...current, lockoutDurationMinutes: next }));
    saveDurationSoon(next);
  };
  const applySensitivity = (detectionSensitivity, password = "") => {
    const call = password ? window.brake?.setSensitivityWithPassword : window.brake?.setSensitivity;
    const previous = status.detectionSensitivity;
    setStatus((current) => ({ ...current, detectionSensitivity }));
    if (password) {
      call?.({ value: detectionSensitivity, password }).then((response) => {
        if (!response?.ok) {
          setStatus((current) => ({ ...current, detectionSensitivity: previous }));
        }
        if (applyBackendResponse(response)) {
          setSettingsPasswordPrompt(null);
        }
      });
      return;
    }
    saveSensitivitySoon(detectionSensitivity);
  };
  const requestSensitivity = (detectionSensitivity) => {
    const current = status.detectionSensitivity;
    if (detectionSensitivity === current) return;
    const currentRank = SENSITIVITY_RANK[current] ?? 1;
    const nextRank = SENSITIVITY_RANK[detectionSensitivity] ?? 1;
    if (nextRank < currentRank) {
      if (status.commitmentActive) {
        setNotice(humanError("commitment_blocks_loosening_sensitivity"));
        return;
      }
      if (status.enabled) {
        setSettingsPasswordPrompt({
          kind: "sensitivity",
          value: detectionSensitivity,
          title: "Lower detection sensitivity",
          body: "Protection is on. Enter your password to make detection less strict.",
          error: ""
        });
        return;
      }
      applySensitivity(detectionSensitivity);
      return;
    }
    setConfirmPrompt({
      title: "Make detection stricter?",
      body: "This raises how strongly Brake responds to possible explicit content.",
      warning: status.commitmentActive ? "Because commitment is active, you will not be able to lower it again until the commitment ends." : "",
      confirmLabel: "Make stricter",
      onConfirm: () => {
        setConfirmPrompt(null);
        applySensitivity(detectionSensitivity);
      }
    });
  };
  const installAnimeDetector = () => {
    setAnimeInstalling(true);
    setStatus((current) => ({ ...current, animeModelStatus: "installing" }));
    setNotice("Downloading illustrated detector. This can take a few minutes the first time.");
    window.brake?.downloadAnime?.().then((response) => {
      setAnimeInstalling(false);
      if (!response?.ok) {
        const nextModelStatus = response?.error === "missing_dependencies" ? "missing_dependencies" : "not_installed";
        setStatus((current) => ({ ...current, animeModelStatus: nextModelStatus }));
        setNotice(humanError(response?.error || "Anime detector download failed."));
        return;
      }
      const modelStatus = response.data?.animeModelStatus || "ready";
      setStatus((current) => ({ ...current, animeModelStatus: modelStatus }));
      setNotice(modelStatus === "ready" ? "Illustrated detector installed." : animeStatusCopy(modelStatus));
    });
  };
  const applyAnimeEnabled = (enabled, password = "") => {
    const call = password ? window.brake?.setAnimeEnabledWithPassword : window.brake?.setAnimeEnabled;
    setStatus((current) => ({ ...current, animeDetectionEnabled: enabled }));
    const arg = password ? { enabled, password } : enabled;
    call?.(arg).then((response) => {
      if (!response?.ok) {
        setStatus((current) => ({ ...current, animeDetectionEnabled: !enabled }));
      }
      if (applyBackendResponse(response)) {
        setSettingsPasswordPrompt(null);
      }
    });
  };
  const requestAnimeEnabled = (enabled) => {
    if (enabled === status.animeDetectionEnabled) return;
    if (enabled && status.animeModelStatus !== "ready") {
      setNotice(humanError("anime_model_not_ready"));
      return;
    }
    if (!enabled) {
      if (status.commitmentActive) {
        setNotice(humanError("commitment_blocks_unlocking_anime"));
        return;
      }
      if (status.enabled) {
        setSettingsPasswordPrompt({
          kind: "anime-enabled",
          value: false,
          title: "Turn off anime detection",
          body: "Protection is on. Enter your password to turn illustrated detection off.",
          error: ""
        });
        return;
      }
      applyAnimeEnabled(false);
      return;
    }
    setConfirmPrompt({
      title: "Turn on anime detection?",
      body: "Brake will start checking illustrated explicit content with the local model.",
      warning: status.commitmentActive ? "Because commitment is active, you will not be able to turn this off until the commitment ends." : "",
      confirmLabel: "Turn on",
      onConfirm: () => {
        setConfirmPrompt(null);
        applyAnimeEnabled(true);
      }
    });
  };
  const applyAnimeMode = (animeDetectionMode, password = "") => {
    const call = password ? window.brake?.setAnimeModeWithPassword : window.brake?.setAnimeMode;
    const previous = status.animeDetectionMode;
    setStatus((current) => ({ ...current, animeDetectionMode }));
    const arg = password ? { value: animeDetectionMode, password } : animeDetectionMode;
    call?.(arg).then((response) => {
      if (!response?.ok) {
        setStatus((current) => ({ ...current, animeDetectionMode: previous }));
      }
      if (applyBackendResponse(response)) {
        setSettingsPasswordPrompt(null);
      }
    });
  };
  const requestAnimeMode = (animeDetectionMode) => {
    const current = status.animeDetectionMode;
    if (animeDetectionMode === current) return;
    const currentRank = ANIME_MODE_RANK[current] ?? 0;
    const nextRank = ANIME_MODE_RANK[animeDetectionMode] ?? 0;
    if (nextRank < currentRank) {
      if (status.commitmentActive) {
        setNotice(humanError("commitment_blocks_loosening_anime"));
        return;
      }
      if (status.enabled) {
        setSettingsPasswordPrompt({
          kind: "anime-mode",
          value: animeDetectionMode,
          title: "Lower anime strictness",
          body: "Protection is on. Enter your password to make illustrated detection less strict.",
          error: ""
        });
        return;
      }
      applyAnimeMode(animeDetectionMode);
      return;
    }
    setConfirmPrompt({
      title: "Make anime detection stricter?",
      body: "Strict mode can turn very high-confidence illustrated explicit hits into a full lockout.",
      warning: status.commitmentActive ? "Because commitment is active, you will not be able to lower it again until the commitment ends." : "",
      confirmLabel: "Make stricter",
      onConfirm: () => {
        setConfirmPrompt(null);
        applyAnimeMode(animeDetectionMode);
      }
    });
  };
  const submitSettingsPassword = (password, localError = "") => {
    if (!settingsPasswordPrompt) return;
    if (localError) {
      setSettingsPasswordPrompt((current) => ({ ...current, error: localError }));
      return;
    }
    const prompt = settingsPasswordPrompt;
    if (prompt.kind === "sensitivity") {
      applySensitivity(prompt.value, password);
    } else if (prompt.kind === "anime-enabled") {
      applyAnimeEnabled(prompt.value, password);
    } else if (prompt.kind === "anime-mode") {
      applyAnimeMode(prompt.value, password);
    }
  };
  const testLockout = () => {
    window.brake?.testLockout?.().then((response) => {
      if (applyBackendResponse(response)) {
        setNotice("Test lockout started.");
      }
    });
  };
  return (
    <main className="app-shell">
      <WindowChrome />
      <header className="titlebar">
        <div className="brand">
          <BrakeMark tone={protectedTone} />
          <div>
            <div className="brand-name">Brake</div>
            <div className="brand-subtitle">Quietly running. Local only.</div>
          </div>
        </div>
      </header>

      <nav className="tabs" aria-label="Main sections">
        <button className={tab === "overview" ? "active" : ""} onClick={() => setTab("overview")}>
          <Gauge size={16} /> Overview
        </button>
        <button className={tab === "detection" ? "active" : ""} onClick={() => setTab("detection")}>
          <ScanEye size={16} /> Detection
        </button>
        <button className={tab === "anime" ? "active" : ""} onClick={() => setTab("anime")}>
          <Activity size={16} /> Anime
        </button>
      </nav>

      <section className="content">
        {tab === "overview" ? (
          <>
            <div className="page-head">
              <h1>Overview</h1>
              <p>Brake runs quietly on your computer and steps in only when it needs to.</p>
              {notice ? <p className="notice">{notice}</p> : null}
            </div>
            <StatusPanel status={status} now={now} />
            <div className="overview-single">
              <Card icon={Clock} title="Session controls" subtitle="Set the friction Brake uses when protection is running.">
                <SettingRow
                  title="Commitment"
                  description={
                    status.commitmentActive
                      ? `Protection is locked. ${formatCommitmentLeft(status.committedUntil, now)}.`
                      : "Lock protection in so your password cannot turn it off early."
                  }
                  aside={
                    <button className={`pill-action ${status.commitmentActive ? "active" : ""}`} onClick={toggleCommitment}>
                      {status.commitmentActive ? formatCommitmentLeft(status.committedUntil, now) || "Locked in" : "No commitment set"}
                    </button>
                  }
                />
                <SettingRow
                  title="Lockout length"
                  description="How long Brake keeps the screen locked after explicit content is detected."
                  aside={
                    <div className="stepper-control">
                      <button aria-label="Decrease lockout length" onClick={() => changeDuration(-1)}>
                        <Minus size={14} />
                      </button>
                      <label>
                        <input
                          aria-label="Lockout length in minutes"
                          inputMode="numeric"
                          min="1"
                          max="60"
                          type="number"
                          value={status.lockoutDurationMinutes}
                          onChange={(event) => changeDurationInput(event.target.value)}
                          onBlur={normalizeDurationInput}
                        />
                        <span>min</span>
                      </label>
                      <button aria-label="Increase lockout length" onClick={() => changeDuration(1)}>
                        <Plus size={14} />
                      </button>
                    </div>
                  }
                />
              </Card>
            </div>
          </>
        ) : tab === "detection" ? (
          <>
            <div className="page-head">
              <h1>Detection</h1>
              <p>Tune how sensitive Brake is and test the lockout without changing the engine.</p>
              {notice ? <p className="notice">{notice}</p> : null}
            </div>
            <Card icon={Activity} title="Sensitivity" subtitle="How readily Brake treats screen content as explicit.">
              <SensitivityOption
                title="Light"
                active={status.detectionSensitivity === "light"}
                description="Only clear explicit content triggers a lockout. Lowest false-positive rate."
                disabled={status.commitmentActive && SENSITIVITY_RANK.light < SENSITIVITY_RANK[status.detectionSensitivity]}
                note={status.commitmentActive && SENSITIVITY_RANK.light < SENSITIVITY_RANK[status.detectionSensitivity] ? "Locked by commitment" : ""}
                onClick={() => requestSensitivity("light")}
              />
              <SensitivityOption
                title="Balanced"
                active={status.detectionSensitivity === "balanced"}
                description="Best for most people. Gives incidental nudity a short warning pause first."
                disabled={status.commitmentActive && SENSITIVITY_RANK.balanced < SENSITIVITY_RANK[status.detectionSensitivity]}
                note={status.commitmentActive && SENSITIVITY_RANK.balanced < SENSITIVITY_RANK[status.detectionSensitivity] ? "Locked by commitment" : ""}
                onClick={() => requestSensitivity("balanced")}
              />
              <SensitivityOption
                title="Strict"
                active={status.detectionSensitivity === "strict"}
                description="Requires two matching scans, then uses warning pauses that grow if it keeps happening."
                onClick={() => requestSensitivity("strict")}
              />
              <div className="card-actions">
                <Button variant="secondary" icon={ShieldCheck} onClick={testLockout}>
                  Test lockout
                </Button>
              </div>
            </Card>
          </>
        ) : (
          <>
            <div className="page-head">
              <h1>Anime</h1>
              <p>Optional local detection for illustrated explicit content.</p>
              {notice ? <p className="notice">{notice}</p> : null}
            </div>
            <Card icon={Activity} title="Illustrated detector" subtitle="A separate model for anime, hentai, drawings, and renders.">
              <SettingRow
                title="Model"
                description="Downloads once to this computer. It runs locally and does not upload screenshots."
                aside={<Badge state={status.animeModelStatus === "ready" ? "protected" : ""}>{animeStatusCopy(status.animeModelStatus)}</Badge>}
              />
              <SettingRow
                title="Anime detection"
                description="When enabled, illustrated hits are treated as context detections. They can pause or warn, but they do not trigger shutdown by themselves."
                aside={
                  <button
                    className={`pill-action ${status.animeDetectionEnabled ? "active" : ""}`}
                    disabled={status.animeModelStatus !== "ready" || (status.commitmentActive && status.animeDetectionEnabled)}
                    onClick={() => requestAnimeEnabled(!status.animeDetectionEnabled)}
                  >
                    {status.animeDetectionEnabled ? "On" : "Off"}
                  </button>
                }
              />
              <SensitivityOption
                title="Not strict"
                active={status.animeDetectionMode === "standard"}
                description="Any illustrated NSFW hit gets a short pause only. No shutdown path from anime detection."
                disabled={status.commitmentActive && status.animeDetectionMode === "strict"}
                note={status.commitmentActive && status.animeDetectionMode === "strict" ? "Locked by commitment" : ""}
                onClick={() => requestAnimeMode("standard")}
              />
              <SensitivityOption
                title="Strict"
                active={status.animeDetectionMode === "strict"}
                description="Very high-confidence illustrated explicit hits can trigger the full lockout. Lower-confidence hits still get a short pause."
                onClick={() => requestAnimeMode("strict")}
              />
              <div className="card-actions">
                <Button
                  variant="primary"
                  icon={Download}
                  disabled={animeInstalling || status.animeModelStatus === "ready"}
                  onClick={installAnimeDetector}
                >
                  {animeInstalling ? "Installing..." : status.animeModelStatus === "ready" ? "Installed" : "Download detector"}
                </Button>
              </div>
            </Card>
          </>
        )}
      </section>

      <footer className="actionbar">
        <Button variant="primary" icon={status.enabled ? ShieldOff : ShieldCheck} onClick={toggleProtection}>
          {status.enabled ? "Turn off protection" : "Turn on protection"}
        </Button>
        <Button variant="warning" onClick={toggleCommitment}>
          {status.commitmentActive ? "Commitment active" : "Lock in commitment"}
        </Button>
        <div className="spacer" />
        <button className="link-button" onClick={() => setShowInfo(true)}>How this tab works</button>
      </footer>

      {showInfo ? (
        <GuideModal tab={tab} status={status} onClose={() => setShowInfo(false)} />
      ) : null}

      {passwordPrompt ? (
        <PasswordModal
          mode={passwordPrompt.mode}
          durationMinutes={Number(status.lockoutDurationMinutes) || 1}
          commitmentActive={status.commitmentActive}
          error={passwordPrompt.error}
          onCancel={() => setPasswordPrompt(null)}
          onSubmit={submitProtectionPassword}
          onRecoverPassword={() => setResetPasswordPrompt({ error: "" })}
        />
      ) : null}

      {resetPasswordPrompt ? (
        <ResetPasswordModal
          error={resetPasswordPrompt.error}
          onCancel={() => setResetPasswordPrompt(null)}
          onSubmit={submitPasswordReset}
        />
      ) : null}

      {commitmentPrompt ? (
        <CommitmentModal
          error={commitmentPrompt.error}
          onCancel={() => setCommitmentPrompt(null)}
          onSubmit={submitCommitment}
        />
      ) : null}

      {confirmPrompt ? (
        <ConfirmModal
          title={confirmPrompt.title}
          body={confirmPrompt.body}
          warning={confirmPrompt.warning}
          confirmLabel={confirmPrompt.confirmLabel}
          onCancel={() => setConfirmPrompt(null)}
          onConfirm={confirmPrompt.onConfirm}
        />
      ) : null}

      {settingsPasswordPrompt ? (
        <SettingsPasswordModal
          title={settingsPasswordPrompt.title}
          body={settingsPasswordPrompt.body}
          error={settingsPasswordPrompt.error}
          onCancel={() => setSettingsPasswordPrompt(null)}
          onSubmit={submitSettingsPassword}
        />
      ) : null}

      {recoveryPrompt ? (
        <RecoveryModal
          token={recoveryPrompt.token}
          regenerated={recoveryPrompt.regenerated}
          onClose={() => setRecoveryPrompt(null)}
        />
      ) : null}
    </main>
  );
}

function humanError(error) {
  const messages = {
    password_too_short: "Password must be at least 6 characters.",
    wrong_password: "That password is not correct.",
    wrong_recovery_code: "That recovery code is not correct.",
    recovery_unavailable: "Recovery code verification is unavailable on this machine.",
    commitment_active: "Commitment is active. Protection cannot be turned off yet.",
    commitment_blocks_loosening: "Commitment is active. You can only make the lockout longer.",
    commitment_blocks_loosening_sensitivity: "Commitment is active. You can only make detection stricter.",
    commitment_blocks_unlocking_anime: "Commitment is active. Anime detection cannot be turned off yet.",
    commitment_blocks_loosening_anime: "Commitment is active. You can only make anime detection stricter.",
    commitment_must_be_future: "Commitment must end in the future.",
    invalid_commitment_until: "That commitment time is not valid.",
    invalid_anime_mode: "That anime detection setting is not valid.",
    not_initialized: "Brake has not been set up yet.",
    password_required: "Enter your password to make this less strict.",
    permission_denied: "Brake could not write settings. Try running through the service or dev mode.",
    anime_model_not_ready: "Download the illustrated detector before turning it on.",
    missing_dependencies: "Python is missing transformers or torch. Install requirements, then try again.",
    model_download_incomplete: "The detector download did not finish cleanly. Try again.",
  };
  return messages[error] || error;
}
