"""MOG2 background-subtraction tracker. Cheap, runs on Pi, but noisy on
front-facing webcams or scenes where everything moves a little. For real
people-counting use the `yolo` engine instead."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import cv2
import numpy as np

from ..config import TrackingConfig
from .line_crossing import LineCrossingDetector

log = logging.getLogger(__name__)


@dataclass
class _Mog2Track:
    track_id: int
    centroid: tuple[int, int]
    last_seen_frame: int


@dataclass
class CrossingTracker:
    """MOG2 + greedy centroid tracker + shared line-crossing detector."""

    cfg: TrackingConfig
    bg: cv2.BackgroundSubtractor = field(init=False)
    detector: LineCrossingDetector = field(init=False)
    tracks: dict[int, _Mog2Track] = field(default_factory=dict)
    next_id: int = 1
    frame_counter: int = 0

    def __post_init__(self) -> None:
        self.bg = cv2.createBackgroundSubtractorMOG2(
            history=500,
            varThreshold=self.cfg.var_threshold,
            detectShadows=False,
        )
        self.detector = LineCrossingDetector(line=self.cfg.line, cooldown_seconds=self.cfg.cooldown_seconds)

    def process(self, frame: np.ndarray) -> tuple[np.ndarray, list[str]]:
        self.frame_counter += 1

        # Downscale to target width
        h, w = frame.shape[:2]
        if w > self.cfg.downscale_width:
            scale = self.cfg.downscale_width / w
            frame = cv2.resize(frame, (self.cfg.downscale_width, int(h * scale)))

        # Background subtraction
        fg_mask = self.bg.apply(frame, learningRate=self.cfg.learning_rate)
        fg_mask = cv2.morphologyEx(fg_mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
        fg_mask = cv2.dilate(fg_mask, np.ones((5, 5), np.uint8), iterations=2)
        _, fg_mask = cv2.threshold(fg_mask, 200, 255, cv2.THRESH_BINARY)

        # Extract centroids
        contours, _ = cv2.findContours(fg_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        centroids: list[tuple[int, int]] = []
        for cnt in contours:
            if cv2.contourArea(cnt) < self.cfg.min_area:
                continue
            x, y, cw, ch = cv2.boundingRect(cnt)
            cx, cy = x + cw // 2, y + ch // 2
            centroids.append((cx, cy))
            cv2.rectangle(frame, (x, y), (x + cw, y + ch), (0, 200, 255), 2)

        crossings = self._update_tracks(centroids, frame)

        # Draw line
        ax, ay = self.cfg.line.a
        bx, by = self.cfg.line.b
        cv2.line(frame, (ax, ay), (bx, by), (255, 80, 80), 2)
        cv2.putText(frame, "MOG2", (10, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200, 200, 200), 1, cv2.LINE_AA)

        return frame, crossings

    def _update_tracks(self, detections: list[tuple[int, int]], frame: np.ndarray) -> list[str]:
        crossings: list[str] = []
        unmatched = set(self.tracks.keys())
        used: set[int] = set()
        for det in detections:
            best_id = None
            best_dist = self.cfg.max_distance
            for tid in unmatched:
                if tid in used:
                    continue
                t = self.tracks[tid]
                d = ((t.centroid[0] - det[0]) ** 2 + (t.centroid[1] - det[1]) ** 2) ** 0.5
                if d < best_dist:
                    best_dist = d
                    best_id = tid
            if best_id is not None:
                self._move_track(best_id, det, crossings)
                used.add(best_id)
            else:
                self._create_track(det)

        # Drop stale tracks
        stale = [tid for tid, t in self.tracks.items() if tid not in used and self.frame_counter - t.last_seen_frame > self.cfg.max_age_frames]
        for tid in stale:
            del self.tracks[tid]
            self.detector.forget(tid)

        # Annotate active tracks
        for t in self.tracks.values():
            cv2.circle(frame, t.centroid, 5, (0, 255, 0), -1)
            cv2.putText(frame, str(t.track_id), (t.centroid[0] + 6, t.centroid[1] - 6),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1, cv2.LINE_AA)

        return crossings

    def _create_track(self, centroid: tuple[int, int]) -> None:
        self.tracks[self.next_id] = _Mog2Track(
            track_id=self.next_id,
            centroid=centroid,
            last_seen_frame=self.frame_counter,
        )
        # Prime the line-crossing detector with initial side
        self.detector.update(self.next_id, centroid)
        self.next_id += 1

    def _move_track(self, tid: int, centroid: tuple[int, int], crossings: list[str]) -> None:
        t = self.tracks[tid]
        crossing = self.detector.update(tid, centroid)
        if crossing is not None:
            crossings.append(crossing)
            log.info("Crossing detected (mog2): %s (track %d)", crossing, tid)
        t.centroid = centroid
        t.last_seen_frame = self.frame_counter
