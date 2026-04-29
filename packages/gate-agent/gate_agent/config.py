from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, field_validator


SourceMode = Literal["manual", "video-file", "webcam"]


class LineConfig(BaseModel):
    """Virtual line for line-crossing detection in CV modes."""

    a: tuple[int, int]
    b: tuple[int, int]
    in_side: Literal["positive", "negative"] = "positive"


class TrackingConfig(BaseModel):
    """Computer-vision pipeline parameters."""

    min_area: int = 1500
    max_distance: int = 80
    max_age_frames: int = 30
    cooldown_seconds: float = 1.0
    line: LineConfig
    downscale_width: int = 640
    learning_rate: float = -1.0
    var_threshold: float = 32.0


class GateConfig(BaseModel):
    gate_id: str
    role: Literal["entry", "exit", "bidirectional"] = "bidirectional"
    mode: SourceMode = "manual"
    mqtt_url: str = "mqtt://localhost:1884"
    mqtt_keepalive: int = 10
    heartbeat_seconds: float = 5.0
    epoch_wait_seconds: float = 2.0
    db_path: str = "data/{gate_id}.db"
    drain_interval_seconds: float = 1.0

    # manual mode (HTTP triggers)
    manual_port: int = 8003

    # video-file mode
    video_path: str | None = None
    video_loop: bool = True

    # webcam mode
    webcam_index: int = 0

    # tracking (used by video-file and webcam)
    tracking: TrackingConfig | None = None

    @field_validator("db_path")
    @classmethod
    def _expand_db_path(cls, v: str, info) -> str:
        gate_id = info.data.get("gate_id", "gate")
        return v.replace("{gate_id}", gate_id)


def load_config(path: str | Path) -> GateConfig:
    text = Path(path).read_text(encoding="utf-8")
    data = yaml.safe_load(text)
    return GateConfig.model_validate(data)
