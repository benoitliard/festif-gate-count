import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import type { CrowdEstimate, GateStatus } from "../types";

interface Props {
  crowds: Record<string, CrowdEstimate>;
  gates: GateStatus[];
}

function formatCount(n: number): string {
  if (n >= 10_000) return `${(n / 1000).toFixed(1)} k`;
  if (n >= 1_000) return n.toLocaleString("fr-FR").replace(/ /g, " ");
  return String(n);
}

function howFresh(ts: string): string {
  const t = Date.parse(ts);
  if (Number.isNaN(t)) return "?";
  const ageSec = Math.max(0, Math.floor((Date.now() - t) / 1000));
  if (ageSec < 60) return `${ageSec}s`;
  if (ageSec < 3600) return `${Math.floor(ageSec / 60)}min`;
  return `${Math.floor(ageSec / 3600)}h`;
}

export function CrowdSection({ crowds, gates }: Props) {
  const ids = Object.keys(crowds).sort();
  if (ids.length === 0) {
    return (
      <div className="rounded-2xl border border-slate-800 bg-slate-900/40 px-4 py-3 text-center text-sm text-slate-400">
        Aucune estimation de foule. Configure un gate <span className="font-mono">mode: crowd-density</span>.
      </div>
    );
  }

  const gateStateById = new Map(gates.map((g) => [g.gate_id, g]));

  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
      {ids.map((id) => {
        const c = crowds[id];
        if (!c) return null;
        const gate = gateStateById.get(id);
        return (
          <CrowdCard key={id} estimate={c} gate={gate} />
        );
      })}
    </div>
  );
}

function CrowdCard({ estimate, gate }: { estimate: CrowdEstimate; gate?: GateStatus }) {
  const [previewOpen, setPreviewOpen] = useState(false);
  const previewUrl = gate?.preview_url ?? null;

  return (
    <div className="rounded-2xl border border-slate-800 bg-gradient-to-b from-slate-900/80 to-slate-900/40 p-5">
      <div className="mb-2 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="h-2 w-2 rounded-full bg-fuchsia-400 shadow-[0_0_10px] shadow-fuchsia-400/40" />
          <span className="font-mono text-sm text-slate-100">{estimate.gate_id}</span>
        </div>
        <div className="flex items-center gap-2">
          {previewUrl && (
            <button
              type="button"
              onClick={() => setPreviewOpen((v) => !v)}
              className="rounded-md border border-slate-700 px-2 py-0.5 font-mono text-[10px] uppercase tracking-widest text-slate-300 hover:bg-slate-800"
            >
              {previewOpen ? "▾ live" : "▸ live"}
            </button>
          )}
          <span className="font-mono text-[10px] uppercase tracking-widest text-slate-500">
            il y a {howFresh(estimate.ts)}
          </span>
        </div>
      </div>

      <div className="flex items-baseline gap-3">
        <AnimatePresence mode="popLayout">
          <motion.span
            key={estimate.ts}
            initial={{ scale: 1.06, color: "#f0abfc" }}
            animate={{ scale: 1, color: "#f8fafc" }}
            transition={{ duration: 0.45, ease: "easeOut" }}
            className="block tabular text-5xl font-mono font-bold leading-none"
          >
            {formatCount(estimate.count)}
          </motion.span>
        </AnimatePresence>
        <span className="text-xs uppercase tracking-widest text-slate-500">
          {estimate.engine ?? "?"}
        </span>
      </div>

      {previewOpen && previewUrl && (
        <div className="mt-3 overflow-hidden rounded-lg border border-slate-800 bg-black">
          <img src={previewUrl} alt={`${estimate.gate_id} preview`} className="block w-full" loading="lazy" />
        </div>
      )}
    </div>
  );
}
