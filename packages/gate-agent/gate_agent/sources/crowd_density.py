"""Crowd density estimation source.

Periodically captures a snapshot from the configured video source (webcam,
video file, RTSP, or a still image) and runs a crowd-counting estimator
on it. The result is a single integer (estimated number of people in the
frame), published to MQTT as a gauge.

Two engines are supported:

* ``yolo-tiles`` – splits the frame into an N×M grid of overlapping tiles,
  runs YOLOv8 person-detection on each tile at high resolution, and
  reconciles duplicates near tile borders with greedy IoU. Works well for
  crowds up to ~2-3 k people and uses the dependencies we already have.

* ``csrnet`` – runs a CSRNet ONNX model that produces a density map and
  sums it. Required for very dense crowds (>3 k). The user must drop an
  exported ONNX file at the path configured in YAML.
"""

from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

import cv2
import numpy as np

from ..config import CrowdDensityConfig
from ..preview import PreviewServer

log = logging.getLogger(__name__)


# A typed callback the runtime supplies — same shape as the line-crossing
# `ingest` for symmetry, but with a single integer payload.
CrowdPublishFn = Callable[[int, str | None], None]


class CrowdDensitySource:
    def __init__(
        self,
        gate_id: str,
        cfg: CrowdDensityConfig,
        publish_crowd: CrowdPublishFn,
        preview: PreviewServer | None = None,
    ):
        self.gate_id = gate_id
        self.cfg = cfg
        self.publish_crowd = publish_crowd
        self.preview = preview
        self._estimator = _build_estimator(cfg)

    def run(self, ingest, stop: threading.Event) -> None:
        # `ingest` is unused for crowd mode (no in/out events), kept in
        # signature so the runtime can hand us its shared callback object.
        del ingest

        log.info(
            "Crowd-density source up (engine=%s, source=%s, every %.1fs)",
            self.cfg.engine, self.cfg.source, self.cfg.snapshot_interval_seconds,
        )
        while not stop.is_set():
            frame = self._grab_frame()
            if frame is None:
                stop.wait(self.cfg.snapshot_interval_seconds)
                continue
            try:
                count, annotated = self._estimator.estimate(frame)
            except Exception:
                log.exception("Crowd estimation failed")
                stop.wait(self.cfg.snapshot_interval_seconds)
                continue

            log.info("[%s] crowd estimate: %d people", self.gate_id, count)
            if self.preview is not None:
                self.preview.push_frame(annotated)
            self.publish_crowd(count, self.cfg.engine)

            stop.wait(self.cfg.snapshot_interval_seconds)

    def _grab_frame(self) -> np.ndarray | None:
        src = self.cfg.source
        if src == "image-file":
            if not self.cfg.image_path:
                log.error("crowd source=image-file requires `crowd.image_path`")
                return None
            img = cv2.imread(self.cfg.image_path)
            if img is None:
                log.error("Could not read image at %s", self.cfg.image_path)
            return img
        if src == "webcam":
            cap = cv2.VideoCapture(self.cfg.webcam_index, cv2.CAP_AVFOUNDATION)
            if not cap.isOpened():
                log.error("Webcam %d failed to open", self.cfg.webcam_index)
                return None
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            # Drain a few frames to settle exposure
            ok, frame = False, None
            for _ in range(5):
                ok, frame = cap.read()
                time.sleep(0.05)
            cap.release()
            return frame if ok else None
        if src == "video-file":
            if not self.cfg.video_path:
                return None
            cap = cv2.VideoCapture(self.cfg.video_path)
            ok, frame = cap.read()
            cap.release()
            return frame if ok else None
        if src == "rtsp":
            if not self.cfg.rtsp_url:
                return None
            cap = cv2.VideoCapture(self.cfg.rtsp_url)
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            ok, frame = cap.read()
            cap.release()
            return frame if ok else None
        log.error("Unknown crowd source: %s", src)
        return None


# --------------------------------------------------------------------------
# Estimator implementations
# --------------------------------------------------------------------------


class _YoloTilesEstimator:
    def __init__(self, cfg: CrowdDensityConfig):
        try:
            from ultralytics import YOLO  # type: ignore
        except ImportError as exc:
            raise SystemExit(
                "yolo-tiles engine requires ultralytics; run "
                "`uv pip install -e '.[yolo]'` in packages/gate-agent"
            ) from exc

        self.cfg = cfg
        self.device = _resolve_device(cfg.yolo_device)
        log.info("Loading YOLO crowd model %s on %s", cfg.yolo_model, self.device)
        self.model = YOLO(cfg.yolo_model)
        # Warm-up
        try:
            dummy = np.zeros((640, 640, 3), dtype=np.uint8)
            self.model.predict(dummy, device=self.device, verbose=False, conf=0.5)
        except Exception:
            pass

    def estimate(self, frame: np.ndarray) -> tuple[int, np.ndarray]:
        h, w = frame.shape[:2]
        rows, cols = self.cfg.tile_grid_rows, self.cfg.tile_grid_cols
        overlap = self.cfg.tile_overlap
        tile_h = int(h / rows)
        tile_w = int(w / cols)
        pad_h = int(tile_h * overlap)
        pad_w = int(tile_w * overlap)

        all_boxes: list[tuple[float, float, float, float, float]] = []  # (x1,y1,x2,y2,conf)

        for r in range(rows):
            for c in range(cols):
                y1 = max(0, r * tile_h - pad_h)
                x1 = max(0, c * tile_w - pad_w)
                y2 = min(h, (r + 1) * tile_h + pad_h)
                x2 = min(w, (c + 1) * tile_w + pad_w)
                tile = frame[y1:y2, x1:x2]
                if tile.size == 0:
                    continue
                results = self.model.predict(
                    tile,
                    device=self.device,
                    classes=self.cfg.yolo_classes,
                    conf=self.cfg.yolo_conf,
                    iou=self.cfg.yolo_iou,
                    imgsz=self.cfg.tile_inference_size,
                    verbose=False,
                )
                if not results:
                    continue
                boxes = results[0].boxes
                if boxes is None or len(boxes) == 0:
                    continue
                xyxy = boxes.xyxy.cpu().numpy()
                confs = boxes.conf.cpu().numpy()
                for (bx1, by1, bx2, by2), cf in zip(xyxy, confs):
                    all_boxes.append(
                        (
                            float(bx1) + x1,
                            float(by1) + y1,
                            float(bx2) + x1,
                            float(by2) + y1,
                            float(cf),
                        )
                    )

        # Greedy NMS to dedupe across tile overlaps
        kept = _nms(all_boxes, iou_threshold=0.45)
        annotated = _draw_boxes(frame.copy(), kept, label_engine="yolo-tiles")
        return len(kept), annotated


def _build_estimator(cfg: CrowdDensityConfig):
    if cfg.engine == "yolo-tiles":
        return _YoloTilesEstimator(cfg)
    if cfg.engine == "csrnet":
        return _CsrnetEstimator(cfg)
    raise SystemExit(f"Unknown crowd engine: {cfg.engine}")


class _CsrnetEstimator:
    """CSRNet ONNX inference. The model must already exist at the configured path.

    See README.md for how to obtain a CSRNet ONNX export. The model takes a
    normalized RGB image of shape (1, 3, H, W) and outputs a density map
    (1, 1, H/8, W/8). Sum of all pixels = estimated count.
    """

    def __init__(self, cfg: CrowdDensityConfig):
        try:
            import onnxruntime as ort  # type: ignore
        except ImportError as exc:
            raise SystemExit(
                "csrnet engine requires `onnxruntime` (and a CSRNet .onnx file). "
                "Install with: uv pip install onnxruntime"
            ) from exc
        if not cfg.csrnet_onnx_path or not Path(cfg.csrnet_onnx_path).exists():
            raise SystemExit(
                f"csrnet engine: ONNX model not found at {cfg.csrnet_onnx_path!r}. "
                "See README.md for download instructions."
            )
        self.cfg = cfg
        providers = ["CoreMLExecutionProvider", "CPUExecutionProvider"]
        self.session = ort.InferenceSession(cfg.csrnet_onnx_path, providers=providers)
        log.info("CSRNet ONNX loaded (providers=%s)", self.session.get_providers())

    def estimate(self, frame: np.ndarray) -> tuple[int, np.ndarray]:
        h_target, w_target = self.cfg.csrnet_input_size
        resized = cv2.resize(frame, (w_target, h_target))
        rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
        # Standard ImageNet normalization
        mean = np.array([0.485, 0.456, 0.406], dtype=np.float32)
        std = np.array([0.229, 0.224, 0.225], dtype=np.float32)
        rgb = (rgb - mean) / std
        chw = np.transpose(rgb, (2, 0, 1))[None, ...]  # (1, 3, H, W)

        input_name = self.session.get_inputs()[0].name
        output = self.session.run(None, {input_name: chw.astype(np.float32)})[0]
        density = output[0, 0]  # (H/8, W/8) — sum of pixels = estimated count
        count = max(0, int(round(float(density.sum()))))

        # Pretty visualization: upsample the density map to the input size
        # (purely cosmetic — the count is the sum of the low-res map).
        density_vis = density / max(density.max(), 1e-6)
        density_vis = (density_vis * 255).astype(np.uint8)
        density_vis = cv2.resize(density_vis, (w_target, h_target))
        heat = cv2.applyColorMap(density_vis, cv2.COLORMAP_JET)
        annotated = cv2.addWeighted(resized, 0.7, heat, 0.3, 0)
        cv2.putText(
            annotated,
            f"CSRNet · ~{count} people",
            (12, 28),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (255, 255, 255),
            2,
            cv2.LINE_AA,
        )
        return count, annotated


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------


def _resolve_device(preferred: str | None) -> str:
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


def _iou(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> float:
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    inter_x1, inter_y1 = max(ax1, bx1), max(ay1, by1)
    inter_x2, inter_y2 = min(ax2, bx2), min(ay2, by2)
    iw = max(0.0, inter_x2 - inter_x1)
    ih = max(0.0, inter_y2 - inter_y1)
    inter = iw * ih
    if inter <= 0:
        return 0.0
    area_a = max(0.0, ax2 - ax1) * max(0.0, ay2 - ay1)
    area_b = max(0.0, bx2 - bx1) * max(0.0, by2 - by1)
    union = area_a + area_b - inter
    return inter / union if union > 0 else 0.0


def _nms(
    boxes: list[tuple[float, float, float, float, float]], iou_threshold: float
) -> list[tuple[float, float, float, float, float]]:
    """Greedy NMS over (x1,y1,x2,y2,conf) tuples."""
    if not boxes:
        return []
    sorted_boxes = sorted(boxes, key=lambda b: b[4], reverse=True)
    kept: list[tuple[float, float, float, float, float]] = []
    for box in sorted_boxes:
        if all(_iou(box[:4], k[:4]) < iou_threshold for k in kept):
            kept.append(box)
    return kept


def _draw_boxes(
    frame: np.ndarray,
    boxes: list[tuple[float, float, float, float, float]],
    label_engine: str,
) -> np.ndarray:
    h, w = frame.shape[:2]
    for x1, y1, x2, y2, _ in boxes:
        cv2.rectangle(frame, (int(x1), int(y1)), (int(x2), int(y2)), (52, 211, 153), 1)
    cv2.putText(
        frame,
        f"{label_engine} · {len(boxes)} people",
        (12, 28),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.7,
        (255, 255, 255),
        2,
        cv2.LINE_AA,
    )
    return frame


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
