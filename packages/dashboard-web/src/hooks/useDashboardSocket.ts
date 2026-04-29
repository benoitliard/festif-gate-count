import { useEffect, useRef, useState } from "react";
import type { DashboardState, ServerMsg } from "../types";

const initial: DashboardState = {
  connected: false,
  epoch: 0,
  in: 0,
  out: 0,
  net: 0,
  gates: [],
  gateTotals: {},
  lastTickAt: 0,
  lastTickDirection: null,
  lastTickGateId: null,
};

const BACKOFF_MS = [1000, 2000, 5000, 10000, 10000];

export function useDashboardSocket(): DashboardState {
  const [state, setState] = useState<DashboardState>(initial);
  const wsRef = useRef<WebSocket | null>(null);
  const attemptRef = useRef(0);
  const timerRef = useRef<number | null>(null);
  const closedRef = useRef(false);

  useEffect(() => {
    closedRef.current = false;

    function connect() {
      const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
      const url = `${proto}//${window.location.host}/ws`;
      const ws = new WebSocket(url);
      wsRef.current = ws;

      ws.onopen = () => {
        attemptRef.current = 0;
        setState((s) => ({ ...s, connected: true }));
      };

      ws.onmessage = (event) => {
        try {
          const msg = JSON.parse(event.data) as ServerMsg;
          setState((s) => reduce(s, msg));
        } catch {
          // ignore malformed
        }
      };

      ws.onclose = () => {
        setState((s) => ({ ...s, connected: false }));
        if (closedRef.current) return;
        const delay = BACKOFF_MS[Math.min(attemptRef.current, BACKOFF_MS.length - 1)];
        attemptRef.current += 1;
        timerRef.current = window.setTimeout(connect, delay);
      };

      ws.onerror = () => {
        ws.close();
      };
    }

    connect();

    return () => {
      closedRef.current = true;
      if (timerRef.current) window.clearTimeout(timerRef.current);
      wsRef.current?.close();
    };
  }, []);

  return state;
}

function reduce(s: DashboardState, msg: ServerMsg): DashboardState {
  switch (msg.type) {
    case "snapshot": {
      const totalsMap = Object.fromEntries(msg.gateTotals.map((t) => [t.gate_id, t]));
      return {
        ...s,
        epoch: msg.epoch,
        in: msg.in,
        out: msg.out,
        net: msg.net,
        gates: msg.gates,
        gateTotals: totalsMap,
      };
    }
    case "tick":
      return {
        ...s,
        in: msg.in,
        out: msg.out,
        net: msg.net,
        gateTotals: { ...s.gateTotals, [msg.gateTotals.gate_id]: msg.gateTotals },
        lastTickAt: Date.now(),
        lastTickDirection: msg.direction,
        lastTickGateId: msg.gateId,
      };
    case "gate": {
      const others = s.gates.filter((g) => g.gate_id !== msg.gate.gate_id);
      return { ...s, gates: [...others, msg.gate].sort((a, b) => a.gate_id.localeCompare(b.gate_id)) };
    }
    case "reset":
      return {
        ...s,
        epoch: msg.epoch,
        in: 0,
        out: 0,
        net: 0,
        gateTotals: {},
        lastTickAt: Date.now(),
        lastTickDirection: null,
        lastTickGateId: null,
      };
    default:
      return s;
  }
}
