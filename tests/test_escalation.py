"""Round-trip + activation tests for signed probation state."""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path


def _fresh_env(tmp: Path):
    os.environ["LOCKITUP_DATA_DIR"] = str(tmp)
    for mod in [k for k in list(sys.modules) if k.startswith("lockitup.")]:
        del sys.modules[mod]
    from lockitup.escalation import ProbationStore, ProbationTamperedError
    return ProbationStore(), ProbationTamperedError


def test_pending_then_activate_after_new_boot(tmp: Path) -> None:
    store, _ = _fresh_env(tmp)
    record = store.create_pending(penalty_duration_seconds=600, reason="TEST")
    assert record.is_pending()
    assert not record.should_activate(record.created_boot_marker)
    assert record.should_activate(record.created_boot_marker + 1000)

    record.activate()
    store.save(record)
    loaded = store.load()
    assert loaded is not None
    assert not loaded.is_pending()
    assert loaded.remaining_seconds() > 0
    print("  [ok] pending probation activates only after boot marker changes")


def test_tamper_rejected(tmp: Path) -> None:
    store, ProbationTamperedError = _fresh_env(tmp)
    store.create_pending(penalty_duration_seconds=600, reason="TEST")
    raw = json.loads((tmp / "probation.json").read_text(encoding="utf-8"))
    raw["payload"]["penalty_duration_seconds"] = 1
    (tmp / "probation.json").write_text(json.dumps(raw), encoding="utf-8")
    try:
        store.load()
    except ProbationTamperedError:
        print("  [ok] tampered probation rejected")
        return
    raise AssertionError("Tampered probation was accepted!")


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="lockitup-escalation-") as td:
        tmp = Path(td)
        print(f"Using temp dir: {tmp}")
        for fn in (test_pending_then_activate_after_new_boot, test_tamper_rejected):
            sub = tmp / fn.__name__
            sub.mkdir()
            print(f"\n{fn.__name__}")
            fn(sub)
    print("\nAll tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
