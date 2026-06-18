"""NudeNet wrapper. Runs locally via onnxruntime, no network calls."""
from __future__ import annotations

import logging
from typing import Dict, List, Optional, Tuple

import numpy as np
from PIL import Image

from brake.config import NudityConfig
from brake.detectors.base import Detector, DetectionResult

_log = logging.getLogger(__name__)

HARD_THRESHOLDS = {
    "MALE_GENITALIA_EXPOSED": 0.55,
    "FEMALE_GENITALIA_EXPOSED": 0.55,
    "ANUS_EXPOSED": 0.60,
}
# A hard finding below this confidence is only trusted when another exposed
# body part is detected in the same region (anatomical agreement). Game
# characters, skin-toned UI, and render noise produce isolated low-score
# genital boxes; real explicit imagery almost always detects several body
# parts together or scores high on its own.
# Solo hard findings need more confidence than the model's raw trigger
# threshold. Male-genital false positives are especially common in clothed
# talking-head scenes, so they get a higher solo bar while still allowing fast
# lockouts when there is anatomical agreement.
HARD_SOLO_CONFIDENCE = 0.78
HARD_SOLO_CONFIDENCE_BY_CLASS = {
    "MALE_GENITALIA_EXPOSED": 0.82,
    "FEMALE_GENITALIA_EXPOSED": 0.78,
    "ANUS_EXPOSED": 0.82,
}
FACE_CLASSES = {"FACE_MALE", "FACE_FEMALE"}
FACE_DOMINANT_MIN_SCORE = 0.65
FACE_DOMINANT_MALE_GENITALIA_SOLO_CONFIDENCE = 0.90
CORROBORATION_MIN_SCORE = 0.45
CORROBORATION_CLASSES = {
    "MALE_GENITALIA_EXPOSED",
    "FEMALE_GENITALIA_EXPOSED",
    "ANUS_EXPOSED",
    "FEMALE_BREAST_EXPOSED",
    "BUTTOCKS_EXPOSED",
    "BELLY_EXPOSED",
}
CONTEXT_THRESHOLDS = {
    "FEMALE_BREAST_EXPOSED": 0.75,
    "BUTTOCKS_EXPOSED": 0.75,
}
CONTEXT_SOFT_THRESHOLD = 0.65
# Below the hard thresholds but high enough to be worth a fast follow-up scan.
HARD_SUSPICION_THRESHOLD = 0.45
# Several simultaneous weak findings in one region (e.g. a thumbnail grid) is
# worth a zoomed verification pass, but it is NOT proof by itself: busy game
# frames also produce clusters of weak boxes. The multi rule therefore only
# raises suspicion; the zoomed pass must find a real trigger.
MULTI_FINDING_MIN_COUNT = 3
# Findings with implausible box geometry never trigger on their own. Tiny
# boxes are icons/specks; extreme aspect ratios are edges and UI slivers.
# They still count as suspicion so the zoom pass can take a closer look.
MIN_BOX_AREA_FRACTION = 0.003
MIN_BOX_ASPECT = 0.25
MAX_BOX_ASPECT = 4.0


Box = Tuple[int, int, int, int]

# Crops smaller than this are upscale noise, not signal.
_MIN_REGION_PX = 48
# A changed-area crop narrower than this fraction of the screen gets padded
# out, so a thin scroll strip still carries some context.
_MIN_CHANGED_FRACTION = 0.15


class NudityDetector(Detector):
    name = "nudity"
    # Watcher may pass profile/changed_box/zoom_region keyword hints.
    accepts_scan_hints = True

    def __init__(self, config: NudityConfig) -> None:
        self.config = config
        self._detector = None  # lazy init — model load is slow
        # Region name -> box from the most recent scan, used to zoom into a
        # suspect region on the confirmation pass.
        self._last_boxes: Dict[str, Box] = {}

    def _ensure_loaded(self) -> None:
        if self._detector is not None:
            return
        from nudenet import NudeDetector  # lazy import
        _log.info("Loading NudeNet ONNX model (one-time)...")
        # Cap ONNX intra-op threads while building the session. The 320px
        # model gains almost nothing from wide parallelism (measured: 240ms
        # vs 245ms per sweep) but unlimited threads burn ~3.5x the CPU time
        # and battery. Two threads is the efficiency sweet spot.
        ort = None
        original_session = None
        try:
            import onnxruntime as ort_module

            ort = ort_module
            options = ort.SessionOptions()
            options.intra_op_num_threads = 2
            options.inter_op_num_threads = 1
            original_session = ort.InferenceSession

            def _capped_session(*args, **kwargs):
                if len(args) <= 1 and "sess_options" not in kwargs:
                    kwargs["sess_options"] = options
                return original_session(*args, **kwargs)

            ort.InferenceSession = _capped_session
        except Exception as e:
            _log.warning("could not cap ONNX threads (%s); using defaults.", e)
        try:
            self._detector = NudeDetector()
        finally:
            if ort is not None and original_session is not None:
                ort.InferenceSession = original_session
        _log.info("NudeNet ready.")

    def _region_boxes(
        self,
        size: Tuple[int, int],
        profile: str,
        changed_box: Optional[Box],
        zoom_region: str,
    ) -> List[Tuple[str, Box]]:
        width, height = size
        boxes: list[tuple[str, Box]] = [("full", (0, 0, width, height))]
        tileable = min(width, height) >= 500

        clamped = None
        if changed_box is not None:
            clamped = self._pad_and_clamp(changed_box, size)

        if tileable:
            half_w = max(1, width // 2)
            half_h = max(1, height // 2)
            video_w = max(1, int(width * 0.70))
            video_h = max(1, int(height * 0.70))
            video_x = max(0, (width - video_w) // 2)
            video_y = max(0, (height - video_h) // 2)
            video_box = (video_x, video_y, video_x + video_w, video_y + video_h)
            if profile == "targeted":
                # Budget profile for sustained-change cadence (video playing):
                # the full frame plus the typical video area. The changed-area
                # crop below covers where the action actually is.
                boxes.append(("video_center", video_box))
            else:
                # NudeNet runs at low input resolution. On a full desktop
                # capture, a video/image that does not fill the whole monitor
                # can be downsampled until explicit parts vanish. Scan
                # overlapping tiles as well.
                tiles = [
                    ("top_left", (0, 0, half_w, half_h)),
                    ("top_right", (width - half_w, 0, width, half_h)),
                    ("bottom_left", (0, height - half_h, half_w, height)),
                    ("bottom_right", (width - half_w, height - half_h, width, height)),
                    ("video_center", video_box),
                    ("center", (
                        max(0, (width - half_w) // 2),
                        max(0, (height - half_h) // 2),
                        min(width, (width + half_w) // 2),
                        min(height, (height + half_h) // 2),
                    )),
                ]
                if clamped is not None:
                    # When we know where the screen changed, unchanged tiles
                    # carry the same pixels they had at the last sweep and
                    # would return the same verdict. Skipping them saves most
                    # of the inference cost; the periodic safety sweep (no
                    # changed box) still covers everything.
                    tiles = [t for t in tiles if self._boxes_intersect(t[1], clamped)]
                boxes.extend(tiles)

        if clamped is not None:
            boxes.append(("changed", clamped))

        if zoom_region:
            parent = self._last_boxes.get(zoom_region)
            if parent is not None:
                # Zoom pass: split the suspect region into quadrants so small
                # content (thumbnails, zoomed-out pages) is seen at roughly
                # double the effective resolution. Region names chain, so a
                # second confirmation can zoom in another level.
                boxes.extend(self._quadrants(zoom_region, parent))

        return boxes

    @staticmethod
    def _boxes_intersect(a: Box, b: Box) -> bool:
        return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]

    @staticmethod
    def _pad_and_clamp(box: Box, size: Tuple[int, int]) -> Optional[Box]:
        width, height = size
        left, top, right, bottom = box
        min_w = int(width * _MIN_CHANGED_FRACTION)
        min_h = int(height * _MIN_CHANGED_FRACTION)
        if right - left < min_w:
            pad = (min_w - (right - left)) // 2 + 1
            left, right = left - pad, right + pad
        if bottom - top < min_h:
            pad = (min_h - (bottom - top)) // 2 + 1
            top, bottom = top - pad, bottom + pad
        left = max(0, int(left))
        top = max(0, int(top))
        right = min(width, int(right))
        bottom = min(height, int(bottom))
        if right - left < _MIN_REGION_PX or bottom - top < _MIN_REGION_PX:
            return None
        return (left, top, right, bottom)

    @staticmethod
    def _quadrants(parent_name: str, box: Box) -> List[Tuple[str, Box]]:
        left, top, right, bottom = box
        mid_x = (left + right) // 2
        mid_y = (top + bottom) // 2
        if mid_x - left < _MIN_REGION_PX or mid_y - top < _MIN_REGION_PX:
            return []
        return [
            (f"{parent_name}~q0", (left, top, mid_x, mid_y)),
            (f"{parent_name}~q1", (mid_x, top, right, mid_y)),
            (f"{parent_name}~q2", (left, mid_y, mid_x, bottom)),
            (f"{parent_name}~q3", (mid_x, mid_y, right, bottom)),
        ]

    def _regions(
        self,
        image: Image.Image,
        profile: str = "full",
        changed_box: Optional[Box] = None,
        zoom_region: str = "",
    ) -> List[Tuple[str, Image.Image]]:
        named_boxes = self._region_boxes(image.size, profile, changed_box, zoom_region)
        self._last_boxes = dict(named_boxes)
        regions: list[tuple[str, Image.Image]] = []
        for name, box in named_boxes:
            if box == (0, 0, image.width, image.height):
                regions.append((name, image))
            else:
                regions.append((name, image.crop(box)))
        return regions

    def _detect_region(self, region_name: str, image: Image.Image) -> List[dict]:
        assert self._detector is not None
        arr = np.array(image)
        findings = self._detector.detect(arr)
        for finding in findings:
            finding["_region"] = region_name
            finding["_region_size"] = image.size
        return findings

    @staticmethod
    def _geometry_ok(finding: dict) -> bool:
        """Plausibility check on the detection box.

        Findings without box data (tests, older nudenet) pass by default.
        """
        box = finding.get("box")
        size = finding.get("_region_size")
        if not box or not size:
            return True
        try:
            w = float(box[2])
            h = float(box[3])
            region_w, region_h = float(size[0]), float(size[1])
        except (IndexError, TypeError, ValueError):
            return True
        if w <= 0 or h <= 0 or region_w <= 0 or region_h <= 0:
            return False
        if (w * h) / (region_w * region_h) < MIN_BOX_AREA_FRACTION:
            return False
        aspect = w / h
        return MIN_BOX_ASPECT <= aspect <= MAX_BOX_ASPECT

    @staticmethod
    def _related_regions(region: str) -> set[str]:
        names = {region, "full"}
        current = region
        while "~" in current:
            current = current.rsplit("~", 1)[0]
            names.add(current)
        if region.startswith("video_center"):
            names.add("video_center")
        if region.startswith("changed"):
            names.add("changed")
        return names

    @classmethod
    def _solo_confidence_for(
        cls,
        class_name: str,
        region: str,
        face_best_by_region: dict[str, float],
    ) -> float:
        threshold = HARD_SOLO_CONFIDENCE_BY_CLASS.get(class_name, HARD_SOLO_CONFIDENCE)
        if class_name == "MALE_GENITALIA_EXPOSED":
            face_score = max(
                (face_best_by_region.get(name, 0.0) for name in cls._related_regions(region)),
                default=0.0,
            )
            if face_score >= FACE_DOMINANT_MIN_SCORE:
                threshold = max(threshold, FACE_DOMINANT_MALE_GENITALIA_SOLO_CONFIDENCE)
        return threshold

    def scan(
        self,
        image: Image.Image,
        *,
        profile: str = "full",
        changed_box: Optional[Box] = None,
        zoom_region: str = "",
    ) -> DetectionResult:
        if not self.config.enabled:
            return DetectionResult.negative(self.name)

        self._ensure_loaded()
        findings: list[dict] = []
        try:
            for region_name, region_img in self._regions(
                image, profile=profile, changed_box=changed_box, zoom_region=zoom_region
            ):
                findings.extend(self._detect_region(region_name, region_img))
        except Exception as e:
            _log.error("NudeNet scan failed: %s", e)
            return DetectionResult.negative(self.name)

        if findings:
            top = sorted(findings, key=lambda f: float(f.get("score", 0.0)), reverse=True)[:8]
            _log.info(
                "NudeNet findings: %s",
                ", ".join(
                    f"{f.get('_region', '?')}/{f.get('class', '')}:{float(f.get('score', 0.0)):.2f}"
                    for f in top
                ),
            )
        else:
            _log.info("NudeNet findings: none")

        context_class = ""
        context_score = 0.0
        context_region = ""
        soft_context_class = ""
        soft_context_score = 0.0
        soft_context_region = ""
        hard_suspect_class = ""
        hard_suspect_score = 0.0
        hard_suspect_region = ""
        hard_candidates: list[tuple[float, str, str]] = []  # (score, class, region)
        corroboration_classes: dict[str, set[str]] = {}
        face_best_by_region: dict[str, float] = {}
        region_counts: dict[str, int] = {}
        region_best: dict[str, float] = {}
        for f in findings:
            cls = f.get("class", "")
            score = float(f.get("score", 0.0))
            region = str(f.get("_region", "full"))
            eligible = self._geometry_ok(f)
            hard_threshold = HARD_THRESHOLDS.get(cls)
            context_threshold = CONTEXT_THRESHOLDS.get(cls)

            if cls in FACE_CLASSES and score > face_best_by_region.get(region, 0.0):
                face_best_by_region[region] = score

            if (
                eligible
                and cls in CORROBORATION_CLASSES
                and score >= CORROBORATION_MIN_SCORE
            ):
                corroboration_classes.setdefault(region, set()).add(cls)

            counts_toward_multi = (
                (hard_threshold is not None and score >= HARD_SUSPICION_THRESHOLD)
                or (context_threshold is not None and score >= CONTEXT_SOFT_THRESHOLD)
            )
            if counts_toward_multi:
                region_counts[region] = region_counts.get(region, 0) + 1
                region_best[region] = max(region_best.get(region, 0.0), score)

            if hard_threshold is not None:
                if eligible and score >= hard_threshold:
                    hard_candidates.append((score, cls, region))
                elif score >= HARD_SUSPICION_THRESHOLD and score > hard_suspect_score:
                    hard_suspect_class = cls
                    hard_suspect_score = score
                    hard_suspect_region = region
                continue

            if context_threshold is not None:
                if eligible and score >= context_threshold and score > context_score:
                    context_class = cls
                    context_score = score
                    context_region = region
                elif score >= CONTEXT_SOFT_THRESHOLD and score > soft_context_score:
                    soft_context_class = cls
                    soft_context_score = score
                    soft_context_region = region

        # A hard candidate triggers only with solo-high confidence or
        # anatomical agreement (a second exposed-class finding in the same
        # region). Everything else is demoted to suspicion for the zoom pass.
        hard_class = ""
        hard_score = 0.0
        hard_region = ""
        for score, cls, region in sorted(hard_candidates, reverse=True):
            corroborated = len(corroboration_classes.get(region, set())) >= 2
            solo_confidence = self._solo_confidence_for(cls, region, face_best_by_region)
            if score >= solo_confidence or corroborated:
                hard_class, hard_score, hard_region = cls, score, region
                break
            if score > hard_suspect_score:
                _log.info(
                    "hard finding demoted to suspicion (uncorroborated solo): %s %.2f in %s threshold=%.2f",
                    cls, score, region, solo_confidence,
                )
                hard_suspect_class, hard_suspect_score, hard_suspect_region = cls, score, region

        if hard_class:
            return DetectionResult(
                detector=self.name,
                triggered=True,
                confidence=hard_score,
                label=f"EXPLICIT ({hard_class})",
                severity="hard",
                region=hard_region,
            )
        if context_class:
            return DetectionResult(
                detector=self.name,
                triggered=True,
                confidence=context_score,
                label=f"CONTEXT NUDITY ({context_class})",
                severity="context",
                region=context_region,
            )
        # Non-triggered results below are suspicion only: the watcher uses them
        # to schedule a fast zoomed follow-up scan, never to lock.
        if hard_suspect_class:
            return DetectionResult(
                detector=self.name,
                triggered=False,
                confidence=hard_suspect_score,
                label=f"SUSPECT ({hard_suspect_class})",
                severity="hard",
                region=hard_suspect_region,
            )
        multi_region = ""
        for region, count in region_counts.items():
            if count >= MULTI_FINDING_MIN_COUNT and (
                not multi_region or region_best[region] > region_best[multi_region]
            ):
                multi_region = region
        if multi_region:
            return DetectionResult(
                detector=self.name,
                triggered=False,
                confidence=region_best[multi_region],
                label=f"CONTEXT NUDITY (MULTIPLE/{multi_region})",
                severity="context",
                region=multi_region,
            )
        if soft_context_class:
            return DetectionResult(
                detector=self.name,
                triggered=False,
                confidence=soft_context_score,
                label=f"CONTEXT NUDITY ({soft_context_class})",
                severity="context",
                region=soft_context_region,
            )
        return DetectionResult.negative(self.name)
