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
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Optional

SCHEMA_VERSION = 9

LOCKOUT_DURATION_MIN = 1
LOCKOUT_DURATION_MAX = 60
LOCKOUT_DURATION_DEFAULT = 3

DETECTION_SENSITIVITY_DEFAULT = "balanced"
DETECTION_SENSITIVITIES = {"light", "balanced", "strict"}
SENSITIVITY_RANK = {"light": 0, "balanced": 1, "strict": 2}

ANIME_DETECTION_MODE_DEFAULT = "standard"
ANIME_DETECTION_MODES = {"standard", "strict"}
ANIME_MODE_RANK = {"standard": 0, "strict": 1}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _clamp_duration(n: int) -> int:
    return max(LOCKOUT_DURATION_MIN, min(LOCKOUT_DURATION_MAX, int(n)))


def normalize_detection_sensitivity(value: object) -> str:
    value_str = str(value or "").strip().lower()
    if value_str in DETECTION_SENSITIVITIES:
        return value_str
    return DETECTION_SENSITIVITY_DEFAULT


def normalize_anime_detection_mode(value: object) -> str:
    value_str = str(value or "").strip().lower()
    if value_str in ANIME_DETECTION_MODES:
        return value_str
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
    created_at: str = field(default_factory=_now_iso)
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        self.lockout_duration_minutes = _clamp_duration(self.lockout_duration_minutes)
        self.detection_sensitivity = normalize_detection_sensitivity(self.detection_sensitivity)
        self.anime_detection_mode = normalize_anime_detection_mode(self.anime_detection_mode)

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
        if version != SCHEMA_VERSION:
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
            created_at=d.get("created_at", _now_iso()),
            schema_version=version,
        )

    def lockout_duration_seconds(self) -> int:
        return self.lockout_duration_minutes * 60

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
