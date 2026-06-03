"""Main scan loop.

Runs in foreground for dev (`python -m lockitup`) and is hosted by the
Windows Service in installed mode.
"""
from __future__ import annotations

import logging
import subprocess
import time
from typing import List, Optional

from PIL import ImageStat

from lockitup.capture.screen import capture_all_monitors
from lockitup.config import Settings, load_settings
from lockitup.detectors.anime_nsfw import AnimeNSFWDetector
from lockitup.detectors.base import DetectionResult, Detector
from lockitup.detectors.nudity import NudityDetector
from lockitup.escalation import ProbationStore, ProbationTamperedError, current_boot_marker
from lockitup.lockout.recovery import active_lockout_exists, spawn_resume_lockout_if_needed
from lockitup.runtime import lockout_command
from lockitup.state import StateStore, StateTamperedError
from lockitup.state.recovery_unlock import apply_due_recovery_unlock
from lockitup.test_mode import is_test_mode, t

_log = logging.getLogger(__name__)

PENALTY_MIN_SECONDS = t(10 * 60, 20)
TEST_MODE_LOCKOUT_SECONDS = 10
FIRST_LOCKOUT_MESSAGE = (
    "Your computer will shut down when this timer ends. After restart, "
    "Brake will run a 5-minute strict watch. If explicit content is "
    "opened again during that window, a longer lockout will start and "
    "Windows will shut down again."
)
PENALTY_LOCKOUT_MESSAGE = (
    "Explicit content was detected during the post-restart strict watch. "
    "Windows will shut down when this timer ends."
)

BALANCED_WARNING_SECONDS = t(10, 3)
BALANCED_COOLDOWN_SECONDS = t(60, 8)
STRICT_PENALTY_LADDER = [
    t(30, 5),
    t(60, 10),
    t(120, 20),
]
STRICT_RESET_SECONDS = t(10 * 60, 30)
STRICT_CONFIRM_WINDOW = t(10, 4)
# Hard explicit video can flicker between labels/frames. A single lower-score
# genital/anus hit arms a short strike window; a second hard hit confirms.
HARD_CONFIRM_WINDOW = t(18, 6)
HARD_IMMEDIATE_CONFIDENCE = 0.90
ANIME_STANDARD_CONTEXT_CONFIDENCE = 0.90
ANIME_STRICT_CONTEXT_CONFIDENCE = 0.86
ANIME_STRICT_HARD_CONFIDENCE = 0.97
BALANCED_WARNING_MESSAGE = (
    "Possible explicit content was detected. This short pause is a chance "
    "to skip or close the scene. Your computer will not shut down."
)
STRICT_WARNING_MESSAGE = (
    "Possible explicit content was detected and confirmed across two scans. "
    "This pause is meant to interrupt the pattern. Your computer will not shut down."
)


def _build_detectors(settings: Settings) -> List[Detector]:
    return [
        NudityDetector(settings.nudity),
        AnimeNSFWDetector(settings.nudity),
    ]


def _spawn_lockout(
    duration: int,
    reason: str,
    message: str = "",
    shutdown_on_done: bool = False,
) -> None:
    _log.warning(
        "LOCKOUT TRIGGERED: reason=%s duration=%ds shutdown_on_done=%s",
        reason, duration, shutdown_on_done,
    )
    args = ["--duration", str(duration), "--reason", reason]
    if message:
        args.extend(["--message", message])
    if shutdown_on_done:
        args.append("--shutdown-on-done")
    subprocess.Popen(lockout_command(args))


class Watcher:
    def __init__(self, store: Optional[StateStore] = None) -> None:
        self.store = store or StateStore()
        self.settings = load_settings()
        self.detectors = _build_detectors(self.settings)
        self.probation = ProbationStore()
        self._lockout_until = 0.0
        self._last_balanced_warning_at = 0.0
        self._last_strict_pending_label = ""
        self._last_strict_pending_at = 0.0
        self._strict_strike_count = 0
        self._last_strict_strike_at = 0.0
        self._last_hard_pending_label = ""
        self._last_hard_pending_at = 0.0
        self._hard_strike_count = 0

    def _current_state(self):
        try:
            s = self.store.load()
            if s is not None:
                s = apply_due_recovery_unlock(self.store, s)
            return s
        except StateTamperedError:
            _log.critical("State tampered. Fail-secure: assume enabled.")
            return None

    def _state_says_run(self) -> bool:
        s = self._current_state()
        if s is None:
            return True
        return s.enabled

    def _current_lockout_duration_seconds(self) -> int:
        if is_test_mode():
            return TEST_MODE_LOCKOUT_SECONDS
        s = self._current_state()
        if s is None:
            return self.settings.lockout_duration_seconds
        return s.lockout_duration_seconds()

    def _current_sensitivity(self) -> str:
        s = self._current_state()
        if s is None:
            return "balanced"
        return getattr(s, "detection_sensitivity", "balanced") or "balanced"

    def _anime_detection_enabled(self) -> bool:
        s = self._current_state()
        if s is None:
            return False
        return bool(getattr(s, "anime_detection_enabled", False))

    def _current_anime_mode(self) -> str:
        s = self._current_state()
        if s is None:
            return "standard"
        mode = getattr(s, "anime_detection_mode", "standard") or "standard"
        return "strict" if mode == "strict" else "standard"

    def _probation_penalty_seconds(self) -> Optional[int]:
        if active_lockout_exists():
            _log.info("Post-restart strict watch waiting for active lockout to finish.")
            return None

        try:
            record = self.probation.load()
        except ProbationTamperedError as e:
            _log.critical("Probation file tampered. Fail-secure penalty path: %s", e)
            return max(self._current_lockout_duration_seconds(), PENALTY_MIN_SECONDS)

        if record is None:
            return None

        boot_marker = current_boot_marker()
        if record.should_activate(boot_marker):
            record.activate()
            self.probation.save(record)
            _log.warning(
                "Post-restart strict watch activated for %ds; penalty=%ds.",
                record.duration_seconds,
                record.penalty_duration_seconds,
            )

        if record.is_pending():
            return None

        if record.is_expired():
            _log.info("Post-restart strict watch expired; clearing probation.")
            self.probation.clear()
            return None

        return max(record.penalty_duration_seconds, PENALTY_MIN_SECONDS)

    def _handle_detection(self, hit: DetectionResult) -> None:
        if hit.detector == "anime_nsfw" and hit.severity == "context":
            self._handle_balanced_context(hit)
            return
        if hit.severity == "context":
            sensitivity = self._current_sensitivity()
            if sensitivity == "balanced":
                self._handle_balanced_context(hit)
            elif sensitivity == "strict":
                self._handle_strict_context(hit)
            else:
                _log.info("context detection ignored in light mode: label=%s", hit.label)
            return
        self._handle_hard(hit)

    def _apply_anime_mode(self, result: DetectionResult) -> DetectionResult:
        if result.detector != "anime_nsfw" or not result.triggered:
            return result
        mode = self._current_anime_mode()
        threshold = ANIME_STRICT_CONTEXT_CONFIDENCE if mode == "strict" else ANIME_STANDARD_CONTEXT_CONFIDENCE
        if result.confidence < threshold:
            return DetectionResult.negative(result.detector)
        if mode == "strict" and result.confidence >= ANIME_STRICT_HARD_CONFIDENCE:
            return DetectionResult(
                detector=result.detector,
                triggered=True,
                confidence=result.confidence,
                label=result.label.replace("POSSIBLE", "EXPLICIT") if result.label else "EXPLICIT ANIME",
                severity="hard",
            )
        return result

    def _handle_hard(self, hit: DetectionResult) -> None:
        now = time.monotonic()
        label = hit.label or hit.detector.upper()
        if hit.confidence >= HARD_IMMEDIATE_CONFIDENCE:
            self._last_hard_pending_label = ""
            self._last_hard_pending_at = 0.0
            self._hard_strike_count = 0
            _log.warning("hard detection immediately confirmed: label=%s conf=%.2f", label, hit.confidence)
            self._apply_hard_lockout(hit)
            return
        if (
            (now - self._last_hard_pending_at) <= HARD_CONFIRM_WINDOW
            and self._hard_strike_count >= 1
        ):
            self._last_hard_pending_label = ""
            self._last_hard_pending_at = 0.0
            self._hard_strike_count = 0
            _log.warning("hard detection confirmed by second strike: label=%s conf=%.2f", label, hit.confidence)
            self._apply_hard_lockout(hit)
            return
        self._last_hard_pending_label = label
        self._last_hard_pending_at = now
        self._hard_strike_count = 1
        _log.warning(
            "hard detection pending confirmation: label=%s conf=%.2f window=%ds",
            label,
            hit.confidence,
            HARD_CONFIRM_WINDOW,
        )

    def _apply_hard_lockout(self, hit: DetectionResult) -> None:
        reason = hit.label or hit.detector.upper()

        probation_penalty = self._probation_penalty_seconds()
        if probation_penalty is not None:
            self.probation.clear()
            _spawn_lockout(
                probation_penalty,
                reason,
                message=PENALTY_LOCKOUT_MESSAGE,
                shutdown_on_done=True,
            )
            self._lockout_until = time.monotonic() + probation_penalty
            return

        duration = self._current_lockout_duration_seconds()
        penalty_duration = max(duration, PENALTY_MIN_SECONDS)
        self.probation.create_pending(penalty_duration, reason)
        _spawn_lockout(
            duration,
            reason,
            message=FIRST_LOCKOUT_MESSAGE,
            shutdown_on_done=True,
        )
        self._lockout_until = time.monotonic() + duration

    def _handle_balanced_context(self, hit: DetectionResult) -> None:
        now = time.monotonic()
        if (
            self._last_balanced_warning_at > 0
            and (now - self._last_balanced_warning_at) < BALANCED_COOLDOWN_SECONDS
        ):
            _log.info("balanced context warning suppressed by cooldown: label=%s", hit.label)
            return
        self._last_balanced_warning_at = now
        reason = hit.label or hit.detector.upper()
        _spawn_lockout(
            BALANCED_WARNING_SECONDS,
            reason,
            message=BALANCED_WARNING_MESSAGE,
            shutdown_on_done=False,
        )
        self._lockout_until = now + BALANCED_WARNING_SECONDS

    def _handle_strict_context(self, hit: DetectionResult) -> None:
        now = time.monotonic()
        label = hit.label or hit.detector.upper()
        if (
            (now - self._last_strict_pending_at) <= STRICT_CONFIRM_WINDOW
            and label == self._last_strict_pending_label
        ):
            self._last_strict_pending_label = ""
            self._last_strict_pending_at = 0.0
            self._apply_strict_context_penalty(hit)
            return
        self._last_strict_pending_label = label
        self._last_strict_pending_at = now
        _log.info("strict: pending confirmation for %s", label)

    def _apply_strict_context_penalty(self, hit: DetectionResult) -> None:
        now = time.monotonic()
        if (now - self._last_strict_strike_at) >= STRICT_RESET_SECONDS:
            self._strict_strike_count = 0
        self._strict_strike_count += 1
        self._last_strict_strike_at = now
        duration = STRICT_PENALTY_LADDER[
            min(self._strict_strike_count - 1, len(STRICT_PENALTY_LADDER) - 1)
        ]
        reason = hit.label or hit.detector.upper()
        _spawn_lockout(
            duration,
            reason,
            message=STRICT_WARNING_MESSAGE,
            shutdown_on_done=False,
        )
        self._lockout_until = now + duration

    def _scan_once(self) -> Optional[DetectionResult]:
        img = capture_all_monitors()
        stat = ImageStat.Stat(img.resize((1, 1)))
        mean = tuple(round(v, 1) for v in stat.mean)
        _log.info("capture: size=%sx%s mean_rgb=%s", img.width, img.height, mean)
        sensitivity = self._current_sensitivity()
        anime_enabled = self._anime_detection_enabled()
        for det in self.detectors:
            if getattr(det, "name", "") == "anime_nsfw" and not anime_enabled:
                _log.info("scan: detector=anime_nsfw skipped because anime detection is off")
                continue
            res = det.scan(img)
            res = self._apply_anime_mode(res)
            _log.info(
                "scan: detector=%s triggered=%s severity=%s conf=%.2f label=%s",
                res.detector,
                res.triggered,
                res.severity,
                res.confidence,
                res.label,
            )
            if res.triggered and res.severity == "hard":
                return res
            if res.triggered and res.severity == "context" and sensitivity in ("balanced", "strict"):
                return res
        return None

    def run_forever(self) -> None:
        interval = 2 if is_test_mode() else self.settings.scan_interval_seconds
        _log.info("Watcher starting: interval=%ds test_mode=%s", interval, is_test_mode())
        spawn_resume_lockout_if_needed("watcher-start")

        while True:
            if not self._state_says_run():
                time.sleep(min(interval, 10))
                continue

            now = time.monotonic()
            if now < self._lockout_until:
                time.sleep(min(interval, 5))
                continue
            self._probation_penalty_seconds()

            try:
                hit = self._scan_once()
            except Exception as e:
                _log.exception("scan_once raised: %s", e)
                hit = None

            if hit:
                self._handle_detection(hit)

            time.sleep(interval)
