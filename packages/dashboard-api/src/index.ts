import Fastify from "fastify";
import websocket from "@fastify/websocket";
import cors from "@fastify/cors";
import { config } from "./config.js";
import { Store } from "./store.js";
import { Broadcaster } from "./ws.js";
import { startMqtt } from "./mqtt.js";

async function main() {
  const fastify = Fastify({
    logger: { transport: { target: "pino-pretty", options: { colorize: true } } },
  });
  await fastify.register(cors, { origin: true });
  await fastify.register(websocket);

  const store = new Store(config.dbPath);
  const broadcaster = new Broadcaster();
  const bus = startMqtt({
    url: config.mqttUrl,
    store,
    broadcaster,
    log: fastify.log,
  });

  // Periodic staleness sweep
  setInterval(() => {
    const changed = store.refreshStaleness(config.staleAfterMs, config.offlineAfterMs);
    for (const gate of changed) {
      broadcaster.broadcast({ type: "gate", gate });
    }
  }, 5000);

  fastify.get("/healthz", async () => ({ ok: true }));

  fastify.get("/api/status", async () => store.getSnapshot());

  fastify.get("/api/history", async () => ({ days: store.getHistoryByDate() }));

  fastify.get("/api/crowds", async () => ({ crowds: store.listCrowdLatest() }));

  fastify.get<{ Params: { gateId: string }; Querystring: { limit?: string } }>(
    "/api/crowds/:gateId/history",
    async (req) => {
      const limit = req.query.limit ? Math.min(1000, Math.max(1, Number(req.query.limit))) : 200;
      return { history: store.getCrowdHistory(req.params.gateId, limit) };
    }
  );

  fastify.get("/api/triggers", async () => {
    const gates = store.listGates();
    return {
      gates: gates.map((g) => ({
        gate_id: g.gate_id,
        state: g.state,
        last_seen_at: g.last_seen_at,
      })),
    };
  });

  fastify.post<{ Body: { token?: string; reason?: string } }>("/api/reset", async (req, reply) => {
    const token = req.body?.token;
    if (!token || token !== config.resetToken) {
      return reply.code(401).send({ error: "invalid_token" });
    }
    const newEpoch = store.bumpEpoch(req.body?.reason);
    bus.publishEpoch(newEpoch);
    broadcaster.broadcast({ type: "reset", epoch: newEpoch });
    return { epoch: newEpoch };
  });

  fastify.get("/ws", { websocket: true }, (socket) => {
    broadcaster.add(socket);
    broadcaster.sendSnapshot(socket, store.getSnapshot());
  });

  try {
    await fastify.listen({ port: config.port, host: config.host });
    fastify.log.info(
      { port: config.port, mqtt: config.mqttUrl, db: config.dbPath },
      "Dashboard API up"
    );
  } catch (err) {
    fastify.log.error(err);
    process.exit(1);
  }
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
