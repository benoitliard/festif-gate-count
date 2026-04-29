import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

export const config = {
  port: Number(process.env.PORT ?? 3101),
  host: process.env.HOST ?? "0.0.0.0",
  mqttUrl: process.env.MQTT_URL ?? "mqtt://localhost:1884",
  resetToken: process.env.RESET_TOKEN ?? "dev-reset-token",
  staleAfterMs: Number(process.env.STALE_AFTER_MS ?? 15_000),
  offlineAfterMs: Number(process.env.OFFLINE_AFTER_MS ?? 30_000),
  dbPath: process.env.DB_PATH ?? path.resolve(__dirname, "../data/dashboard.db"),
} as const;
