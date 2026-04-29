import { motion, AnimatePresence } from "framer-motion";
import type { GateStatus, GateTotals } from "../types";

interface Props {
  status: GateStatus;
  totals: GateTotals | undefined;
  highlight: boolean;
  highlightAt: number;
  highlightDirection: "in" | "out" | null;
}

const dotClass: Record<GateStatus["state"], string> = {
  online: "bg-emerald-400 shadow-emerald-400/40",
  stale: "bg-amber-400 shadow-amber-400/40",
  offline: "bg-rose-500 shadow-rose-500/40",
};

const stateLabel: Record<GateStatus["state"], string> = {
  online: "live",
  stale: "lat.",
  offline: "offline",
};

export function GateCard({ status, totals, highlight, highlightAt, highlightDirection }: Props) {
  const inCount = totals?.in ?? 0;
  const outCount = totals?.out ?? 0;
  const net = inCount - outCount;
  const inGlow = highlight && highlightDirection === "in";
  const outGlow = highlight && highlightDirection === "out";

  return (
    <div
      className={`relative rounded-2xl border bg-slate-900/60 p-4 transition-colors ${
        highlight ? "border-emerald-500/60" : "border-slate-800"
      }`}
    >
      <div className="mb-3 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className={`h-2 w-2 rounded-full shadow-[0_0_10px] ${dotClass[status.state]}`} />
          <span className="font-mono text-sm text-slate-100">{status.gate_id}</span>
        </div>
        <span className="font-mono text-[10px] uppercase tracking-widest text-slate-500">
          {stateLabel[status.state]}
        </span>
      </div>

      <div className="flex items-baseline justify-between">
        <div className="flex items-baseline gap-2">
          <AnimatePresence mode="popLayout">
            <motion.span
              key={`net-${highlightAt || "init"}-${net}`}
              initial={highlight ? { scale: 1.15, color: highlightDirection === "in" ? "#34d399" : "#fbbf24" } : false}
              animate={{ scale: 1, color: "#f8fafc" }}
              transition={{ duration: 0.4, ease: "easeOut" }}
              className="block tabular text-4xl font-mono font-bold leading-none"
            >
              {net}
            </motion.span>
          </AnimatePresence>
          <span className="text-[10px] uppercase tracking-widest text-slate-500">net</span>
        </div>

        <div className="flex flex-col items-end gap-1 text-xs tabular">
          <span className={`flex items-center gap-1 transition-colors ${inGlow ? "text-emerald-300" : "text-emerald-400/80"}`}>
            <span className="text-[10px]">↑</span>
            <span className="font-mono">{inCount}</span>
          </span>
          <span className={`flex items-center gap-1 transition-colors ${outGlow ? "text-amber-300" : "text-amber-400/80"}`}>
            <span className="text-[10px]">↓</span>
            <span className="font-mono">{outCount}</span>
          </span>
        </div>
      </div>
    </div>
  );
}
