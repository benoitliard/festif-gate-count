from __future__ import annotations

import logging
import threading
import time
from pathlib import Path

import cv2

from ..config import TrackingConfig
from .base import IngestFn
from .tracking import CrossingTracker

log = logging.getLogger(__name__)


class VideoFileSource:
    def __init__(self, path: str, loop: bool, tracking: TrackingConfig):
        self.path = Path(path)
        self.loop = loop
        self.tracking = tracking

    def run(self, ingest: IngestFn, stop: threading.Event) -> None:
        if not self.path.exists():
            log.error("Video file not found: %s", self.path)
            return
        tracker = CrossingTracker(self.tracking)
        cap = cv2.VideoCapture(str(self.path))
        fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
        delay = 1.0 / fps
        log.info("Video file source: %s (fps=%.1f, loop=%s)", self.path.name, fps, self.loop)

        try:
            while not stop.is_set():
                ok, frame = cap.read()
                if not ok:
                    if self.loop:
                        cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                        continue
                    break
                _, crossings = tracker.process(frame)
                for direction in crossings:
                    ingest(direction)  # type: ignore[arg-type]
                time.sleep(delay)
        finally:
            cap.release()
