import { motion, AnimatePresence } from "framer-motion";

interface Props {
  net: number;
  in: number;
  out: number;
  lastTickAt: number;
  lastTickDirection: "in" | "out" | null;
}

export function Counter({ net, in: inCount, out, lastTickAt, lastTickDirection }: Props) {
  const tickColor = lastTickDirection === "in" ? "#34d399" : lastTickDirection === "out" ? "#fbbf24" : "#f1f5f9";
  return (
    <div className="flex flex-col items-center gap-2">
      <span className="text-sm uppercase tracking-widest text-slate-400">Présents</span>
      <div className="relative">
        <AnimatePresence mode="popLayout">
          <motion.span
            key={lastTickAt || "init"}
            initial={{ scale: 1.12, color: tickColor }}
            animate={{ scale: 1, color: "#f8fafc" }}
            transition={{ duration: 0.5, ease: "easeOut" }}
            className="block tabular text-[8.5rem] leading-none font-mono font-bold"
          >
            {net}
          </motion.span>
        </AnimatePresence>
      </div>
      <div className="flex gap-6 text-base text-slate-300 tabular">
        <span>
          <span className="text-emerald-400">↑ {inCount}</span>
          <span className="ml-1 text-slate-500">in</span>
        </span>
        <span>
          <span className="text-amber-400">↓ {out}</span>
          <span className="ml-1 text-slate-500">out</span>
        </span>
      </div>
    </div>
  );
}
