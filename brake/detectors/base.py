"""Detector ABC + DetectionResult."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

from PIL import Image


@dataclass
class DetectionResult:
    detector: str            # "nudity" | "anime_nsfw"
    triggered: bool
    confidence: float        # 0..1, or hit-count normalized
    label: str = ""          # short tag for the lockout reason line
    severity: str = "none"   # "hard" | "context" | "none"
    region: str = ""         # scan region the winning finding came from
    details: Optional[str] = None  # debug-only; never persisted

    @classmethod
    def negative(cls, detector: str) -> "DetectionResult":
        return cls(detector=detector, triggered=False, confidence=0.0)


class Detector(ABC):
    name: str = "base"

    @abstractmethod
    def scan(self, image: Image.Image) -> DetectionResult: ...
