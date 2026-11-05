#!/usr/bin/env bash
# All-in-one process supervisor for free-tier hosts (Render web service).
# Starts Fayda/CBS sandboxes + queue worker + cleanup + API in one dyno.
set -euo pipefail
cd "$(dirname "$0")/.."

normalize_database_url() {
  local url="${DATABASE_URL:-}"
  if [[ -z "$url" ]]; then
    echo "DATABASE_URL is required" >&2
    exit 1
  fi
  url="${url/postgres:\/\//postgresql:\/\/}"
  if [[ "$url" != postgresql+asyncpg://* ]]; then
    url="${url/postgresql:\/\//postgresql+asyncpg:\/\/}"
  fi
  export DATABASE_URL="$url"
}

normalize_database_url

export FAYDA_SANDBOX_URL="${FAYDA_SANDBOX_URL:-http://127.0.0.1:8081/fayda/v2}"
export BANK_CBS_SANDBOX_URL="${BANK_CBS_SANDBOX_URL:-http://127.0.0.1:8082/cbs/v1}"
export FAYDA_API_KEY="${FAYDA_API_KEY:-dev-fayda-key}"
export BANK_API_KEY="${BANK_API_KEY:-dev-bank-key}"
export JWT_SECRET_KEY="${JWT_SECRET_KEY:-change-me-jwt-secret-min-32-chars-long!!}"
export HMAC_SALT_KEY="${HMAC_SALT_KEY:-change-me-hmac-salt-min-32-chars-long!!}"
export AES_MASTER_KEY="${AES_MASTER_KEY:-01234567890123456789012345678901}"
export PORT="${PORT:-8000}"

echo "[cloud] Applying migrations..."
python -m alembic upgrade head

echo "[cloud] Ensuring ORM tables exist (create_all safety net)..."
python - <<'PY'
import asyncio
from src.models.base import init_models
asyncio.run(init_models(retries=8, delay=2.0))
print("[cloud] schema ready")
PY

echo "[cloud] Waiting for Redis..."
python - <<'PY'
import asyncio, os, sys
import redis.asyncio as redis

async def wait_redis():
    url = os.environ["REDIS_URL"]
    client = redis.from_url(url, socket_connect_timeout=5.0)
    for i in range(30):
        try:
            if await client.ping():
                print("[cloud] redis ready")
                await client.aclose()
                return
        except Exception as exc:
            print(f"[cloud] redis wait {i+1}/30: {exc}")
            await asyncio.sleep(1)
    await client.aclose()
    sys.exit("Redis not reachable")

asyncio.run(wait_redis())
PY

echo "[cloud] Starting Fayda sandbox on :8081"
PORT=8081 python sandbox/fayda_sandbox.py &
FAYDA_PID=$!

echo "[cloud] Starting CBS sandbox on :8082"
PORT=8082 python sandbox/bank_cbs_sandbox.py &
CBS_PID=$!

sleep 2

echo "[cloud] Starting bank submission worker"
python -m src.workers.bank_submission &
WORKER_PID=$!

echo "[cloud] Starting cleanup worker"
python -m src.workers.cleanup &
CLEANUP_PID=$!

shutdown() {
  echo "[cloud] Shutting down..."
  kill "$WORKER_PID" "$CLEANUP_PID" "$FAYDA_PID" "$CBS_PID" 2>/dev/null || true
  wait 2>/dev/null || true
}
trap shutdown EXIT INT TERM

echo "[cloud] Starting API on :$PORT"
exec python -m uvicorn src.api.main:app --host 0.0.0.0 --port "$PORT"
