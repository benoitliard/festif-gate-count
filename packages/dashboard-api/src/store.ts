import Database from "better-sqlite3";
import path from "node:path";
import fs from "node:fs";

export interface GateEvent {
  event_id: string;
  gate_id: string;
  direction: "in" | "out";
  ts: string;
  epoch: number;
}

export interface Snapshot {
  epoch: number;
  in: number;
  out: number;
  net: number;
  gates: GateStatusRow[];
  updatedAt: number;
}

export interface GateStatusRow {
  gate_id: string;
  state: "online" | "offline" | "stale";
  last_seen_at: number;
}

export interface ApplyResult {
  applied: boolean;
  totals: { in: number; out: number };
}

export class Store {
  private db: Database.Database;

  constructor(dbPath: string) {
    fs.mkdirSync(path.dirname(dbPath), { recursive: true });
    this.db = new Database(dbPath);
    this.db.pragma("journal_mode = WAL");
    this.db.pragma("synchronous = NORMAL");
    this.migrate();
    this.ensureCurrentEpoch();
  }

  private migrate() {
    this.db.exec(`
      CREATE TABLE IF NOT EXISTS epochs (
        epoch       INTEGER PRIMARY KEY,
        started_at  INTEGER NOT NULL,
        reason      TEXT
      );
      CREATE TABLE IF NOT EXISTS totals (
        epoch       INTEGER PRIMARY KEY,
        in_count    INTEGER NOT NULL DEFAULT 0,
        out_count   INTEGER NOT NULL DEFAULT 0,
        updated_at  INTEGER NOT NULL,
        FOREIGN KEY (epoch) REFERENCES epochs(epoch)
      );
      CREATE TABLE IF NOT EXISTS events_seen (
        event_id    TEXT PRIMARY KEY,
        gate_id     TEXT NOT NULL,
        direction   TEXT NOT NULL,
        ts          TEXT NOT NULL,
        epoch       INTEGER NOT NULL,
        applied_at  INTEGER NOT NULL
      );
      CREATE INDEX IF NOT EXISTS idx_events_seen_epoch ON events_seen(epoch);
      CREATE TABLE IF NOT EXISTS gate_status (
        gate_id        TEXT PRIMARY KEY,
        state          TEXT NOT NULL,
        last_seen_at   INTEGER NOT NULL
      );
      CREATE TABLE IF NOT EXISTS meta (
        key   TEXT PRIMARY KEY,
        value TEXT NOT NULL
      );
    `);
  }

  private ensureCurrentEpoch() {
    const existing = this.db
      .prepare("SELECT value FROM meta WHERE key = 'current_epoch'")
      .get() as { value: string } | undefined;
    if (!existing) {
      const tx = this.db.transaction(() => {
        const now = Date.now();
        this.db.prepare("INSERT INTO epochs (epoch, started_at, reason) VALUES (1, ?, 'initial')").run(now);
        this.db.prepare("INSERT INTO totals (epoch, in_count, out_count, updated_at) VALUES (1, 0, 0, ?)").run(now);
        this.db.prepare("INSERT INTO meta (key, value) VALUES ('current_epoch', '1')").run();
      });
      tx();
    }
  }

  getCurrentEpoch(): number {
    const row = this.db.prepare("SELECT value FROM meta WHERE key = 'current_epoch'").get() as { value: string };
    return Number(row.value);
  }

  applyEvent(evt: GateEvent): ApplyResult {
    const currentEpoch = this.getCurrentEpoch();
    if (evt.epoch < currentEpoch) {
      // Stale event from a prior epoch (pre-reset). Ignore silently.
      const totals = this.getTotals(currentEpoch);
      return { applied: false, totals };
    }
    const tx = this.db.transaction(() => {
      const insert = this.db
        .prepare(
          "INSERT OR IGNORE INTO events_seen (event_id, gate_id, direction, ts, epoch, applied_at) VALUES (?, ?, ?, ?, ?, ?)"
        )
        .run(evt.event_id, evt.gate_id, evt.direction, evt.ts, evt.epoch, Date.now());
      if (insert.changes === 0) return false;
      const col = evt.direction === "in" ? "in_count" : "out_count";
      this.db
        .prepare(`UPDATE totals SET ${col} = ${col} + 1, updated_at = ? WHERE epoch = ?`)
        .run(Date.now(), currentEpoch);
      return true;
    });
    const applied = tx();
    return { applied, totals: this.getTotals(currentEpoch) };
  }

  getTotals(epoch: number): { in: number; out: number } {
    const row = this.db
      .prepare("SELECT in_count, out_count FROM totals WHERE epoch = ?")
      .get(epoch) as { in_count: number; out_count: number } | undefined;
    return { in: row?.in_count ?? 0, out: row?.out_count ?? 0 };
  }

  bumpEpoch(reason?: string): number {
    const tx = this.db.transaction(() => {
      const current = this.getCurrentEpoch();
      const next = current + 1;
      const now = Date.now();
      this.db.prepare("INSERT INTO epochs (epoch, started_at, reason) VALUES (?, ?, ?)").run(next, now, reason ?? null);
      this.db.prepare("INSERT INTO totals (epoch, in_count, out_count, updated_at) VALUES (?, 0, 0, ?)").run(next, now);
      this.db.prepare("UPDATE meta SET value = ? WHERE key = 'current_epoch'").run(String(next));
      return next;
    });
    return tx();
  }

  upsertGateStatus(gateId: string, state: "online" | "offline" | "stale", lastSeenAt: number) {
    this.db
      .prepare(
        `INSERT INTO gate_status (gate_id, state, last_seen_at) VALUES (?, ?, ?)
         ON CONFLICT(gate_id) DO UPDATE SET state = excluded.state, last_seen_at = excluded.last_seen_at`
      )
      .run(gateId, state, lastSeenAt);
  }

  touchGate(gateId: string, at: number) {
    this.db
      .prepare(
        `INSERT INTO gate_status (gate_id, state, last_seen_at) VALUES (?, 'online', ?)
         ON CONFLICT(gate_id) DO UPDATE SET state = 'online', last_seen_at = excluded.last_seen_at`
      )
      .run(gateId, at);
  }

  listGates(): GateStatusRow[] {
    return this.db
      .prepare("SELECT gate_id, state, last_seen_at FROM gate_status ORDER BY gate_id")
      .all() as GateStatusRow[];
  }

  refreshStaleness(staleAfterMs: number, offlineAfterMs: number): GateStatusRow[] {
    const now = Date.now();
    const changed: GateStatusRow[] = [];
    const rows = this.listGates();
    for (const row of rows) {
      const age = now - row.last_seen_at;
      let newState: "online" | "offline" | "stale" = row.state;
      if (age > offlineAfterMs) newState = "offline";
      else if (age > staleAfterMs) newState = "stale";
      else newState = "online";
      if (newState !== row.state) {
        this.db.prepare("UPDATE gate_status SET state = ? WHERE gate_id = ?").run(newState, row.gate_id);
        changed.push({ ...row, state: newState });
      }
    }
    return changed;
  }

  getSnapshot(): Snapshot {
    const epoch = this.getCurrentEpoch();
    const totals = this.getTotals(epoch);
    return {
      epoch,
      in: totals.in,
      out: totals.out,
      net: totals.in - totals.out,
      gates: this.listGates(),
      updatedAt: Date.now(),
    };
  }
}
