from __future__ import annotations

import logging
import queue
import threading
import time
from typing import Optional

import cv2

from ..config import TrackingConfig
from ..preview import PreviewServer
from .base import IngestFn
from .tracker_factory import build_tracker

log = logging.getLogger(__name__)


class WebcamSource:
    """macOS-friendly webcam source: thread reader with bounded queue, drops stale frames."""

    def __init__(self, index: int, tracking: TrackingConfig, preview: Optional[PreviewServer] = None):
        self.index = index
        self.tracking = tracking
        self.preview = preview

    def run(self, ingest: IngestFn, stop: threading.Event) -> None:
        cap = cv2.VideoCapture(self.index, cv2.CAP_AVFOUNDATION)
        if not cap.isOpened():
            log.error("Webcam %d failed to open (check macOS Camera permission)", self.index)
            return
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        cap.set(cv2.CAP_PROP_FPS, 15)

        frame_q: queue.Queue = queue.Queue(maxsize=1)

        def reader() -> None:
            while not stop.is_set():
                ok, frame = cap.read()
                if not ok:
                    time.sleep(0.05)
                    continue
                # Drop any pending stale frame
                try:
                    while True:
                        frame_q.get_nowait()
                except queue.Empty:
                    pass
                frame_q.put(frame)

        reader_thread = threading.Thread(target=reader, daemon=True, name="webcam-reader")
        reader_thread.start()
        log.info("Webcam source up (index=%d). First frame may take a moment due to permission prompt.", self.index)

        tracker = build_tracker(self.tracking)
        try:
            while not stop.is_set():
                try:
                    frame = frame_q.get(timeout=0.5)
                except queue.Empty:
                    continue
                annotated, crossings = tracker.process(frame)
                if self.preview is not None:
                    self.preview.push_frame(annotated)
                for direction in crossings:
                    ingest(direction)  # type: ignore[arg-type]
        finally:
            cap.release()
            reader_thread.join(timeout=1.0)
