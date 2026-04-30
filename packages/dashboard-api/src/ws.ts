import type { WebSocket } from "@fastify/websocket";
import type { Snapshot, GateStatusRow, GateTotals, CrowdEstimate } from "./store.js";

export type ServerMsg =
  | {
      type: "snapshot";
      epoch: number;
      in: number;
      out: number;
      net: number;
      gates: GateStatusRow[];
      gateTotals: GateTotals[];
      crowds: CrowdEstimate[];
      updatedAt: number;
    }
  | {
      type: "tick";
      gateId: string;
      direction: "in" | "out";
      in: number;
      out: number;
      net: number;
      gateTotals: GateTotals;
    }
  | {
      type: "crowd";
      gateId: string;
      count: number;
      raw_count: number;
      factor: number;
      confidence: string | null;
      engine: string | null;
      ts: string;
    }
  | {
      type: "calibration";
      gateId: string;
      factor: number;
    }
  | { type: "gate"; gate: GateStatusRow }
  | { type: "reset"; epoch: number };

export class Broadcaster {
  private clients = new Set<WebSocket>();

  add(ws: WebSocket) {
    this.clients.add(ws);
    ws.on("close", () => this.clients.delete(ws));
    ws.on("error", () => this.clients.delete(ws));
  }

  send(ws: WebSocket, msg: ServerMsg) {
    try {
      ws.send(JSON.stringify(msg));
    } catch {
      this.clients.delete(ws);
    }
  }

  broadcast(msg: ServerMsg) {
    const payload = JSON.stringify(msg);
    for (const client of this.clients) {
      try {
        client.send(payload);
      } catch {
        this.clients.delete(client);
      }
    }
  }

  sendSnapshot(ws: WebSocket, snap: Snapshot) {
    this.send(ws, { type: "snapshot", ...snap });
  }
}
