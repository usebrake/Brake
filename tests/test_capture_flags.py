"""Verifies the CAPTUREBLT flag is disabled on Windows.

CAPTUREBLT in the mss GDI blit causes a brief grey flash/stutter during
captures, most visible around fullscreen video transitions. Importing
brake.capture.screen must zero it out.
"""
from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def test_captureblt_disabled_on_windows() -> None:
    if sys.platform != "win32":
        print("  [skip] not Windows")
        return

    import brake.capture.screen  # noqa: F401  (import applies the patch)

    patched = False
    try:
        from mss.windows import gdi  # mss >= 10.2

        assert gdi.CAPTUREBLT == 0
        patched = True
    except ImportError:
        pass
    if not patched:
        import mss.windows as mw  # mss < 10.2

        assert getattr(mw, "CAPTUREBLT", 0) == 0
    print("  [ok] CAPTUREBLT disabled for flicker-free captures")


def main() -> int:
    print("\ntest_captureblt_disabled_on_windows")
    test_captureblt_disabled_on_windows()
    print("\nAll tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
