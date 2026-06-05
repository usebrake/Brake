r"""Canonical filesystem paths for brake.

Production install layout (chosen in milestone 9):
    C:\\Program Files\\brake\\\           binaries (admin-only write)
    C:\\ProgramData\\brake\\\             state + logs + models (this module)

For development, set env var BRAKE_DATA_DIR to redirect everything under the
repo, e.g. `$env:BRAKE_DATA_DIR = "$pwd\\local_state"`.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path


def _default_data_dir() -> Path:
    if sys.platform == "win32":
        program_data = os.environ.get("PROGRAMDATA", r"C:\ProgramData")
        return Path(program_data) / "brake"
    return Path.home() / ".brake"


def data_dir() -> Path:
    override = os.environ.get("BRAKE_DATA_DIR")
    base = Path(override).expanduser() if override else _default_data_dir()
    base.mkdir(parents=True, exist_ok=True)
    return base


def state_file() -> Path:
    return data_dir() / "state.json"


def state_initialized_file() -> Path:
    return data_dir() / "state.initialized"


def key_file() -> Path:
    return data_dir() / "state.key"


def lockout_file() -> Path:
    return data_dir() / "lockout.json"


def lockout_pid_file() -> Path:
    return data_dir() / "lockout.pid"


def probation_file() -> Path:
    return data_dir() / "probation.json"


def recovery_file() -> Path:
    return data_dir() / "recovery.json"


def logs_dir() -> Path:
    d = data_dir() / "logs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def models_dir() -> Path:
    d = data_dir() / "models"
    d.mkdir(parents=True, exist_ok=True)
    return d
