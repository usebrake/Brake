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
    "MALE_GENITALIA_EXPOSED": 0.45,
    "FEMALE_GENITALIA_EXPOSED": 0.45,
    "ANUS_EXPOSED": 0.50,
}
CONTEXT_THRESHOLDS = {
    "FEMALE_BREAST_EXPOSED": 0.75,
    "BUTTOCKS_EXPOSED": 0.75,
}
CONTEXT_SOFT_THRESHOLD = 0.65
# Below the hard thresholds but high enough to be worth a fast follow-up scan.
HARD_SUSPICION_THRESHOLD = 0.35
# Image-search result grids show many small explicit thumbnails at once. Each
# one downsamples to a low score, but several simultaneous low-score findings
# in the same region is strong evidence. Counts findings at or above the
# suspicion/soft thresholds.
MULTI_FINDING_MIN_COUNT = 3


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
        self._detector = NudeDetector()
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
                boxes.extend([
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
                ])

        if changed_box is not None:
            clamped = self._pad_and_clamp(changed_box, size)
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
        return findings

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

        hard_class = ""
        hard_score = 0.0
        hard_region = ""
        context_class = ""
        context_score = 0.0
        context_region = ""
        soft_context_class = ""
        soft_context_score = 0.0
        soft_context_region = ""
        hard_suspect_class = ""
        hard_suspect_score = 0.0
        hard_suspect_region = ""
        region_counts: dict[str, int] = {}
        region_best: dict[str, float] = {}
        for f in findings:
            cls = f.get("class", "")
            score = float(f.get("score", 0.0))
            region = str(f.get("_region", "full"))
            hard_threshold = HARD_THRESHOLDS.get(cls)
            context_threshold = CONTEXT_THRESHOLDS.get(cls)
            counts_toward_multi = (
                (hard_threshold is not None and score >= HARD_SUSPICION_THRESHOLD)
                or (context_threshold is not None and score >= CONTEXT_SOFT_THRESHOLD)
            )
            if counts_toward_multi:
                region_counts[region] = region_counts.get(region, 0) + 1
                region_best[region] = max(region_best.get(region, 0.0), score)

            if hard_threshold is not None:
                if score >= hard_threshold and score > hard_score:
                    hard_class = cls
                    hard_score = score
                    hard_region = region
                elif score >= HARD_SUSPICION_THRESHOLD and score > hard_suspect_score:
                    hard_suspect_class = cls
                    hard_suspect_score = score
                    hard_suspect_region = region
                continue

            if context_threshold is not None:
                if score >= context_threshold and score > context_score:
                    context_class = cls
                    context_score = score
                    context_region = region
                elif score >= CONTEXT_SOFT_THRESHOLD and score > soft_context_score:
                    soft_context_class = cls
                    soft_context_score = score
                    soft_context_region = region

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
        multi_region = ""
        for region, count in region_counts.items():
            if count >= MULTI_FINDING_MIN_COUNT and (
                not multi_region or region_best[region] > region_best[multi_region]
            ):
                multi_region = region
        if multi_region:
            return DetectionResult(
                detector=self.name,
                triggered=True,
                confidence=region_best[multi_region],
                label=f"CONTEXT NUDITY (MULTIPLE/{multi_region})",
                severity="context",
                region=multi_region,
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
