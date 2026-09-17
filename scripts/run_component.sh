#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

component="${1:-}"
case "$component" in
  data-source)
    exec uv run python -m producers.alpaca_producer
    ;;
  factor-engine)
    exec uv run python -m processing.factor_stream
    ;;
  factor-engine-replay)
    exec uv run python -m processing.replay_factor_stream
    ;;
  cep)
    exec uv run python -m cep.online_scorer
    ;;
  replay)
    if [[ $# -lt 2 ]]; then
      echo "Usage: scripts/run_component.sh replay PATH [--speed N] [--no-wait]" >&2
      exit 2
    fi
    shift
    exec uv run python -m producers.replay_producer "$@"
    ;;
  replay-labels)
    shift
    exec uv run python -m replay.labels "$@"
    ;;
  collect-reviewed-replay)
    shift
    exec uv run python -m replay.alpaca_history "$@"
    ;;
  evaluate-reviewed-replay)
    shift
    exec uv run python -m replay.evaluator "$@"
    ;;
  dashboard)
    exec uv run streamlit run dashboard/app.py --server.port 8501
    ;;
  *)
    echo "Usage: scripts/run_component.sh {data-source|factor-engine|factor-engine-replay|cep|replay|replay-labels|collect-reviewed-replay|evaluate-reviewed-replay|dashboard}" >&2
    exit 2
    ;;
esac
