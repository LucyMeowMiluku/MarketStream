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

echo "[4/5] Starting pipeline components..."
uv run python -m producers.price_producer &
PID_PRICE=$!
uv run python -m producers.news_producer &
PID_NEWS=$!
uv run python -m processing.stream_app &
PID_STREAM=$!
uv run python -m ml.online_scorer &
PID_SCORER=$!

echo "Pipeline PIDs: price=$PID_PRICE news=$PID_NEWS stream=$PID_STREAM scorer=$PID_SCORER"

echo "[5/5] Starting Streamlit dashboard..."
uv run streamlit run dashboard/app.py --server.port 8501 &
PID_DASH=$!

echo ""
echo "=== MarketStream is running ==="
echo "  Dashboard:  http://localhost:8501"
echo "  Kafka UI:   http://localhost:8080"
echo ""
echo "Press Ctrl+C to stop all components."

cleanup() {
    echo "Stopping all components..."
    kill $PID_PRICE $PID_NEWS $PID_STREAM $PID_SCORER $PID_DASH 2>/dev/null || true
    echo "Stopping Docker services..."
    docker-compose down
    echo "Done."
}
trap cleanup EXIT INT TERM

wait
