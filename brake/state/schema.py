"""Persistent state schema. Plain dataclass; serialized to canonical JSON for HMAC signing.

Schema history:
  v1: { password_hash, enabled, locked_until, created_at, schema_version }
  v2: dropped locked_until; added lockout_duration_minutes (1..60).
  v3: added ocr_enabled (bool, default False).
  v4: added committed_until (Optional[str] ISO datetime).
  v5: removed ocr_enabled. OCR text scanning was deleted from the product.
  v6: added detection_sensitivity ("light" | "balanced" | "strict").
  v7: added anime_detection_enabled (bool, default False).
  v8: added anime_detection_mode ("standard" | "strict").
  v9: added recovery_unlock_after (Optional[str] ISO datetime).
  v10: added recovery cooldown settings.
  v11: collapsed detection/anime modes to single defaults; added shutdown_after_lockout.
  v12: added rolling 24-hour lockout recovery usage limits.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Optional

SCHEMA_VERSION = 12

LOCKOUT_DURATION_MIN = 1
LOCKOUT_DURATION_MAX = 60
LOCKOUT_DURATION_DEFAULT = 15

RECOVERY_COOLDOWN_MIN = 1
RECOVERY_COOLDOWN_MAX = 60
RECOVERY_UNLOCK_DELAY_DEFAULT = 15
LOCKOUT_RECOVERY_ENABLED_DEFAULT = True
LOCKOUT_RECOVERY_COOLDOWN_MIN = 0
LOCKOUT_RECOVERY_DELAY_DEFAULT = 0
LOCKOUT_RECOVERY_USES_DEFAULT = 1
LOCKOUT_RECOVERY_USES_UNLIMITED = 0
LOCKOUT_RECOVERY_USES_ALLOWED = (0, 1, 2, 3, 4)
LOCKOUT_RECOVERY_WINDOW_HOURS = 24
SHUTDOWN_AFTER_LOCKOUT_DEFAULT = False

DETECTION_SENSITIVITY_DEFAULT = "balanced"

ANIME_DETECTION_MODE_DEFAULT = "standard"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _clamp_duration(n: int) -> int:
    return max(LOCKOUT_DURATION_MIN, min(LOCKOUT_DURATION_MAX, int(n)))


def _clamp_recovery_cooldown(n: int) -> int:
    return max(RECOVERY_COOLDOWN_MIN, min(RECOVERY_COOLDOWN_MAX, int(n)))


def _clamp_lockout_recovery_cooldown(n: int) -> int:
    return max(LOCKOUT_RECOVERY_COOLDOWN_MIN, min(RECOVERY_COOLDOWN_MAX, int(n)))


def _normalize_lockout_recovery_uses(n: int) -> int:
    value = int(n)
    return value if value in LOCKOUT_RECOVERY_USES_ALLOWED else LOCKOUT_RECOVERY_USES_DEFAULT


def normalize_detection_sensitivity(value: object) -> str:
    return DETECTION_SENSITIVITY_DEFAULT


def normalize_anime_detection_mode(value: object) -> str:
    return ANIME_DETECTION_MODE_DEFAULT


@dataclass
class State:
    password_hash: str
    enabled: bool = False
    lockout_duration_minutes: int = LOCKOUT_DURATION_DEFAULT
    committed_until: Optional[str] = None
    detection_sensitivity: str = DETECTION_SENSITIVITY_DEFAULT
    anime_detection_enabled: bool = False
    anime_detection_mode: str = ANIME_DETECTION_MODE_DEFAULT
    recovery_unlock_after: Optional[str] = None
    recovery_unlock_delay_minutes: int = RECOVERY_UNLOCK_DELAY_DEFAULT
    lockout_recovery_enabled: bool = LOCKOUT_RECOVERY_ENABLED_DEFAULT
    lockout_recovery_delay_minutes: int = LOCKOUT_RECOVERY_DELAY_DEFAULT
    lockout_recovery_uses_per_24h: int = LOCKOUT_RECOVERY_USES_DEFAULT
    lockout_recovery_used_at: list[str] = field(default_factory=list)
    shutdown_after_lockout: bool = SHUTDOWN_AFTER_LOCKOUT_DEFAULT
    created_at: str = field(default_factory=_now_iso)
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        self.lockout_duration_minutes = _clamp_duration(self.lockout_duration_minutes)
        self.detection_sensitivity = normalize_detection_sensitivity(self.detection_sensitivity)
        self.anime_detection_mode = normalize_anime_detection_mode(self.anime_detection_mode)
        self.recovery_unlock_delay_minutes = _clamp_recovery_cooldown(self.recovery_unlock_delay_minutes)
        self.lockout_recovery_enabled = bool(self.lockout_recovery_enabled)
        self.lockout_recovery_delay_minutes = _clamp_lockout_recovery_cooldown(
            self.lockout_recovery_delay_minutes
        )
        self.lockout_recovery_uses_per_24h = _normalize_lockout_recovery_uses(
            self.lockout_recovery_uses_per_24h
        )
        self.lockout_recovery_used_at = [str(value) for value in self.lockout_recovery_used_at]
        self.shutdown_after_lockout = bool(self.shutdown_after_lockout)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "State":
        version = int(d.get("schema_version", 1))
        if version == 1:
            return cls(
                password_hash=d["password_hash"],
                enabled=bool(d.get("enabled", False)),
                lockout_duration_minutes=LOCKOUT_DURATION_DEFAULT,
                committed_until=None,
                detection_sensitivity=DETECTION_SENSITIVITY_DEFAULT,
                anime_detection_enabled=False,
                anime_detection_mode=ANIME_DETECTION_MODE_DEFAULT,
                created_at=d.get("created_at", _now_iso()),
                schema_version=SCHEMA_VERSION,
            )
        if version == 2:
            return cls(
                password_hash=d["password_hash"],
                enabled=bool(d.get("enabled", False)),
                lockout_duration_minutes=int(d.get("lockout_duration_minutes", LOCKOUT_DURATION_DEFAULT)),
                committed_until=None,
                detection_sensitivity=DETECTION_SENSITIVITY_DEFAULT,
                anime_detection_enabled=False,
                anime_detection_mode=ANIME_DETECTION_MODE_DEFAULT,
                created_at=d.get("created_at", _now_iso()),
                schema_version=SCHEMA_VERSION,
            )
        if version == 3:
            return cls(
                password_hash=d["password_hash"],
                enabled=bool(d.get("enabled", False)),
                lockout_duration_minutes=int(d.get("lockout_duration_minutes", LOCKOUT_DURATION_DEFAULT)),
                committed_until=None,
                detection_sensitivity=DETECTION_SENSITIVITY_DEFAULT,
                anime_detection_enabled=False,
                anime_detection_mode=ANIME_DETECTION_MODE_DEFAULT,
                created_at=d.get("created_at", _now_iso()),
                schema_version=SCHEMA_VERSION,
            )
        if version == 4:
            return cls(
                password_hash=d["password_hash"],
                enabled=bool(d.get("enabled", False)),
                lockout_duration_minutes=int(d.get("lockout_duration_minutes", LOCKOUT_DURATION_DEFAULT)),
                committed_until=d.get("committed_until"),
                detection_sensitivity=DETECTION_SENSITIVITY_DEFAULT,
                anime_detection_enabled=False,
                anime_detection_mode=ANIME_DETECTION_MODE_DEFAULT,
                created_at=d.get("created_at", _now_iso()),
                schema_version=SCHEMA_VERSION,
            )
        if version == 5:
            return cls(
                password_hash=d["password_hash"],
                enabled=bool(d.get("enabled", False)),
                lockout_duration_minutes=int(d.get("lockout_duration_minutes", LOCKOUT_DURATION_DEFAULT)),
                committed_until=d.get("committed_until"),
                detection_sensitivity=DETECTION_SENSITIVITY_DEFAULT,
                anime_detection_enabled=False,
                anime_detection_mode=ANIME_DETECTION_MODE_DEFAULT,
                created_at=d.get("created_at", _now_iso()),
                schema_version=SCHEMA_VERSION,
            )
        if version == 6:
            return cls(
                password_hash=d["password_hash"],
                enabled=bool(d.get("enabled", False)),
                lockout_duration_minutes=int(d.get("lockout_duration_minutes", LOCKOUT_DURATION_DEFAULT)),
                committed_until=d.get("committed_until"),
                detection_sensitivity=normalize_detection_sensitivity(
                    d.get("detection_sensitivity", DETECTION_SENSITIVITY_DEFAULT)
                ),
                anime_detection_enabled=bool(d.get("anime_detection_enabled", False)),
                anime_detection_mode=ANIME_DETECTION_MODE_DEFAULT,
                created_at=d.get("created_at", _now_iso()),
                schema_version=SCHEMA_VERSION,
            )
        if version == 7:
            return cls(
                password_hash=d["password_hash"],
                enabled=bool(d.get("enabled", False)),
                lockout_duration_minutes=int(d.get("lockout_duration_minutes", LOCKOUT_DURATION_DEFAULT)),
                committed_until=d.get("committed_until"),
                detection_sensitivity=normalize_detection_sensitivity(
                    d.get("detection_sensitivity", DETECTION_SENSITIVITY_DEFAULT)
                ),
                anime_detection_enabled=bool(d.get("anime_detection_enabled", False)),
                anime_detection_mode=ANIME_DETECTION_MODE_DEFAULT,
                created_at=d.get("created_at", _now_iso()),
                schema_version=SCHEMA_VERSION,
            )
        if version == 8:
            return cls(
                password_hash=d["password_hash"],
                enabled=bool(d.get("enabled", False)),
                lockout_duration_minutes=int(d.get("lockout_duration_minutes", LOCKOUT_DURATION_DEFAULT)),
                committed_until=d.get("committed_until"),
                detection_sensitivity=normalize_detection_sensitivity(
                    d.get("detection_sensitivity", DETECTION_SENSITIVITY_DEFAULT)
                ),
                anime_detection_enabled=bool(d.get("anime_detection_enabled", False)),
                anime_detection_mode=normalize_anime_detection_mode(
                    d.get("anime_detection_mode", ANIME_DETECTION_MODE_DEFAULT)
                ),
                recovery_unlock_after=None,
                created_at=d.get("created_at", _now_iso()),
                schema_version=SCHEMA_VERSION,
            )
        if version == 9:
            return cls(
                password_hash=d["password_hash"],
                enabled=bool(d.get("enabled", False)),
                lockout_duration_minutes=int(d.get("lockout_duration_minutes", LOCKOUT_DURATION_DEFAULT)),
                committed_until=d.get("committed_until"),
                detection_sensitivity=normalize_detection_sensitivity(
                    d.get("detection_sensitivity", DETECTION_SENSITIVITY_DEFAULT)
                ),
                anime_detection_enabled=bool(d.get("anime_detection_enabled", False)),
                anime_detection_mode=normalize_anime_detection_mode(
                    d.get("anime_detection_mode", ANIME_DETECTION_MODE_DEFAULT)
                ),
                recovery_unlock_after=d.get("recovery_unlock_after"),
                created_at=d.get("created_at", _now_iso()),
                schema_version=SCHEMA_VERSION,
            )
        if version == 10:
            return cls(
                password_hash=d["password_hash"],
                enabled=bool(d.get("enabled", False)),
                lockout_duration_minutes=int(d.get("lockout_duration_minutes", LOCKOUT_DURATION_DEFAULT)),
                committed_until=d.get("committed_until"),
                detection_sensitivity=normalize_detection_sensitivity(
                    d.get("detection_sensitivity", DETECTION_SENSITIVITY_DEFAULT)
                ),
                anime_detection_enabled=bool(d.get("anime_detection_enabled", False)),
                anime_detection_mode=normalize_anime_detection_mode(
                    d.get("anime_detection_mode", ANIME_DETECTION_MODE_DEFAULT)
                ),
                recovery_unlock_after=d.get("recovery_unlock_after"),
                recovery_unlock_delay_minutes=int(
                    d.get("recovery_unlock_delay_minutes", RECOVERY_UNLOCK_DELAY_DEFAULT)
                ),
                lockout_recovery_enabled=bool(
                    d.get("lockout_recovery_enabled", LOCKOUT_RECOVERY_ENABLED_DEFAULT)
                ),
                lockout_recovery_delay_minutes=int(
                    d.get("lockout_recovery_delay_minutes", LOCKOUT_RECOVERY_DELAY_DEFAULT)
                ),
                shutdown_after_lockout=SHUTDOWN_AFTER_LOCKOUT_DEFAULT,
                created_at=d.get("created_at", _now_iso()),
                schema_version=SCHEMA_VERSION,
            )
        if version not in (11, SCHEMA_VERSION):
            raise ValueError(f"Unsupported state schema_version {version}")
        return cls(
            password_hash=d["password_hash"],
            enabled=bool(d.get("enabled", False)),
            lockout_duration_minutes=int(d.get("lockout_duration_minutes", LOCKOUT_DURATION_DEFAULT)),
            committed_until=d.get("committed_until"),
            detection_sensitivity=normalize_detection_sensitivity(
                d.get("detection_sensitivity", DETECTION_SENSITIVITY_DEFAULT)
            ),
            anime_detection_enabled=bool(d.get("anime_detection_enabled", False)),
            anime_detection_mode=normalize_anime_detection_mode(
                d.get("anime_detection_mode", ANIME_DETECTION_MODE_DEFAULT)
            ),
            recovery_unlock_after=d.get("recovery_unlock_after"),
            recovery_unlock_delay_minutes=int(
                d.get("recovery_unlock_delay_minutes", RECOVERY_UNLOCK_DELAY_DEFAULT)
            ),
            lockout_recovery_enabled=bool(d.get("lockout_recovery_enabled", LOCKOUT_RECOVERY_ENABLED_DEFAULT)),
            lockout_recovery_delay_minutes=int(
                d.get("lockout_recovery_delay_minutes", LOCKOUT_RECOVERY_DELAY_DEFAULT)
            ),
            lockout_recovery_uses_per_24h=int(
                d.get("lockout_recovery_uses_per_24h", LOCKOUT_RECOVERY_USES_DEFAULT)
            ),
            lockout_recovery_used_at=list(d.get("lockout_recovery_used_at", [])),
            shutdown_after_lockout=bool(d.get("shutdown_after_lockout", SHUTDOWN_AFTER_LOCKOUT_DEFAULT)),
            created_at=d.get("created_at", _now_iso()),
            schema_version=SCHEMA_VERSION,
        )

    def lockout_duration_seconds(self) -> int:
        return self.lockout_duration_minutes * 60

    def recovery_unlock_delay_seconds(self) -> int:
        return self.recovery_unlock_delay_minutes * 60

    def lockout_recovery_delay_seconds(self) -> int:
        return self.lockout_recovery_delay_minutes * 60

    def recent_lockout_recovery_uses(self, now: Optional[datetime] = None) -> list[str]:
        current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        cutoff = current - timedelta(hours=LOCKOUT_RECOVERY_WINDOW_HOURS)
        recent: list[str] = []
        for raw in self.lockout_recovery_used_at:
            try:
                used_at = datetime.fromisoformat(raw)
                if used_at.tzinfo is None:
                    used_at = used_at.replace(tzinfo=timezone.utc)
                used_at = used_at.astimezone(timezone.utc)
            except (TypeError, ValueError):
                continue
            if used_at > cutoff:
                recent.append(used_at.isoformat(timespec="seconds"))
        return recent

    def lockout_recovery_limit_available(self, now: Optional[datetime] = None) -> bool:
        if self.lockout_recovery_uses_per_24h == LOCKOUT_RECOVERY_USES_UNLIMITED:
            return True
        return len(self.recent_lockout_recovery_uses(now)) < self.lockout_recovery_uses_per_24h

    def record_lockout_recovery_use(self, now: Optional[datetime] = None) -> None:
        current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        self.lockout_recovery_used_at = self.recent_lockout_recovery_uses(current)
        self.lockout_recovery_used_at.append(current.isoformat(timespec="seconds"))

    def committed_until_dt(self) -> Optional[datetime]:
        if not self.committed_until:
            return None
        dt = datetime.fromisoformat(self.committed_until)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)

    def commitment_active(self) -> bool:
        until = self.committed_until_dt()
        return bool(until and until > datetime.now(timezone.utc))

    def recovery_unlock_after_dt(self) -> Optional[datetime]:
        if not self.recovery_unlock_after:
            return None
        dt = datetime.fromisoformat(self.recovery_unlock_after)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)

    def recovery_unlock_pending(self) -> bool:
        unlock_after = self.recovery_unlock_after_dt()
        return bool(unlock_after and unlock_after > datetime.now(timezone.utc))

    def recovery_unlock_due(self) -> bool:
        unlock_after = self.recovery_unlock_after_dt()
        return bool(unlock_after and unlock_after <= datetime.now(timezone.utc))
