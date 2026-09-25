#!/usr/bin/env python3
"""R8 mathematical specification checks, NOT a codec implementation or smoke test.

Exhaustive finite-domain checks support the proofs in the design document.
Synthetic costs do not establish that a CABAC state occurs in real bitstreams.
"""
import argparse
from collections import Counter
from itertools import combinations_with_replacement
import json
import math
from pathlib import Path


def remap(a, p):
    return 0 if a == 0 else 1 if a == p else a + 1 if a < p else a


def inverse(v, p):
    return 0 if v == 0 else p if v == 1 and p > 0 else v - int(v <= p)


def canonical(p):
    return 0 if p <= 1 else p


def candidates(values, limit, complete=True):
    out = {0}
    for v in values:
        if v > 0:
            out.add(canonical(v))
            if complete:
                out.add(canonical(min(v + 1, limit)))
    return sorted(out)


def smooth(values, limit):
    out = Counter()
    for a in values:
        for delta, weight in ((-1, 1), (0, 2), (1, 1)):
            out[min(limit, max(0, a + delta))] += weight
    return out


def rank(p, current):
    p, current = canonical(p), canonical(current)
    return (p != current, p != 0, p)


def regret_fast(loss):
    totals = [sum(row) for row in loss]
    n = len(loss[0])
    best = [min(totals)] + [min(totals[k] - row[i] for k, row in enumerate(loss))
                            for i in range(n)]
    return [max([totals[k] - best[0]] +
                [totals[k] - row[i] - best[i + 1] for i in range(n)])
            for k, row in enumerate(loss)]


def regret_brute(loss):
    n = len(loss[0])
    return [max(sum(row[i] for i in range(n) if i != j) -
                min(sum(other[i] for i in range(n) if i != j) for other in loss)
                for j in range(-1, n)) for row in loss]


def check_manifest(path):
    manifest = json.loads(path.read_text())
    rows = manifest['experiments']
    assert manifest['status'] == 'design_only'
    assert [r['mode'] for r in rows] == list(range(1, 25))
    assert [r['id'] for r in rows] == ([f'A{i:02}' for i in range(1, 13)] +
                                     [f'B{i:02}' for i in range(1, 9)] +
                                     [f'C{i:02}' for i in range(1, 5)])
    assert len({r['directory'] for r in rows}) == 24
    assert len({r['runtime_reserved'] for r in rows}) == 24
    for r in rows:
        assert r['directory'].startswith(f"r8_{r['mode']}_")
        assert r['status'] == 'not_implemented'
        assert r['needs_rate_context'] == (r['cost'] != 'integer')
        assert r['direct_controls']
    by_id = {r['id']: r for r in rows}
    first = manifest['first_batch']
    assert first == ['A01', 'A04', 'A08', 'B01', 'B03', 'B04', 'B05', 'B07']
    assert [by_id[k]['mode'] for k in first] == [1, 4, 8, 13, 15, 16, 17, 19]
    assert {r['id'] for r in rows if r['batch'] == '1'} == set(first)
    primary = manifest['first_batch_primary_controls']
    assert set(primary) == set(first)
    assert all(p in first or p in ('R7-1', 'R7-2') for p in primary.values())
    assert primary['B07'] == 'B04'  # Smoothing must not lose its complete-candidate control.
    jobs = manifest['first_batch_point_counts']
    per_smoke = len(manifest['smoke']['sequences']) * len(manifest['smoke']['qp'])
    assert jobs == dict(lb_ce_new=len(first) * 7 * len(manifest['qp']),
                        smoke_new=len(first) * per_smoke,
                        smoke_controls=len(manifest['smoke']['controls']) * per_smoke,
                        smoke_total=(len(first) + len(manifest['smoke']['controls'])) * per_smoke)
    for child, parent, field in [('B04', 'B03', 'sparse'), ('B06', 'B05', 'candidates'),
                                 ('B08', 'B07', 'sparse'), ('C02', 'C01', 'cost')]:
        changes = [f for f in ('cost', 'samples', 'candidates', 'decision', 'sparse', 'search')
                   if by_id[child][f] != by_id[parent][f]]
        assert changes == [field], (child, parent, changes)
    assert by_id['C03']['search'] == by_id['C04']['search'] == 'dual_tu_up'
    return len(rows)


def check_math():
    limit, count, smooth_count, regret_count = 12, 0, 0, 0
    for a in range(limit + 1):
        for p in range(limit + 1):
            assert inverse(remap(a, p), p) == a
        assert remap(a, 0) == remap(a, 1)
    for n in range(6):
        for samples in combinations_with_replacement(range(1, 9), n):
            full = candidates(samples, limit)
            vector = lambda p: tuple(remap(a, p) for a in samples)
            assert {vector(p) for p in full} == {vector(p) for p in range(limit + 1)}
            assert len(full) <= 2 * n + 1
            weights = smooth(samples, limit)
            support = sorted(weights)
            smoothed = candidates(support, limit)
            vec_s = lambda p: tuple(remap(a, p) for a in support)
            assert {vec_s(p) for p in smoothed} == {vec_s(p) for p in range(limit + 1)}
            assert len(smoothed) <= 4 * n + 1
            assert sum(weights.values()) == 4 * n
            count += 1; smooth_count += 1
            # Deliberately nonmonotone, deterministic costs. No CABAC reachability claim.
            cost = lambda v: 0 if not v else 1 + (v * v + 7 * v + 3) % 19
            current = canonical(max(samples[:2], default=0))
            loss = [[cost(remap(a, p)) for a in samples] for p in full]
            fast = regret_fast(loss)
            assert fast == regret_brute(loss)
            assert fast == regret_fast([list(reversed(row)) for row in loss])
            assert regret_fast([[7 * v for v in row] for row in loss]) == [7 * v for v in fast]
            def choose(ps):
                matrix = [[cost(remap(a, p)) for a in samples] for p in ps]
                regrets = regret_fast(matrix)
                return min(range(len(ps)), key=lambda k:
                           (regrets[k], sum(matrix[k]), rank(ps[k], current)))
            all_p = [0] + list(range(2, limit + 1))
            k1, k2 = choose(full), choose(all_p)
            assert vector(full[k1]) == vector(all_p[k2])
            regret_count += 1
    # Clipped smoothing and candidates at the maximum legal magnitude.
    for samples in ((1,), (limit,), (1, limit), (limit,) * 5):
        weights = smooth(samples, limit)
        assert sum(weights.values()) == 4 * len(samples)
        assert all(0 <= v <= limit for v in weights)
        support = sorted(weights)
        vec = lambda p: tuple(remap(a, p) for a in support)
        assert {vec(p) for p in candidates(support, limit)} == {vec(p) for p in range(limit + 1)}
    # Nonmonotone fractional-cost counterexample from the supplied plan.
    c1 = -math.log2(0.2)
    c3 = -math.log2(0.8) - math.log2(0.1) - math.log2(0.2)
    c4 = -math.log2(0.8) - math.log2(0.9) - math.log2(0.8) - math.log2(0.9)
    assert c4 < c1 < c3
    # Native round/min/up union never exceeds three candidates, even without remap==1.
    for scaled in range(8 * limit + 1):
        rounded = min(limit, (scaled + 4) // 8)
        minimum = max(1, rounded - 1)
        up = min(limit, scaled // 8 + 1)
        levels = {rounded, minimum, up}
        assert len(levels) <= 3
    return dict(original_multisets=count, smoothed_multisets=smooth_count,
                minimax_checks=regret_count, remap_roundtrips=(limit + 1) ** 2,
                constructed_cost_bits={'C1': c1, 'C3': c3, 'C4': c4},
                codec_verified=False, bdrate_measured=False)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--manifest', type=Path,
                   default=Path(__file__).with_name('ts_r8_experiment_manifest.json'))
    args = p.parse_args()
    result = check_math()
    result['planned_experiments'] = check_manifest(args.manifest)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
