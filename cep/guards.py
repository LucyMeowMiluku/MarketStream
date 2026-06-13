"""Guard factories for transition predicates.

Each factory returns a ``Guard`` — a callable ``(features: dict) -> bool``
that is evaluated when a transition matches by event type.  The transition
fires only if the guard also returns ``True``.

Guards must be **pure** and **O(1)** — no I/O, no state, no allocations
beyond a single comparison.
"""

from __future__ import annotations

from cep.automaton import Guard


def feature_gt(key: str, threshold: float) -> Guard:
    return lambda f: float(f.get(key, 0)) > threshold


def feature_lt(key: str, threshold: float) -> Guard:
    return lambda f: float(f.get(key, 0)) < threshold


def feature_gte(key: str, threshold: float) -> Guard:
    return lambda f: float(f.get(key, 0)) >= threshold


def feature_abs_gt(key: str, threshold: float) -> Guard:
    return lambda f: abs(float(f.get(key, 0))) > threshold
