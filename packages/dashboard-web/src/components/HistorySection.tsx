import { useEffect, useState } from "react";
import type { DayTotal } from "../types";

interface Props {
  epoch: number;
  lastTickAt: number;
}

const MONTHS_FR = ["jan", "fév", "mar", "avr", "mai", "juin", "juil", "août", "sep", "oct", "nov", "déc"];

function formatDate(iso: string): string {
  const [y, m, d] = iso.split("-").map(Number);
  if (!y || !m || !d) return iso;
  return `${d} ${MONTHS_FR[m - 1]} ${y}`;
}

function isToday(iso: string): boolean {
  const today = new Date();
  const tz = today.getTimezoneOffset();
  const local = new Date(today.getTime() - tz * 60_000);
  const todayIso = local.toISOString().slice(0, 10);
  return iso === todayIso;
}

export function HistorySection({ epoch, lastTickAt }: Props) {
  const [days, setDays] = useState<DayTotal[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Coalesce ticks: only refresh once per 3s window
  const tickBucket = Math.floor(lastTickAt / 3000);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      setLoading(true);
      setError(null);
      try {
        const res = await fetch("/api/history");
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = (await res.json()) as { days: DayTotal[] };
        if (!cancelled) setDays(data.days);
      } catch (err) {
        if (!cancelled) setError((err as Error).message);
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    load();
    return () => {
      cancelled = true;
    };
  }, [epoch, tickBucket]);

  return (
    <div>
      {loading && days.length === 0 && (
        <div className="rounded-2xl border border-slate-800 bg-slate-900/40 px-4 py-3 text-center text-sm text-slate-400">
          Chargement...
        </div>
      )}
      {error && (
        <div className="rounded-2xl border border-rose-500/40 bg-rose-500/10 px-4 py-3 text-sm text-rose-300">
          {error}
        </div>
      )}
      {!error && days.length === 0 && !loading && (
        <div className="rounded-2xl border border-slate-800 bg-slate-900/40 px-4 py-3 text-center text-sm text-slate-400">
          Aucun événement enregistré
        </div>
      )}
      <ul className="flex flex-col gap-2">
        {days.map((d) => (
          <li
            key={d.date}
            className={`rounded-xl border bg-slate-900/60 px-3 py-2.5 ${
              isToday(d.date) ? "border-emerald-500/40" : "border-slate-800"
            }`}
          >
            <div className="flex items-baseline justify-between">
              <div className="flex items-baseline gap-2">
                <span className="font-mono text-sm text-slate-100">{formatDate(d.date)}</span>
                {isToday(d.date) && (
                  <span className="rounded-full bg-emerald-500/20 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-widest text-emerald-300">
                    today
                  </span>
                )}
              </div>
              <span className="font-mono tabular text-2xl font-bold text-slate-100">{d.net}</span>
            </div>
            <div className="mt-1 flex justify-end gap-3 font-mono text-xs tabular text-slate-400">
              <span className="text-emerald-400/80">↑ {d.in}</span>
              <span className="text-amber-400/80">↓ {d.out}</span>
              <span className="text-slate-500">· {d.events} ev.</span>
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}
