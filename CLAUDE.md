# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

MarketStream is a capstone project: a real-time, explainable market anomaly detector. Python 3.12 only (`>=3.12,<3.13`), managed with `uv`. README and much of `docs/` are in Chinese.

## Commands

```bash
uv sync                                   # install (incl. dev group: pytest, ruff)
uv run pytest -q                          # full test suite (testpaths = tests/)
uv run pytest tests/test_factor_cep.py::test_name -q   # single test
uv run ruff check .                       # lint (CI runs ruff then pytest)

# Infrastructure (Kafka + TimescaleDB via docker-compose)
docker-compose up -d
bash scripts/create_topics.sh
uv run python -m storage.init_db

# Pipeline
bash scripts/start_all.sh                 # whole stack + Streamlit dashboard on :8501, Kafka UI on :8080
bash scripts/run_component.sh <component> # data-source | factor-engine | factor-engine-replay | cep | replay PATH | replay-labels | collect-reviewed-replay | evaluate-reviewed-replay | dashboard

uv run python -m evaluation.run_synthetic # controlled synthetic experiment (no infra needed)
```

`start_all.sh` modes: `MARKETSTREAM_SOURCE=replay MARKETSTREAM_REPLAY_PATH=/abs/events.jsonl` for replay; otherwise live, which **requires** `FACTOR_BASELINE_STARTUP_MODE` (plus Alpaca credentials). Settings come from `config/settings.py` (pydantic-settings, reads `.env`; see `.env.example`).

## Architecture

There is exactly one online pipeline; live and replay share it:

```
Alpaca producer / replay producer
 → MarketEvent            (Kafka: raw.market_events)
 → EventQualityGate       (processing/data_quality.py)
 → LightweightFactorEngine: 8 factors at 10s / 60s / 300s cadences
 → FactorSnapshot         (Kafka: stream.factor_snapshots)
 → CEPDetector: 6 explicit state machines (cep/state_machines.py)
 → DetectionResult        (Kafka: stream.anomalies) → TimescaleDB → Streamlit dashboard
```

- **Data contracts** live in `processing/event_models.py` (`MarketEvent`, `FactorSnapshot`, `AtomicEvent`, `PatternMatch`, `DetectionResult`). They serialize to plain JSON dicts so live and replay traffic traverse the same topics; a `marketstream-mode` Kafka header distinguishes them. Changing a contract affects ingestion, factors, CEP, replay, storage, and the golden trace.
- **Factor engine** (`processing/factor_engine.py`, with `factor_calculations.py` and `factor_state.py`) is bounded per ticker (`factor_max_tickers`) and scores factors against rolling Median/MAD baselines keyed by (ticker, cadence, session, slot, factor).
- **Two factor runners**: `processing/factor_stream.py` is the durable live runner (baseline epochs, offsets and runtime state persisted via `baseline/`); `processing/replay_factor_stream.py` is an ephemeral runner that must never read or modify live baseline epochs.
- **Baseline startup is deliberately explicit** (`baseline/startup.py`): `COLD_START`, `RESTORE` (needs `FACTOR_BASELINE_EPOCH_ID`), or `VERIFIED_BACKFILL` (needs a manifest + sha256). Never add a guessed/default mode. Details: `docs/BASELINE_PERSISTENCE.md`.
- **CEP** (`cep/cep_detector.py`) converts snapshot factors into atomic events, advances each `PatternMachine`, applies cooldown/dedupe and quality suppression, and emits severity + evidence. Generic NFA, negation, repeat and meta-patterns were intentionally removed — keep patterns as small explicit machines.
- **Isolation Forest** (`evaluation/isolation_forest.py`) is the only ML component and is an offline comparison baseline only: it consumes the same `FactorSnapshot`s and has no feature pipeline or online process of its own.
- **Reviewed replay** (`replay/`): `alpaca_history` collects data, `labels` manages label registries, `evaluator` produces `metrics.json`, `trace.jsonl`, `replay_report.html`, `detector_comparison.json`. The evaluator refuses to run unless labels are independently approved and frozen; event matching is strictly forward, one-to-one (`evaluation/metrics.py`).

## Testing notes

- `tests/test_cep_golden_trace.py` compares CEP output on synthetic scenarios (`evaluation/synthetic_scenarios.py`) to `tests/fixtures/cep_golden_trace.json`. Any intentional change to state machines, scoring or evidence requires regenerating that fixture deliberately — don't edit it to make a failure disappear.
- `tests/test_replay_consistency.py` asserts live and replay produce identical snapshots and CEP decisions; preserve this property.

## Repository conventions

- Several core files (`cep/`, `processing/`, `evaluation/metrics.py`, `replay/labels.py`, `replay/evaluator.py`) begin with a Chinese provenance/authorship header block (来源归属…) and contain Chinese design comments. These support the capstone ownership-evidence documents in `report/ownership_evidence/` and `docs/CORE_CODE_AUTHORSHIP_AND_REFERENCES_*.md`; preserve them when editing.
- Evidence boundaries matter in docs/reports: unit and synthetic tests prove declared behavior only; real-market Precision/Recall/F1 may only be claimed from reviewed replay on frozen labels.
- The old four-model ensemble, ML shadow, generic NFA and old feature pipeline were removed; `CHANGELOG.md` and the `codex/pre-simplification-snapshot` branch are historical. Don't reintroduce them. `ml/` and `state/` are untracked leftovers.
- `docs/CORE_WALKTHROUGH_CN.md` is the source-reading guide; `docs/STATUS.md` tracks what is and isn't done.
