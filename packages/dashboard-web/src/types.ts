export type GateState = "online" | "offline" | "stale";

export interface GateStatus {
  gate_id: string;
  state: GateState;
  last_seen_at: number;
}

export interface GateTotals {
  gate_id: string;
  in: number;
  out: number;
}

export type ServerMsg =
  | {
      type: "snapshot";
      epoch: number;
      in: number;
      out: number;
      net: number;
      gates: GateStatus[];
      gateTotals: GateTotals[];
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
  | { type: "gate"; gate: GateStatus }
  | { type: "reset"; epoch: number };

export interface DashboardState {
  connected: boolean;
  epoch: number;
  in: number;
  out: number;
  net: number;
  gates: GateStatus[];
  gateTotals: Record<string, GateTotals>;
  lastTickAt: number;
  lastTickDirection: "in" | "out" | null;
  lastTickGateId: string | null;
}
