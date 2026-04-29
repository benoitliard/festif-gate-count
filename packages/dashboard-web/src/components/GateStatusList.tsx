import type { GateStatus } from "../types";

interface Props {
  gates: GateStatus[];
}

const stateLabel: Record<GateStatus["state"], string> = {
  online: "En ligne",
  stale: "Latence",
  offline: "Hors ligne",
};

const dotClass: Record<GateStatus["state"], string> = {
  online: "bg-emerald-400 shadow-emerald-400/40",
  stale: "bg-amber-400 shadow-amber-400/40",
  offline: "bg-rose-500 shadow-rose-500/40",
};

export function GateStatusList({ gates }: Props) {
  if (gates.length === 0) {
    return (
      <div className="rounded-2xl border border-slate-800 bg-slate-900/40 px-4 py-3 text-center text-sm text-slate-400">
        Aucun gate connecté
      </div>
    );
  }
  return (
    <ul className="flex flex-col gap-2">
      {gates.map((g) => (
        <li
          key={g.gate_id}
          className="flex items-center justify-between rounded-xl border border-slate-800 bg-slate-900/60 px-3 py-2"
        >
          <div className="flex items-center gap-3">
            <span className={`h-2.5 w-2.5 rounded-full shadow-[0_0_10px] ${dotClass[g.state]}`} />
            <span className="font-mono text-sm text-slate-100">{g.gate_id}</span>
          </div>
          <span className="text-xs uppercase tracking-wider text-slate-400">{stateLabel[g.state]}</span>
        </li>
      ))}
    </ul>
  );
}
