"""Small idempotent SQL migrations for deployments created before factor CEP."""

from __future__ import annotations

from sqlalchemy import Connection, text


MIGRATIONS = (
    "ALTER TABLE factor_snapshots ADD COLUMN IF NOT EXISTS input_summary JSONB",
    "ALTER TABLE anomaly_alerts ADD COLUMN IF NOT EXISTS pattern_name VARCHAR(100)",
    "ALTER TABLE anomaly_alerts ADD COLUMN IF NOT EXISTS direction VARCHAR(10)",
    "ALTER TABLE anomaly_alerts ADD COLUMN IF NOT EXISTS severity VARCHAR(20)",
    "ALTER TABLE anomaly_alerts ADD COLUMN IF NOT EXISTS event_start TIMESTAMPTZ",
    "ALTER TABLE anomaly_alerts ADD COLUMN IF NOT EXISTS event_end TIMESTAMPTZ",
    "ALTER TABLE anomaly_alerts ADD COLUMN IF NOT EXISTS first_detected_at TIMESTAMPTZ",
    "ALTER TABLE anomaly_alerts ADD COLUMN IF NOT EXISTS factor_evidence JSONB",
    "ALTER TABLE anomaly_alerts ADD COLUMN IF NOT EXISTS trigger_event_ids JSONB",
    "ALTER TABLE anomaly_alerts ADD COLUMN IF NOT EXISTS data_quality JSONB",
    "ALTER TABLE anomaly_alerts ADD COLUMN IF NOT EXISTS dedupe_key VARCHAR(64)",
    "ALTER TABLE anomaly_alerts ADD COLUMN IF NOT EXISTS persisted_at TIMESTAMPTZ "
    "NOT NULL DEFAULT CURRENT_TIMESTAMP",
    "CREATE INDEX IF NOT EXISTS ix_anomaly_alerts_pattern_name ON anomaly_alerts (pattern_name)",
    "CREATE INDEX IF NOT EXISTS ix_anomaly_alerts_persisted_at ON anomaly_alerts (persisted_at)",
    "CREATE UNIQUE INDEX IF NOT EXISTS ux_anomaly_alerts_dedupe_key "
    "ON anomaly_alerts (dedupe_key) WHERE dedupe_key IS NOT NULL",
)


def run_migrations(connection: Connection) -> None:
    for statement in MIGRATIONS:
        connection.execute(text(statement))
