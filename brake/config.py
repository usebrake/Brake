"""Load + validate settings.yaml.

settings.yaml lookup order:
  1. $BRAKE_CONFIG (full path) if set
  2. $BRAKE_DATA_DIR/settings.yaml if it exists
  3. <repo>/config/settings.default.yaml (shipped default)
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List

import yaml

from brake import paths

REPO_ROOT = Path(__file__).resolve().parent.parent


@dataclass
class NudityConfig:
    enabled: bool = True
    confidence_threshold: float = 0.55
    trigger_classes: List[str] = field(default_factory=list)


@dataclass
class LoggingConfig:
    level: str = "INFO"
    max_bytes: int = 1_048_576
    backup_count: int = 3


@dataclass
class HardeningConfig:
    block_taskmgr: bool = True
    block_timedate: bool = True
    # 500ms keeps blocked windows closing fast while halving the wakeup rate
    # (frequent timer wakeups are a real battery cost on laptops).
    poll_interval_ms: int = 500


@dataclass
class Settings:
    scan_interval_seconds: int = 15
    lockout_duration_seconds: int = 900
    nudity: NudityConfig = field(default_factory=NudityConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    hardening: HardeningConfig = field(default_factory=HardeningConfig)


def _settings_path() -> Path:
    override = os.environ.get("BRAKE_CONFIG")
    if override:
        return Path(override)
    user_path = paths.data_dir() / "settings.yaml"
    if user_path.exists():
        return user_path
    return REPO_ROOT / "config" / "settings.default.yaml"


def load_settings() -> Settings:
    path = _settings_path()
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    hardening_raw = raw.get("hardening") or {}
    hardening_fields = set(HardeningConfig.__dataclass_fields__)
    return Settings(
        scan_interval_seconds=int(raw.get("scan_interval_seconds", 15)),
        lockout_duration_seconds=int(raw.get("lockout_duration_seconds", 900)),
        nudity=NudityConfig(**(raw.get("nudity") or {})),
        logging=LoggingConfig(**(raw.get("logging") or {})),
        hardening=HardeningConfig(
            **{k: v for k, v in hardening_raw.items() if k in hardening_fields}
        ),
    )
