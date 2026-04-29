import type { GateStatus, GateTotals } from "../types";
import { GateCard } from "./GateCard";

interface Props {
  gates: GateStatus[];
  gateTotals: Record<string, GateTotals>;
  lastTickAt: number;
  lastTickGateId: string | null;
  lastTickDirection: "in" | "out" | null;
}

export function GateStatusList({ gates, gateTotals, lastTickAt, lastTickGateId, lastTickDirection }: Props) {
  if (gates.length === 0) {
    return (
      <div className="rounded-2xl border border-slate-800 bg-slate-900/40 px-4 py-3 text-center text-sm text-slate-400">
        Aucun gate connecté
      </div>
    );
  }
  // include any gates that have totals but no status row (defensive)
  const knownIds = new Set(gates.map((g) => g.gate_id));
  const phantomGates = Object.keys(gateTotals).filter((id) => !knownIds.has(id));
  const allRows = [
    ...gates,
    ...phantomGates.map<GateStatus>((id) => ({ gate_id: id, state: "offline", last_seen_at: 0, preview_url: null })),
  ];

  return (
    <div className="grid grid-cols-1 gap-2">
      {allRows.map((g) => {
        const isHighlight = g.gate_id === lastTickGateId && Date.now() - lastTickAt < 1500;
        return (
          <GateCard
            key={g.gate_id}
            status={g}
            totals={gateTotals[g.gate_id]}
            highlight={isHighlight}
            highlightAt={lastTickAt}
            highlightDirection={lastTickDirection}
          />
        );
      })}
    </div>
  );
}
