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

    # Manual pads always offer both directions — the operator counts whoever
    # walks past, regardless of where the gate is physically placed. The
    # `role` is kept as a label only.
    allowed: tuple[Direction, ...] = ("in", "out")

    @app.get("/manifest.webmanifest")
    def manifest():
        return JSONResponse(
            {
                "name": f"Gate · {gate_id}",
                "short_name": gate_id,
                "description": f"Trigger pad for {gate_id}",
                "theme_color": "#0f172a",
                "background_color": "#0f172a",
                "display": "standalone",
                "orientation": "portrait",
                "start_url": "/",
                "scope": "/",
                "icons": [
                    {"src": "/icon.svg", "sizes": "any", "type": "image/svg+xml", "purpose": "any maskable"},
                ],
            }
        )

    @app.get("/icon.svg")
    def icon():
        svg = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512"><rect width="512" height="512" rx="96" fill="#0f172a"/><circle cx="256" cy="256" r="120" fill="none" stroke="#34d399" stroke-width="20"/><text x="170" y="290" font-family="ui-monospace, monospace" font-size="120" font-weight="800" text-anchor="middle" fill="#34d399">↑</text><text x="342" y="290" font-family="ui-monospace, monospace" font-size="120" font-weight="800" text-anchor="middle" fill="#fbbf24">↓</text></svg>"""
        return HTMLResponse(content=svg, media_type="image/svg+xml")

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        buttons_html = ""
        for d in allowed:
            label = "ENTRÉE" if d == "in" else "SORTIE"
            arrow = "↑" if d == "in" else "↓"
            buttons_html += f"""
            <button data-dir="{d}" class="dir-btn dir-{d}">
              <span class="arrow">{arrow}</span>
              <span class="label">{label}</span>
              <span class="count" data-count="{d}">0</span>
            </button>"""
        return f"""<!doctype html>
<html lang="fr">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover, user-scalable=no" />
  <meta name="theme-color" content="#0f172a" />
  <meta name="color-scheme" content="dark" />
  <meta name="apple-mobile-web-app-capable" content="yes" />
  <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent" />
  <meta name="apple-mobile-web-app-title" content="{gate_id}" />
  <link rel="manifest" href="/manifest.webmanifest" />
  <link rel="icon" href="/icon.svg" type="image/svg+xml" />
  <link rel="apple-touch-icon" href="/icon.svg" />
  <title>{gate_id}</title>
  <style>
    :root {{ color-scheme: dark; }}
    * {{ box-sizing: border-box; }}
    html, body {{ height: 100%; }}
    body {{
      margin: 0;
      font-family: system-ui, -apple-system, sans-serif;
      background: #0f172a;
      color: #f1f5f9;
      display: flex;
      flex-direction: column;
      padding: max(16px, env(safe-area-inset-top)) 16px max(16px, env(safe-area-inset-bottom));
      gap: 20px;
      -webkit-tap-highlight-color: transparent;
      overscroll-behavior: none;
    }}
    header {{ text-align: center; }}
    h1 {{ margin: 0; font-family: ui-monospace, monospace; font-size: 1.3rem; }}
    .role {{ font-size: 0.7rem; letter-spacing: 0.2em; text-transform: uppercase; color: #94a3b8; }}
    .buttons {{
      display: grid;
      grid-template-rows: 1fr 1fr;
      gap: 14px;
      flex: 1;
    }}
    .dir-btn {{
      border: none;
      border-radius: 24px;
      padding: 24px;
      cursor: pointer;
      transition: transform 0.06s ease, box-shadow 0.2s ease, filter 0.15s ease;
      color: #0f172a;
      touch-action: manipulation;
      display: grid;
      grid-template-areas:
        "arrow label"
        "arrow count";
      grid-template-columns: auto 1fr;
      grid-template-rows: auto auto;
      align-items: center;
      gap: 0 16px;
      text-align: left;
    }}
    .dir-btn:active {{ transform: scale(0.985); filter: brightness(1.08); }}
    .dir-in {{ background: #34d399; box-shadow: 0 14px 28px -10px rgba(52, 211, 153, 0.5); }}
    .dir-out {{ background: #fbbf24; box-shadow: 0 14px 28px -10px rgba(251, 191, 36, 0.5); }}
    .arrow {{
      grid-area: arrow;
      font-size: 4.5rem;
      font-weight: 900;
      line-height: 1;
    }}
    .label {{
      grid-area: label;
      font-size: 1.6rem;
      font-weight: 800;
      letter-spacing: 0.06em;
      align-self: end;
    }}
    .count {{
      grid-area: count;
      font-family: ui-monospace, monospace;
      font-variant-numeric: tabular-nums;
      font-size: 1.05rem;
      font-weight: 700;
      opacity: 0.7;
      align-self: start;
    }}
    .log {{
      font-family: ui-monospace, monospace;
      font-size: 0.75rem;
      color: #64748b;
      min-height: 16px;
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
    const STORAGE_KEY = 'gate-counter:local:{gate_id}';
    const local = {{ in: 0, out: 0, ...JSON.parse(localStorage.getItem(STORAGE_KEY) || '{{}}') }};

    function refreshCounts() {{
      document.querySelectorAll('.count').forEach(span => {{
        const dir = span.dataset.count;
        span.textContent = local[dir] || 0;
      }});
    }}
    refreshCounts();

    document.querySelectorAll('.dir-btn').forEach(btn => {{
      btn.addEventListener('click', async () => {{
        const dir = btn.dataset.dir;
        if (navigator.vibrate) navigator.vibrate(10);
        // Optimistic local count
        local[dir] = (local[dir] || 0) + 1;
        localStorage.setItem(STORAGE_KEY, JSON.stringify(local));
        refreshCounts();
        try {{
          const r = await fetch('/trigger/' + dir, {{ method: 'POST' }});
          if (!r.ok) throw new Error('HTTP ' + r.status);
          const data = await r.json();
          log.textContent = dir + ' ✓ ' + (data.event_id || '').slice(-6);
        }} catch (err) {{
          // Roll back local count on failure
          local[dir] = Math.max(0, (local[dir] || 0) - 1);
          localStorage.setItem(STORAGE_KEY, JSON.stringify(local));
          refreshCounts();
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
