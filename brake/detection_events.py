"""Structured detector-hit log for the desktop Logs tab.

This is intentionally not the verbose agent log. It stores only meaningful
detector results: context/suspicion/hard hits with a timestamp and compact
metadata suitable for local display.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, List

from brake import paths
from brake.detectors.base import DetectionResult

MAX_EVENTS_ON_DISK = 500
DEFAULT_EVENT_LIMIT = 100


def append_detection_event(
    result: DetectionResult,
    *,
    action: str,
    scan_reason: str = "",
    profile: str = "",
    zoom_region: str = "",
) -> None:
    if result.severity == "none" or not result.label:
        return
    event = {
        "ts": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "detector": result.detector,
        "severity": result.severity,
        "triggered": bool(result.triggered),
        "action": action,
        "label": result.label,
        "confidence": round(float(result.confidence or 0.0), 4),
        "region": result.region,
        "scan_reason": scan_reason,
        "profile": profile,
        "zoom_region": zoom_region,
        "details": result.details or "",
    }
    path = paths.detection_events_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(event, separators=(",", ":"), ensure_ascii=False) + "\n")
    _trim(path)


def list_detection_events(limit: int = DEFAULT_EVENT_LIMIT) -> List[Dict[str, Any]]:
    limit = max(1, min(500, int(limit or DEFAULT_EVENT_LIMIT)))
    path = paths.detection_events_file()
    if not path.exists():
        return []
    events: list[dict[str, Any]] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    for order, line in enumerate(lines[-limit:]):
        try:
            raw = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(raw, dict):
            event = _normalize_event(raw)
            event["_order"] = order
            events.append(event)
    events.sort(key=lambda item: (str(item.get("ts", "")), int(item.get("_order", 0))), reverse=True)
    for event in events:
        event.pop("_order", None)
    return events


def clear_detection_events() -> None:
    path = paths.detection_events_file()
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass


def _normalize_event(raw: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "ts": str(raw.get("ts", "")),
        "detector": str(raw.get("detector", "")),
        "severity": str(raw.get("severity", "none")),
        "triggered": bool(raw.get("triggered", False)),
        "action": str(raw.get("action", "observed")),
        "label": str(raw.get("label", "")),
        "confidence": float(raw.get("confidence", 0.0) or 0.0),
        "region": str(raw.get("region", "")),
        "scanReason": str(raw.get("scan_reason", "")),
        "profile": str(raw.get("profile", "")),
        "zoomRegion": str(raw.get("zoom_region", "")),
        "details": str(raw.get("details", "")),
    }


def _trim(path) -> None:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
        if len(lines) <= MAX_EVENTS_ON_DISK:
            return
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text("\n".join(lines[-MAX_EVENTS_ON_DISK:]) + "\n", encoding="utf-8")
        os.replace(tmp, path)
    except OSError:
        pass
