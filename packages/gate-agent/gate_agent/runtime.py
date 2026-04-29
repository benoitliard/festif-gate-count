from __future__ import annotations

import logging
import queue
import signal
import threading
import time
from typing import Optional

from .buffer import EventBuffer
from .config import GateConfig
from .events import GateEvent, Direction
from .mqtt_client import MqttBus
from .preview import PreviewServer
from .sources.base import EventSource

log = logging.getLogger(__name__)


class GateRuntime:
    """Owns the event buffer, the MQTT bus, and the source-emit loop."""

    def __init__(self, config: GateConfig):
        self.config = config
        self.buffer = EventBuffer(config.db_path)
        self._epoch_lock = threading.Lock()
        self._epoch: Optional[int] = None
        self._mid_to_event: dict[int, str] = {}
        self._mid_lock = threading.Lock()
        self._stop = threading.Event()
        self._epoch_received = threading.Event()

        # Preview server (optional). Started before MQTT so the URL can be advertised.
        self.preview: Optional[PreviewServer] = None
        if config.preview_port is not None:
            self.preview = PreviewServer(gate_id=config.gate_id, port=config.preview_port)

        self.bus = MqttBus(
            url=config.mqtt_url,
            gate_id=config.gate_id,
            keepalive=config.mqtt_keepalive,
            on_epoch=self._handle_epoch,
            on_publish_ack=self._handle_ack,
            preview_url=self.preview.url if self.preview else None,
        )

    # --- event ingestion (called by sources) ---

    def ingest(self, direction: Direction) -> Optional[GateEvent]:
        epoch = self._current_epoch()
        if epoch is None:
            log.warning("Dropping %s event: no epoch yet", direction)
            return None
        evt = GateEvent.new(
            gate_id=self.config.gate_id,
            direction=direction,
            epoch=epoch,
            source=self.config.mode,
        )
        self.buffer.append(evt, created_at_ms=int(time.time() * 1000))
        log.info("[%s] %s event %s buffered (epoch=%d)", self.config.gate_id, direction, evt.event_id, epoch)
        return evt

    # --- epoch handling ---

    def _handle_epoch(self, epoch: int) -> None:
        with self._epoch_lock:
            previous = self._epoch
            if previous is not None and epoch > previous:
                # Reset received: flush buffered events from prior epochs
                flushed = self.buffer.flush_below_epoch(epoch)
                if flushed:
                    log.info("Reset received: flushed %d pre-epoch-%d events", flushed, epoch)
            self._epoch = epoch
        self._epoch_received.set()
        log.info("Epoch set to %d", epoch)

    def _current_epoch(self) -> Optional[int]:
        with self._epoch_lock:
            return self._epoch

    # --- ack handling ---

    def _handle_ack(self, mid: int) -> None:
        with self._mid_lock:
            event_id = self._mid_to_event.pop(mid, None)
        if event_id:
            self.buffer.mark_sent([event_id])

    # --- main loop ---

    def run(self, source: EventSource) -> None:
        signal.signal(signal.SIGINT, self._on_signal)
        signal.signal(signal.SIGTERM, self._on_signal)

        if self.preview is not None:
            self.preview.start()

        self.bus.connect_async()

        # Wait briefly for retained epoch
        if self._epoch_received.wait(self.config.epoch_wait_seconds):
            log.info("Initial epoch received quickly")
        else:
            log.info("No retained epoch within %.1fs; will publish once received", self.config.epoch_wait_seconds)

        # Start drain loop
        drain_thread = threading.Thread(target=self._drain_loop, daemon=True, name="drain")
        drain_thread.start()

        # Start heartbeat loop
        heartbeat_thread = threading.Thread(target=self._heartbeat_loop, daemon=True, name="heartbeat")
        heartbeat_thread.start()

        # Run source in foreground (sources may run their own threads)
        try:
            source.run(self.ingest, stop=self._stop)
        finally:
            self._stop.set()
            self.bus.shutdown()
            if self.preview is not None:
                self.preview.stop()
            self.buffer.close()

    def _on_signal(self, signum, frame):  # type: ignore[no-untyped-def]
        log.info("Signal %s received, stopping", signum)
        self._stop.set()

    def _drain_loop(self) -> None:
        while not self._stop.is_set():
            try:
                self._drain_once()
            except Exception:
                log.exception("Drain loop error")
            self._stop.wait(self.config.drain_interval_seconds)

    def _drain_once(self) -> None:
        if not self.bus.connected:
            return
        if self._current_epoch() is None:
            return
        rows = self.buffer.fetch_unsent(limit=200)
        if not rows:
            return
        published = 0
        for event_id, payload, _attempts in rows:
            mid = self.bus.publish_event(payload)
            if mid is None:
                # not connected anymore — stop and retry next tick
                break
            with self._mid_lock:
                self._mid_to_event[mid] = event_id
            self.buffer.increment_attempt(event_id)
            published += 1
        if published:
            log.debug("Drained %d events to broker", published)

    def _heartbeat_loop(self) -> None:
        while not self._stop.is_set():
            try:
                self.bus.publish_heartbeat()
            except Exception:
                log.exception("Heartbeat error")
            self._stop.wait(self.config.heartbeat_seconds)
