"""Finite-state automata for complex event processing.

Two implementations share the same ``Transition`` dataclass:

* ``EventAutomaton`` — the original DFA (one state per key). Kept for
  backward compatibility and as a reference baseline.
* ``NFAEventAutomaton`` — a bounded NFA that tracks multiple concurrent
  match instances per key.  Supports per-transition gap constraints,
  guard predicates, negation (absence detection), and Kleene repetition.
  This is the production engine.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

Guard = Callable[[dict], bool]


@dataclass(frozen=True)
class Transition:
    from_state: int
    event: str
    to_state: int
    max_gap: int | None = None
    guard: Guard | None = None

    def __hash__(self) -> int:
        return hash((self.from_state, self.event, self.to_state))

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Transition):
            return NotImplemented
        return (
            self.from_state == other.from_state
            and self.event == other.event
            and self.to_state == other.to_state
        )


@dataclass(frozen=True)
class NegationEdge:
    """Fires when ``absent_event`` does NOT appear for ``timeout`` windows."""

    from_state: int
    absent_event: str
    to_state: int
    timeout: int


@dataclass(frozen=True)
class RepeatEdge:
    """Requires ``event`` to fire in at least ``min_count`` windows before
    outgoing transitions from ``state`` become available."""

    state: int
    event: str
    min_count: int
    max_count: int | None = None


# ---------------------------------------------------------------------------
# Original DFA (preserved for backward compatibility)
# ---------------------------------------------------------------------------


class EventAutomaton:
    """Single-pattern DFA, evaluated per key (ticker).

    States are integers; ``0`` is the start state and ``accept_state`` is the
    (single) accepting state. ``max_gap`` bounds how many windows may pass
    between consecutive matched events before a partial match expires and resets
    to the start.
    """

    def __init__(
        self,
        name: str,
        transitions: list[Transition],
        accept_state: int,
        severity: float = 0.8,
        max_gap: int = 3,
    ):
        self.name = name
        self.severity = severity
        self._accept = accept_state
        self._max_gap = max_gap
        self._table: dict[tuple[int, str], int] = {
            (t.from_state, t.event): t.to_state for t in transitions
        }
        self._state: dict[str, int] = {}
        self._age: dict[str, int] = {}

    def step(self, key: str, events: set[str], features: dict | None = None) -> float:
        """Advance the automaton for *key* given this window's events.

        Returns the pattern severity (> 0) if the accepting state is reached
        this window, else ``0.0``.
        """
        state = self._state.get(key, 0)
        age = self._age.get(key, 0)

        if state != 0 and age >= self._max_gap:
            state = 0

        remaining = set(events)
        advanced = False
        while True:
            moved = False
            for ev in sorted(remaining):
                nxt = self._table.get((state, ev))
                if nxt is not None:
                    state = nxt
                    remaining.discard(ev)
                    moved = advanced = True
                    break
            if not moved or state == self._accept:
                break

        if state == self._accept:
            self._state[key] = 0
            self._age[key] = 0
            return self.severity

        self._state[key] = state
        if advanced:
            self._age[key] = 0
        elif state != 0:
            self._age[key] = age + 1
        else:
            self._age[key] = 0
        return 0.0


# ---------------------------------------------------------------------------
# NFA with bounded instance tracking
# ---------------------------------------------------------------------------


@dataclass
class MatchInstance:
    state: int
    age: int = 0
    birth: int = 0
    negation_counter: int = 0
    repeat_counter: int = 0


class NFAEventAutomaton:
    """Bounded NFA that tracks multiple concurrent match instances per key.

    Compared with :class:`EventAutomaton`:

    * **Overlapping matches** — a new triggering event spawns a fresh instance
      without destroying an existing partial match.
    * **Per-transition gap** — each ``Transition`` can override the automaton-
      level ``max_gap``.
    * **Guard conditions** — a ``Transition.guard`` callable receives the
      window's feature dict and must return ``True`` for the transition to fire.
    * **Negation (absence)** — a :class:`NegationEdge` fires when its
      ``absent_event`` does NOT appear for ``timeout`` consecutive windows.
    * **Kleene repetition** — a :class:`RepeatEdge` requires its ``event``
      to fire in at least ``min_count`` windows before outgoing normal
      transitions become available.
    * **Bounded instances** — ``max_instances`` caps per-key concurrency;
      the oldest non-advanced instance is evicted when the limit is reached.
    """

    def __init__(
        self,
        name: str,
        transitions: list[Transition],
        accept_state: int,
        severity: float = 0.8,
        max_gap: int = 3,
        max_instances: int = 8,
        negations: list[NegationEdge] | None = None,
        repeats: list[RepeatEdge] | None = None,
    ):
        self.name = name
        self.severity = severity
        self._accept = accept_state
        self._max_gap = max_gap
        self._max_inst = max_instances

        self._transitions = transitions
        self._table: dict[int, list[Transition]] = {}
        for t in transitions:
            self._table.setdefault(t.from_state, []).append(t)

        self._start_events: set[str] = {
            t.event for t in transitions if t.from_state == 0
        }

        self._negation_table: dict[int, NegationEdge] = {}
        for neg in negations or []:
            self._negation_table[neg.from_state] = neg

        self._repeat_table: dict[int, RepeatEdge] = {}
        for rep in repeats or []:
            self._repeat_table[rep.state] = rep
            self._start_events.add(rep.event)

        self._state_max_gap: dict[int, int] = {}
        states_with_edges: dict[int, list[int]] = {}
        for t in transitions:
            gap = t.max_gap if t.max_gap is not None else max_gap
            states_with_edges.setdefault(t.from_state, []).append(gap)
        for neg in negations or []:
            states_with_edges.setdefault(neg.from_state, []).append(neg.timeout)
        for s, gaps in states_with_edges.items():
            self._state_max_gap[s] = max(gaps)

        self._instances: dict[str, list[MatchInstance]] = {}
        self._clock: dict[str, int] = {}

    def _effective_gap(self, state: int) -> int:
        return self._state_max_gap.get(state, self._max_gap)

    def _try_transitions(
        self, state: int, events: set[str], features: dict | None
    ) -> tuple[int, bool]:
        """Try normal transitions from *state*.  Returns (new_state, advanced)."""
        remaining = set(events)
        advanced = False
        while remaining:
            moved = False
            for ev in sorted(remaining):
                for t in self._table.get(state, []):
                    if t.event != ev:
                        continue
                    if t.guard is not None:
                        if features is None or not t.guard(features):
                            continue
                    state = t.to_state
                    remaining.discard(ev)
                    moved = advanced = True
                    break
                if moved:
                    break
            if not moved or state == self._accept:
                break
        return state, advanced

    def step(self, key: str, events: set[str], features: dict | None = None) -> float:
        """Advance all instances for *key*.  Returns max severity fired."""
        clock = self._clock.get(key, 0)
        instances = self._instances.get(key, [])

        alive: list[MatchInstance] = []
        for inst in instances:
            if inst.state != 0 and inst.age >= self._effective_gap(inst.state):
                continue
            alive.append(inst)
        instances = alive

        best_sev = 0.0
        next_instances: list[MatchInstance] = []
        repeat_consumed: set[str] = set()

        for inst in instances:
            state = inst.state

            # --- Kleene repetition ---
            rep = self._repeat_table.get(state)
            if rep is not None:
                if rep.event in events:
                    inst.repeat_counter += 1
                    inst.age = 0
                    repeat_consumed.add(rep.event)
                    if rep.max_count is not None and inst.repeat_counter > rep.max_count:
                        continue  # exceeded max -> drop
                    next_instances.append(inst)
                    continue  # consumed by repeat, don't try normal transitions
                elif inst.repeat_counter < rep.min_count:
                    inst.age += 1
                    next_instances.append(inst)
                    continue  # threshold not met, keep waiting
                # threshold met, fall through to normal transitions

            # --- Normal transitions ---
            state, advanced = self._try_transitions(state, events, features)

            if state == self._accept:
                if self.severity > best_sev:
                    best_sev = self.severity
                continue  # accepted -> don't keep instance

            # --- Negation (absence) ---
            neg = self._negation_table.get(state)
            if neg is not None and not advanced:
                if neg.absent_event in events:
                    inst.negation_counter = 0  # event appeared, reset
                else:
                    inst.negation_counter += 1
                    if inst.negation_counter >= neg.timeout:
                        state = neg.to_state
                        inst.negation_counter = 0
                        advanced = True
                        if state == self._accept:
                            if self.severity > best_sev:
                                best_sev = self.severity
                            continue

            inst.state = state
            inst.age = 0 if advanced else inst.age + 1
            next_instances.append(inst)

        instances = next_instances

        # --- Spawn new instance if a start event appeared ---
        spawn_events = (events & self._start_events) - repeat_consumed
        if spawn_events:
            should_spawn = True
            for inst in instances:
                if inst.state == 0 and inst.age == 0:
                    should_spawn = False
                    break
            if should_spawn:
                new_inst = MatchInstance(state=0, age=0, birth=clock)

                rep = self._repeat_table.get(0)
                if rep is not None and rep.event in events:
                    new_inst.repeat_counter = 1
                    instances.append(new_inst)
                else:
                    state, _ = self._try_transitions(0, events, features)
                    if state == self._accept:
                        if self.severity > best_sev:
                            best_sev = self.severity
                    elif state != 0:
                        new_inst.state = state
                        instances.append(new_inst)

        if len(instances) > self._max_inst:
            instances.sort(key=lambda i: i.birth)
            instances = instances[-self._max_inst :]

        self._instances[key] = instances
        self._clock[key] = clock + 1
        return best_sev
