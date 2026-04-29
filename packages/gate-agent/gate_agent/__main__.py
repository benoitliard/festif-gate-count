from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from .config import GateConfig, load_config
from .preview import PreviewServer
from .runtime import GateRuntime
from .sources.base import EventSource


def _build_source(cfg: GateConfig, preview: PreviewServer | None) -> EventSource:
    if cfg.mode == "manual":
        from .sources.manual import ManualSource

        return ManualSource(gate_id=cfg.gate_id, port=cfg.manual_port, role=cfg.role)
    if cfg.mode == "video-file":
        if not cfg.video_path or not cfg.tracking:
            raise SystemExit("video-file mode requires `video_path` and `tracking` in config")
        from .sources.video_file import VideoFileSource

        return VideoFileSource(path=cfg.video_path, loop=cfg.video_loop, tracking=cfg.tracking, preview=preview)
    if cfg.mode == "webcam":
        if not cfg.tracking:
            raise SystemExit("webcam mode requires `tracking` in config")
        from .sources.webcam import WebcamSource

        return WebcamSource(index=cfg.webcam_index, tracking=cfg.tracking, preview=preview)
    raise SystemExit(f"Unknown mode: {cfg.mode}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="gate-agent")
    parser.add_argument("--config", required=True, help="Path to YAML config file")
    parser.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )

    config_path = Path(args.config).resolve()
    if not config_path.exists():
        print(f"Config not found: {config_path}", file=sys.stderr)
        return 1

    cfg = load_config(config_path)
    logging.info("Starting gate %s (mode=%s)", cfg.gate_id, cfg.mode)

    runtime = GateRuntime(cfg)
    source = _build_source(cfg, preview=runtime.preview)
    runtime.run(source)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
