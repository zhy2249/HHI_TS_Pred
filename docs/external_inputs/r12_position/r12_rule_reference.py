"""R12 mathematical selectors; not a codec patch or rate/BD-speed benchmark.
Rows use caller-supplied causal expert losses. Q is a proxy cost unit, not a QP.
Run: python r12_rule_reference.py [validation.json]
"""
from __future__ import annotations
import itertools
import json
import random
import sys
from typing import Sequence

W = (2, 2, 1, 1, 1)  # L,U,D,LL,UU; never compress positions before weighting.

def canonical(p: int) -> int:
    return 0 if p <= 1 else p

def remap(a: int, p: int) -> int:
    if a == 0 or p <= 1:
        return a
    return 1 if a == p else a + 1 if a < p else a

def small_ci(a: int) -> int:
    """Exact documented syntaxCost part for a<10; tests stay in this range."""
    if not 0 <= a < 10:
        raise ValueError('small_ci only covers levels below 10')
    return a if a < 2 else 2 + sum(a >= x for x in (2, 4, 6, 8))

def weighted_predict(h: Sequence[int], costs: Sequence[int], policy: str,
                     weights: Sequence[int] = W) -> tuple[int, int, int, int]:
    """Return final predictor, raw winner, G_w, removed positive contribution.
    policy raw/full/soft: no deletion/full weighted deletion/one-unit deletion.
    This is the candidate C replacement, not the outer three-expert selector.
    """
    if len(h) != 5 or len(weights) != 5 or any(x < 0 for x in h):
        raise ValueError('five nonnegative magnitudes and weights required')
    current = canonical(max(h[:2]))
    if sum(x > 0 for x in h) < 3:
        return current, current, 0, 0
    candidates = [current] + [p for p in sorted({0, *(canonical(x) for x in h if x)}) if p != current]
    def score(p: int) -> int:
        return sum(w * costs[remap(a, p)] for a, w in zip(h, weights) if a)
    winner = min(candidates, key=score)  # list ordering preserves Current-first ties
    d = [costs[remap(a, current)] - costs[remap(a, winner)] if a else 0 for a in h]
    gain = sum(w * x for w, x in zip(weights, d))
    if policy == 'raw':
        penalty = 0
    elif policy == 'full':
        penalty = max([0] + [w * x for w, x in zip(weights, d)])
    elif policy == 'soft':
        if tuple(weights) != W:
            raise ValueError('soft policy is frozen to W=(2,2,1,1,1)')
        penalty = max([0] + d)
    else:
        raise ValueError(policy)
    return (winner if gain > penalty else current), winner, gain, penalty

def argmins(values: Sequence[int]) -> list[int]:
    v = min(values)
    return [e for e, x in enumerate(values) if x == v]

def totals(rows: Sequence[Sequence[int]], k: int, weights: Sequence[int] | None = None) -> list[int]:
    weights = list(weights) if weights is not None else [1] * len(rows)
    return [sum(weights[j] * row[e] for j, row in enumerate(rows)) for e in range(k)]

def baseline(ci: Sequence[Sequence[int]], cf: Sequence[Sequence[int]], k: int = 3) -> int:
    if not ci:
        return 0
    li, lf = totals(ci, k), totals(cf, k)
    return min(argmins(li), key=lambda e: (lf[e], e))

def strict_cf(pool: set[int], cf: Sequence[Sequence[int]], incumbent: int) -> int:
    """CF ties keep the preexisting R10-3 choice; only strict reduction switches."""
    lf = totals(cf, len(cf[0]))
    best = min(pool, key=lambda e: (lf[e], e))
    return best if lf[best] < lf[incumbent] else incumbent

def loo_pool(ci: Sequence[Sequence[int]], effective: Sequence[bool], winner: int) -> set[int]:
    """A deletion is meaningful only if at least one effective row remains."""
    out = {winner}
    if sum(effective) < 2:
        return out
    li = totals(ci, 3)
    for r, ok in enumerate(effective):
        if ok:
            out.update(argmins([li[e] - ci[r][e] for e in range(3)]))
    return out

def select(mode: int, ci: Sequence[Sequence[int]], cf: Sequence[Sequence[int]],
           positions: Sequence[int], effective: Sequence[bool], q: int = 1) -> int:
    """Reference for selector modes 1..6,9,10; current action shortcuts belong to codec.
    mode3 requires four columns; all others need >=3. positions index L,U,D,LL,UU.
    Rows are already filtered by the exact native V0 eligibility rules.
    """
    if mode not in (1, 2, 3, 4, 5, 6, 9, 10) or q <= 0:
        raise ValueError('unsupported selector or nonpositive q')
    if len(ci) != len(cf) or len(ci) != len(positions) or len(ci) != len(effective):
        raise ValueError('row metadata mismatch')
    if not ci:
        return 0
    k = 4 if mode == 3 else 3
    if any(len(x) < k for x in list(ci) + list(cf)) or any(x not in range(5) for x in positions):
        raise ValueError('invalid columns/positions')
    b = baseline(ci, cf)
    li = totals(ci, 3)
    t0 = argmins(li)
    if mode == 9:
        w = [W[p] for p in positions]
        wi, wf = totals(ci, 3, w), totals(cf, 3, w)
        return min(argmins(wi), key=lambda e: (wf[e], e))
    if mode == 10:
        wf = totals(cf, 3, [W[p] for p in positions])
        return min(t0, key=lambda e: (wf[e], e))
    if mode == 5:
        idx = [j for j, p in enumerate(positions) if p < 2]
        direct = totals([ci[j] for j in idx], 3)
        td = argmins(direct)
        return td[0] if idx and len(td) == 1 else b
    # Modes 1/2/3/4/6 protect ALL original exact-tie states before adding challengers.
    if len(t0) != 1:
        return b
    w = t0[0]
    near = {e for e in range(3) if 0 < li[e] - li[w] <= q}
    if mode == 1:
        pool = {w} | near
    elif mode == 2:
        pool = {w} | ({2} if 2 in near else set())
    elif mode == 3:
        ld = totals(ci, 4)[3]
        pool = {w} | ({3} if 0 <= ld - li[w] <= q else set())
    elif mode == 4:
        pool = loo_pool(ci, effective, w)
    else:  # true OR/union combination of modes 2 and 4
        pool = loo_pool(ci, effective, w) | ({2} if 2 in near else set())
    return strict_cf(pool, cf, w)

def tests() -> dict:
    rng = random.Random(12070809)
    n_rules = 0
    # Exact-tie guard: original draft would admit expert 2 and pick it.
    ci, cf = [[10, 10, 11]], [[8, 7, 1]]
    for m in (1, 2, 3, 4, 6):
        xci = [ci[0] + [10]] if m == 3 else ci
        xcf = [cf[0] + [0]] if m == 3 else cf
        assert select(m, xci, xcf, [0], [True]) == 1
        n_rules += 1
    # Far-better D is not a near challenger under the corrected two-sided condition.
    assert select(3, [[10, 12, 13, 2]], [[8, 9, 10, 1]], [0], [True]) == 0
    # Only one informative row: deleting it must not trigger LOO.
    assert select(4, [[1, 3, 4]], [[9, 2, 1]], [0], [True]) == 0
    # Union combination must activate C-near even when no meaningful LOO deletion is available.
    ci, cf = [[10, 10, 10], [10, 10, 10], [10, 12, 11]], [[5, 5, 5], [5, 5, 5], [9, 7, 1]]
    ef = [False, False, True]  # only one differing-mapping row in this synthetic fixture
    assert select(2, ci, cf, [0, 1, 2], ef) == 2
    assert select(4, ci, cf, [0, 1, 2], ef) == 0
    assert select(6, ci, cf, [0, 1, 2], ef) == 2
    n_rules += 5
    for _ in range(6000):
        n = rng.randrange(6)
        pos = rng.sample(range(5), n)
        ci = [[rng.randrange(1, 10) for _ in range(4)] for _ in range(n)]
        cf = [[rng.randrange(1, 800) for _ in range(4)] for _ in range(n)]
        ef = [bool(rng.randrange(2)) for _ in range(n)]
        b = baseline(ci, cf)
        li = totals(ci, 3)
        t = argmins(li)
        for m in (1, 2, 3, 4, 5, 6, 9, 10):
            e = select(m, ci, cf, pos, ef)
            assert 0 <= e < (4 if m == 3 else 3)
            # Common cost/threshold scaling must not change a decision.
            assert e == select(m, [[8*v for v in r] for r in ci],
                               [[8*v for v in r] for r in cf], pos, ef, q=8)
            if m in (1, 2, 3, 4, 6) and len(t) > 1:
                assert e == b
            if m == 10 and len(t) == 1:
                assert e == b
            n_rules += 1
    # Exhaustive small-amplitude algebra, real documented integer costs only.
    costs = [small_ci(i) for i in range(10)]
    n_neighborhood = 0
    example_groups = {}
    for h in itertools.product(range(6), repeat=5):
        raw = weighted_predict(h, costs, 'raw')
        full = weighted_predict(h, costs, 'full')
        soft = weighted_predict(h, costs, 'soft')
        current = canonical(max(h[:2]))
        assert raw[1] == full[1] == soft[1]
        if full[0] != current:
            assert full[0] == soft[0] == raw[0]
        if soft[0] != current:
            assert soft[0] == raw[0]
        # Increasing all weights by the same factor does not change raw/full choices.
        for policy in ('raw', 'full'):
            assert weighted_predict(h, costs, policy)[0] == weighted_predict(h, costs, policy, [2*w for w in W])[0]
        # L<->U, LL<->UU symmetry of the frozen distance weights.
        ht = (h[1], h[0], h[2], h[4], h[3])
        assert weighted_predict(ht, costs, 'raw')[0] == raw[0]
        # Preserve position labels: demonstrate a rearrangement can change the rule.
        key = (tuple(sorted(h)), current)
        entry = example_groups.setdefault(key, {})
        entry.setdefault(raw[0], h)
        n_neighborhood += 1
    example = next((list(v.items())[:2] for v in example_groups.values() if len(v) > 1), None)
    # Nonmonotone fractional-like synthetic tables are allowed in the algebra too.
    for _ in range(2000):
        h = tuple(rng.randrange(8) for _ in range(5))
        costs = [0] + [rng.randrange(1, 1000) for _ in range(9)]
        rr = [weighted_predict(h, costs, k) for k in ('raw', 'full', 'soft')]
        assert rr[0][1] == rr[1][1] == rr[2][1]
        assert rr[1][3] >= rr[2][3] >= 0
        n_rules += 1
    return {'status': 'pass', 'selector_and_random_algebra_cases': n_rules,
            'exhaustive_small_integer_neighborhoods': n_neighborhood,
            'same_amplitudes_different_positions_example': example,
            'scope': 'pure loss selectors and weighted candidate algebra; NOT codec integration, native scan, CABAC sync, video BD-rate, or timing'}

if __name__ == '__main__':
    report = tests()
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if len(sys.argv) > 1:
        with open(sys.argv[1], 'w', encoding='utf-8') as f:
            f.write(text + '\n')
    print(text)
