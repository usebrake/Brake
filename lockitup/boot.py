"""Login-time recovery script. Fired by the HKCU Run key on every user login.

If a persistent lockout is still active, re-spawn the lockout window with the
remaining time. If the lockout file is gone or expired, exit silently. If
it's tampered, fail-secure by re-issuing a fresh default-duration lockout.

This file is run directly (`pythonw.exe lockitup\\boot.py`) by the Run key,
so we have to set up sys.path before importing the package.
"""
from __future__ import annotations

import sys
from pathlib import Path

# Make `import lockitup` work when invoked by absolute path from HKCU\...\Run.
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from lockitup.lockout.recovery import spawn_resume_lockout_if_needed  # noqa: E402


def main() -> int:
    spawn_resume_lockout_if_needed("boot")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
