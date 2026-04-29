from __future__ import annotations

import threading
from typing import Callable, Protocol

from ..events import GateEvent, Direction


IngestFn = Callable[[Direction], "GateEvent | None"]


class EventSource(Protocol):
    """A source of gate events. Sources call ``ingest(direction)`` for each detection."""

    def run(self, ingest: IngestFn, stop: threading.Event) -> None: ...
