import { useState } from "react";

const TOKEN_KEY = "gate-counter:reset-token";

export function ResetButton() {
  const [open, setOpen] = useState(false);
  const [token, setToken] = useState(() => localStorage.getItem(TOKEN_KEY) ?? "");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function doReset() {
    setPending(true);
    setError(null);
    try {
      const res = await fetch("/api/reset", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ token, reason: "manual" }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        setError(body.error ?? `HTTP ${res.status}`);
        setPending(false);
        return;
      }
      localStorage.setItem(TOKEN_KEY, token);
      setOpen(false);
      setPending(false);
    } catch (err) {
      setError((err as Error).message);
      setPending(false);
    }
  }

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="w-full rounded-xl border border-rose-500/40 bg-rose-500/10 px-4 py-3 text-sm font-semibold uppercase tracking-wider text-rose-300 transition hover:bg-rose-500/20 active:scale-[0.99]"
      >
        Réinitialiser le compteur
      </button>
      {open && (
        <div className="fixed inset-0 z-10 flex items-end justify-center bg-black/60 p-4 sm:items-center">
          <div className="w-full max-w-sm rounded-2xl border border-slate-800 bg-slate-900 p-5 shadow-xl">
            <h2 className="mb-1 text-lg font-semibold text-slate-100">Confirmer le reset</h2>
            <p className="mb-4 text-sm text-slate-400">
              Tous les compteurs vont être remis à zéro. Les gates hors ligne flush leurs events bufferés.
            </p>
            <label className="mb-3 block text-xs uppercase tracking-wider text-slate-400">
              Token admin
              <input
                type="password"
                value={token}
                onChange={(e) => setToken(e.target.value)}
                className="mt-1 block w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100 outline-none ring-rose-500/30 focus:ring-2"
                placeholder="dev-reset-token"
              />
            </label>
            {error && <div className="mb-3 rounded-lg bg-rose-500/10 px-3 py-2 text-xs text-rose-300">{error}</div>}
            <div className="flex gap-2">
              <button
                type="button"
                onClick={() => setOpen(false)}
                className="flex-1 rounded-lg border border-slate-700 px-4 py-2 text-sm text-slate-300 hover:bg-slate-800"
              >
                Annuler
              </button>
              <button
                type="button"
                onClick={doReset}
                disabled={pending || !token}
                className="flex-1 rounded-lg bg-rose-500 px-4 py-2 text-sm font-semibold text-white disabled:opacity-50"
              >
                {pending ? "..." : "Confirmer"}
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
