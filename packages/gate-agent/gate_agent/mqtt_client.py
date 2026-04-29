from __future__ import annotations

import json
import logging
import threading
import time
from typing import Callable
from urllib.parse import urlparse

import paho.mqtt.client as mqtt

log = logging.getLogger(__name__)


EPOCH_TOPIC = "dashboard/control/epoch"


class MqttBus:
    """Wraps paho-mqtt with LWT, reconnect, retained-topic epoch sync, and ACK tracking."""

    def __init__(
        self,
        url: str,
        gate_id: str,
        keepalive: int,
        on_epoch: Callable[[int], None],
        on_publish_ack: Callable[[int], None],
        preview_url: str | None = None,
    ):
        self.url = url
        self.gate_id = gate_id
        self.keepalive = keepalive
        self._on_epoch = on_epoch
        self._on_publish_ack = on_publish_ack
        self.preview_url = preview_url

        parsed = urlparse(url)
        host = parsed.hostname or "localhost"
        port = parsed.port or 1883

        client_id = f"{gate_id}-{int(time.time())}"
        self.client = mqtt.Client(
            client_id=client_id,
            protocol=mqtt.MQTTv5,
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
        )
        self.client.username_pw_set(parsed.username, parsed.password) if parsed.username else None

        # LWT (offline, no preview)
        will_payload = json.dumps({"state": "offline", "ts": _now_iso(), "preview_url": None})
        self.client.will_set(
            f"gates/{gate_id}/status",
            payload=will_payload,
            qos=1,
            retain=True,
        )

        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        self.client.on_message = self._on_message
        self.client.on_publish = self._on_publish

        self._connected = threading.Event()
        self._host = host
        self._port = port

    @property
    def connected(self) -> bool:
        return self._connected.is_set()

    def connect_async(self) -> None:
        self.client.reconnect_delay_set(min_delay=1, max_delay=10)
        self.client.connect_async(self._host, self._port, keepalive=self.keepalive)
        self.client.loop_start()

    def shutdown(self) -> None:
        # Publish offline status before disconnecting
        if self._connected.is_set():
            self.client.publish(
                f"gates/{self.gate_id}/status",
                payload=json.dumps({"state": "offline", "ts": _now_iso(), "preview_url": None}),
                qos=1,
                retain=True,
            )
            time.sleep(0.1)
        self.client.loop_stop()
        try:
            self.client.disconnect()
        except Exception:
            pass

    def publish_event(self, payload: str) -> int | None:
        if not self._connected.is_set():
            return None
        info = self.client.publish(f"gates/{self.gate_id}/events", payload=payload, qos=1, retain=False)
        if info.rc != mqtt.MQTT_ERR_SUCCESS:
            return None
        return info.mid

    def publish_heartbeat(self) -> None:
        if not self._connected.is_set():
            return
        self.client.publish(
            f"gates/{self.gate_id}/heartbeat",
            payload=json.dumps({"ts": _now_iso()}),
            qos=0,
            retain=False,
        )

    def publish_crowd(self, count: int, engine: str | None = None, confidence: str | None = None) -> None:
        """Publish a crowd-density gauge reading. Retained so a late dashboard sees it."""
        if not self._connected.is_set():
            return
        self.client.publish(
            f"gates/{self.gate_id}/crowd",
            payload=json.dumps(
                {
                    "count": int(count),
                    "ts": _now_iso(),
                    "engine": engine,
                    "confidence": confidence,
                }
            ),
            qos=1,
            retain=True,
        )

    # paho callbacks ---------------------------------------------------

    def _on_connect(self, client, userdata, flags, reason_code, properties=None):  # type: ignore[no-untyped-def]
        if reason_code != 0:
            log.error("MQTT connect failed: %s", reason_code)
            return
        log.info("MQTT connected to %s:%s", self._host, self._port)
        # Announce online (retained, overrides LWT)
        client.publish(
            f"gates/{self.gate_id}/status",
            payload=json.dumps(
                {"state": "online", "ts": _now_iso(), "preview_url": self.preview_url}
            ),
            qos=1,
            retain=True,
        )
        # Subscribe to retained epoch
        client.subscribe(EPOCH_TOPIC, qos=1)
        self._connected.set()

    def _on_disconnect(self, client, userdata, *args):  # type: ignore[no-untyped-def]
        # paho v2 emits varying signatures depending on protocol — be lenient
        log.warning("MQTT disconnected")
        self._connected.clear()

    def _on_message(self, client, userdata, msg):  # type: ignore[no-untyped-def]
        if msg.topic == EPOCH_TOPIC:
            try:
                data = json.loads(msg.payload.decode("utf-8"))
                epoch = int(data["epoch"])
                self._on_epoch(epoch)
            except Exception:
                log.exception("Failed to parse epoch payload")

    def _on_publish(self, client, userdata, mid, *args):  # type: ignore[no-untyped-def]
        self._on_publish_ack(mid)


def _now_iso() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
