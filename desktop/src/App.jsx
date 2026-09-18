import {
  Activity,
  Clock3,
  Download,
  Github,
  Info,
  Gauge,
  KeyRound,
  Mail,
  Maximize,
  MessageCircle,
  Minus,
  Plus,
  Power,
  ScanEye,
  ScrollText,
  ShieldCheck,
  ShieldOff,
  Trash2,
  X
} from "lucide-react";
import React from "react";
import { useEffect, useRef, useState } from "react";

const fallbackStatus = {
  initialized: true,
  enabled: false,
  failSecure: false,
  stateError: "",
  commitmentActive: false,
  committedUntil: null,
  lockoutDurationMinutes: 15,
  detectionSensitivity: "balanced",
  animeDetectionEnabled: false,
  animeModelStatus: "not_installed",
  recoveryUnlockAfter: null,
  recoveryUnlockPending: false,
  recoveryUnlockDelayMinutes: 15,
  lockoutRecoveryEnabled: true,
  lockoutRecoveryDelayMinutes: 0,
  lockoutRecoveryUsesPer24h: 1,
  shutdownAfterLockout: false
};
const MIN_PASSWORD_LENGTH = 6;
const INCREASE_CONFIRM_GRACE_MS = 45000;
const RECOVERY_COOLDOWN_MIN = 1;
const RECOVERY_COOLDOWN_MAX = 60;
const LOCKOUT_RECOVERY_COOLDOWN_MIN = 0;
const LOCKOUT_RECOVERY_USES_DEFAULT = 1;
const LOCKOUT_RECOVERY_USES_ALLOWED = [1, 2, 3, 4, 0];

function clampRecoveryMinutes(value) {
  return Math.max(
    RECOVERY_COOLDOWN_MIN,
    Math.min(RECOVERY_COOLDOWN_MAX, Number(value) || 15)
  );
}

function clampLockoutRecoveryMinutes(value) {
  const minutes = Number(value);
  return Math.max(
    LOCKOUT_RECOVERY_COOLDOWN_MIN,
    Math.min(RECOVERY_COOLDOWN_MAX, Number.isFinite(minutes) ? minutes : 0)
  );
}

function normalizeRecoveryUses(value) {
  const uses = Number(value);
  return LOCKOUT_RECOVERY_USES_ALLOWED.includes(uses) ? uses : LOCKOUT_RECOVERY_USES_DEFAULT;
}

function recoveryUsesRank(value) {
  const uses = normalizeRecoveryUses(value);
  return uses === 0 ? Number.POSITIVE_INFINITY : uses;
}

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
  if (totalMinutes < 1) return "ending soon";
  if (totalMinutes < 60) {
    return `${totalMinutes} ${totalMinutes === 1 ? "minute" : "minutes"} left`;
  }

  const totalHours = Math.floor(totalMinutes / 60);
  if (totalHours < 24) {
    return `${totalHours} ${totalHours === 1 ? "hour" : "hours"} left`;
  }

  const totalDays = Math.floor(totalHours / 24);
  return `${totalDays} ${totalDays === 1 ? "day" : "days"} left`;
}

function formatRecoveryUnlockLeft(unlockAfter, now) {
  if (!unlockAfter) return "";
  const end = new Date(unlockAfter).getTime();
  const remainingMs = end - now;
  if (!Number.isFinite(end) || remainingMs <= 0) return "ending soon";
  const totalMinutes = Math.floor(remainingMs / 60000);
  if (totalMinutes < 1) return "ending soon";
  return `${totalMinutes} ${totalMinutes === 1 ? "minute" : "minutes"} left`;
}

function animeStatusCopy(status) {
  const labels = {
    ready: "Installed",
    not_installed: "Not installed",
    missing_dependencies: "Not installed",
    installing: "Installing"
  };
  return labels[status] || "Not installed";
}

function detectorCopy(detector) {
  if (detector === "anime_nsfw") return "Illustrated";
  if (detector === "nudity") return "Regular";
  return detector || "Detector";
}

function eventSeverityCopy(event) {
  if (event.severity === "hard") return "Hard";
  if (event.triggered) return "Context";
  return "Suspicion";
}

function eventTimeCopy(ts) {
  const date = new Date(ts);
  if (!Number.isFinite(date.getTime())) return "Unknown";
  return date.toLocaleString([], {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit"
  });
}

function confidenceCopy(confidence) {
  const value = Number(confidence);
  if (!Number.isFinite(value) || value <= 0) return "";
  return `${Math.round(value * 100)}%`;
}

function DetectionLogs({ events, loading, onRefresh, onClear }) {
  return (
    <Card
      icon={ScrollText}
      title="Detection history"
      subtitle="Review when detector checks were triggered."
      actions={
        <div className="log-actions">
          <button className="pill-action" onClick={onRefresh}>Refresh</button>
          <button className="pill-action danger" onClick={onClear} disabled={loading || !events.length}>
            <Trash2 size={14} strokeWidth={2.2} />
            <span>Clear</span>
          </button>
        </div>
      }
    >
      {events.length ? (
        <div className="log-list">
          {events.map((event, index) => (
            <div className="log-row" key={`${event.ts}-${event.detector}-${event.label}-${index}`}>
              <div className="log-time">{eventTimeCopy(event.ts)}</div>
              <div className="log-main">
                <div className="log-title">
                  <span>{detectorCopy(event.detector)}</span>
                  <Badge state={event.severity === "hard" ? "committed" : event.triggered ? "protected" : ""}>
                    {eventSeverityCopy(event)}
                  </Badge>
                </div>
                <div className="log-label">{event.label}</div>
                <div className="log-meta">
                  {confidenceCopy(event.confidence) ? <span>{confidenceCopy(event.confidence)}</span> : null}
                  {event.region ? <span>{event.region}</span> : null}
                  {event.action ? <span>{event.action}</span> : null}
                  {event.scanReason ? <span>{event.scanReason}</span> : null}
                </div>
              </div>
            </div>
          ))}
        </div>
      ) : (
        <div className="empty-log">
          <h3>No detections recorded</h3>
          <p>Brake will list regular and illustrated detector hits here when they happen.</p>
        </div>
      )}
    </Card>
  );
}

function StatusPanel({ status, now, onToggleProtection, onCancelRecoveryUnlock }) {
  const committed = status.commitmentActive;
  const failSecure = status.failSecure;
  const enabled = status.enabled || failSecure;
  const recoveryLeft = status.recoveryUnlockPending ? formatRecoveryUnlockLeft(status.recoveryUnlockAfter, now) : "";
  const state = failSecure ? "protected" : committed ? "committed" : enabled ? "protected" : "off";
  const commitmentLeft = committed && !recoveryLeft ? formatCommitmentLeft(status.committedUntil, now) : "";
  const description = failSecure
    ? "Brake could not verify its settings. Use your recovery code to repair protection."
    : recoveryLeft
    ? "Recovery accepted. Brake will turn protection off after the cooldown."
    : "";

  return (
    <section className={`status-panel ${state}`}>
      <button
        className="status-orb"
        type="button"
        aria-label={recoveryLeft ? "Cancel emergency unlock cooldown" : failSecure ? "Repair protection" : enabled ? "Turn off protection" : "Turn on protection"}
        title={recoveryLeft ? "Cancel emergency unlock cooldown" : failSecure ? "Repair protection" : enabled ? "Turn off protection" : "Turn on protection"}
        onClick={recoveryLeft ? onCancelRecoveryUnlock : onToggleProtection}
      >
        <svg className="status-ring" viewBox="0 0 132 132" aria-hidden="true">
          <circle className="status-ring-track" cx="66" cy="66" r="62.5" />
          <circle className="status-ring-progress" cx="66" cy="66" r="62.5" />
        </svg>
        {enabled || committed ? (
          <ShieldCheck size={44} strokeWidth={1.8} />
        ) : (
          <Power size={44} strokeWidth={1.8} />
        )}
      </button>
      <div className="status-copy">
        <h2>{failSecure ? "Protection needs repair" : recoveryLeft ? "Emergency unlock pending" : committed ? "Commitment active" : enabled ? "Protection is active" : "Protection is off"}</h2>
        {description ? <p>{description}</p> : null}
        {commitmentLeft ? <p className="status-meta">{commitmentLeft}</p> : null}
        {recoveryLeft ? <p className="status-meta">{recoveryLeft}</p> : null}
      </div>
    </section>
  );
}

function Card({ icon: Icon, title, subtitle, actions, children }) {
  return (
    <section className="card">
      <header className="card-head">
        {Icon ? (
          <span className="lead-icon">
            <Icon size={17} />
          </span>
        ) : null}
        <div className="card-head-copy">
          <h3>{title}</h3>
          {subtitle ? <p>{subtitle}</p> : null}
        </div>
        {actions ? <div className="card-head-actions">{actions}</div> : null}
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

function MinuteStepper({ value, onChange, disabled = false, ariaLabel, allowZero = false }) {
  const minimum = allowZero ? LOCKOUT_RECOVERY_COOLDOWN_MIN : RECOVERY_COOLDOWN_MIN;
  const minutes = allowZero ? clampLockoutRecoveryMinutes(value) : clampRecoveryMinutes(value);
  return (
    <div className="stepper-control">
      <button
        type="button"
        aria-label={`Decrease ${ariaLabel}`}
        disabled={disabled || minutes <= minimum}
        onClick={() => onChange(minutes - 1)}
      >
        <Minus size={14} />
      </button>
      <label>
        <input aria-label={ariaLabel} readOnly value={minutes} />
        <span>min</span>
      </label>
      <button
        type="button"
        aria-label={`Increase ${ariaLabel}`}
        disabled={disabled || minutes >= RECOVERY_COOLDOWN_MAX}
        onClick={() => onChange(minutes + 1)}
      >
        <Plus size={14} />
      </button>
    </div>
  );
}

function RecoveryUsesSelect({ value, onChange, disabled = false }) {
  return (
    <select
      className="setting-select"
      aria-label="Lockout recovery uses allowed every 24 hours"
      value={normalizeRecoveryUses(value)}
      disabled={disabled}
      onChange={(event) => onChange(Number(event.target.value))}
    >
      <option value={1}>1</option>
      <option value={2}>2</option>
      <option value={3}>3</option>
      <option value={4}>4</option>
      <option value={0}>∞</option>
    </select>
  );
}

function Modal({ title, subtitle = "Local accountability for explicit content.", children, onClose }) {
  return (
    <div className="modal-scrim" role="presentation" onMouseDown={onClose}>
      <section className="modal" role="dialog" aria-modal="true" aria-label={title} onMouseDown={(event) => event.stopPropagation()}>
        <header className="modal-head">
          <span className="lead-icon">
            <Info size={17} />
          </span>
          <div>
            <h2>{title}</h2>
            {subtitle ? <p>{subtitle}</p> : null}
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
            ? "Set the password used to turn protection off. Without a commitment, this password can turn protection off anytime."
            : commitmentActive
              ? "Commitment is active. Your password cannot turn protection off right now. A recovery code starts the configured emergency cooldown instead."
              : "Enter your password to turn protection off. A recovery code can also start the configured emergency cooldown."}
        </p>
        {enabling ? (
          <p>
            Brake watches the screen and reacts; it does not block websites or apps. Clear explicit content triggers a <strong>{durationMinutes}-minute</strong> lockout. Save your work often. If illustrated content is a risk, turn that detector on in Illustrated.
          </p>
        ) : null}
        <label className="field">
          <span>{enabling ? "New password" : "Password"}</span>
          <input
            autoFocus
            type="text"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
          />
        </label>
        {enabling ? (
          <label className="field">
            <span>Confirm password</span>
            <input
              type="text"
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
          Use your recovery code to set a new protection password. Protection and any active commitment stay in place.
        </p>
        <label className="field">
          <span>Recovery code</span>
          <input
            autoFocus
            type="text"
            value={recoveryCode}
            onChange={(event) => setRecoveryCode(event.target.value)}
          />
        </label>
        <label className="field">
          <span>New password</span>
          <input
            type="text"
            value={newPassword}
            onChange={(event) => setNewPassword(event.target.value)}
          />
        </label>
        <label className="field">
          <span>Confirm password</span>
          <input
            type="text"
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
            type="text"
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

function CommitmentModal({ mode = "create", committedUntil = null, error, onCancel, onSubmit }) {
  const extending = mode === "extend";
  const [amount, setAmount] = useState(extending ? 1 : 3);
  const [unit, setUnit] = useState(extending ? "hours" : "days");
  const [password, setPassword] = useState("");

  const submit = (event) => {
    event.preventDefault();
    if (!password) {
      onSubmit(null, "Enter your password.");
      return;
    }
    const safeAmount = Math.max(1, Math.min(365, Number(amount) || 1));
    const millis = safeAmount * (unit === "hours" ? 60 * 60 * 1000 : 24 * 60 * 60 * 1000);
    const currentUntilMs = Date.parse(committedUntil || "");
    const baseMs = extending && !Number.isNaN(currentUntilMs) && currentUntilMs > Date.now() ? currentUntilMs : Date.now();
    const until = new Date(baseMs + millis).toISOString().replace("Z", "+00:00");
    onSubmit({ until, password, mode }, "");
  };

  return (
    <Modal title={extending ? "Extend commitment" : "Lock in a commitment"} onClose={onCancel}>
      <form className="password-form" onSubmit={submit}>
        <p>
          {extending
            ? "Add time to the active commitment. Brake will only accept a later end time, and your password still cannot shorten or remove it."
            : "Choose how long Brake should stay locked in. During a commitment, your password cannot turn protection off. You can make settings stricter, but not easier to bypass."}
        </p>
        <div className="inline-fields">
          <label className="field compact">
            <span>{extending ? "Add" : "Lock in for"}</span>
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
            type="text"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
          />
        </label>
        {error ? <p className="form-error">{error}</p> : null}
        <div className="modal-actions">
          <button className="btn secondary" type="button" onClick={onCancel}>Cancel</button>
          <button className="btn primary" type="submit">{extending ? "Extend" : "Lock it in"}</button>
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
          This code can reset your password immediately. It can also start the configured emergency cooldown before Brake turns off. You will not see this exact code again.
        </p>
        <p>
          Do not store it somewhere easy to reach on this computer. Write it on paper, take a photo on your phone, or give it to someone you trust. For the strongest commitment, you can choose not to copy it, but a forgotten password may then require a full reset.
        </p>
        <label className="field">
          <span>Recovery code</span>
          <input readOnly value={token} onFocus={(event) => event.target.select()} />
        </label>
        <p className="form-warning">Anyone with this code can reset your password or schedule emergency disable on this device. Treat it like a password, but keep it away from easy access.</p>
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

function GuideList({ items }) {
  return (
    <ul className="guide-list">
      {items.map((item) => <li key={item}>{item}</li>)}
    </ul>
  );
}

function GuideModal({ tab, status, onClose }) {
  const duration = Number(status.lockoutDurationMinutes) || 1;
  const title = tab === "advanced"
    ? "How advanced settings work"
    : tab === "illustrated"
      ? "How illustrated detection works"
      : tab === "logs"
        ? "How detection history works"
        : "How Brake works";

  return (
    <Modal title={title} subtitle="" onClose={onClose}>
      {tab === "overview" ? (
        <div className="guide">
          <GuideSection title="Screen checks">
            <GuideList items={[
              "Brake checks your screen locally. Images are not uploaded or saved.",
              "It reacts to what appears on screen. It does not block websites or apps."
            ]} />
          </GuideSection>
          <GuideSection title="Lockouts">
            <GuideList items={[
              `A detection starts a ${duration}-minute lockout.`,
              "Repeated lockouts within 24 hours may make the next one longer.",
              "If shutdown is enabled, Windows shuts down when the timer ends."
            ]} />
          </GuideSection>
          <GuideSection title="Commitment">
            <GuideList items={[
              "Without a commitment, your password can turn protection off.",
              "During a commitment, settings can become stricter but not easier to bypass.",
              "Your recovery code can reset the password or start the configured cooldown."
            ]} />
          </GuideSection>
        </div>
      ) : tab === "illustrated" ? (
        <div className="guide">
          <GuideSection title="Image detection">
            <GuideList items={[
              "A separate local model scans drawings, animations, and rendered images.",
              "When enabled, high-confidence matches can trigger a full lockout.",
              "When disabled, Brake ignores these image types."
            ]} />
          </GuideSection>
          <GuideSection title="Local model">
            <GuideList items={[
              "The detector package downloads once to this computer.",
              "Scanning stays on-device. Screenshots are not uploaded or saved."
            ]} />
          </GuideSection>
        </div>
      ) : tab === "logs" ? (
        <div className="guide">
          <GuideSection title="Detection history">
            <GuideList items={[
              "Recent detector events appear here.",
              "Each entry shows the detector, severity, confidence, and action taken."
            ]} />
          </GuideSection>
          <GuideSection title="Controls">
            <GuideList items={[
              "Refresh reloads the latest local events.",
              "Clear removes the detection history from this device."
            ]} />
          </GuideSection>
        </div>
      ) : (
        <div className="guide">
          <GuideSection title="Recovery">
            <GuideList items={[
              "The recovery code can reset a forgotten password or start the emergency cooldown.",
              "Lockout recovery controls whether the code can shorten an active lockout and how often."
            ]} />
          </GuideSection>
          <GuideSection title="Lockout behavior">
            <GuideList items={[
              "Shutdown controls whether Windows turns off when a full lockout ends.",
              "During commitment, settings cannot be changed to make protection easier to bypass."
            ]} />
          </GuideSection>
          <GuideSection title="Test lockout">
            <GuideList items={[
              "Use Test lockout to preview the full-screen lockout experience."
            ]} />
          </GuideSection>
        </div>
      )}
    </Modal>
  );
}

function FeedbackModal({ onClose }) {
  const openIssue = () => {
    window.brake?.openFeedbackIssue?.();
  };
  const openEmail = () => {
    window.brake?.openFeedbackEmail?.();
  };

  return (
    <Modal title="Send feedback" onClose={onClose}>
      <div className="feedback-panel">
        <p>If Brake locks you out incorrectly, use your configured recovery option if needed, then send feedback describing what was on screen. Do not include sensitive screenshots, passwords, or recovery codes.</p>
        <p>Brake will open your browser or email app. Nothing is sent from Brake automatically.</p>
        <div className="feedback-actions">
          <Button variant="safe" icon={Github} onClick={openIssue}>
            Report an issue
          </Button>
          <Button variant="secondary" icon={Mail} onClick={openEmail}>
            Email feedback
          </Button>
        </div>
      </div>
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
  const [showFeedback, setShowFeedback] = useState(false);
  const [notice, setNotice] = useState("");
  const [passwordPrompt, setPasswordPrompt] = useState(null);
  const [resetPasswordPrompt, setResetPasswordPrompt] = useState(null);
  const [commitmentPrompt, setCommitmentPrompt] = useState(null);
  const [recoveryPrompt, setRecoveryPrompt] = useState(null);
  const [confirmPrompt, setConfirmPrompt] = useState(null);
  const [settingsPasswordPrompt, setSettingsPasswordPrompt] = useState(null);
  const [animeInstalling, setAnimeInstalling] = useState(false);
  const [detectionEvents, setDetectionEvents] = useState([]);
  const [logsLoading, setLogsLoading] = useState(false);
  const [now, setNow] = useState(Date.now());
  const durationSaveTimer = useRef(null);
  const recoverySaveTimer = useRef(null);
  const pendingDuration = useRef(false);
  const pendingRecovery = useRef(false);
  const durationPreserveUntil = useRef(0);
  const recoveryPreserveUntil = useRef(0);
  const durationDraft = useRef(fallbackStatus.lockoutDurationMinutes);
  const recoveryDraft = useRef(null);
  const recoveryBaseline = useRef(null);
  const lockoutIncreaseConfirmUntil = useRef(0);
  const commitmentIncreaseConfirmUntil = useRef(0);
  const recoveryIncreaseConfirmUntil = useRef(0);

  const refreshDetectionLogs = () => {
    setLogsLoading(true);
    window.brake?.detectionLogs?.().then((response) => {
      setLogsLoading(false);
      if (response?.ok) {
        setDetectionEvents(Array.isArray(response.data?.events) ? response.data.events : []);
      } else {
        setNotice(humanError(response?.error || "Detection logs are unavailable."));
      }
    });
  };

  const clearDetectionLogs = () => {
    setLogsLoading(true);
    window.brake?.clearDetectionLogs?.().then((response) => {
      setLogsLoading(false);
      if (response?.ok) {
        setDetectionEvents([]);
      } else {
        setNotice(humanError(response?.error || "Detection logs could not be cleared."));
      }
    });
  };

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
    window.brake?.detectionLogs?.().then((response) => {
      if (!alive || !response?.ok) return;
      setDetectionEvents(Array.isArray(response.data?.events) ? response.data.events : []);
    });
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
      window.clearTimeout(recoverySaveTimer.current);
    };
  }, []);

  useEffect(() => {
    if (tab !== "logs") return undefined;
    refreshDetectionLogs();
    const timer = window.setInterval(refreshDetectionLogs, 5000);
    return () => window.clearInterval(timer);
  }, [tab]);

  const protectedTone = status.failSecure ? "amber" : status.commitmentActive ? "amber" : status.enabled ? "teal" : "gold";
  const recoverySnapshot = (source) => ({
    recoveryUnlockDelayMinutes: clampRecoveryMinutes(source?.recoveryUnlockDelayMinutes),
    lockoutRecoveryEnabled: Boolean(source?.lockoutRecoveryEnabled ?? fallbackStatus.lockoutRecoveryEnabled),
    lockoutRecoveryDelayMinutes: clampLockoutRecoveryMinutes(source?.lockoutRecoveryDelayMinutes),
    lockoutRecoveryUsesPer24h: normalizeRecoveryUses(source?.lockoutRecoveryUsesPer24h)
  });
  const mergeBackendStatus = (data) => {
    setStatus((current) => {
      const now = Date.now();
      const keepDuration = pendingDuration.current || now < durationPreserveUntil.current;
      const keepRecovery = pendingRecovery.current || now < recoveryPreserveUntil.current;
      const nextDuration = keepDuration ? current.lockoutDurationMinutes : data.lockoutDurationMinutes;
      const nextRecovery = keepRecovery ? recoverySnapshot(current) : recoverySnapshot(data);
      durationDraft.current = Number(nextDuration) || fallbackStatus.lockoutDurationMinutes;
      if (!keepRecovery) {
        recoveryDraft.current = nextRecovery;
        recoveryBaseline.current = nextRecovery;
      }
      return {
        ...fallbackStatus,
        ...data,
        lockoutDurationMinutes: nextDuration,
        ...nextRecovery,
        ...(animeInstalling ? { animeModelStatus: "installing" } : {})
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
  const toggleProtection = () => {
    if (status.failSecure) {
      setResetPasswordPrompt({ error: "Brake could not verify settings. Use your recovery code to repair protection." });
      return;
    }
    setPasswordPrompt({ mode: status.enabled ? "disable" : "enable", error: "" });
  };
  const requestCancelRecoveryUnlock = () => {
    if (!status.recoveryUnlockPending) return;
    setConfirmPrompt({
      title: "Cancel emergency unlock?",
      body: "Brake will keep protection and your commitment active. This only cancels the pending overview cooldown.",
      warning: "",
      confirmLabel: "Cancel cooldown",
      onConfirm: () => {
        setConfirmPrompt(null);
        window.brake?.cancelRecoveryUnlock?.().then((response) => {
          if (applyBackendResponse(response)) {
            setNotice("Emergency unlock canceled.");
          }
        });
      }
    });
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
        if (mode === "disable" && response.data?.recoveryUnlockPending) {
          const delay = Number(response.data?.recoveryUnlockDelayMinutes || status.recoveryUnlockDelayMinutes) || 15;
          setNotice(`Recovery code accepted. Protection will turn off after the ${delay}-minute cooldown.`);
        }
        return;
      }
      setPasswordPrompt((current) => ({
        ...current,
        error: humanError(response?.error || "That password was not accepted.")
      }));
    });
  };
  const requestTimedConfirmation = (kind, prompt, action) => {
    const ref = kind === "commitment"
      ? commitmentIncreaseConfirmUntil
      : kind === "recovery"
        ? recoveryIncreaseConfirmUntil
        : lockoutIncreaseConfirmUntil;
    if (Date.now() < ref.current) {
      action();
      return;
    }
    setConfirmPrompt({
      ...prompt,
      onConfirm: () => {
        ref.current = Date.now() + INCREASE_CONFIRM_GRACE_MS;
        setConfirmPrompt(null);
        action();
      }
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
    setCommitmentPrompt({ error: "", mode: status.commitmentActive ? "extend" : "create" });
  };
  const submitCommitment = (payload, localError = "") => {
    if (localError) {
      setCommitmentPrompt((current) => ({ ...current, error: localError }));
      return;
    }
    const currentUntilMs = Date.parse(status.committedUntil || "");
    const nextUntilMs = Date.parse(payload?.until || "");
    const extendsActiveCommitment = status.commitmentActive && !Number.isNaN(currentUntilMs) && !Number.isNaN(nextUntilMs) && nextUntilMs > currentUntilMs;
    const cancelsPendingRecovery = status.recoveryUnlockPending;
    const submit = () => window.brake?.setCommitment?.(payload).then((response) => {
      if (response?.ok) {
        applyBackendResponse(response);
        setCommitmentPrompt(null);
        if (cancelsPendingRecovery) {
          setNotice("Pending emergency unlock canceled.");
        }
        return;
      }
      setCommitmentPrompt((current) => ({
        ...current,
        error: humanError(response?.error || "Commitment was not accepted.")
      }));
    });
    if (extendsActiveCommitment) {
      requestTimedConfirmation("commitment", {
        title: "Extend commitment?",
        body: cancelsPendingRecovery
          ? "This adds time to the active commitment and cancels the pending emergency unlock. Protection will stay on until the new end time."
          : "This adds time to the active commitment. Your password still cannot shorten it or turn protection off until the new end time.",
        warning: "Use this only when you are sure you want stronger commitment.",
        confirmLabel: "Extend"
      }, submit);
      return;
    }
    submit();
  };
  const applyDuration = (next) => {
    durationDraft.current = next;
    setStatus((current) => ({ ...current, lockoutDurationMinutes: next }));
    saveDurationSoon(next);
  };
  const confirmDurationIncrease = (next, action) => {
    if (next <= (Number(durationDraft.current) || 1)) {
      action();
      return;
    }
    requestTimedConfirmation("lockout", {
      title: "Increase lockout length?",
      body: "This makes future full lockouts last longer before Brake releases the screen and continues its shutdown flow.",
      warning: status.commitmentActive ? "Because commitment is active, you may not be able to lower this again until the commitment ends." : "You can lower it later if protection allows it.",
      confirmLabel: "Increase"
    }, action);
  };
  const changeDuration = (delta) => {
    const next = Math.max(1, Math.min(60, (Number(durationDraft.current) || 1) + delta));
    confirmDurationIncrease(next, () => applyDuration(next));
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
    confirmDurationIncrease(next, () => applyDuration(next));
  };
  const normalizeDurationInput = () => {
    const next = Math.max(1, Math.min(60, Number(status.lockoutDurationMinutes) || 1));
    confirmDurationIncrease(next, () => applyDuration(next));
  };
  const installAnimeDetector = () => {
    setAnimeInstalling(true);
    setStatus((current) => ({ ...current, animeModelStatus: "installing" }));
    setNotice("Downloading illustrated detector. This can take a few minutes on first setup.");
    window.brake?.downloadAnime?.().then((response) => {
      setAnimeInstalling(false);
      if (!response?.ok) {
        setStatus((current) => ({ ...current, animeModelStatus: "not_installed" }));
        setNotice(humanError(response?.error || "Illustrated detector download failed."));
        return;
      }
      const modelStatus = response.data?.animeModelStatus || "ready";
      setStatus((current) => ({ ...current, animeModelStatus: modelStatus }));
      setNotice(modelStatus === "ready" ? "Illustrated detector is ready." : animeStatusCopy(modelStatus));
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
          title: "Turn off illustrated detection",
          body: "Protection is on. Enter your password to turn illustrated detection off.",
          error: ""
        });
        return;
      }
      applyAnimeEnabled(false);
      return;
    }
    setConfirmPrompt({
      title: "Turn on illustrated detection?",
      body: "Brake will start checking illustrated explicit content with the local model.",
      warning: status.commitmentActive ? "Because commitment is active, you will not be able to turn this off until the commitment ends." : "",
      confirmLabel: "Turn on",
      onConfirm: () => {
        setConfirmPrompt(null);
        applyAnimeEnabled(true);
      }
    });
  };
  const recoverySettingsPayload = (overrides = {}, base = recoveryDraft.current || recoverySnapshot(status)) => ({
    recoveryUnlockDelayMinutes: clampRecoveryMinutes(
      overrides.recoveryUnlockDelayMinutes ?? base.recoveryUnlockDelayMinutes
    ),
    lockoutRecoveryEnabled: Boolean(overrides.lockoutRecoveryEnabled ?? base.lockoutRecoveryEnabled),
    lockoutRecoveryDelayMinutes: clampLockoutRecoveryMinutes(
      overrides.lockoutRecoveryDelayMinutes ?? base.lockoutRecoveryDelayMinutes
    ),
    lockoutRecoveryUsesPer24h: normalizeRecoveryUses(
      overrides.lockoutRecoveryUsesPer24h ?? base.lockoutRecoveryUsesPer24h
    )
  });
  const recoverySettingsLooser = (next, base = recoveryBaseline.current || recoverySnapshot(status)) => (
    next.recoveryUnlockDelayMinutes < Number(base.recoveryUnlockDelayMinutes)
    || (next.lockoutRecoveryEnabled && !base.lockoutRecoveryEnabled)
    || next.lockoutRecoveryDelayMinutes < Number(base.lockoutRecoveryDelayMinutes)
    || recoveryUsesRank(next.lockoutRecoveryUsesPer24h) > recoveryUsesRank(base.lockoutRecoveryUsesPer24h)
  );
  const recoverySettingsStricter = (next, base = recoveryBaseline.current || recoverySnapshot(status)) => (
    next.recoveryUnlockDelayMinutes > Number(base.recoveryUnlockDelayMinutes)
    || (!next.lockoutRecoveryEnabled && base.lockoutRecoveryEnabled)
    || next.lockoutRecoveryDelayMinutes > Number(base.lockoutRecoveryDelayMinutes)
    || recoveryUsesRank(next.lockoutRecoveryUsesPer24h) < recoveryUsesRank(base.lockoutRecoveryUsesPer24h)
  );
  const applyRecoverySettingsResponse = (response, fallback) => {
    pendingRecovery.current = false;
    recoveryPreserveUntil.current = response?.ok ? Date.now() + 700 : 0;
    if (!response?.ok && fallback) {
      recoveryDraft.current = fallback;
      setStatus((current) => ({ ...current, ...fallback }));
    }
    if (applyBackendResponse(response)) {
      setSettingsPasswordPrompt(null);
    }
  };
  const saveRecoverySettingsSoon = (next, password = "") => {
    pendingRecovery.current = true;
    recoveryPreserveUntil.current = Date.now() + 1200;
    window.clearTimeout(recoverySaveTimer.current);
    recoverySaveTimer.current = window.setTimeout(() => {
      const fallback = recoveryBaseline.current || recoverySnapshot(status);
      window.brake?.setRecoverySettings?.({ ...next, password }).then((response) => {
        applyRecoverySettingsResponse(response, fallback);
      });
    }, 180);
  };
  const applyRecoverySettings = (next, password = "", options = {}) => {
    const normalized = recoverySettingsPayload(next);
    recoveryDraft.current = normalized;
    setStatus((current) => ({ ...current, ...normalized }));
    if (options.debounce) {
      saveRecoverySettingsSoon(normalized, password);
      return;
    }
    window.clearTimeout(recoverySaveTimer.current);
    pendingRecovery.current = true;
    recoveryPreserveUntil.current = Date.now() + 1200;
    const fallback = recoveryBaseline.current || recoverySnapshot(status);
    window.brake?.setRecoverySettings?.({ ...normalized, password }).then((response) => {
      applyRecoverySettingsResponse(response, fallback);
    });
  };
  const requestRecoverySettings = (next, options = {}) => {
    const normalized = recoverySettingsPayload(next);
    const unchanged =
      normalized.recoveryUnlockDelayMinutes === Number(recoveryDraft.current?.recoveryUnlockDelayMinutes ?? status.recoveryUnlockDelayMinutes)
      && normalized.lockoutRecoveryEnabled === Boolean(recoveryDraft.current?.lockoutRecoveryEnabled ?? status.lockoutRecoveryEnabled)
      && normalized.lockoutRecoveryDelayMinutes === Number(recoveryDraft.current?.lockoutRecoveryDelayMinutes ?? status.lockoutRecoveryDelayMinutes)
      && normalized.lockoutRecoveryUsesPer24h === Number(recoveryDraft.current?.lockoutRecoveryUsesPer24h ?? status.lockoutRecoveryUsesPer24h);
    if (unchanged) return;
    const looser = recoverySettingsLooser(normalized);
    if (looser) {
      if (status.commitmentActive) {
        setNotice(humanError("commitment_blocks_loosening_recovery"));
        return;
      }
      if (status.enabled) {
        setSettingsPasswordPrompt({
          kind: "recovery-settings",
          value: normalized,
          title: "Change recovery settings",
          body: "Protection is on. Enter your password to make recovery easier.",
          error: ""
        });
        return;
      }
      applyRecoverySettings(normalized, "", options);
      return;
    }
    if (recoverySettingsStricter(normalized)) {
      requestTimedConfirmation("recovery", {
        title: "Make recovery stricter?",
        body: "This increases the delay or removes the lockout emergency release path.",
        warning: status.commitmentActive ? "Because commitment is active, you will not be able to make this easier until the commitment ends." : "",
        confirmLabel: "Apply"
      }, () => applyRecoverySettings(normalized, "", options));
      return;
    }
    applyRecoverySettings(normalized, "", options);
  };
  const applyShutdownAfterLockout = (enabled, password = "") => {
    const previous = status.shutdownAfterLockout;
    setStatus((current) => ({ ...current, shutdownAfterLockout: enabled }));
    window.brake?.setShutdownAfterLockout?.({ enabled, password }).then((response) => {
      if (!response?.ok) {
        setStatus((current) => ({ ...current, shutdownAfterLockout: previous }));
      }
      if (applyBackendResponse(response)) {
        setSettingsPasswordPrompt(null);
      }
    });
  };
  const requestShutdownAfterLockout = (enabled) => {
    if (enabled === status.shutdownAfterLockout) return;
    const looser = status.shutdownAfterLockout && !enabled;
    if (looser) {
      if (status.commitmentActive) {
        setNotice(humanError("commitment_blocks_loosening_shutdown"));
        return;
      }
      if (status.enabled) {
        setSettingsPasswordPrompt({
          kind: "shutdown-after-lockout",
          value: enabled,
          title: "Turn off shutdown after lockout",
          body: "Protection is on. Enter your password to make lockouts end without shutting down Windows.",
          error: ""
        });
        return;
      }
    }
    applyShutdownAfterLockout(enabled);
  };
  const submitSettingsPassword = (password, localError = "") => {
    if (!settingsPasswordPrompt) return;
    if (localError) {
      setSettingsPasswordPrompt((current) => ({ ...current, error: localError }));
      return;
    }
    const prompt = settingsPasswordPrompt;
    if (prompt.kind === "anime-enabled") {
      applyAnimeEnabled(prompt.value, password);
    } else if (prompt.kind === "recovery-settings") {
      applyRecoverySettings(prompt.value, password);
    } else if (prompt.kind === "shutdown-after-lockout") {
      applyShutdownAfterLockout(prompt.value, password);
    }
  };
  const testLockout = () => {
    window.brake?.testLockout?.().then((response) => {
      applyBackendResponse(response);
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
          </div>
        </div>
      </header>

      <nav className="tabs" aria-label="Main sections">
        <button className={tab === "overview" ? "active" : ""} onClick={() => setTab("overview")}>
          <Gauge size={16} /> Overview
        </button>
        <button className={tab === "illustrated" ? "active" : ""} onClick={() => setTab("illustrated")}>
          <ScanEye size={16} /> Illustrated
        </button>
        <button className={tab === "logs" ? "active" : ""} onClick={() => setTab("logs")}>
          <ScrollText size={16} /> Logs
        </button>
        <button className={tab === "advanced" ? "active" : ""} onClick={() => setTab("advanced")}>
          <Activity size={16} /> Advanced
        </button>
      </nav>

      <section className="content">
        {tab === "overview" ? (
          <>
            <div className="page-head">
              <h1>Overview</h1>
              {notice ? <p className="notice">{notice}</p> : null}
            </div>
            <StatusPanel
              status={status}
              now={now}
              onToggleProtection={toggleProtection}
              onCancelRecoveryUnlock={requestCancelRecoveryUnlock}
            />
            <div className="overview-single">
              <section className="overview-controls" aria-label="Overview controls">
                <div className="lockout-length-row">
                  <div className="lockout-length-copy">
                    <Clock3 size={24} strokeWidth={1.8} aria-hidden="true" />
                    <div>
                      <div className="setting-title">Lockout length</div>
                      <div className="setting-description">Choose how long each lockout lasts.</div>
                    </div>
                  </div>
                  <div className="stepper-control overview-stepper">
                    <button aria-label="Decrease lockout length" disabled={status.failSecure} onClick={() => changeDuration(-1)}>
                      <Minus size={17} />
                    </button>
                    <label>
                      <input
                        aria-label="Lockout length in minutes"
                        inputMode="numeric"
                        min="1"
                        max="60"
                        type="number"
                        disabled={status.failSecure}
                        value={status.lockoutDurationMinutes}
                        onChange={(event) => changeDurationInput(event.target.value)}
                        onBlur={normalizeDurationInput}
                      />
                      <span>min</span>
                    </label>
                    <button aria-label="Increase lockout length" disabled={status.failSecure} onClick={() => changeDuration(1)}>
                      <Plus size={17} />
                    </button>
                  </div>
                </div>
              </section>
            </div>
          </>
        ) : tab === "illustrated" ? (
          <>
            <div className="page-head">
              <h1>Illustrated</h1>
              {notice ? <p className="notice">{notice}</p> : null}
            </div>
            <Card icon={ScanEye} title="Image content detection" subtitle="Manage detection for drawings and animations.">
              {status.animeModelStatus !== "ready" ? (
                <SettingRow
                  title="Detector package"
                  description="Install the local model used to scan drawings and animations."
                  aside={<Badge state="">{animeStatusCopy(status.animeModelStatus)}</Badge>}
                />
              ) : null}
              <SettingRow
                title="Image detection"
                description="Scans drawings, animations, and other non-photographic content."
                aside={
                  <button
                    className={`toggle-action ${status.animeDetectionEnabled ? "active" : ""}`}
                    disabled={status.failSecure || status.animeModelStatus !== "ready" || (status.commitmentActive && status.animeDetectionEnabled)}
                    onClick={() => requestAnimeEnabled(!status.animeDetectionEnabled)}
                  >
                    <span className="toggle-knob" aria-hidden="true" />
                    <span>{status.animeDetectionEnabled ? "On" : "Off"}</span>
                  </button>
                }
              />
              {status.animeModelStatus !== "ready" ? (
                <div className="card-actions">
                  <Button
                    variant="primary"
                    icon={Download}
                    disabled={status.failSecure || animeInstalling}
                    onClick={installAnimeDetector}
                  >
                    {animeInstalling ? "Installing..." : "Download detector"}
                  </Button>
                </div>
              ) : null}
            </Card>
          </>
        ) : tab === "logs" ? (
          <>
            <div className="page-head">
              <h1>Logs</h1>
              {notice ? <p className="notice">{notice}</p> : null}
            </div>
            <DetectionLogs
              events={detectionEvents}
              loading={logsLoading}
              onRefresh={refreshDetectionLogs}
              onClear={clearDetectionLogs}
            />
          </>
        ) : (
          <>
            <div className="page-head">
              <h1>Advanced</h1>
              {notice ? <p className="notice">{notice}</p> : null}
            </div>
            <div className="advanced-stack">
              <Card icon={KeyRound} title="Recovery code" subtitle="Manage how recovery works during lockouts.">
                <SettingRow
                  title="Emergency cooldown"
                  description="How long Brake waits before the recovery code turns protection off."
                  aside={
                    <MinuteStepper
                      ariaLabel="emergency recovery cooldown"
                      value={status.recoveryUnlockDelayMinutes}
                      disabled={status.failSecure}
                      onChange={(value) => requestRecoverySettings({ recoveryUnlockDelayMinutes: value }, { debounce: true })}
                    />
                  }
                />
                <SettingRow
                  title="Recovery during lockout"
                  description="When allowed, the lockout screen shows a small emergency release option. Protection stays on."
                  aside={
                    <button
                      className={`toggle-action ${status.lockoutRecoveryEnabled ? "active" : ""}`}
                      disabled={status.failSecure}
                      onClick={() => requestRecoverySettings({ lockoutRecoveryEnabled: !status.lockoutRecoveryEnabled })}
                    >
                      <span className="toggle-knob" aria-hidden="true" />
                      <span>{status.lockoutRecoveryEnabled ? "On" : "Off"}</span>
                    </button>
                  }
                />
                <SettingRow
                  title="Lockout recovery cooldown"
                  description="After the recovery code is accepted during a lockout, this replaces the remaining timer and skips shutdown."
                  aside={
                    <MinuteStepper
                      ariaLabel="lockout recovery cooldown"
                      disabled={status.failSecure || !status.lockoutRecoveryEnabled}
                      value={status.lockoutRecoveryDelayMinutes}
                      allowZero
                      onChange={(value) => requestRecoverySettings({ lockoutRecoveryDelayMinutes: value }, { debounce: true })}
                    />
                  }
                />
                <SettingRow
                  title="Recovery uses every 24 hours"
                  description="How many successful lockout recoveries are allowed in a rolling 24-hour window."
                  aside={
                    <RecoveryUsesSelect
                      disabled={status.failSecure || !status.lockoutRecoveryEnabled}
                      value={status.lockoutRecoveryUsesPer24h}
                      onChange={(value) => requestRecoverySettings({ lockoutRecoveryUsesPer24h: value })}
                    />
                  }
                />
              </Card>
              <Card icon={Power} title="Lockout behavior" subtitle="Choose what happens when a lockout ends.">
                <SettingRow
                  title="Shutdown after lockout"
                  description="When on, Windows shuts down after a full lockout timer ends. During commitment, this cannot be turned off."
                  aside={
                    <button
                      className={`toggle-action ${status.shutdownAfterLockout ? "active" : ""}`}
                      disabled={status.failSecure || (status.commitmentActive && status.shutdownAfterLockout)}
                      onClick={() => requestShutdownAfterLockout(!status.shutdownAfterLockout)}
                    >
                      <span className="toggle-knob" aria-hidden="true" />
                      <span>{status.shutdownAfterLockout ? "On" : "Off"}</span>
                    </button>
                  }
                />
                <div className="card-actions">
                  <Button variant="secondary" icon={ShieldCheck} disabled={status.failSecure} onClick={testLockout}>
                    Test lockout
                  </Button>
                </div>
              </Card>
            </div>
          </>
        )}
      </section>

      <footer className="actionbar">
        {tab !== "overview" ? (
          <Button variant="primary" icon={status.failSecure ? KeyRound : status.enabled ? ShieldOff : ShieldCheck} onClick={toggleProtection}>
            {status.failSecure ? "Repair with recovery code" : status.enabled ? "Turn off protection" : "Turn on protection"}
          </Button>
        ) : null}
        <Button variant="warning" onClick={toggleCommitment} disabled={status.failSecure}>
          {status.commitmentActive ? "Extend commitment" : "Lock in commitment"}
        </Button>
        <div className="spacer" />
        <Button variant="safe" icon={MessageCircle} onClick={() => setShowFeedback(true)}>
          Send feedback
        </Button>
        <button className="link-button" onClick={() => setShowInfo(true)}>How this works</button>
      </footer>

      {showInfo ? (
        <GuideModal tab={tab} status={status} onClose={() => setShowInfo(false)} />
      ) : null}

      {showFeedback ? (
        <FeedbackModal onClose={() => setShowFeedback(false)} />
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
          mode={commitmentPrompt.mode || "create"}
          committedUntil={status.committedUntil}
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
    commitment_blocks_unlocking_anime: "Commitment is active. Illustrated detection cannot be turned off yet.",
    commitment_blocks_loosening_anime: "Commitment is active. Illustrated detection cannot be made easier.",
    commitment_blocks_loosening_recovery: "Commitment is active. You can only make recovery stricter.",
    commitment_must_be_future: "Commitment must end in the future.",
    invalid_commitment_until: "That commitment time is not valid.",
    invalid_anime_mode: "That illustrated detection setting is not valid.",
    recovery_cooldown_out_of_range: "The selected recovery settings are outside the allowed range.",
    not_initialized: "Brake has not been set up yet.",
    password_required: "Enter your password to make this less strict.",
    permission_denied: "Brake could not write settings. Restart Brake or run the latest BrakeSetup.exe again.",
    backend_missing_reinstall: "Brake is not fully installed. Reinstall Brake, then open it again.",
    service_unavailable: "Brake could not reach the background service. Restart Brake or run the latest BrakeSetup.exe again.",
    state_untrusted: "Brake could not verify its settings. Use your recovery code to repair protection.",
    anime_model_not_ready: "Download the illustrated detector before turning it on.",
    missing_dependencies: "The illustrated detector package is not available yet. Try again after updating Brake.",
    model_package_unavailable: "The illustrated detector package could not be downloaded. Check your connection or try again later.",
    model_package_invalid: "The illustrated detector package was not valid. Try again later.",
    model_package_incomplete: "The illustrated detector package was incomplete. Try again later.",
    model_package_untrusted: "The illustrated detector package had unexpected files. Try again later.",
    model_download_incomplete: "The detector download did not finish cleanly. Try again.",
  };
  return messages[error] || error;
}
