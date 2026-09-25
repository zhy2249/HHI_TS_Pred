#!/usr/bin/env python3
"""Executable mathematical specification for the selected R8 first eight.

NOT linked into the codec. Inputs are five causal magnitudes and immutable cost
tables in common Q15 units; no target coefficient or encoder-only information.
Synthetic activity establishes non-equivalence, not reachable CABAC/CTC gains.
"""
from dataclasses import dataclass
from itertools import product
import json

from ts_r8_design_check import candidates, canonical, rank, regret_fast, remap, smooth

FIRST8 = (1, 4, 8, 13, 15, 16, 17, 19)
PRIMARY = {1: 'R7-1', 4: 1, 8: 'R7-2', 13: 1, 15: 'R7-1', 16: 1, 17: 1, 19: 16}
# cost / samples / candidates / decision / sparse. Existing R7 controls are
# included only as reference formulas; this file does not execute old binaries.
SPEC = {
    'R7-1': ('fractional10', 'empirical', 'P0', 'raw', 'S0'),
    'R7-2': ('fractional10', 'empirical', 'P0', 'guard', 'S0'),
    1: ('fractional10', 'empirical', 'P0', 'raw', 'Smax'),
    4: ('fractional10', 'empirical', 'P0', 'guard', 'Smax'),
    8: ('fractional10', 'empirical', 'P0', 'rejected_to_identity', 'S0'),
    13: ('integer_fractional_1_1', 'empirical', 'P0', 'raw', 'Smax'),
    15: ('fractional10', 'empirical', 'P1', 'raw', 'S0'),
    16: ('fractional10', 'empirical', 'P1', 'raw', 'Smax'),
    17: ('fractional10', 'empirical', 'P0', 'minimax_regret', 'Smax'),
    19: ('fractional10', 'smooth_121', 'Psmooth', 'raw', 'Smax'),
}


@dataclass(frozen=True)
class Decision:
    current: int
    predictor: int
    support: int
    candidates: tuple = ()
    scores: tuple = ()
    raw_winner: object = None
    raw_gain: object = None
    raw_margin: object = None
    regrets: tuple = ()


def select(mode, neighbours, cf_q15, ci_q15, limit):
    if mode not in SPEC:
        raise ValueError('Mode is not a selected first-eight or an R7 reference')
    a, cf, ci = tuple(neighbours), tuple(cf_q15), tuple(ci_q15)
    if len(a) != 5 or any(type(v) is not int or not 0 <= v <= limit for v in a):
        raise ValueError('Expected five nonnegative legal L/U/D/LL/UU magnitudes')
    for table in (cf, ci):
        if len(table) <= limit or table[0] != 0 or any(type(v) is not int or v < 0 for v in table):
            raise ValueError('Expected nonnegative integer cost table, with zero at level zero')
    cost_model, sample_model, candidate_model, rule, sparse = SPEC[mode]
    current = canonical(max(a[:2]))
    nz = tuple(v for v in a if v)
    n = len(nz)
    if n < 3:
        keep = sparse == 'S0' or (n == 2 and a[0] and a[1])
        return Decision(current, current if keep else 0, n)

    table = tuple(x + y for x, y in zip(cf, ci)) if cost_model == 'integer_fractional_1_1' else cf
    support = smooth(nz, limit) if sample_model == 'smooth_121' else nz
    ps = tuple(candidates(support, limit, complete=candidate_model != 'P0'))
    # Preserve original positions as independent loss entries. For smoothing,
    # each entry is its clipped 1:2:1 weighted loss, not a new support count.
    weights = [smooth((v,), limit) if sample_model == 'smooth_121' else {v: 1} for v in nz]
    loss = [[sum(w * table[remap(v, p)] for v, w in entry.items()) for entry in weights] for p in ps]
    scores = tuple(map(sum, loss))
    raw_idx = min(range(len(ps)), key=lambda k: (scores[k], rank(ps[k], current)))
    cur_idx = ps.index(current)
    raw = ps[raw_idx]
    gain = scores[cur_idx] - scores[raw_idx]
    best_positive = max([0] + [x - y for x, y in zip(loss[cur_idx], loss[raw_idx])])
    margin = gain - best_positive
    chosen, regrets = raw, ()
    if rule == 'guard':
        chosen = raw if margin > 0 else current
    elif rule == 'rejected_to_identity':
        chosen = 0 if raw != current and margin <= 0 else raw
    elif rule == 'minimax_regret':
        regrets = tuple(regret_fast(loss))
        idx = min(range(len(ps)), key=lambda k: (regrets[k], scores[k], rank(ps[k], current)))
        chosen = ps[idx]
    return Decision(current, chosen, n, ps, scores, raw, gain, margin, regrets)


def verify_grid():
    limit = 12
    # CI values for this finite domain, Rice=1 (all remainders below escape).
    ci = tuple(v << 15 for v in (0, 1, 3, 3, 4, 4, 5, 5, 6, 6, 8, 8, 8))
    profiles = (ci, tuple([0] + [32768] * limit),
                tuple([0] + [(1 + (v * v + 7 * v + 3) % 19) << 15 for v in range(1, limit + 1)]))
    counts = {str(m): dict(predictor_diff_templates=0, remap_diff_targets=0) for m in FIRST8}
    decisions = 0
    for cf in profiles:
        for neighbours in product(range(4), repeat=5):
            result = {m: select(m, neighbours, cf, ci, limit) for m in SPEC}
            decisions += len(result)
            for mode in FIRST8:
                d, parent = result[mode], result[PRIMARY[mode]]
                assert 0 <= d.predictor <= limit
                if mode == 13 and cf == ci:
                    assert d.predictor == result[1].predictor
                if d.support >= 3:
                    assert result[1].predictor == result['R7-1'].predictor
                    assert result[4].predictor == result['R7-2'].predictor
                    assert result[15].predictor == result[16].predictor
                    assert len(d.candidates) <= (21 if mode == 19 else 11 if mode in (15, 16) else 6)
                    if mode in (15, 16):
                        score = lambda p: sum(cf[remap(v, p)] for v in neighbours if v)
                        brute = min(range(limit + 1), key=lambda p: (score(p), rank(p, d.current)))
                        assert d.predictor == canonical(brute)
                    if mode == 8:
                        expected = 0 if d.raw_winner != d.current and d.raw_margin <= 0 else d.raw_winner
                        assert d.predictor == expected
                counts[str(mode)]['predictor_diff_templates'] += d.predictor != parent.predictor
                counts[str(mode)]['remap_diff_targets'] += sum(
                    remap(v, d.predictor) != remap(v, parent.predictor) for v in range(1, limit + 1))
    return dict(causal_templates_per_profile=4 ** 5, synthetic_cost_profiles=len(profiles),
                reference_decisions=decisions, relative_to_primary_controls=counts,
                codec_verified=False, ctc_activity_measured=False, bdrate_measured=False)


if __name__ == '__main__':
    print(json.dumps(verify_grid(), indent=2))
