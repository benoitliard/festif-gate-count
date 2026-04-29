from __future__ import annotations

import logging
import threading
from typing import Callable

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse

from ..events import Direction
from .base import IngestFn

log = logging.getLogger(__name__)


def _build_app(gate_id: str, ingest: IngestFn, role: str) -> FastAPI:
    app = FastAPI(title=f"Gate {gate_id}", docs_url=None, redoc_url=None)

    allowed: tuple[Direction, ...] = (
        ("in",) if role == "entry" else ("out",) if role == "exit" else ("in", "out")
    )

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        buttons_html = ""
        for d in allowed:
            color = "emerald" if d == "in" else "amber"
            label = "ENTRÉE ↑" if d == "in" else "SORTIE ↓"
            buttons_html += f"""
            <button data-dir="{d}" class="dir-btn dir-{d}">
              {label}
            </button>"""
        return f"""<!doctype html>
<html lang="fr">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1, user-scalable=no" />
  <title>{gate_id}</title>
  <style>
    :root {{ color-scheme: dark; }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      min-height: 100vh;
      font-family: system-ui, -apple-system, sans-serif;
      background: #0f172a;
      color: #f1f5f9;
      display: flex;
      flex-direction: column;
      padding: 24px;
      gap: 24px;
    }}
    header {{
      text-align: center;
    }}
    h1 {{
      margin: 0;
      font-family: ui-monospace, monospace;
      font-size: 1.4rem;
    }}
    .role {{
      font-size: 0.75rem;
      letter-spacing: 0.2em;
      text-transform: uppercase;
      color: #94a3b8;
    }}
    .buttons {{
      display: grid;
      grid-template-columns: 1fr;
      gap: 16px;
      flex: 1;
    }}
    .dir-btn {{
      border: none;
      border-radius: 24px;
      padding: 32px;
      font-size: 1.6rem;
      font-weight: 700;
      letter-spacing: 0.05em;
      cursor: pointer;
      transition: transform 0.06s ease, box-shadow 0.2s ease;
      color: #0f172a;
    }}
    .dir-btn:active {{
      transform: scale(0.98);
    }}
    .dir-in {{
      background: #34d399;
      box-shadow: 0 14px 28px -10px rgba(52, 211, 153, 0.6);
    }}
    .dir-out {{
      background: #fbbf24;
      box-shadow: 0 14px 28px -10px rgba(251, 191, 36, 0.6);
    }}
    .log {{
      font-family: ui-monospace, monospace;
      font-size: 0.8rem;
      color: #64748b;
      min-height: 18px;
      text-align: center;
    }}
  </style>
</head>
<body>
  <header>
    <h1>{gate_id}</h1>
    <div class="role">role: {role}</div>
  </header>
  <div class="buttons">{buttons_html}</div>
  <div class="log" id="log">prêt</div>
  <script>
    const log = document.getElementById('log');
    document.querySelectorAll('.dir-btn').forEach(btn => {{
      btn.addEventListener('click', async () => {{
        const dir = btn.dataset.dir;
        try {{
          const r = await fetch('/trigger/' + dir, {{ method: 'POST' }});
          if (!r.ok) throw new Error('HTTP ' + r.status);
          const data = await r.json();
          log.textContent = dir + ' ✓ ' + (data.event_id || '');
        }} catch (err) {{
          log.textContent = 'ERROR: ' + err.message;
        }}
      }});
    }});
  </script>
</body>
</html>
"""

    @app.post("/trigger/{direction}")
    def trigger(direction: str):
        if direction not in allowed:
            raise HTTPException(status_code=400, detail=f"direction not allowed: {direction}")
        evt = ingest(direction)  # type: ignore[arg-type]
        if evt is None:
            return JSONResponse(status_code=503, content={"error": "no_epoch_yet"})
        return {"event_id": evt.event_id, "direction": evt.direction, "epoch": evt.epoch}

    @app.get("/health")
    def health():
        return {"ok": True, "gate_id": gate_id}

    return app


class ManualSource:
    """HTTP server with IN/OUT buttons. The most reliable POC source."""

    def __init__(self, gate_id: str, port: int, role: str):
        self.gate_id = gate_id
        self.port = port
        self.role = role
        self._server: uvicorn.Server | None = None

    def run(self, ingest: IngestFn, stop: threading.Event) -> None:
        app = _build_app(self.gate_id, ingest, self.role)
        config = uvicorn.Config(app, host="0.0.0.0", port=self.port, log_level="warning", access_log=False)
        self._server = uvicorn.Server(config)

        thread = threading.Thread(target=self._server.run, daemon=True, name=f"uvicorn-{self.gate_id}")
        thread.start()
        log.info("Manual trigger server up at http://localhost:%d/", self.port)

        try:
            while not stop.wait(0.5):
                pass
        finally:
            if self._server:
                self._server.should_exit = True
            thread.join(timeout=2)
