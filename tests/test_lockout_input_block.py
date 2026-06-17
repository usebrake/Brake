from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from brake.lockout.input_block import (
    VK_CAPITAL,
    VK_ESCAPE,
    VK_F4,
    VK_LWIN,
    VK_SHIFT,
    VK_TAB,
    KeyboardBlocker,
)


def test_recovery_text_entry_keys_are_not_blocked():
    assert KeyboardBlocker._should_block(VK_CAPITAL, alt=False, ctrl=False, shift=False) is False
    assert KeyboardBlocker._should_block(VK_SHIFT, alt=False, ctrl=False, shift=False) is False
    assert KeyboardBlocker._should_block(ord("A"), alt=False, ctrl=False, shift=True) is False
    assert KeyboardBlocker._should_block(ord("1"), alt=False, ctrl=False, shift=True) is False


def test_escape_shortcuts_stay_blocked():
    assert KeyboardBlocker._should_block(VK_LWIN, alt=False, ctrl=False, shift=False) is True
    assert KeyboardBlocker._should_block(VK_TAB, alt=True, ctrl=False, shift=False) is True
    assert KeyboardBlocker._should_block(VK_F4, alt=True, ctrl=False, shift=False) is True
    assert KeyboardBlocker._should_block(VK_ESCAPE, alt=False, ctrl=True, shift=False) is True
    assert KeyboardBlocker._should_block(VK_ESCAPE, alt=False, ctrl=True, shift=True) is True


if __name__ == "__main__":
    tests = [
        test_recovery_text_entry_keys_are_not_blocked,
        test_escape_shortcuts_stay_blocked,
    ]
    for test in tests:
        test()
        print(f"  [ok] {test.__name__}")
    print("All tests passed.")
