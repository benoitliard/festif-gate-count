"""YOLOv8 + ByteTrack people tracker.

Uses ultralytics' built-in `model.track()` which wraps ByteTrack and gives
stable per-person track IDs. Much more accurate than MOG2 on real scenes
with crowds, occlusion, or moving cameras — at the cost of a heavier
dependency (`ultralytics`, ~2 GB once torch is in).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np

from ..config import TrackingConfig
from .line_crossing import LineCrossingDetector

log = logging.getLogger(__name__)


def _resolve_device(preferred: str | None) -> str:
    """Pick the best available device. Apple Silicon → mps, Nvidia → cuda, else cpu."""
    if preferred:
        return preferred
    try:
        import torch  # type: ignore

        if torch.backends.mps.is_available():
            return "mps"
        if torch.cuda.is_available():
            return "cuda"
    except Exception:
        pass
    return "cpu"


@dataclass
class YoloTracker:
    cfg: TrackingConfig
    detector: LineCrossingDetector = field(init=False)
    model: object = field(init=False)  # ultralytics.YOLO
    device: str = field(init=False)

    def __post_init__(self) -> None:
        try:
            from ultralytics import YOLO  # type: ignore
        except ImportError as exc:
            raise SystemExit(
                "YOLO engine requested but `ultralytics` not installed. "
                "Run: cd packages/gate-agent && uv pip install -e '.[yolo]'"
            ) from exc

        self.detector = LineCrossingDetector(
            line=self.cfg.line, cooldown_seconds=self.cfg.cooldown_seconds
        )
        self.device = _resolve_device(self.cfg.yolo_device)
        log.info("YOLO loading model=%s device=%s", self.cfg.yolo_model, self.device)
        self.model = YOLO(self.cfg.yolo_model)
        # Warm up on a small dummy frame to amortize first-call latency
        try:
            dummy = np.zeros((480, 640, 3), dtype=np.uint8)
            self.model.predict(dummy, device=self.device, verbose=False, conf=self.cfg.yolo_conf)
        except Exception:
            log.warning("YOLO warmup failed (non-fatal)")
        log.info("YOLO ready (classes=%s, conf=%.2f)", self.cfg.yolo_classes, self.cfg.yolo_conf)

    def process(self, frame: np.ndarray) -> tuple[np.ndarray, list[str]]:
        # Downscale to target width to keep inference fast
        h, w = frame.shape[:2]
        if w > self.cfg.downscale_width:
            scale = self.cfg.downscale_width / w
            frame = cv2.resize(frame, (self.cfg.downscale_width, int(h * scale)))

        # Run tracking. persist=True keeps the tracker state between calls.
        results = self.model.track(
            frame,
            persist=True,
            classes=self.cfg.yolo_classes,
            conf=self.cfg.yolo_conf,
            iou=self.cfg.yolo_iou,
            device=self.device,
            verbose=False,
            tracker="bytetrack.yaml",
        )
        result = results[0] if results else None

        crossings: list[str] = []
        alive_ids: set[int] = set()

        if result is not None and result.boxes is not None and result.boxes.id is not None:
            xyxy = result.boxes.xyxy.cpu().numpy().astype(int)
            ids = result.boxes.id.cpu().numpy().astype(int)
            confs = result.boxes.conf.cpu().numpy()
            for (x1, y1, x2, y2), tid, conf in zip(xyxy, ids, confs):
                cx, cy = int((x1 + x2) / 2), int((y1 + y2) / 2)
                track_id = int(tid)
                alive_ids.add(track_id)

                # Skip the very first frame for a track (no last_side yet)
                crossing = self.detector.update(track_id, (cx, cy))
                if crossing is not None:
                    crossings.append(crossing)
                    log.info("Crossing detected (yolo): %s (track %d, conf %.2f)", crossing, track_id, float(conf))

                # Annotate
                cv2.rectangle(frame, (int(x1), int(y1)), (int(x2), int(y2)), (52, 211, 153), 2)
                label = f"#{track_id} {conf:.2f}"
                cv2.putText(
                    frame,
                    label,
                    (int(x1), max(int(y1) - 6, 12)),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.45,
                    (52, 211, 153),
                    1,
                    cv2.LINE_AA,
                )
                cv2.circle(frame, (cx, cy), 4, (52, 211, 153), -1)

        # GC line-crossing state for tracks that disappeared
        self.detector.gc(alive_ids)

        # Draw the virtual line
        ax, ay = self.cfg.line.a
        bx, by = self.cfg.line.b
        cv2.line(frame, (ax, ay), (bx, by), (255, 80, 80), 2)
        cv2.putText(
            frame,
            f"YOLO {Path(self.cfg.yolo_model).stem} · {len(alive_ids)} ppl",
            (10, 22),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            (200, 200, 200),
            1,
            cv2.LINE_AA,
        )

        return frame, crossings
