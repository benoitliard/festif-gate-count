#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

echo "==> Starting Mosquitto broker"
docker compose up -d mosquitto

echo "==> Waiting for broker on localhost:1884..."
for i in $(seq 1 50); do
  if nc -z localhost 1884 2>/dev/null; then
    echo "Broker ready"
    break
  fi
  sleep 0.2
done

echo "==> Launching all services (api, web, 4 gates)"
exec pnpm dev
