export type GateState = "online" | "offline" | "stale";

export interface GateStatus {
  gate_id: string;
  state: GateState;
  last_seen_at: number;
  preview_url: string | null;
}

export interface DayTotal {
  date: string;
  in: number;
  out: number;
  net: number;
  events: number;
}

export interface CrowdEstimate {
  gate_id: string;
  count: number;
  confidence: string | null;
  engine: string | null;
  ts: string;
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
      crowds: (CrowdEstimate & { applied_at: number })[];
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
      confidence: string | null;
      engine: string | null;
      ts: string;
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
  crowds: Record<string, CrowdEstimate>;
  lastTickAt: number;
  lastTickDirection: "in" | "out" | null;
  lastTickGateId: string | null;
}
