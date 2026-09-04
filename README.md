# osi-aggregator-tinyllm

Dockerized Python aggregator that pulls **passive** [osirisai.live](https://osirisai.live/docs) read APIs, consolidates snapshots in Python, then runs **broad â†’ fine** analysis with a local tiny LLM via [Ollama](https://ollama.com).

This does **not** fork the OSIRIS Next.js app. It is a research toolset alongside the mobile shells in this monorepo.

## Architecture

```
osirisai.live /api  â†’  worker (ingest + consolidate)  â†’  Ollama (broad/fine)
                              â†•
                         ./data/{snapshots,reports}
                              â†•
                         FastAPI :8787
```

## Responsible use

- **Passive feeds only** in v1. Active RECON routes (`/api/scanner`, `/api/osint/sweep`, CCTV proxies, SDK ingest writes, cloud `/api/ai/*`) are deny-listed in code.
- Only use OSINT lookups against targets you own or have written authorization to investigate.
- Poll no faster than feed TTLs (~45â€“60s). Default interval is **120s**.

## Quick start (Docker)

Prerequisites: Docker Desktop (or Engine + Compose) with network access to pull images and reach `osirisai.live`.

```bash
cd osi-aggregator-tinyllm   # or this repo root
cp .env.example .env
docker compose up --build -d
```

First boot pulls `qwen2.5:1.5b` into the Ollama volume (can take several minutes).

| Service | Host port |
|---------|-----------|
| FastAPI | `8787` |
| Ollama  | `11435` → container `11434` (avoids clash with another local Ollama on `11434`) |

### One-shot run (no schedule)

```bash
docker compose run --rm -e WORKER_MODE=once worker python -m osi_sandbox.worker --once --mode full
```

**Ingest only** (no Ollama image pull â€” recommended first smoke test):

```bash
docker compose run --rm --no-deps -e WORKER_MODE=once worker \
  python -m osi_sandbox.worker --once --mode ingest
```

> First full `docker compose up` pulls the Ollama image (multiâ€‘GB) and downloads `qwen2.5:1.5b`. Use `--no-deps` + `--mode ingest` until you are ready for local LLM analysis.

### API

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/health` | Liveness |
| GET | `/status` | Current / last run |
| GET | `/feeds` | Catalog + deny-list |
| POST | `/run` | `{ "mode": "full", "focus": "earthquakes", "wait": false }` |
| GET | `/reports/latest` | Latest consolidated + markdown |
| GET | `/reports/{run_id}` | Specific run |
| GET | `/reports/{run_id}/broad.md` | Broad briefing |
| GET | `/reports/{run_id}/fine.md` | Fine briefing |

```bash
curl -s http://localhost:8787/health
curl -s -X POST http://localhost:8787/run -H "content-type: application/json" -d "{\"mode\":\"full\",\"wait\":true}"
curl -s http://localhost:8787/reports/latest | head
```

## Configuration

See [`.env.example`](.env.example).

| Variable | Default | Notes |
|----------|---------|-------|
| `OSIRIS_BASE_URL` | `https://osirisai.live` | Point at a self-hosted instance later |
| `OLLAMA_MODEL` | `qwen2.5:1.5b` | Tiny model; swap freely |
| `POLL_INTERVAL_SEC` | `120` | Minimum enforced in settings: 60 |
| `WORKER_MODE` | `schedule` | `once` for single run |
| `CORE_FEEDS` | (all core) | Comma-separated feed ids |
| `TOP_N` | `12` | Items kept per feed after consolidation |
| `SANDBOX_API_PORT` | `8787` | Host port for FastAPI |

## Local Python (without Docker)

```bash
cd osi-sandbox
python -m venv .venv
# Windows: .venv\Scripts\activate
source .venv/bin/activate
pip install -r requirements.txt
pip install -e .
cp .env.example .env
# Start Ollama locally and: ollama pull qwen2.5:1.5b
set DATA_DIR=./data
python -m osi_sandbox.worker --once --mode ingest
```

`ingest` mode skips the LLM and only writes snapshots + `consolidated.json`.

## Outputs

```
data/
  snapshots/{run_id}/
    health.json, stats.json, â€¦, consolidated.json
  reports/{run_id}/
    broad.md, fine.md, meta.json
  status.json
```

## Feed pack (v1)

**System:** `/api/health`, `/api/stats`  
**Core:** earthquakes, fires, conflicts, news, cyber-threats, maritime, flights, markets, space-weather  
**On-demand (API catalog only for now):** region-dossier, gdelt, cyber-attacks, passive OSINT lookups

## Layout

```
osi-sandbox/
  docker-compose.yml
  Dockerfile
  prompts/{broad,fine}.md
  src/osi_sandbox/
    client.py feeds.py consolidate.py analyze.py
    store.py pipeline.py worker.py api.py config.py
```

