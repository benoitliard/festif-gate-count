"""Factory that picks the right tracker engine based on TrackingConfig."""

from __future__ import annotations

from typing import Protocol, Tuple

import numpy as np

from ..config import TrackingConfig


class Tracker(Protocol):
    def process(self, frame: np.ndarray) -> Tuple[np.ndarray, list[str]]: ...


def build_tracker(cfg: TrackingConfig) -> Tracker:
    if cfg.engine == "yolo":
        from .yolo_tracker import YoloTracker

        return YoloTracker(cfg)
    if cfg.engine == "mog2":
        from .tracking import CrossingTracker

        return CrossingTracker(cfg)
    raise ValueError(f"Unknown tracking engine: {cfg.engine}")
