from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal

from ulid import ULID


Direction = Literal["in", "out"]


@dataclass(frozen=True)
class GateEvent:
    event_id: str
    gate_id: str
    direction: Direction
    ts: str
    epoch: int
    source: str
    schema_version: int = 1

    @classmethod
    def new(cls, gate_id: str, direction: Direction, epoch: int, source: str) -> "GateEvent":
        return cls(
            event_id=str(ULID()),
            gate_id=gate_id,
            direction=direction,
            ts=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            epoch=epoch,
            source=source,
        )

    def to_json(self) -> str:
        return json.dumps(
            {
                "event_id": self.event_id,
                "gate_id": self.gate_id,
                "direction": self.direction,
                "ts": self.ts,
                "epoch": self.epoch,
                "source": self.source,
                "schema_version": self.schema_version,
            },
            separators=(",", ":"),
        )

    @classmethod
    def from_json(cls, raw: str) -> "GateEvent":
        data = json.loads(raw)
        return cls(
            event_id=data["event_id"],
            gate_id=data["gate_id"],
            direction=data["direction"],
            ts=data["ts"],
            epoch=int(data["epoch"]),
            source=data.get("source", "unknown"),
            schema_version=int(data.get("schema_version", 1)),
        )
