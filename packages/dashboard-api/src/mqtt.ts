import mqtt, { type MqttClient } from "mqtt";
import type { FastifyBaseLogger } from "fastify";
import type { Store, GateEvent } from "./store.js";
import type { Broadcaster } from "./ws.js";

const TOPIC_EVENTS = "gates/+/events";
const TOPIC_STATUS = "gates/+/status";
const TOPIC_HEARTBEAT = "gates/+/heartbeat";
const TOPIC_EPOCH = "dashboard/control/epoch";

export interface MqttBus {
  client: MqttClient;
  publishEpoch(epoch: number): void;
}

export function startMqtt(opts: {
  url: string;
  store: Store;
  broadcaster: Broadcaster;
  log: FastifyBaseLogger;
}): MqttBus {
  const { url, store, broadcaster, log } = opts;
  const client = mqtt.connect(url, {
    clientId: `dashboard-api-${Math.random().toString(16).slice(2, 8)}`,
    reconnectPeriod: 2000,
    clean: true,
  });

  client.on("connect", () => {
    log.info({ url }, "MQTT connected");
    client.subscribe([TOPIC_EVENTS, TOPIC_STATUS, TOPIC_HEARTBEAT], { qos: 1 }, (err) => {
      if (err) log.error({ err }, "MQTT subscribe failed");
    });
    // Re-publish current epoch retained so any newly-connected gate gets it.
    const epoch = store.getCurrentEpoch();
    publishEpochRetained(client, epoch);
  });

  client.on("reconnect", () => log.warn("MQTT reconnecting"));
  client.on("close", () => log.warn("MQTT connection closed"));
  client.on("error", (err) => log.error({ err: err.message }, "MQTT error"));

  client.on("message", (topic, payload) => {
    try {
      handleMessage(topic, payload.toString(), { store, broadcaster, log });
    } catch (err) {
      log.error({ err: (err as Error).message, topic }, "Failed to handle MQTT message");
    }
  });

  return {
    client,
    publishEpoch(epoch: number) {
      publishEpochRetained(client, epoch);
    },
  };
}

function publishEpochRetained(client: MqttClient, epoch: number) {
  client.publish(
    TOPIC_EPOCH,
    JSON.stringify({ epoch, ts: new Date().toISOString() }),
    { qos: 1, retain: true }
  );
}

function handleMessage(
  topic: string,
  raw: string,
  ctx: { store: Store; broadcaster: Broadcaster; log: FastifyBaseLogger }
) {
  const parts = topic.split("/");
  // gates/{gate_id}/{kind}
  if (parts[0] === "gates" && parts.length === 3) {
    const gateId = parts[1];
    const kind = parts[2];
    if (!gateId) return;
    if (kind === "events") return handleEvent(gateId, raw, ctx);
    if (kind === "status") return handleStatus(gateId, raw, ctx);
    if (kind === "heartbeat") return handleHeartbeat(gateId, ctx);
  }
}

function handleEvent(
  gateId: string,
  raw: string,
  ctx: { store: Store; broadcaster: Broadcaster; log: FastifyBaseLogger }
) {
  const evt = JSON.parse(raw) as Partial<GateEvent>;
  if (!evt.event_id || !evt.direction || !evt.ts || typeof evt.epoch !== "number") {
    ctx.log.warn({ evt }, "Invalid event payload");
    return;
  }
  if (evt.direction !== "in" && evt.direction !== "out") return;
  const fullEvent: GateEvent = {
    event_id: evt.event_id,
    gate_id: gateId,
    direction: evt.direction,
    ts: evt.ts,
    epoch: evt.epoch,
  };
  const result = ctx.store.applyEvent(fullEvent);
  ctx.store.touchGate(gateId, Date.now());
  if (result.applied) {
    ctx.broadcaster.broadcast({
      type: "tick",
      gateId,
      direction: fullEvent.direction,
      in: result.totals.in,
      out: result.totals.out,
      net: result.totals.in - result.totals.out,
      gateTotals: result.gateTotals,
    });
  }
}

function handleStatus(
  gateId: string,
  raw: string,
  ctx: { store: Store; broadcaster: Broadcaster; log: FastifyBaseLogger }
) {
  let state: "online" | "offline" = "offline";
  let previewUrl: string | null = null;
  try {
    const parsed = JSON.parse(raw) as { state?: string; preview_url?: string | null };
    if (parsed.state === "online") state = "online";
    previewUrl = parsed.preview_url ?? null;
  } catch {
    // tolerate empty / invalid status retained payload
  }
  const now = Date.now();
  ctx.store.upsertGateStatus(gateId, state, now, previewUrl);
  ctx.broadcaster.broadcast({
    type: "gate",
    gate: { gate_id: gateId, state, last_seen_at: now, preview_url: previewUrl },
  });
}

function handleHeartbeat(gateId: string, ctx: { store: Store; broadcaster: Broadcaster }) {
  const now = Date.now();
  const existing = ctx.store.listGates().find((g) => g.gate_id === gateId);
  ctx.store.touchGate(gateId, now);
  if (existing?.state !== "online") {
    ctx.broadcaster.broadcast({
      type: "gate",
      gate: {
        gate_id: gateId,
        state: "online",
        last_seen_at: now,
        preview_url: existing?.preview_url ?? null,
      },
    });
  }
}
