#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

echo "=== Starting MarketStream ==="

echo "[1/5] Starting Docker services..."
docker-compose up -d
echo "Waiting for Kafka to be healthy..."
until docker-compose ps kafka 2>/dev/null | grep -q "(healthy)"; do
    sleep 5
done
echo "Kafka is ready."
echo "Waiting for TimescaleDB to be healthy..."
until docker-compose ps timescaledb 2>/dev/null | grep -q "(healthy)"; do
    sleep 3
done
echo "TimescaleDB is ready."

echo "[2/5] Creating Kafka topics..."
bash scripts/create_topics.sh

echo "[3/5] Initializing database..."
uv run python -m storage.init_db

echo "[4/5] Starting backend-first pipeline..."
PIDS=()

if [[ "${MARKETSTREAM_SOURCE:-live}" == "replay" ]]; then
    if [[ -z "${MARKETSTREAM_REPLAY_PATH:-}" ]]; then
        echo "MARKETSTREAM_REPLAY_PATH is required when MARKETSTREAM_SOURCE=replay" >&2
        exit 2
    fi
    scripts/run_component.sh replay "$MARKETSTREAM_REPLAY_PATH" --speed "${MARKETSTREAM_REPLAY_SPEED:-1}" &
    FACTOR_COMPONENT="factor-engine-replay"
else
    if [[ -z "${FACTOR_BASELINE_STARTUP_MODE:-}" ]]; then
        echo "FACTOR_BASELINE_STARTUP_MODE is required for live startup" >&2
        exit 2
    fi
    scripts/run_component.sh data-source &
    FACTOR_COMPONENT="factor-engine"
fi
PIDS+=("$!")

scripts/run_component.sh "$FACTOR_COMPONENT" &
PIDS+=("$!")
scripts/run_component.sh cep &
PIDS+=("$!")

echo "Backend PIDs: ${PIDS[*]}"

echo "[5/5] Starting Streamlit dashboard..."
uv run streamlit run dashboard/app.py --server.port 8501 &
PID_DASH=$!
PIDS+=("$PID_DASH")

echo ""
echo "=== MarketStream is running ==="
echo "  Dashboard:  http://localhost:8501"
echo "  Kafka UI:   http://localhost:8080"
echo ""
echo "Press Ctrl+C to stop all components."

cleanup() {
    echo "Stopping all components..."
    kill "${PIDS[@]}" 2>/dev/null || true
    echo "Stopping Docker services..."
    docker-compose down
    echo "Done."
}
trap cleanup EXIT INT TERM

wait
