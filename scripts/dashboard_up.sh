#!/usr/bin/env bash
# One-shot script to bring up the full dashboard stack and seed it with data.
#
# Usage:
#   ./scripts/dashboard_up.sh
#
# Prerequisites:
#   - Docker Desktop running ('docker ps' must succeed)
#   - .env with ANTHROPIC_API_KEY and FMP_API_KEY populated
#
# What it does:
#   1. Verifies docker daemon is up
#   2. Starts FastAPI in the background (uvicorn, port 8000)
#   3. Starts docker-compose (Prometheus 9090 + Grafana 3000)
#   4. Submits 5 validations to populate metrics
#   5. Polls until each is completed
#   6. Prints next-step URLs

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

echo "==> Verifying docker daemon..."
if ! docker info > /dev/null 2>&1; then
  echo "ERROR: docker daemon not reachable. Start Docker Desktop first." >&2
  exit 1
fi

echo "==> Starting FastAPI (background, port 8000)..."
nohup uv run uvicorn src.api.main:app --port 8000 > /tmp/itv-api.log 2>&1 &
API_PID=$!
echo "    pid=$API_PID  log=/tmp/itv-api.log"

# Wait for /health
for i in $(seq 1 20); do
  if curl -fsS http://localhost:8000/health > /dev/null 2>&1; then
    echo "    API ready."
    break
  fi
  sleep 1
done
if ! curl -fsS http://localhost:8000/health > /dev/null 2>&1; then
  echo "ERROR: API did not come up. Check /tmp/itv-api.log" >&2
  kill $API_PID 2>/dev/null || true
  exit 1
fi

echo ""
echo "==> Starting docker-compose stack (Prometheus + Grafana)..."
docker compose -f infra/docker-compose.yml up -d

echo ""
echo "==> Waiting 15s for Prometheus to do its first scrape..."
sleep 15

echo ""
echo "==> Submitting 5 validations to seed metrics..."
THESES=(
  '{"thesis":"AAPL trailing free cash flow margin exceeds 25%","ticker":"AAPL"}'
  '{"thesis":"NVDA quarterly revenue grew >40% YoY","ticker":"NVDA"}'
  '{"thesis":"TSM gross margin is below 50%","ticker":"TSM"}'
  '{"thesis":"MSFT does not generate revenue from cloud","ticker":"MSFT"}'
  '{"thesis":"AMZN reported zero advertising revenue in FY2024","ticker":"AMZN"}'
)
JOB_IDS=()
for body in "${THESES[@]}"; do
  jid=$(curl -fsS -X POST http://localhost:8000/validate \
    -H 'content-type: application/json' \
    -d "$body" | python3 -c 'import sys,json; print(json.load(sys.stdin)["job_id"])')
  JOB_IDS+=("$jid")
  echo "    submitted: $jid  → $body"
done

echo ""
echo "==> Polling all 5 to completion..."
for jid in "${JOB_IDS[@]}"; do
  for i in $(seq 1 60); do
    status=$(curl -fsS "http://localhost:8000/validate/$jid" \
      | python3 -c 'import sys,json; print(json.load(sys.stdin)["status"])')
    if [[ "$status" == "completed" || "$status" == "failed" ]]; then
      echo "    $jid  $status"
      break
    fi
    sleep 2
  done
done

echo ""
echo "==> Done. Dashboard URLs:"
echo "    Grafana:    http://localhost:3000  (ITV → ITV — Validator Overview)"
echo "    Prometheus: http://localhost:9090/targets  (verify 'itv' target is UP)"
echo "    API docs:   http://localhost:8000/docs"
echo ""
echo "To stop everything:"
echo "    kill $API_PID  (or kill \$(lsof -t -i:8000))"
echo "    docker compose -f infra/docker-compose.yml down"
