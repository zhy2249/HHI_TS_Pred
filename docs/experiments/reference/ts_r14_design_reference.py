#!/usr/bin/env python3
"""R14-NF-168-v3: independent DESIGN reference, not production codec code.

Only NONE and PAIR2 remain. No pending target/direction and no encoder calls.
Every valid update uses sign(new target - current OUTPUT weight).
PAIR2 has two adjacent states per weight; neutral/ineligible events preserve it.
The built-in C fixture only covers 0..9, not a complete Rice implementation.
"""
from __future__ import annotations

import itertools
import json
import random
from dataclasses import dataclass
from fractions import Fraction
from typing import Callable, Sequence

Cost = Callable[[int], int]
REVISION = "R14-NF-168-v3"
MODES = ("NONE", "PAIR2")
RHO = Fraction(21, 2)


def canonical(p: int) -> int:
    return 0 if p <= 1 else p


def validate_h(h: Sequence[int]) -> tuple[int, ...]:
    h = tuple(h)
    if len(h) != 5 or any(not isinstance(x, int) or x < 0 for x in h):
        raise ValueError("H must contain five nonnegative integer magnitudes")
    return h


def validate_grid(k: int, grid: Sequence[int] | None = None) -> tuple[int, ...]:
    g = tuple(range(k + 1)) if grid is None else tuple(grid)
    if (k <= 0 or not g or tuple(sorted(set(g))) != g
            or any(not isinstance(x, int) for x in g) or g[0] < 0 or g[-1] > k):
        raise ValueError("Invalid K/grid")
    return g


def factor(mode: str) -> int:
    if mode not in MODES:
        raise ValueError("Only NONE and PAIR2 are active; legacy buffers retired")
    return 1 if mode == "NONE" else 2


def down168(c: int) -> int:
    if c < 1:
        raise ValueError("Positive magnitude cost must be at least one")
    return 168 * c - 4 * (c - 1) ** 2 if c <= 22 else 1932


def up168(c: int) -> int:
    if c < 1:
        raise ValueError("Positive magnitude cost must be at least one")
    return 168 * c - 4 * (c - 1) ** 2 if c <= 11 else 84 * c + 525


def loss168(m: int, p: int, cost: Cost) -> int:
    if m <= 0 or p < 0:
        raise ValueError("Positive sample and nonnegative predictor required")
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
    pool = {0, current, *(canonical(x) for x in h if x > 0)}
    return (current,) + tuple(sorted(pool - {current}))


def all_winners(h: Sequence[int], k: int, cost: Cost,
                grid: Sequence[int] | None = None) -> dict[int, int]:
    h = validate_h(h)
    grid = validate_grid(k, grid)
    if sum(m > 0 for m in h) < 3:
        return {r: max(h[:2]) for r in grid}
    best, scores = {}, {}
    for p in candidate_order(h):
        near = sum(loss168(m, p, cost) for m in h[:2] if m)
        far = sum(loss168(m, p, cost) for m in h[2:] if m)
        value = k * near
        for r in range(k + 1):
            if r in grid and (r not in scores or value < scores[r]):
                scores[r], best[r] = value, p
            value += far
    return best


def fixed_q_cost(a: int, p: int, cost: Cost) -> int:
    if a < 0 or p < 0:
        raise ValueError("Nonnegative values required")
    if a == 0:
        return 0  # Zero excluded from feedback; not a free syntax claim.
    if p <= 1:
        return cost(a)
    if p == a:
        return cost(1)
    return cost(a + 1 if p > a else a)


def feedback_target(winners: dict[int, int], r: int, a: int, cost: Cost) -> int:
    if a <= 0 or r not in winners:
        raise ValueError("Positive committed magnitude and valid weight required")
    ca, cap = cost(a), cost(a + 1)
    def value(p: int) -> int:
        return ca if p <= 1 else 1 if p == a else cap if p > a else ca
    return min(winners, key=lambda t: (value(winners[t]), abs(t - r), -t))


def eligible(h: Sequence[int], a: int, target_path: bool = True) -> bool:
    h = validate_h(h)
    return (target_path and a > 0 and sum(m > 0 for m in h) >= 3
            and any(h[:2]) and any(h[2:]))


@dataclass(frozen=True)
class State:
    # Index within microstates, NOT an absolute sparse-grid weight.
    value: int


def output_weight(state: State, mode: str, grid: Sequence[int]) -> int:
    g = factor(mode)
    if not 0 <= state.value < g * len(grid):
        raise ValueError("State outside legal range")
    return grid[state.value // g]


def initial_state(r0: int, mode: str, grid: Sequence[int]) -> State:
    grid = tuple(grid)
    if r0 not in grid:
        raise ValueError("Initial weight outside grid")
    g = factor(mode)
    idx = grid.index(r0)
    # Endpoint priors use endpoint microstates; Half uses lower microstate.
    return State(g * len(grid) - 1 if idx == len(grid) - 1 else g * idx)


def step(state: State, wanted: int | None, mode: str,
         grid: Sequence[int], valid: bool = True) -> State:
    grid = tuple(grid)
    if not grid or tuple(sorted(set(grid))) != grid:
        raise ValueError("Sorted unique grid required")
    r = output_weight(state, mode, grid)
    if not valid:
        return state
    if wanted not in grid:
        raise ValueError("Valid target must be on grid")
    d = (wanted > r) - (wanted < r)
    # Neutral evidence preserves phase: never reset to 2*r or clear a buffer.
    return State(max(0, min(factor(mode) * len(grid) - 1, state.value + d)))


# Independent test oracles, not deployed predictor code.
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
    result = 168 * (base - correction)
    assert result.denominator == 1
    return int(result)


def oracle_winner(h: Sequence[int], k: int, r: int, cost: Cost) -> int:
    if sum(x > 0 for x in h) < 3:
        return max(h[:2])
    native = canonical(max(h[:2]))
    pool = {0, native, *(canonical(x) for x in h if x > 0)}
    def key(p: int) -> tuple[int, int, int]:
        score = sum(w * oracle_loss(m, p, cost)
                    for w, m in zip((k, k, r, r, r), h) if m)
        return score, 0 if p == native else 1, p
    return min(pool, key=key)


def oracle_step(state: State, wanted: int | None, mode: str,
                grid: Sequence[int], valid: bool = True) -> State:
    labels = tuple(r for r in grid for _ in range(1 if mode == "NONE" else 2))
    here = labels[state.value]
    if not valid or wanted == here:
        return state
    if wanted > here:
        return State(min(state.value + 1, len(labels) - 1))
    return State(max(state.value - 1, 0))


def small_cost(a: int) -> int:
    values = (0, 1, 3, 3, 4, 4, 5, 5, 6, 6)
    if not 0 <= a < len(values):
        raise ValueError("Fixture only defines C for 0..9")
    return values[a]


def run_tests() -> dict[str, object]:
    counts = dict(rational_table_entries=0, neighborhoods=0,
                  eligible_grid_winner_checks=0, microstate_transitions=0,
                  synthetic_feedback_events=0, scaled_grid_steps=0,
                  explicit_cases=0)
    for c in range(1, 257):
        for upper, fn in ((2 * RHO, down168), (RHO, up168)):
            expected = 168 * (c - positive_area(c - 1, upper) / (2 * RHO))
            assert expected.denominator == 1 and fn(c) == expected
            counts['rational_table_entries'] += 1
    for h in itertools.product(range(5), repeat=5):
        counts['neighborhoods'] += 1
        for k in (2, 4):
            for r, p in all_winners(h, k, small_cost).items():
                assert p == oracle_winner(h, k, r, small_cost)
                if sum(x > 0 for x in h) >= 3:
                    counts['eligible_grid_winner_checks'] += 1
        w2 = all_winners(h, 2, small_cost)
        w4 = all_winners(h, 4, small_cost, (0, 2, 4))
        assert all(w2[r] == w4[2*r] for r in w2)
    for k in (2, 4):
        grid = tuple(range(k + 1))
        for mode in MODES:
            labels = [r for r in grid for _ in range(factor(mode))]
            for v, r in enumerate(labels):
                before = State(v)
                assert output_weight(before, mode, grid) == r
                for wanted in (None,) + grid:
                    valid = wanted is not None
                    after = step(before, wanted, mode, grid, valid)
                    assert after == oracle_step(before, wanted, mode, grid, valid)
                    assert abs(after.value - v) <= 1
                    assert abs(output_weight(after, mode, grid) - r) <= 1
                    if not valid or wanted == r:
                        assert after == before
                    counts['microstate_transitions'] += 1
    rng = random.Random(20261023)
    for k in (2, 4):
        grid = tuple(range(k + 1))
        for mode in MODES:
            for init in (k, k // 2, 0):
                state = initial_state(init, mode, grid)
                saved = state
                for i in range(1000):
                    if i % 16 == 0:
                        saved = state
                    h = tuple(rng.randrange(9) for _ in range(5))
                    a = rng.randrange(9)
                    w = all_winners(h, k, small_cost)
                    r = output_weight(state, mode, grid)
                    valid = eligible(h, a)
                    t = feedback_target(w, r, a, small_cost) if valid else None
                    if valid:
                        assert t == min(grid, key=lambda x:
                            (fixed_q_cost(a, w[x], small_cost), abs(x-r), -x))
                    new = step(state, t, mode, grid, valid)
                    assert new == oracle_step(state, t, mode, grid, valid)
                    assert abs(output_weight(new, mode, grid)-r) <= 1
                    state = new
                    if i % 16 == 15 and rng.randrange(4) == 0:
                        state = saved  # Restore microstate including parity/phase.
                        assert state == saved
                    counts['synthetic_feedback_events'] += 1
    for mode in MODES:
        for init in (0, 1, 2):
            s2 = initial_state(init, mode, (0, 1, 2))
            s4 = initial_state(2 * init, mode, (0, 2, 4))
            for _ in range(1000):
                h = tuple(rng.randrange(9) for _ in range(5))
                a = rng.randrange(9)
                w2 = all_winners(h, 2, small_cost)
                w4 = all_winners(h, 4, small_cost, (0, 2, 4))
                r2 = output_weight(s2, mode, (0, 1, 2))
                r4 = output_weight(s4, mode, (0, 2, 4))
                assert r4 == 2*r2 and w4[r4] == w2[r2]
                valid = eligible(h, a)
                t2 = feedback_target(w2, r2, a, small_cost) if valid else None
                t4 = feedback_target(w4, r4, a, small_cost) if valid else None
                assert t4 == (None if t2 is None else 2*t2)
                s2 = step(s2, t2, mode, (0, 1, 2), valid)
                s4 = step(s4, t4, mode, (0, 2, 4), valid)
                assert s2 == s4  # Microstate is a grid index, same after scaling.
                counts['scaled_grid_steps'] += 1
    for k in (2, 4):
        grid = tuple(range(k + 1))
        assert [output_weight(State(s), 'PAIR2', grid) for s in range(2*k+2)] == [r for r in grid for _ in (0, 1)]
        counts['explicit_cases'] += 1
        for init in (0, k//2, k):
            state = initial_state(init, 'PAIR2', grid)
            expected = 2*k+1 if init == k else 2*init
            assert state == State(expected) and output_weight(state, 'PAIR2', grid) == init
            counts['explicit_cases'] += 1
        for mode in MODES:
            g = factor(mode)
            low, high = initial_state(0, mode, grid), initial_state(k, mode, grid)
            up, down = [], []
            for _ in range(g*k):
                low = step(low, k, mode, grid)
                high = step(high, 0, mode, grid)
                up.append(output_weight(low, mode, grid))
                down.append(output_weight(high, mode, grid))
            assert up == [i//g for i in range(1, g*k+1)]
            assert down == [(g*(k+1)-1-i)//g for i in range(1, g*k+1)]
            counts['explicit_cases'] += 1
    # Boundary reversal can change the weight after ONE event, unlike strict DIR2.
    s = step(State(3), 4, 'PAIR2', range(5))
    assert s == State(4) and output_weight(s, 'PAIR2', range(5)) == 2
    assert step(s, 0, 'PAIR2', range(5)) == State(3)
    counts['explicit_cases'] += 1
    # Target 3 then 4: both give +; targets themselves are never remembered.
    s = step(step(State(4), 3, 'PAIR2', range(5)), 4, 'PAIR2', range(5))
    assert s == State(6)
    counts['explicit_cases'] += 1
    # Neutral and invalid feedback do not destroy an odd microstate.
    assert step(State(5), 2, 'PAIR2', range(5)) == State(5)
    assert step(State(5), None, 'PAIR2', range(5), False) == State(5)
    counts['explicit_cases'] += 1
    # Rollback must restore the low bit, not just the output weight.
    saved = State(5)
    trial = step(saved, 4, 'PAIR2', range(5))
    assert trial == State(6)
    trial = saved
    assert step(trial, 4, 'PAIR2', range(5)) == State(6)
    counts['explicit_cases'] += 1
    assert all_winners((4, 4, 3, 3, 3), 2, small_cost) == {0: 4, 1: 4, 2: 3}
    counts['explicit_cases'] += 1
    w = all_winners((0, 1, 2, 3, 6), 2, small_cost)
    assert w == {0: 0, 1: 0, 2: 6} and feedback_target(w, 1, 3, small_cost) == 1
    counts['explicit_cases'] += 1
    # A distant better target does not imply every intermediate output is better.
    w = {0: 0, 1: 6, 2: 3}
    t = feedback_target(w, 0, 3, small_cost)
    s = step(step(State(0), t, 'PAIR2', range(3)), t, 'PAIR2', range(3))
    assert s == State(2) and fixed_q_cost(3, w[1], small_cost) > fixed_q_cost(3, w[0], small_cost)
    counts['explicit_cases'] += 1
    for retired in ('TARGET2', 'DIR2'):
        try:
            factor(retired)
        except ValueError:
            pass
        else:
            raise AssertionError('Retired rule accepted')
        counts['explicit_cases'] += 1
    return {'revision': REVISION, 'status': 'pass', 'checks': counts,
            'scope': 'Pure mathematical/state reference only; no codec integration or video encoding',
            'transition': 'direction only; NONE one weight step; PAIR2 one microstate step',
            'seed': 20261023}


if __name__ == '__main__':
    print(json.dumps(run_tests(), ensure_ascii=False, indent=2))
