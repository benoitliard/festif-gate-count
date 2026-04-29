import { useDashboardSocket } from "./hooks/useDashboardSocket";
import { Counter } from "./components/Counter";
import { GateStatusList } from "./components/GateStatusList";
import { HistorySection } from "./components/HistorySection";
import { ResetButton } from "./components/ResetButton";

export function App() {
  const state = useDashboardSocket();

  return (
    <main className="min-h-full bg-slate-950 text-slate-100">
      <div className="mx-auto flex min-h-full max-w-md flex-col px-4 pb-8 pt-6">
        <header className="flex items-center justify-between">
          <h1 className="text-base font-semibold tracking-tight">
            <span className="text-emerald-400">●</span> Gate Counter
          </h1>
          <span
            className={`font-mono text-[11px] uppercase tracking-widest ${
              state.connected ? "text-emerald-400" : "text-rose-400"
            }`}
          >
            {state.connected ? "live" : "offline"}
          </span>
        </header>

        <section className="my-10 flex flex-col items-center">
          <Counter
            net={state.net}
            in={state.in}
            out={state.out}
            lastTickAt={state.lastTickAt}
            lastTickDirection={state.lastTickDirection}
          />
          <span className="mt-3 text-[11px] uppercase tracking-widest text-slate-500">
            epoch #{state.epoch}
          </span>
        </section>

        <section className="mb-8">
          <h2 className="mb-2 text-xs font-semibold uppercase tracking-widest text-slate-400">
            Gates ({state.gates.length})
          </h2>
          <GateStatusList
            gates={state.gates}
            gateTotals={state.gateTotals}
            lastTickAt={state.lastTickAt}
            lastTickGateId={state.lastTickGateId}
            lastTickDirection={state.lastTickDirection}
          />
        </section>

        <section className="mb-8">
          <h2 className="mb-2 text-xs font-semibold uppercase tracking-widest text-slate-400">
            Historique
          </h2>
          <HistorySection epoch={state.epoch} lastTickAt={state.lastTickAt} />
        </section>

        <section className="mt-auto">
          <ResetButton />
        </section>
      </div>
    </main>
  );
}
