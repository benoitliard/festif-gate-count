export type GateState = "online" | "offline" | "stale";

export interface GateStatus {
  gate_id: string;
  state: GateState;
  last_seen_at: number;
}

export type ServerMsg =
  | {
      type: "snapshot";
      epoch: number;
      in: number;
      out: number;
      net: number;
      gates: GateStatus[];
      updatedAt: number;
    }
  | {
      type: "tick";
      gateId: string;
      direction: "in" | "out";
      in: number;
      out: number;
      net: number;
    }
  | { type: "gate"; gate: GateStatus }
  | { type: "reset"; epoch: number };

export interface DashboardState {
  connected: boolean;
  epoch: number;
  in: number;
  out: number;
  net: number;
  gates: GateStatus[];
  lastTickAt: number;
  lastTickDirection: "in" | "out" | null;
}
