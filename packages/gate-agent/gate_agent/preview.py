from __future__ import annotations

import logging
import threading
import time
from typing import Optional

import cv2
import numpy as np
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, StreamingResponse

log = logging.getLogger(__name__)


class FrameBuffer:
    """Thread-safe latest-frame holder. Encodes once per push to avoid double-encoding per HTTP client."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._jpeg: Optional[bytes] = None
        self._cond = threading.Condition(self._lock)

    def push(self, frame: np.ndarray, quality: int = 70) -> None:
        ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, quality])
        if not ok:
            return
        with self._lock:
            self._jpeg = bytes(buf)
            self._cond.notify_all()

    def wait_for(self, timeout: float = 1.0) -> Optional[bytes]:
        with self._cond:
            self._cond.wait(timeout=timeout)
            return self._jpeg


class PreviewServer:
    """Tiny FastAPI app that serves an MJPEG stream + a tiny HTML viewer page."""

    def __init__(self, gate_id: str, port: int):
        self.gate_id = gate_id
        self.port = port
        self.buffer = FrameBuffer()
        self._server: uvicorn.Server | None = None
        self._thread: threading.Thread | None = None

    @property
    def url(self) -> str:
        return f"http://localhost:{self.port}/preview"

    @property
    def viewer_url(self) -> str:
        return f"http://localhost:{self.port}/"

    def push_frame(self, frame: np.ndarray) -> None:
        self.buffer.push(frame)

    def start(self) -> None:
        app = self._build_app()
        config = uvicorn.Config(app, host="0.0.0.0", port=self.port, log_level="warning", access_log=False)
        self._server = uvicorn.Server(config)
        self._thread = threading.Thread(target=self._server.run, daemon=True, name=f"preview-{self.gate_id}")
        self._thread.start()
        log.info("Preview MJPEG up at %s", self.viewer_url)

    def stop(self) -> None:
        if self._server is not None:
            self._server.should_exit = True
        if self._thread is not None:
            self._thread.join(timeout=2)

    def _build_app(self) -> FastAPI:
        gate_id = self.gate_id
        buffer = self.buffer
        app = FastAPI(docs_url=None, redoc_url=None)
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=False,
            allow_methods=["GET"],
            allow_headers=["*"],
        )

        BOUNDARY = "frame"

        def stream():
            # Send a tiny placeholder if no frame yet
            placeholder_sent = False
            while True:
                jpeg = buffer.wait_for(timeout=1.0)
                if jpeg is None:
                    if not placeholder_sent:
                        # 1x1 black JPEG, just to avoid a hung client
                        placeholder_sent = True
                    time.sleep(0.05)
                    continue
                yield (
                    f"--{BOUNDARY}\r\n".encode("ascii")
                    + b"Content-Type: image/jpeg\r\n"
                    + f"Content-Length: {len(jpeg)}\r\n\r\n".encode("ascii")
                    + jpeg
                    + b"\r\n"
                )

        @app.get("/preview")
        def preview():
            return StreamingResponse(
                stream(),
                media_type=f"multipart/x-mixed-replace; boundary={BOUNDARY}",
                headers={"Cache-Control": "no-cache, no-store, must-revalidate", "Pragma": "no-cache"},
            )

        @app.get("/", response_class=HTMLResponse)
        def index() -> str:
            return f"""<!doctype html>
<html lang="fr"><head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{gate_id} preview</title>
  <style>
    body {{ margin: 0; background: #0f172a; color: #f1f5f9; font-family: system-ui; padding: 16px; }}
    h1 {{ margin: 0 0 12px; font-size: 1rem; font-family: ui-monospace, monospace; }}
    img {{ max-width: 100%; border-radius: 12px; display: block; }}
  </style>
</head><body>
  <h1>● {gate_id} — live</h1>
  <img src="/preview" alt="live preview" />
</body></html>"""

        @app.get("/health")
        def health():
            return {"ok": True, "gate_id": gate_id}

        return app
