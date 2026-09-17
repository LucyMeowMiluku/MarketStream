"""FactorSnapshot to explainable DetectionResult orchestration.

The six temporal rules live in ``cep.state_machines``. This module keeps only
the shared alert policy: atomic-event extraction, quality suppression,
severity, cooldown, evidence and deterministic identities.
"""

from __future__ import annotations

import hashlib
from collections import OrderedDict
from datetime import datetime, timedelta, timezone

from cep.state_machines import build_state_machines
from config.settings import settings
from processing.event_models import AtomicEvent, DetectionResult, FactorSnapshot, PatternMatch

PATTERN_SEVERITY = {
    "stock_specific_dislocation": 0.82,
    "liquidity_pressure_move": 0.88,
    "news_confirmed_move": 0.90,
    "flash_reversal": 0.86,
    "sustained_pressure": 0.92,
    "cross_asset_shock": 0.95,
}

CRITICAL_QUALITY_FLAGS = {"duplicate", "stale", "invalid_price", "crossed_quote"}


class CEPDetector:
    """Run six bounded state machines over one factor snapshot at a time."""

    def __init__(
        self,
        *,
        cooldown_seconds: int | None = None,
        max_factor_frames: int = 64,
        enabled_factor_patterns: set[str] | None = None,
        max_tickers: int | None = None,
    ) -> None:
        self._machines = build_state_machines(max_factor_frames)
        self._cooldown = timedelta(
            seconds=cooldown_seconds
            if cooldown_seconds is not None
            else settings.cep_cooldown_seconds
        )
        self._cooldown_until: dict[tuple[str, str, str], datetime] = {}
        self._enabled_patterns = (
            set(PATTERN_SEVERITY)
            if enabled_factor_patterns is None
            else set(enabled_factor_patterns)
        )
        self._max_tickers = max_tickers or settings.factor_max_tickers
        self._tickers: OrderedDict[str, None] = OrderedDict()
        self._last_match: dict[str, str] = {}

    @property
    def name(self) -> str:
        return "cep"

    def process(
        self,
        snapshot: FactorSnapshot,
        *,
        detected_at: datetime | None = None,
    ) -> DetectionResult:
        """Advance every pattern machine and apply the shared alert policy."""

        self._touch_ticker(snapshot.ticker)
        atoms = self._atomic_events(snapshot)
        completed: list[PatternMatch] = []
        pending: list[PatternMatch] = []
        for machine in self._machines:
            machine_completed, machine_pending = machine.advance(snapshot, atoms)
            if machine.name in self._enabled_patterns:
                completed.extend(machine_completed)
                pending.extend(machine_pending)
        completed = self._unique_patterns(completed)
        pending = self._unique_patterns(pending)

        suppressed_reason = self._suppressed_reason(snapshot)
        primary = max(
            completed,
            key=lambda item: PATTERN_SEVERITY.get(item.name, 0.0),
            default=None,
        )
        is_alert = primary is not None and not suppressed_reason
        dedupe_key = None
        if primary is not None:
            is_alert, suppressed_reason = self._apply_cooldown(
                snapshot, primary, is_alert, suppressed_reason
            )
            dedupe_key = self._dedupe_key(snapshot, primary)

        evidence = self._factor_evidence(snapshot, atoms)
        severity_score = self._severity_score(primary, atoms)
        explanation = self._explain(snapshot, primary, evidence, suppressed_reason)
        if primary:
            self._last_match[snapshot.ticker] = primary.name
        else:
            self._last_match.pop(snapshot.ticker, None)

        return DetectionResult(
            ticker=snapshot.ticker,
            event_time=snapshot.event_time,
            detected_at=detected_at or datetime.now(timezone.utc),
            cadence=snapshot.cadence,
            score=-round(severity_score, 6),
            severity=self._severity_label(severity_score),
            is_alert=is_alert,
            direction=primary.direction if primary else None,
            atomic_events=atoms,
            patterns=completed + pending,
            factor_evidence=evidence,
            source_event_ids=snapshot.source_event_ids,
            data_quality=snapshot.data_quality,
            explanation=explanation,
            dedupe_key=dedupe_key,
            run_id=snapshot.run_id,
            dataset_id=snapshot.dataset_id,
            mode=snapshot.mode,
            provenance=snapshot.provenance,
        )

    def _touch_ticker(self, ticker: str) -> None:
        if ticker in self._tickers:
            self._tickers.move_to_end(ticker)
            return
        self._tickers[ticker] = None
        if len(self._tickers) <= self._max_tickers:
            return
        evicted, _ = self._tickers.popitem(last=False)
        for machine in self._machines:
            machine.reset(evicted)
        for key in [key for key in self._cooldown_until if key[0] == evicted]:
            del self._cooldown_until[key]
        self._last_match.pop(evicted, None)

    @property
    def factor_state_size(self) -> dict[str, int]:
        return {
            "tickers": len(self._tickers),
            "histories": max((machine.state_keys for machine in self._machines), default=0),
            "cooldowns": len(self._cooldown_until),
            "cross_asset_frames": next(
                (
                    machine.state_keys
                    for machine in self._machines
                    if machine.name == "cross_asset_shock"
                ),
                0,
            ),
        }

    @staticmethod
    def _atomic_events(snapshot: FactorSnapshot) -> list[AtomicEvent]:
        atoms: list[AtomicEvent] = []
        for factor, state in snapshot.factor_states.items():
            if state.get("state") not in {"elevated", "extreme"}:
                continue
            direction = state.get("direction", "up")
            atoms.append(
                AtomicEvent(
                    name=f"{factor}:{direction}",
                    group=state.get("group", "unknown"),
                    direction=direction,
                    event_time=snapshot.event_time,
                    factor=factor,
                    value=float(snapshot.factor_values.get(factor, 0.0)),
                    robust_z=float(state.get("robust_z", 0.0)),
                    source_event_ids=snapshot.source_event_ids,
                )
            )
        return atoms

    @staticmethod
    def _suppressed_reason(snapshot: FactorSnapshot) -> str:
        if snapshot.warmup_status != "ready":
            return "baseline warm-up is incomplete"
        flags = set(snapshot.data_quality.get("flags", []))
        if flags.intersection(CRITICAL_QUALITY_FLAGS):
            return "input data quality is degraded"
        return ""

    def _apply_cooldown(self, snapshot, primary, is_alert, reason):
        key = (snapshot.ticker, primary.name, primary.direction)
        cooldown_until = self._cooldown_until.get(key)
        if is_alert and cooldown_until and snapshot.event_time < cooldown_until:
            primary.status = "merged"
            return False, "merged into an alert inside the cooldown window"
        if is_alert:
            self._cooldown_until[key] = snapshot.event_time + self._cooldown
        return is_alert, reason

    @staticmethod
    def _dedupe_key(snapshot, primary) -> str:
        identity = (
            f"{snapshot.ticker}|{primary.name}|{primary.direction}|"
            f"{primary.started_at.isoformat()}"
        )
        return hashlib.sha256(identity.encode()).hexdigest()[:32]

    @staticmethod
    def _factor_evidence(snapshot, atoms):
        return {
            atom.factor: {
                "group": atom.group,
                "direction": atom.direction,
                "value": atom.value,
                "robust_z": atom.robust_z,
                "state": snapshot.factor_states.get(atom.factor, {}).get("state"),
            }
            for atom in atoms
        }

    @staticmethod
    def _severity_score(primary, atoms):
        if primary is None:
            return 0.0
        base_score = PATTERN_SEVERITY.get(primary.name, 0.0)
        max_z = max((abs(atom.robust_z) for atom in atoms), default=0.0)
        return min(1.0, max(base_score, max_z / 10))

    @staticmethod
    def _severity_label(score: float) -> str:
        if score >= 0.95:
            return "critical"
        if score >= 0.85:
            return "high"
        if score > 0:
            return "medium"
        return "none"

    @staticmethod
    def _unique_patterns(patterns: list[PatternMatch]) -> list[PatternMatch]:
        unique: dict[tuple[str, str], PatternMatch] = {}
        for pattern in patterns:
            unique[(pattern.name, pattern.direction)] = pattern
        return list(unique.values())

    @staticmethod
    def _explain(snapshot, primary, evidence, suppressed_reason):
        if primary is None:
            if snapshot.warmup_status != "ready":
                return "No alert: baseline warm-up is incomplete."
            return "No confirmed multi-factor or persistent anomaly pattern."
        factors = ", ".join(primary.evidence)
        message = (
            f"{primary.name} ({primary.direction}) confirmed by {factors}. "
            f"Observed {len(evidence)} elevated or extreme factors."
        )
        if suppressed_reason:
            message += f" Alert suppressed because {suppressed_reason}."
        return message

    def last_match(self, ticker: str = "_default") -> str | None:
        return self._last_match.get(ticker)
