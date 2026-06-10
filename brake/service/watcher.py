"""Main scan loop.

Runs in foreground for dev (`python -m brake`) and is hosted by the
Windows Service in installed mode.
"""
from __future__ import annotations

import logging
import subprocess
import time
from typing import List, Optional, Tuple

from PIL import ImageStat

from brake.capture.screen import capture_all_monitors, reset_capture_handle
from brake.config import Settings, load_settings
from brake.detectors.anime_nsfw import AnimeNSFWDetector
from brake.detectors.base import DetectionResult, Detector
from brake.detectors.nudity import NudityDetector
from brake.escalation import ProbationStore, ProbationTamperedError, current_boot_marker
from brake.lockout.recovery import active_lockout_exists, spawn_resume_lockout_if_needed
from brake.runtime import lockout_command
from brake.service.scan_environment import ScanEnvironmentMonitor
from brake.service.scan_pacer import FramePacer, SUSTAINED_SCAN_SECONDS
from brake.state import StateStore, StateTamperedError
from brake.state.recovery_unlock import apply_due_recovery_unlock
from brake.test_mode import is_test_mode, t

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

# How many back-to-back zoom confirmations a suspicion streak may trigger
# before the loop falls back to the pacer's normal cadence. Bounds CPU on
# persistently borderline screens; the streak resets after the next clean scan.
FAST_RESCAN_MAX_STREAK = 2
# How often slow housekeeping (state file read, probation check) runs. The
# tick loop itself is much faster than this.
HOUSEKEEPING_SECONDS = 2.0
BALANCED_WARNING_SECONDS = t(10, 3)
BALANCED_COOLDOWN_SECONDS = t(60, 8)
BALANCED_ESCALATION_WINDOW = t(5 * 60, 30)
BALANCED_CONTEXT_STRIKES_TO_LOCKOUT = 2
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
STRICT_LOCKOUT_MESSAGE = (
    "Strict mode treats confirmed nudity as a full lockout. Your computer "
    "will shut down when this timer ends."
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
        self._last_balanced_context_at = 0.0
        self._balanced_context_strike_count = 0
        self._last_strict_pending_label = ""
        self._last_strict_pending_at = 0.0
        self._last_hard_pending_label = ""
        self._last_hard_pending_at = 0.0
        self._hard_strike_count = 0
        self.scan_environment = ScanEnvironmentMonitor()
        self._state_cached_at = 0.0
        self._state_cache: Optional[tuple] = None  # (state,) once loaded

    def _current_state(self):
        # The tick loop asks for state several times per second; reading and
        # HMAC-verifying the state file that often is wasted work. A short
        # cache keeps the loop cheap while staying responsive to toggles.
        now = time.monotonic()
        if self._state_cache is not None and (now - self._state_cached_at) < HOUSEKEEPING_SECONDS:
            return self._state_cache[0]
        try:
            s = self.store.load()
            if s is not None:
                s = apply_due_recovery_unlock(self.store, s)
        except StateTamperedError:
            _log.critical("State tampered. Fail-secure: assume enabled.")
            s = None
        self._state_cache = (s,)
        self._state_cached_at = now
        return s

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

    def _handle_detection(self, hit: DetectionResult) -> bool:
        """Handle one hit. Return True when a fast confirmation scan should run."""
        if hit.detector == "anime_nsfw" and hit.severity == "context":
            self._handle_balanced_context(hit)
            return False

        sensitivity = self._current_sensitivity()
        if hit.severity == "context":
            if sensitivity == "balanced":
                self._handle_balanced_context(hit)
            elif sensitivity == "strict":
                return self._handle_strict_context(hit)
            else:
                _log.info("context detection ignored in light mode: label=%s", hit.label)
            return False

        if sensitivity == "strict":
            _log.warning(
                "strict hard detection treated as full lockout: label=%s conf=%.2f",
                hit.label,
                hit.confidence,
            )
            self._apply_hard_lockout(hit, message=STRICT_LOCKOUT_MESSAGE)
            return False
        return self._handle_hard(hit, fast_confirm=(sensitivity == "balanced"))

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
                region=result.region,
            )
        return result

    def _handle_hard(self, hit: DetectionResult, *, fast_confirm: bool = False) -> bool:
        now = time.monotonic()
        label = hit.label or hit.detector.upper()
        if hit.confidence >= HARD_IMMEDIATE_CONFIDENCE:
            self._last_hard_pending_label = ""
            self._last_hard_pending_at = 0.0
            self._hard_strike_count = 0
            _log.warning("hard detection immediately confirmed: label=%s conf=%.2f", label, hit.confidence)
            self._apply_hard_lockout(hit)
            return False
        if (
            (now - self._last_hard_pending_at) <= HARD_CONFIRM_WINDOW
            and self._hard_strike_count >= 1
        ):
            self._last_hard_pending_label = ""
            self._last_hard_pending_at = 0.0
            self._hard_strike_count = 0
            _log.warning("hard detection confirmed by second strike: label=%s conf=%.2f", label, hit.confidence)
            self._apply_hard_lockout(hit)
            return False
        self._last_hard_pending_label = label
        self._last_hard_pending_at = now
        self._hard_strike_count = 1
        _log.warning(
            "hard detection pending confirmation: label=%s conf=%.2f window=%ds fast_confirm=%s",
            label,
            hit.confidence,
            HARD_CONFIRM_WINDOW,
            fast_confirm,
        )
        return bool(fast_confirm)

    def _apply_hard_lockout(self, hit: DetectionResult, message: str = FIRST_LOCKOUT_MESSAGE) -> None:
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
            message=message,
            shutdown_on_done=True,
        )
        self._lockout_until = time.monotonic() + duration

    def _handle_balanced_context(self, hit: DetectionResult) -> None:
        now = time.monotonic()
        if (now - self._last_balanced_context_at) > BALANCED_ESCALATION_WINDOW:
            self._balanced_context_strike_count = 0

        if now < self._lockout_until:
            # The warning overlay is still up; the user has not had a chance
            # to act on it yet, so this hit does not count as a new strike.
            _log.info("balanced context ignored while warning active: label=%s", hit.label)
            return

        self._balanced_context_strike_count += 1
        self._last_balanced_context_at = now
        if self._balanced_context_strike_count >= BALANCED_CONTEXT_STRIKES_TO_LOCKOUT:
            self._balanced_context_strike_count = 0
            _log.warning("balanced context escalated to full lockout: label=%s", hit.label)
            self._apply_hard_lockout(hit)
            return

        if (
            self._last_balanced_warning_at > 0
            and (now - self._last_balanced_warning_at) < BALANCED_COOLDOWN_SECONDS
        ):
            _log.info(
                "balanced context strike counted, warning suppressed by cooldown: label=%s",
                hit.label,
            )
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

    def _handle_strict_context(self, hit: DetectionResult) -> bool:
        now = time.monotonic()
        label = hit.label or hit.detector.upper()
        if (
            (now - self._last_strict_pending_at) <= STRICT_CONFIRM_WINDOW
            and label == self._last_strict_pending_label
        ):
            self._last_strict_pending_label = ""
            self._last_strict_pending_at = 0.0
            _log.warning("strict context confirmed as full lockout: label=%s", label)
            self._apply_hard_lockout(hit, message=STRICT_LOCKOUT_MESSAGE)
            return False
        self._last_strict_pending_label = label
        self._last_strict_pending_at = now
        _log.info("strict: pending fast confirmation for %s", label)
        return True

    def _scan_once(
        self,
        img=None,
        *,
        profile: str = "full",
        changed_box=None,
        zoom_region: str = "",
        reason: str = "",
    ) -> Tuple[Optional[DetectionResult], Optional[DetectionResult]]:
        """Run one detection pass over ``img`` (captured here when omitted).

        Returns (hit, suspicion). ``hit`` is a policy-relevant triggered
        result. ``suspicion`` is the strongest sub-threshold result, if any;
        the loop uses it to schedule a fast zoomed follow-up scan.
        """
        scan_started = time.monotonic()
        if img is None:
            img = capture_all_monitors()
        capture_ms = (time.monotonic() - scan_started) * 1000.0
        stat = ImageStat.Stat(img.resize((1, 1)))
        mean = tuple(round(v, 1) for v in stat.mean)
        sensitivity = self._current_sensitivity()
        anime_enabled = self._anime_detection_enabled()
        suspicion: Optional[DetectionResult] = None
        hit: Optional[DetectionResult] = None
        timings = [f"capture={capture_ms:.0f}ms"]
        for det in self.detectors:
            if getattr(det, "name", "") == "anime_nsfw":
                if not anime_enabled:
                    continue
                if profile == "targeted":
                    # The anime classifier is the heaviest model; it runs on
                    # full sweeps only so the sustained cadence stays cheap.
                    continue
            det_started = time.monotonic()
            if getattr(det, "accepts_scan_hints", False):
                res = det.scan(
                    img,
                    profile=profile,
                    changed_box=changed_box,
                    zoom_region=zoom_region,
                )
            else:
                res = det.scan(img)
            res = self._apply_anime_mode(res)
            timings.append(f"{getattr(det, 'name', '?')}={(time.monotonic() - det_started) * 1000.0:.0f}ms")
            _log.info(
                "scan: detector=%s triggered=%s severity=%s conf=%.2f label=%s region=%s",
                res.detector,
                res.triggered,
                res.severity,
                res.confidence,
                res.label,
                res.region,
            )
            if not res.triggered and res.severity != "none":
                if suspicion is None or res.confidence > suspicion.confidence:
                    suspicion = res
            if res.triggered and res.severity == "hard":
                hit = res
                break
            if res.triggered and res.severity == "context" and sensitivity in ("balanced", "strict"):
                hit = res
                break
        _log.info(
            "scan timing: %s total=%.0fms reason=%s profile=%s zoom=%s size=%sx%s mean_rgb=%s suspicion=%s hit=%s",
            " ".join(timings),
            (time.monotonic() - scan_started) * 1000.0,
            reason or "manual",
            profile,
            zoom_region or "-",
            img.width,
            img.height,
            mean,
            suspicion.label if suspicion else "none",
            hit.label if hit else "none",
        )
        return hit, suspicion

    def run_forever(self) -> None:
        sustained = min(float(self.settings.scan_interval_seconds), SUSTAINED_SCAN_SECONDS)
        if is_test_mode():
            sustained = 1.0
        pacer = FramePacer(sustained_scan_seconds=sustained)
        _log.info(
            "Watcher starting: tick-driven, sustained_scan=%.1fs test_mode=%s",
            sustained,
            is_test_mode(),
        )
        spawn_resume_lockout_if_needed("watcher-start")

        pending_zoom: Optional[str] = None  # region to zoom-confirm next tick
        confirm_streak = 0
        last_probation_at = 0.0
        last_window_sig: Optional[tuple] = None
        last_virtual_screen = None

        while True:
            if not self._state_says_run():
                pending_zoom = None
                confirm_streak = 0
                time.sleep(t(3, 1))
                continue

            now = time.monotonic()
            if now < self._lockout_until:
                pending_zoom = None
                confirm_streak = 0
                time.sleep(min(5.0, max(0.5, self._lockout_until - now)))
                continue

            if now - last_probation_at >= HOUSEKEEPING_SECONDS:
                last_probation_at = now
                self._probation_penalty_seconds()

            defer_seconds = self.scan_environment.defer_seconds()
            if defer_seconds > 0:
                time.sleep(min(defer_seconds, 0.5))
                continue
            snapshot = self.scan_environment.last_snapshot

            # A new foreground window or page title means new content: look
            # right away instead of waiting for the pixel diff to notice.
            window_changed = False
            if snapshot is not None:
                window_sig = (snapshot.hwnd, snapshot.title)
                window_changed = last_window_sig is not None and window_sig != last_window_sig
                last_window_sig = window_sig
                if last_virtual_screen not in (None, snapshot.virtual_screen):
                    reset_capture_handle()
                last_virtual_screen = snapshot.virtual_screen

            try:
                img = capture_all_monitors()
            except Exception as e:
                _log.warning("capture failed, retrying: %s", e)
                reset_capture_handle()
                time.sleep(1.0)
                continue

            force_confirm = pending_zoom is not None
            decision = pacer.observe(
                img,
                now=time.monotonic(),
                force_scan=force_confirm or window_changed,
                force_reason="confirm" if force_confirm else "window",
            )

            hit: Optional[DetectionResult] = None
            suspicion: Optional[DetectionResult] = None
            if decision.scan:
                zoom = pending_zoom or ""
                pending_zoom = None
                try:
                    hit, suspicion = self._scan_once(
                        img,
                        profile=decision.sweep,
                        changed_box=decision.changed_box,
                        zoom_region=zoom,
                        reason=decision.reason,
                    )
                except Exception as e:
                    _log.exception("scan_once raised: %s", e)

                wants_confirm = False
                confirm_region = ""
                if hit:
                    wants_confirm = self._handle_detection(hit)
                    confirm_region = hit.region
                elif suspicion is not None and self._current_sensitivity() in ("balanced", "strict"):
                    # Something landed below the trigger thresholds. Zoom into
                    # that region next tick: small/zoomed-out content usually
                    # crosses the threshold at double resolution.
                    wants_confirm = True
                    confirm_region = suspicion.region

                if (
                    wants_confirm
                    and confirm_streak < FAST_RESCAN_MAX_STREAK
                    and time.monotonic() >= self._lockout_until
                ):
                    confirm_streak += 1
                    pending_zoom = confirm_region or ""
                    _log.info(
                        "zoom confirmation armed: region=%s streak=%d/%d",
                        confirm_region or "-",
                        confirm_streak,
                        FAST_RESCAN_MAX_STREAK,
                    )
                elif hit is None and suspicion is None:
                    confirm_streak = 0

            tick = decision.tick_seconds
            if snapshot is not None and snapshot.share_sensitive:
                tick = max(tick, 1.0)
            time.sleep(tick)
