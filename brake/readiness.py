"""First-run readiness check.

We can't really stop the user from clicking Enable, but we can audit the
environment at GUI startup and flag missing pieces clearly so detection
doesn't silently degrade or fail loud-but-confusing on the first scan.

Each check is a try-import. We never call out to the network or read the
user's screen; everything is local.

Returns a list of ReadinessIssue. severity="blocker" means protection
literally won't work (no NudeNet, no Pillow). severity="warning" means a
specific capability is missing (e.g. illustrated detection won't run).
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import List


@dataclass
class ReadinessIssue:
    name: str
    severity: str         # "blocker" | "warning"
    message: str
    fix_command: str


def _check_import(module: str) -> bool:
    try:
        __import__(module)
        return True
    except ImportError:
        return False


def check_all() -> List[ReadinessIssue]:
    issues: List[ReadinessIssue] = []

    # --- BLOCKERS ---
    if not _check_import("PIL"):
        issues.append(ReadinessIssue(
            "Pillow", "blocker",
            "Image library (Pillow) is missing. Screen capture and detection require it.",
            "pip install Pillow",
        ))
    if not _check_import("mss"):
        issues.append(ReadinessIssue(
            "mss", "blocker",
            "Screen capture library (mss) is missing.",
            "pip install mss",
        ))
    if not _check_import("nudenet"):
        issues.append(ReadinessIssue(
            "NudeNet", "blocker",
            "NudeNet is missing. Photographic NSFW detection won't work.",
            "pip install nudenet",
        ))
    if not _check_import("onnxruntime"):
        issues.append(ReadinessIssue(
            "ONNX Runtime", "blocker",
            "ONNX Runtime is missing. NudeNet cannot run without it.",
            "pip install onnxruntime",
        ))
    if sys.platform == "win32" and not _check_import("win32api"):
        issues.append(ReadinessIssue(
            "pywin32", "blocker",
            "pywin32 is missing. The Windows service, IPC, and DPAPI key storage all need it.",
            "pip install pywin32",
        ))

    # --- WARNINGS (optional features) ---
    if not _check_import("transformers"):
        issues.append(ReadinessIssue(
            "transformers", "warning",
            "transformers is missing. Illustrated detection will silently skip. "
            "Only photographic content will be caught.",
            "pip install transformers torch",
        ))
    elif not _check_import("torch"):
        issues.append(ReadinessIssue(
            "torch", "warning",
            "torch is missing. The illustrated detector loads on torch. Installed transformers can't run it without torch.",
            "pip install torch",
        ))

    if not _check_import("argon2"):
        issues.append(ReadinessIssue(
            "argon2-cffi", "blocker",
            "argon2-cffi is missing. Password hashing won't work.",
            "pip install argon2-cffi",
        ))

    return issues


def has_blockers(issues: List[ReadinessIssue]) -> bool:
    return any(i.severity == "blocker" for i in issues)




