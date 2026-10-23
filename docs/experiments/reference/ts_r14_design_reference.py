#!/usr/bin/env python3
"""R14-NF-168-v2: independent pure-function DESIGN reference; not codec code.

No encoder calls, input video, external packages or network access.
Run with Python 3.10+: python3 ts_r14_design_reference.py
C is a callback returning the EXISTING integer syntaxCost. The built-in
verification fixture covers only magnitudes 0..9; it is not a full Rice coder.
"""
from __future__ import annotations

import itertools
import json
import random
from dataclasses import dataclass
from fractions import Fraction
from typing import Callable, Sequence

Cost = Callable[[int], int]
MODES = ("NONE", "TARGET2", "DIR2")
RHO = Fraction(21, 2)


def canonical(p: int) -> int:
    return 0 if p <= 1 else p


def validate_h(h: Sequence[int]) -> tuple[int, ...]:
    h = tuple(h)
    if len(h) != 5 or any(not isinstance(x, int) or x < 0 for x in h):
        raise ValueError("H must contain five nonnegative integer magnitudes")
    return h


def validate_grid(k: int, grid: Sequence[int] | None) -> tuple[int, ...]:
    if k <= 0:
        raise ValueError("K must be positive")
    g = tuple(range(k + 1)) if grid is None else tuple(grid)
    if not g or tuple(sorted(set(g))) != g or g[0] < 0 or g[-1] > k:
        raise ValueError("Grid must be sorted, unique, nonempty and in [0,K]")
    return g


def down168(c: int) -> int:
    if c < 1:
        raise ValueError("Positive magnitude cost must be at least one")
    return 168 * c - 4 * (c - 1) ** 2 if c <= 22 else 1932


def up168(c: int) -> int:
    if c < 1:
        raise ValueError("Positive magnitude cost must be at least one")
    return 168 * c - 4 * (c - 1) ** 2 if c <= 11 else 84 * c + 525


def loss168(m: int, p: int, cost: Cost) -> int:
    """Positive-neighbour scoring only; actual zero/RDOQ rules are unchanged."""
    if m <= 0 or p < 0:
        raise ValueError("m must be positive and p nonnegative")
    if p <= 1:
        return 168 * cost(m)
    if p == m:
        return 168
    if p == m - 1:
        return down168(cost(m))
    if p == m + 1:
        return up168(cost(m + 1))
    return 168 * cost(m if p < m else m + 1)


def candidate_order(h: Sequence[int]) -> tuple[int, ...]:
    h = validate_h(h)
    current = canonical(max(h[:2]))
    candidates = {0, current, *(canonical(m) for m in h if m > 0)}
    return (current,) + tuple(sorted(candidates - {current}))


def all_winners(h: Sequence[int], k: int, cost: Cost,
                grid: Sequence[int] | None = None) -> dict[int, int]:
    """Cache near/far sums; generate every score via repeated addition.

    For n<3 return native Current without canonicalizing its raw value 1.
    This function never changes an adaptation state.
    """
    h = validate_h(h)
    grid = validate_grid(k, grid)
    current = max(h[:2])
    if sum(m > 0 for m in h) < 3:
        return {r: current for r in grid}
    order = candidate_order(h)
    best = {r: order[0] for r in grid}
    best_score: dict[int, int | None] = {r: None for r in grid}
    for p in order:
        near = sum(loss168(m, p, cost) for m in h[:2] if m)
        far = sum(loss168(m, p, cost) for m in h[2:] if m)
        value = k * near
        for r in range(k + 1):
            if r in best_score:
                old = best_score[r]
                if old is None or value < old:
                    best_score[r], best[r] = value, p
            value += far
    return best


def fixed_q_cost(a: int, p: int, cost: Cost) -> int:
    """Feedback on one ALREADY DETERMINED q, not counterfactual RDOQ."""
    if a < 0 or p < 0:
        raise ValueError("Nonnegative magnitude and predictor required")
    if a == 0:
        return 0  # Feedback eligibility excludes this case.
    if p <= 1:
        return cost(a)
    if p == a:
        return cost(1)
    return cost(a + 1 if p > a else a)


def feedback_target(winners: dict[int, int], current_r: int,
                    a: int, cost: Cost) -> int:
    """Current wins equal feedback cost; then distance; then larger far r.

    Precomputes at most C(a) and C(a+1). This function cannot see source x.
    """
    if a <= 0 or current_r not in winners:
        raise ValueError("Positive determined q and a grid member required")
    ca, cap = cost(a), cost(a + 1)

    def value(p: int) -> int:
        if p <= 1:
            return ca
        if p == a:
            return 1
        return cap if p > a else ca

    return min(winners, key=lambda r:
               (value(winners[r]), abs(r - current_r), -r))


def eligible(h: Sequence[int], a: int, target_path: bool = True) -> bool:
    h = validate_h(h)
    return (target_path and a > 0 and sum(m > 0 for m in h) >= 3
            and any(h[:2]) and any(h[2:]))


@dataclass(frozen=True)
class State:
    r: int
    pending: int | None = None


def step(state: State, wanted: int | None, mode: str,
         grid: Sequence[int], valid: bool = True) -> State:
    """One post-coefficient update; invalid freezes, valid neutral clears.

    TARGET2 pending is an absolute target r. DIR2 pending is -1 or +1.
    Every committed update moves ONE adjacent grid level towards wanted.
    Production grids are 0..K, so this means exactly +1 or -1, never a jump.
    Sparse grids are supported only for equivalent-rescaling tests.
    Each move clears pending; another buffered move needs fresh confirmation.
    """
    grid = tuple(grid)
    if not grid or tuple(sorted(set(grid))) != grid:
        raise ValueError("Grid must be sorted, unique and nonempty")
    if mode not in MODES or state.r not in grid:
        raise ValueError("Invalid mode or current state")
    if mode == "NONE" and state.pending is not None:
        raise ValueError("NONE cannot have a pending event")
    if mode == "TARGET2" and state.pending is not None:
        if state.pending not in grid or state.pending == state.r:
            raise ValueError("Invalid pending target")
    if mode == "DIR2" and state.pending not in (None, -1, 1):
        raise ValueError("Invalid pending direction")
    if not valid:
        return state
    if wanted not in grid:
        raise ValueError("Valid feedback must have a target on the grid")
    if wanted == state.r:
        return State(state.r)
    direction = 1 if wanted > state.r else -1
    next_r = grid[grid.index(state.r) + direction]
    if mode == "NONE":
        return State(next_r)
    token = wanted if mode == "TARGET2" else direction
    if state.pending == token:
        return State(next_r)
    return State(state.r, token)


# Independent, readable oracles used only by the tests below.
def positive_area(b: int, upper: Fraction) -> Fraction:
    t = min(max(Fraction(b), Fraction(0)), upper)
    return Fraction(b) * t - t * t / 2


def oracle_loss(m: int, p: int, cost: Cost) -> int:
    if p <= 1:
        base, correction = cost(m), Fraction(0)
    elif p == m:
        base, correction = 1, Fraction(0)
    else:
        base = cost(m + 1 if m < p else m)
        correction = Fraction(0)
        if p == m - 1:
            correction = positive_area(base - 1, 2 * RHO) / (2 * RHO)
        elif p == m + 1:
            correction = positive_area(base - 1, RHO) / (2 * RHO)
    value = 168 * (base - correction)
    assert value.denominator == 1
    return int(value)


def oracle_winner(h: Sequence[int], k: int, r: int, cost: Cost) -> int:
    if sum(x > 0 for x in h) < 3:
        return max(h[:2])
    native = canonical(max(h[:2]))
    pool = {0, native, *(canonical(x) for x in h if x > 0)}
    def key(p: int) -> tuple[int, int, int]:
        weights = (k, k, r, r, r)
        score = sum(w * oracle_loss(m, p, cost)
                    for w, m in zip(weights, h) if m)
        return (score, 0 if p == native else 1, p)
    return min(pool, key=key)


def oracle_step(state: State, wanted: int | None, mode: str,
                valid: bool, grid: Sequence[int]) -> State:
    if not valid:
        return state
    if wanted == state.r:
        return State(state.r)
    if wanted > state.r:
        neighbor = min(r for r in grid if r > state.r)
    else:
        neighbor = max(r for r in grid if r < state.r)
    if mode == "NONE":
        return State(neighbor)
    if mode == "TARGET2":
        confirmed = state.pending is not None and wanted == state.pending
        return State(neighbor) if confirmed else State(state.r, wanted)
    direction = 1 if wanted > state.r else -1
    confirmed = state.pending is not None and direction == state.pending
    return State(neighbor) if confirmed else State(state.r, direction)


def small_cost(a: int) -> int:
    values = (0, 1, 3, 3, 4, 4, 5, 5, 6, 6)
    if not 0 <= a < len(values):
        raise ValueError("Test fixture only defines C for magnitudes 0..9")
    return values[a]


def run_tests() -> dict[str, object]:
    count = dict(rational_table_entries=0, neighborhoods=0,
                 eligible_grid_winner_checks=0, state_transition_checks=0,
                 synthetic_feedback_events=0, scaled_grid_steps=0,
                 explicit_boundary_cases=0, exhaustive_unit_step_checks=0)

    # Two exact fractional integrals at each c=1..256, including high tails.
    for c in range(1, 257):
        for upper, fn in ((2 * RHO, down168), (RHO, up168)):
            expected = 168 * (c - positive_area(c - 1, upper) / (2 * RHO))
            assert expected.denominator == 1 and fn(c) == expected
            count["rational_table_entries"] += 1

    # 5^5 H cases; n>=3 in 2944, and G2/G4 have 3+5=8 weights.
    for h in itertools.product(range(5), repeat=5):
        count["neighborhoods"] += 1
        for k in (2, 4):
            got = all_winners(h, k, small_cost)
            for r, p in got.items():
                assert p == oracle_winner(h, k, r, small_cost)
                if sum(x > 0 for x in h) >= 3:
                    count["eligible_grid_winner_checks"] += 1
        w2 = all_winners(h, 2, small_cost)
        w4 = all_winners(h, 4, small_cost, (0, 2, 4))
        assert all(w2[r] == w4[2 * r] for r in w2)

    # 8 current weights x 3 modes x 12 deterministic transition cases.
    for k in (2, 4):
        grid = tuple(range(k + 1))
        for r in grid:
            alt = [x for x in grid if x != r]
            for mode in MODES:
                for j in range(12):
                    pending = None
                    if mode == "TARGET2" and j % 3:
                        pending = alt[j % len(alt)]
                    elif mode == "DIR2" and j % 3:
                        pending = 1 if j % 2 else -1
                    state = State(r, pending)
                    valid = j % 4 != 0
                    wanted = (r if j % 4 == 1 else alt[j % len(alt)]) if valid else None
                    assert step(state, wanted, mode, grid, valid) == oracle_step(
                        state, wanted, mode, valid, grid)
                    count["state_transition_checks"] += 1

    # Exhaust all legal state/pending/target combinations on production grids.
    for k in (2, 4):
        grid = tuple(range(k + 1))
        for mode in MODES:
            for r in grid:
                tokens = ((None,) if mode == "NONE" else
                          (None, -1, 1) if mode == "DIR2" else
                          (None,) + tuple(t for t in grid if t != r))
                for pending in tokens:
                    before = State(r, pending)
                    for wanted in (None,) + grid:
                        valid = wanted is not None
                        after = step(before, wanted, mode, grid, valid)
                        assert after == oracle_step(before, wanted, mode, valid, grid)
                        assert abs(after.r - before.r) <= 1
                        if after.r != before.r:
                            assert after.pending is None
                            assert abs(wanted - after.r) < abs(wanted - before.r)
                        if not valid:
                            assert after == before
                        elif wanted == r:
                            assert after == State(r)
                        count["exhaustive_unit_step_checks"] += 1

    # Six deterministic random streams, 2000 coefficient events each.
    rng = random.Random(20261023)
    for k in (2, 4):
        grid = tuple(range(k + 1))
        for mode in MODES:
            state = State(k)
            saved = state
            for i in range(2000):
                if i % 200 == 0:  # Exercise all three TU initialization choices.
                    state = State((k, k // 2, 0)[(i // 200) % 3])
                if i % 16 == 0:
                    saved = state
                h = tuple(rng.randrange(9) for _ in range(5))
                a = rng.randrange(9)
                winners = all_winners(h, k, small_cost)
                valid = eligible(h, a)
                wanted = feedback_target(winners, state.r, a, small_cost) if valid else None
                if valid:
                    brute = min(grid, key=lambda r:
                                (fixed_q_cost(a, winners[r], small_cost), abs(r-state.r), -r))
                    assert wanted == brute
                    assert fixed_q_cost(a, winners[wanted], small_cost) <= fixed_q_cost(
                        a, winners[state.r], small_cost)
                state2 = step(state, wanted, mode, grid, valid)
                assert state2 == oracle_step(state, wanted, mode, valid, grid)
                assert 0 <= state2.r <= k
                assert abs(state2.r - state.r) <= 1
                if state2.r != state.r:
                    assert state2.pending is None
                state = state2
                if i % 16 == 15 and rng.randrange(4) == 0:
                    state = saved  # Abstract whole-CG rollback of BOTH fields.
                    assert state == saved
                count["synthetic_feedback_events"] += 1

    # One ADJACENT LEGAL level: 0->1 in G2 maps to 0->2 on test-only {0,2,4}.
    # This scaled representation is not the production full 5-level G4.
    for mode in MODES:
        for init in (0, 1, 2):
            s2, s4 = State(init), State(2 * init)
            for _ in range(1000):
                h = tuple(rng.randrange(9) for _ in range(5))
                a = rng.randrange(9)
                w2 = all_winners(h, 2, small_cost)
                w4 = all_winners(h, 4, small_cost, (0, 2, 4))
                assert all(w2[r] == w4[2*r] for r in w2)
                valid = eligible(h, a)
                t2 = feedback_target(w2, s2.r, a, small_cost) if valid else None
                t4 = feedback_target(w4, s4.r, a, small_cost) if valid else None
                assert t4 == (2 * t2 if t2 is not None else None)
                s2 = step(s2, t2, mode, (0, 1, 2), valid)
                s4 = step(s4, t4, mode, (0, 2, 4), valid)
                expected_pending = s2.pending
                if mode == "TARGET2" and expected_pending is not None:
                    expected_pending *= 2
                assert s4 == State(2*s2.r, expected_pending)
                count["scaled_grid_steps"] += 1

    # Explicit regression: actual achievable winner vs a tempting target label.
    assert all_winners((4, 4, 3, 3, 3), 2, small_cost) == {0: 4, 1: 4, 2: 3}
    count["explicit_boundary_cases"] += 1
    w = all_winners((0, 1, 2, 3, 6), 2, small_cost)
    assert w == {0: 0, 1: 0, 2: 6}
    assert feedback_target(w, 1, 3, small_cost) == 1
    count["explicit_boundary_cases"] += 1
    st = State(2, 3)
    assert step(st, None, "TARGET2", range(5), False) == st
    assert step(st, 2, "TARGET2", range(5), True) == State(2)
    count["explicit_boundary_cases"] += 1
    target, direction = State(2), State(2)
    for wanted in (3, 4):
        target = step(target, wanted, "TARGET2", range(5))
        direction = step(direction, wanted, "DIR2", range(5))
    assert target == State(2, 4) and direction == State(3)
    count["explicit_boundary_cases"] += 1

    # Both directions require every intermediate production weight.
    for mode in MODES:
        state = State(0)
        up, down = [], []
        events = 4 if mode == "NONE" else 8
        for _ in range(events):
            state = step(state, 4, mode, range(5))
            up.append(state.r)
        for _ in range(events):
            state = step(state, 0, mode, range(5))
            down.append(state.r)
        assert up == ([1, 2, 3, 4] if mode == "NONE" else
                      [0, 1, 1, 2, 2, 3, 3, 4])
        assert down == ([3, 2, 1, 0] if mode == "NONE" else
                        [4, 3, 3, 2, 2, 1, 1, 0])
        assert state == State(0)
        count["explicit_boundary_cases"] += 1

    # A confirmed move spends its evidence, even if the target remains distant.
    for mode in ("TARGET2", "DIR2"):
        state = State(0)
        state = step(step(state, 4, mode, range(5)), 4, mode, range(5))
        assert state == State(1)
        first_reverse = step(state, 0, mode, range(5))
        assert first_reverse.r == 1
        assert step(first_reverse, 0, mode, range(5)) == State(0)
    count["explicit_boundary_cases"] += 1

    # Ineligible events freeze pending; eligible neutral events clear it.
    for mode in ("TARGET2", "DIR2"):
        token = 4 if mode == "TARGET2" else 1
        state = State(1, token)
        assert step(state, None, mode, range(5), False) == state
        neutral = step(state, 1, mode, range(5))
        assert neutral == State(1)
        assert step(neutral, 4, mode, range(5)) == State(1, token)
    count["explicit_boundary_cases"] += 1

    # Preserve the global target rule; moving one level is NOT a local-loss guard.
    winners = {0: 0, 1: 6, 2: 3}
    wanted = feedback_target(winners, 0, 3, small_cost)
    assert wanted == 2
    moved = step(State(0), wanted, "NONE", (0, 1, 2))
    assert moved == State(1)
    assert fixed_q_cost(3, winners[moved.r], small_cost) > fixed_q_cost(
        3, winners[0], small_cost)
    count["explicit_boundary_cases"] += 1

    assert count == {
        "rational_table_entries": 512,
        "neighborhoods": 3125,
        "eligible_grid_winner_checks": 23552,
        "state_transition_checks": 288,
        "synthetic_feedback_events": 12000,
        "scaled_grid_steps": 9000,
        "explicit_boundary_cases": 10,
        "exhaustive_unit_step_checks": 354,
    }
    return {"revision": "R14-NF-168-v2", "status": "pass", "checks": count,
            "scope": "Pure mathematical/state reference only; no codec integration or video encoding",
            "transition": "one-adjacent-grid-level; production max abs(delta_r)=1",
            "seed": 20261023}


if __name__ == "__main__":
    print(json.dumps(run_tests(), ensure_ascii=False, indent=2))
