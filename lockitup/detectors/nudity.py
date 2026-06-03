"""NudeNet wrapper. Runs locally via onnxruntime, no network calls."""
from __future__ import annotations

import logging
from typing import List, Tuple

import numpy as np
from PIL import Image

from lockitup.config import NudityConfig
from lockitup.detectors.base import Detector, DetectionResult

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


class NudityDetector(Detector):
    name = "nudity"

    def __init__(self, config: NudityConfig) -> None:
        self.config = config
        self._detector = None  # lazy init — model load is slow

    def _ensure_loaded(self) -> None:
        if self._detector is not None:
            return
        from nudenet import NudeDetector  # lazy import
        _log.info("Loading NudeNet ONNX model (one-time)...")
        self._detector = NudeDetector()
        _log.info("NudeNet ready.")

    def _regions(self, image: Image.Image) -> List[Tuple[str, Image.Image]]:
        width, height = image.size
        regions: list[tuple[str, Image.Image]] = [("full", image)]
        if min(width, height) < 500:
            return regions

        # NudeNet runs at low input resolution. On a full desktop capture, a
        # video/image that does not fill the whole monitor can be downsampled
        # until explicit parts vanish. Scan overlapping tiles as well.
        half_w = max(1, width // 2)
        half_h = max(1, height // 2)
        video_w = max(1, int(width * 0.70))
        video_h = max(1, int(height * 0.70))
        video_x = max(0, (width - video_w) // 2)
        video_y = max(0, (height - video_h) // 2)
        boxes = [
            ("top_left", (0, 0, half_w, half_h)),
            ("top_right", (width - half_w, 0, width, half_h)),
            ("bottom_left", (0, height - half_h, half_w, height)),
            ("bottom_right", (width - half_w, height - half_h, width, height)),
            ("video_center", (video_x, video_y, video_x + video_w, video_y + video_h)),
            ("center", (
                max(0, (width - half_w) // 2),
                max(0, (height - half_h) // 2),
                min(width, (width + half_w) // 2),
                min(height, (height + half_h) // 2),
            )),
        ]
        for name, box in boxes:
            regions.append((name, image.crop(box)))
        return regions

    def _detect_region(self, region_name: str, image: Image.Image) -> List[dict]:
        assert self._detector is not None
        arr = np.array(image)
        findings = self._detector.detect(arr)
        for finding in findings:
            finding["_region"] = region_name
        return findings

    def scan(self, image: Image.Image) -> DetectionResult:
        if not self.config.enabled:
            return DetectionResult.negative(self.name)

        self._ensure_loaded()
        findings: list[dict] = []
        try:
            for region_name, region_img in self._regions(image):
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
        context_class = ""
        context_score = 0.0
        soft_context_class = ""
        soft_context_score = 0.0
        for f in findings:
            cls = f.get("class", "")
            score = float(f.get("score", 0.0))
            hard_threshold = HARD_THRESHOLDS.get(cls)
            if hard_threshold is not None and score >= hard_threshold and score > hard_score:
                hard_class = cls
                hard_score = score
                continue

            context_threshold = CONTEXT_THRESHOLDS.get(cls)
            if context_threshold is not None:
                if score >= context_threshold and score > context_score:
                    context_class = cls
                    context_score = score
                elif score >= CONTEXT_SOFT_THRESHOLD and score > soft_context_score:
                    soft_context_class = cls
                    soft_context_score = score

        if hard_class:
            return DetectionResult(
                detector=self.name,
                triggered=True,
                confidence=hard_score,
                label=f"EXPLICIT ({hard_class})",
                severity="hard",
            )
        if context_class:
            return DetectionResult(
                detector=self.name,
                triggered=True,
                confidence=context_score,
                label=f"CONTEXT NUDITY ({context_class})",
                severity="context",
            )
        if soft_context_class:
            return DetectionResult(
                detector=self.name,
                triggered=False,
                confidence=soft_context_score,
                label=f"CONTEXT NUDITY ({soft_context_class})",
                severity="context",
            )
        return DetectionResult.negative(self.name)
