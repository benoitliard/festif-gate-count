# Gate Counter — Festival POC

Système de comptage temps-réel pour festival : N gates publient leurs entrées/sorties via MQTT, un dashboard web affiche le total live.

**Tout tourne en local sur Mac** — zéro hardware Raspberry Pi requis pour ce POC.

## Architecture

```
gate-agent (Python) ──MQTT QoS1──▶ Mosquitto (Docker) ──▶ dashboard-api (Node) ──WS──▶ dashboard-web (React)
       │
       └─ SQLite buffer local (replay au reconnect)
```

- **Fault tolerance** : chaque gate buffer ses events sur disque (SQLite WAL). Si le broker tombe, les events sont replay au retour.
- **Idempotence** : événements identifiés par ULID, dédupliqués côté serveur (`INSERT OR IGNORE`).
- **Reset** : bouton admin → bump d'un epoch monotone diffusé via topic retained MQTT. Les events des epochs antérieurs sont silencieusement flush.
- **LWT + heartbeat** : statut online/stale/offline en moins de 30s après crash.

## Stack

| Composant | Techno |
|---|---|
| Broker | Mosquitto 2.x (Docker) sur ports `1884` (TCP) / `9003` (WS) |
| Gate agent | Python 3.12 + `paho-mqtt` + `opencv-python` + `fastapi` (mode manual) |
| Dashboard API | Node 20 + Fastify 5 + `better-sqlite3` + `mqtt.js` + `@fastify/websocket` |
| Dashboard web | Vite + React 18 + Tailwind + framer-motion |

## Prérequis

- Docker Desktop
- Node 20+ (`nvm use 20`)
- pnpm 10
- Python 3.12 + [uv](https://docs.astral.sh/uv/)

## Quickstart

```bash
# 1. Installer les deps
pnpm install
cd packages/gate-agent && uv venv --python 3.12 && uv pip install -e ".[dev]" && cd ../..

# 2. Tout démarrer
./scripts/dev.sh
```

Ensuite :
- Dashboard : <http://localhost:5174/>
- Triggers manuels :
  - `gate-entry-1` → <http://localhost:8001/>
  - `gate-entry-2` → <http://localhost:8002/>
  - `gate-exit-1`  → <http://localhost:8003/>
  - `gate-exit-2`  → <http://localhost:8004/>
- API : <http://localhost:3101/api/status>
- Token reset par défaut : `dev-reset-token` (override via `RESET_TOKEN=`)

## Modes de gate

Chaque gate est piloté par un fichier YAML dans `packages/gate-agent/configs/`.

| Mode | Description |
|---|---|
| `manual` | Mini-serveur HTTP avec boutons IN/OUT — idéal pour démo rapide ou tests fault-tolerance |
| `video-file` | Lit un `.mp4` en boucle, OpenCV MOG2 ou YOLO + line-crossing |
| `webcam` | Webcam Mac (USB ou built-in), OpenCV MOG2 ou YOLO + line-crossing |
| `crowd-density` | Snapshot périodique → estimation **gauge** "il y a ≈14 800 devant la scène" |

### Crowd-density avec CSRNet (recommandé pour foules denses)

YOLO compte mal les foules très denses (têtes < 15 px, occlusion, contre-jour).
Pour ce cas il faut un modèle "density map" comme CSRNet.

```bash
# 1. Télécharger des weights CSRNet pretrained (ShanghaiTech Part B)
cd packages/gate-agent
mkdir -p data
curl -L -o data/partBmodel_best.pth.tar \
  "https://huggingface.co/BedirYilmaz/crowdguessr-csrnet/resolve/main/partBmodel_best.pth.tar"

# 2. Exporter en ONNX (single-file, ~62 MB)
uv run python scripts/export_csrnet_onnx.py \
  --weights data/partBmodel_best.pth.tar \
  --output ../../assets/csrnet.onnx \
  --input-size 768 1024

# 3. Pointer une config crowd-density vers le modèle
#    (configs/gate-crowd-stage.yaml en a déjà un exemple)

# 4. Lancer
pnpm gate:crowd-stage
```

L'inférence tourne sur **CoreML** (Apple Silicon) ou CPU — typiquement 200-500 ms par image.
Le compte estimé apparaît dans la section **Foules** du dashboard, animé à chaque update.

> ℹ️ CSRNet est entraîné sur ShanghaiTech B (foules urbaines diurnes). Il sous-compte
> les festivals nocturnes très denses d'environ 30-50%. Pour de la précision
> production, fine-tune sur un dataset festival ou applique un facteur de
> calibration empirique mesuré sur place.

Exemple de lancement webcam :

```bash
cd packages/gate-agent
uv run python -m gate_agent --config configs/gate-webcam.example.yaml
```

> ⚠️ La première exécution déclenche la popup macOS pour la permission Caméra.

## Schéma MQTT

| Topic | QoS | Retained | Direction |
|---|---|---|---|
| `gates/{gate_id}/events` | 1 | non | gate → backend |
| `gates/{gate_id}/status` | 1 | **oui** (LWT) | gate → broker |
| `gates/{gate_id}/heartbeat` | 0 | non | gate → broker |
| `dashboard/control/epoch` | 1 | **oui** | backend → gates |

Payload event :
```json
{"event_id":"01J...","gate_id":"gate-entry-1","direction":"in","ts":"...","epoch":1,"source":"manual","schema_version":1}
```

## Vérification E2E (manuel)

### Smoke test

1. `./scripts/dev.sh`, ouvre <http://localhost:5174>.
2. Compteur à 0, 4 gates "online".
3. Clique IN x3 sur <http://localhost:8001/>, OUT x1 sur <http://localhost:8003/>.
4. Compteur dashboard : `↑3 ↓1`, net = 2, animation pulse.

### Buffering & replay

1. État initial : compteur = 0.
2. `pnpm broker:down` (ou `docker compose down`).
3. Au bout de ~30s, gates → "offline" sur dashboard.
4. Clique IN x5 sur gate-entry-1 (les events sont bufferés en SQLite).
5. Vérifie : `sqlite3 packages/gate-agent/data/gate-entry-1.db "SELECT count(*) FROM pending_events WHERE sent=0"` → 5.
6. `pnpm broker:up`. En 5-10s : gates back online, compteur saute à 5.
7. Re-vérifie SQLite : 0 events `sent=0`. **Aucune perte, aucun double-comptage.**

### Idempotence

```bash
# Re-publish le même event 3 fois
docker run --rm --network host eclipse-mosquitto:2.0 mosquitto_pub -h localhost -p 1884 \
  -t gates/test/events -q 1 \
  -m '{"event_id":"01J5K2X9F8H3M4QY9R7Z0VN2WB","gate_id":"test","direction":"in","ts":"2026-04-29T13:42:11Z","epoch":1,"source":"test","schema_version":1}'
```

Compteur : `+1` (pas +3).

### Reset avec gate offline

1. Compteur in=10. `kill -STOP <pid de gate-entry-1>`.
2. Reset depuis dashboard → compteur = 0, epoch = 2.
3. `kill -CONT <pid>` → compteur reste à 0 (events pré-reset flushés silencieusement).
4. Trigger 1 event neuf → compteur = 1.

## Scripts

| Commande | Description |
|---|---|
| `pnpm dev` | Lance api + web + 4 gates manual via `concurrently` |
| `pnpm broker:up` / `broker:down` / `broker:reset` | Manage Mosquitto |
| `pnpm dev:api` / `dev:web` | Lance API ou web seul |
| `pnpm gate:entry-1` (idem `entry-2`, `exit-1`, `exit-2`) | Lance un gate seul |
| `cd packages/gate-agent && uv run pytest` | Tests unitaires du buffer |

## Layout

```
gate-counter/
├── docker-compose.yml          # Mosquitto sur 1884/9003
├── infra/mosquitto/             # config + persistence
├── packages/
│   ├── gate-agent/             # Python 3.12 — gate process
│   ├── dashboard-api/          # Node + Fastify — broker → WS
│   └── dashboard-web/          # Vite + React mobile-first
└── scripts/dev.sh
```

## Hors-scope (à venir)

- Pas d'auth (token simple env var pour reset).
- Pas de TLS MQTT (`allow_anonymous` en POC local).
- Pas de packaging Raspberry Pi (architecture pure-Python + MQTT + SQLite portera trivialement).
- Pas d'historique/timeline graphique.
