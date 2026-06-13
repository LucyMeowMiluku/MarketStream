"""A minimal finite-state automaton for complex event processing.

Each automaton recognises an ordered sequence of primitive events that must
complete within a bounded number of windows — the classic CEP "within N"
temporal constraint. Reaching the accepting state emits a complex event with a
configured severity. Automata are instantiated once and tracked per key
(ticker); state is kept in dicts keyed by ticker so one instance handles all
symbols on the stream.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Transition:
    from_state: int
    event: str
    to_state: int


class EventAutomaton:
    """Single-pattern automaton, evaluated per key (ticker).

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
        # Per-key runtime state.
        self._state: dict[str, int] = {}
        self._age: dict[str, int] = {}  # windows since the last advance

    def step(self, key: str, events: set[str]) -> float:
        """Advance the automaton for ``key`` given this window's events.

        Returns the pattern severity (> 0) if the accepting state is reached
        this window, else ``0.0``. Multiple events in one window can chain
        several hops (so a simultaneous A+B+C completes immediately); a partial
        match persists across windows until it completes or expires.
        """
        state = self._state.get(key, 0)
        age = self._age.get(key, 0)

        # Expire a stale partial match before processing this window.
        if state != 0 and age >= self._max_gap:
            state = 0

        remaining = set(events)
        advanced = False
        while True:
            moved = False
            for ev in list(remaining):
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
