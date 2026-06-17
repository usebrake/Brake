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
from brake.detection_events import append_detection_event
from brake.detectors.anime_nsfw import AnimeNSFWDetector
from brake.detectors.base import DetectionResult, Detector
from brake.detectors.nudity import NudityDetector
from brake.incident_memory import IncidentLedger
from brake.lockout.persistence import LockoutPersistence, _TamperedLockoutError
from brake.lockout.recovery import spawn_resume_lockout_if_needed
from brake.runtime import lockout_command
from brake.service.scan_environment import ScanEnvironmentMonitor
from brake.service.scan_pacer import FramePacer, SUSTAINED_SCAN_SECONDS
from brake.state import StateStore, StateTamperedError
from brake.state.recovery_unlock import apply_due_recovery_unlock
from brake.state.schema import LOCKOUT_DURATION_DEFAULT
from brake.test_mode import is_test_mode, t

_log = logging.getLogger(__name__)

TEST_MODE_LOCKOUT_SECONDS = 10

# How many back-to-back zoom confirmations a suspicion streak may trigger
# before the loop falls back to the pacer's normal cadence. Bounds CPU on
# persistently borderline screens; the streak resets after the next clean scan.
FAST_RESCAN_MAX_STREAK = 2
# How often slow housekeeping (state file read) runs. The tick loop itself is
# much faster than this.
HOUSEKEEPING_SECONDS = 2.0
# How often the battery state is re-checked to toggle power-saver pacing.
POWER_CHECK_SECONDS = 30.0
DETECTION_EVENT_DEDUPE_SECONDS = 20.0
# Hard explicit video can flicker between labels/frames. A single lower-score
# genital/anus hit arms a short strike window; a second hard hit confirms.
HARD_CONFIRM_WINDOW = t(18, 6)
# A single uncorroborated frame causing an instant shutdown lockout must be
# near-certain. Real content below this still locks within ~1s via the
# strike + zoom confirmation path.
HARD_IMMEDIATE_CONFIDENCE = 0.90
ANIME_EXPLICIT_CONFIDENCE = 0.90


def _ordinal(n: int) -> str:
    n = max(1, int(n))
    if 10 <= (n % 100) <= 20:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def _format_minutes(seconds: int) -> str:
    minutes = max(1, int(round(int(seconds) / 60)))
    return f"{minutes} minute" if minutes == 1 else f"{minutes} minutes"


def _lockout_message(incident_number: int, duration_seconds: int, shutdown_on_done: bool) -> str:
    ordinal = _ordinal(incident_number)
    duration = _format_minutes(duration_seconds)
    consequence = (
        "Your computer will shut down when this timer ends."
        if shutdown_on_done
        else "This window will close when the timer ends."
    )
    return (
        f"This is your {ordinal} full lockout in the last 24 hours. "
        f"Full lockout time: {duration}. {consequence}"
    )


def _build_detectors(settings: Settings) -> List[Detector]:
    return [
        NudityDetector(settings.nudity),
        AnimeNSFWDetector(settings.nudity),
    ]


def _window_scan_signature(snapshot) -> tuple:
    # Deliberately excludes title text. Browser/media titles can churn while
    # the same surface remains active; pixel diffing catches actual content.
    return (snapshot.hwnd, snapshot.process_name, snapshot.window_rect)


def _running_on_battery() -> bool:
    try:
        import psutil

        battery = psutil.sensors_battery()
        return bool(battery and not battery.power_plugged)
    except Exception:
        return False


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
    def __init__(
        self,
        store: Optional[StateStore] = None,
        incidents: Optional[IncidentLedger] = None,
        lockouts: Optional[LockoutPersistence] = None,
    ) -> None:
        self.store = store or StateStore()
        self.settings = load_settings()
        self.detectors = _build_detectors(self.settings)
        self.incidents = incidents or IncidentLedger()
        self.lockouts = lockouts or LockoutPersistence()
        self._lockout_until = 0.0
        self._last_hard_pending_label = ""
        self._last_hard_pending_at = 0.0
        self._hard_strike_count = 0
        self.scan_environment = ScanEnvironmentMonitor()
        self._state_cached_at = 0.0
        self._state_cache: Optional[tuple] = None  # (state, fail_secure)
        self._last_detection_event_at: dict[tuple[str, str, str, str, str], float] = {}

    def _load_state(self) -> tuple:
        """Return (state, fail_secure).

        state is None in two very different situations:
        - fail_secure False: no state has ever been created (fresh install
          before first-run setup). There is nothing to protect, so the
          watcher must NOT capture the screen.
        - fail_secure True: the state exists but cannot be trusted
          (tampered, deleted after initialization, or unreadable). Treat
          protection as enabled so deleting/corrupting files is not an off
          switch.
        """
        # The tick loop asks for state several times per second; reading and
        # HMAC-verifying the state file that often is wasted work. A short
        # cache keeps the loop cheap while staying responsive to toggles.
        now = time.monotonic()
        if self._state_cache is not None and (now - self._state_cached_at) < HOUSEKEEPING_SECONDS:
            return self._state_cache
        try:
            s = self.store.load()
            if s is not None:
                s = apply_due_recovery_unlock(self.store, s)
            result = (s, False)
        except StateTamperedError:
            _log.critical("State tampered. Fail-secure: assume enabled.")
            result = (None, True)
        except Exception as e:
            # StateMissingError, corrupt JSON, transient IO errors. Never let
            # a bad state file crash the loop into a respawn cycle.
            _log.critical("State unreadable (%s). Fail-secure: assume enabled.", e)
            result = (None, True)
        self._state_cache = result
        self._state_cached_at = now
        return result

    def _current_state(self):
        return self._load_state()[0]

    def _state_says_run(self) -> bool:
        state, fail_secure = self._load_state()
        if state is not None:
            return state.enabled
        return fail_secure

    def _current_lockout_duration_seconds(self) -> int:
        if is_test_mode():
            return TEST_MODE_LOCKOUT_SECONDS
        s = self._current_state()
        if s is None:
            return LOCKOUT_DURATION_DEFAULT * 60
        return s.lockout_duration_seconds()

    def _anime_detection_enabled(self) -> bool:
        s = self._current_state()
        if s is None:
            return False
        return bool(getattr(s, "anime_detection_enabled", False))

    def _shutdown_after_lockout(self) -> bool:
        s = self._current_state()
        if s is None:
            return True
        return bool(getattr(s, "shutdown_after_lockout", True))

    def _active_lockout_remaining(self, now: float) -> float:
        """Return seconds the watcher should pause for an active lockout.

        The lockout process owns the persistent timer. Recovery during lockout
        can shorten that timer and disable shutdown, so the watcher must not
        rely only on the original in-memory duration it set when spawning the
        lockout. Re-read the signed lockout record while paused so scanning
        resumes promptly after recovery completes.
        """
        if now >= self._lockout_until:
            return 0.0
        try:
            record = self.lockouts.resume()
        except _TamperedLockoutError:
            _log.critical("Active lockout record is tampered; keeping watcher paused fail-secure.")
            return max(0.5, self._lockout_until - now)
        except Exception as e:
            _log.warning("Could not read active lockout record while paused: %s", e)
            return max(0.5, self._lockout_until - now)

        if record is None or record.is_expired():
            try:
                self.lockouts.clear()
            except Exception:
                pass
            self._lockout_until = 0.0
            return 0.0

        remaining = record.remaining_seconds()
        self._lockout_until = now + remaining
        return remaining

    def _handle_detection(self, hit: DetectionResult, *, evidential: bool = True) -> bool:
        """Handle one hit. Return True when a fast confirmation scan should run.

        ``evidential`` is False for safety-sweep rescans of an unchanged
        screen: identical pixels re-scored by the same model add no new
        information, so they may arm pending strikes but never confirm one.
        """
        if hit.severity == "context":
            _log.info("context detection noted without lockout: label=%s", hit.label)
            return True

        return self._handle_hard(
            hit, fast_confirm=True, evidential=evidential
        )

    def _record_detection_event(
        self,
        result: DetectionResult,
        *,
        action: str,
        scan_reason: str,
        profile: str,
        zoom_region: str,
    ) -> None:
        if result.severity == "none" or not result.label:
            return
        now = time.monotonic()
        signature = (
            result.detector,
            result.severity,
            result.label,
            result.region,
            action,
        )
        last = self._last_detection_event_at.get(signature, 0.0)
        if now - last < DETECTION_EVENT_DEDUPE_SECONDS:
            return
        self._last_detection_event_at[signature] = now
        append_detection_event(
            result,
            action=action,
            scan_reason=scan_reason,
            profile=profile,
            zoom_region=zoom_region,
        )

    def _apply_anime_mode(self, result: DetectionResult) -> DetectionResult:
        if result.detector != "anime_nsfw" or not result.triggered:
            return result
        if result.confidence < ANIME_EXPLICIT_CONFIDENCE:
            return DetectionResult.negative(result.detector)
        return DetectionResult(
            detector=result.detector,
            triggered=True,
            confidence=result.confidence,
            label=result.label.replace("POSSIBLE", "EXPLICIT") if result.label else "EXPLICIT ILLUSTRATED",
            severity="hard",
            region=result.region,
        )

    def _handle_hard(
        self, hit: DetectionResult, *, fast_confirm: bool = False, evidential: bool = True
    ) -> bool:
        now = time.monotonic()
        label = hit.label or hit.detector.upper()
        if hit.detector != "anime_nsfw" and hit.confidence >= HARD_IMMEDIATE_CONFIDENCE and evidential:
            self._last_hard_pending_label = ""
            self._last_hard_pending_at = 0.0
            self._hard_strike_count = 0
            _log.warning("hard detection immediately confirmed: label=%s conf=%.2f", label, hit.confidence)
            self._apply_hard_lockout(hit)
            return False
        if not evidential and self._hard_strike_count >= 1:
            # Safety-sweep rescan of unchanged pixels: keep the pending strike
            # alive conceptually but do not let identical input confirm itself.
            _log.info("hard hit on unchanged screen not counted as confirmation: label=%s", label)
            return bool(fast_confirm)
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

    def _apply_hard_lockout(self, hit: DetectionResult, message: str = "") -> None:
        reason = hit.label or hit.detector.upper()
        prior_incidents = self.incidents.recent_count()
        self.incidents.record()

        base_duration = self._current_lockout_duration_seconds()
        duration = self.incidents.scale(base_duration, prior_incidents)
        shutdown_on_done = self._shutdown_after_lockout()
        message = message or _lockout_message(
            incident_number=prior_incidents + 1,
            duration_seconds=duration,
            shutdown_on_done=shutdown_on_done,
        )
        if duration != base_duration:
            _log.warning(
                "Incident memory scaled lockout: base=%ds prior=%d duration=%ds",
                base_duration,
                prior_incidents,
                duration,
            )
        _spawn_lockout(
            duration,
            reason,
            message=message,
            shutdown_on_done=shutdown_on_done,
        )
        self._lockout_until = time.monotonic() + duration

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
        anime_enabled = self._anime_detection_enabled()
        suspicion: Optional[DetectionResult] = None
        hit: Optional[DetectionResult] = None
        timings = [f"capture={capture_ms:.0f}ms"]
        for det in self.detectors:
            if getattr(det, "name", "") == "anime_nsfw":
                if not anime_enabled:
                    continue
                if profile == "targeted" and not zoom_region:
                    # The anime classifier is the heaviest model; it runs on
                    # full sweeps only so the sustained cadence stays cheap.
                    # It still runs on targeted confirmation passes when a
                    # previous illustrated hit supplied a zoom region.
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
            if res.triggered and res.severity == "context":
                hit = res
                break
        for result, action in ((suspicion, "observed"), (hit, "detected")):
            if result is not None:
                self._record_detection_event(
                    result,
                    action=action,
                    scan_reason=reason or "manual",
                    profile=profile,
                    zoom_region=zoom_region,
                )
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
        last_power_check_at = 0.0
        last_window_sig: Optional[tuple] = None
        last_virtual_screen = None
        was_running = None  # tri-state so the first pass logs either way

        while True:
            if not self._state_says_run():
                if was_running is not False:
                    was_running = False
                    _log.info(
                        "Scanning paused: protection is disabled or not yet "
                        "set up. No screen capture while paused."
                    )
                pending_zoom = None
                confirm_streak = 0
                time.sleep(t(3, 1))
                continue
            if was_running is not True:
                was_running = True
                _log.info("Scanning active: protection is enabled.")

            now = time.monotonic()
            lockout_remaining = self._active_lockout_remaining(now)
            if lockout_remaining > 0:
                pending_zoom = None
                confirm_streak = 0
                time.sleep(min(5.0, max(0.5, lockout_remaining)))
                continue

            if now - last_power_check_at >= POWER_CHECK_SECONDS:
                last_power_check_at = now
                on_battery = _running_on_battery()
                if on_battery != pacer.power_saver:
                    pacer.power_saver = on_battery
                    _log.info(
                        "power profile: %s (repeat cadences %s)",
                        "battery" if on_battery else "plugged in",
                        "stretched 1.5x" if on_battery else "normal",
                    )

            defer_seconds = self.scan_environment.defer_seconds()
            if defer_seconds > 0:
                time.sleep(min(defer_seconds, 0.5))
                continue
            snapshot = self.scan_environment.last_snapshot

            # A new foreground window or page title means new content: look
            # right away instead of waiting for the pixel diff to notice.
            window_changed = False
            if snapshot is not None:
                window_sig = _window_scan_signature(snapshot)
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
                    # Periodic safety sweeps re-scan unchanged pixels; they
                    # may arm strikes/warnings but never confirm a lockout.
                    wants_confirm = self._handle_detection(
                        hit, evidential=(decision.reason != "periodic")
                    )
                    confirm_region = hit.region
                elif suspicion is not None:
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
            if snapshot is not None and snapshot.fullscreen:
                # Fewer captures while a fullscreen surface is up: each grab
                # is a compositor copy, and a grab landing on the exit
                # transition is what shows as a flash. Detection is
                # unaffected; fullscreen video is scanned on the sustained
                # cadence, which is slower than this tick anyway.
                tick = max(tick, 1.5)
            time.sleep(tick)
