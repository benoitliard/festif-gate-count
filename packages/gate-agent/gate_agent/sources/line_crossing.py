"""Shared line-crossing detector — used by both MOG2 and YOLO trackers."""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from ..config import LineConfig


@dataclass
class _TrackState:
    last_side: int = 0  # -1, 0, +1
    last_crossing_at: float = 0.0


@dataclass
class LineCrossingDetector:
    """Detects direction-aware line crossings for any tracked centroid."""

    line: LineConfig
    cooldown_seconds: float = 1.0
    _states: dict[int, _TrackState] = field(default_factory=dict)

    def update(self, track_id: int, centroid: tuple[int, int]) -> str | None:
        """Feed a new centroid for this track. Returns 'in'/'out' on a fresh crossing, else None."""
        side = self._side_of_line(centroid)
        state = self._states.setdefault(track_id, _TrackState())
        now = time.time()

        crossing: str | None = None
        if (
            state.last_side != 0
            and side != 0
            and side != state.last_side
            and (now - state.last_crossing_at) > self.cooldown_seconds
        ):
            in_pos = self.line.in_side == "positive"
            if side > 0:
                crossing = "in" if in_pos else "out"
            else:
                crossing = "out" if in_pos else "in"
            state.last_crossing_at = now

        if side != 0:
            state.last_side = side
        return crossing

    def forget(self, track_id: int) -> None:
        self._states.pop(track_id, None)

    def gc(self, alive_ids: set[int]) -> None:
        """Drop state for tracks that are no longer alive."""
        for tid in list(self._states.keys()):
            if tid not in alive_ids:
                del self._states[tid]

    def _side_of_line(self, p: tuple[int, int]) -> int:
        ax, ay = self.line.a
        bx, by = self.line.b
        cross = (bx - ax) * (p[1] - ay) - (by - ay) * (p[0] - ax)
        if cross > 0:
            return 1
        if cross < 0:
            return -1
        return 0
