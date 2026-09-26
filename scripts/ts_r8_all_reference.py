"""Independent literal R8 design evaluator; deliberately no codec optimizations.

Input CF is the already mixed immutable cost for C01/C02; native codec tests
separately verify their path weights, CABAC snapshots and CG causality.
"""
import json
from pathlib import Path
from ts_r8_design_check import canonical, candidates, rank, regret_brute, remap, smooth
from ts_r8_first8_reference import Decision

SPEC = {r['mode']: r for r in json.loads(Path(__file__).with_name('ts_r8_experiment_manifest.json').read_text())['experiments']}


def select(mode, neighbours, cf, ci, limit):
    spec = SPEC[mode]
    a = tuple(neighbours)
    current = canonical(max(a[:2]))
    nz = tuple(v for v in a if v)
    n = len(nz)
    if n < 3 and not (mode == 20 and n):
        pred = current
        if spec['sparse'] != 'S0':
            pred = 0
            if n == 2 and a[0] and a[1]:
                pred = canonical((a[0]+a[1]+1)//2 if spec['sparse'] == 'Smean' else
                                 min(a[:2]) if spec['sparse'] == 'Smin' else max(a[:2]))
        return Decision(current, pred, n)
    cost = ci if spec['cost'] == 'integer' else (
        tuple(x+y for x,y in zip(cf,ci)) if spec['cost'] == 'integer_fractional_1_1' else cf)
    smoothed = spec['samples'] == 'smooth_121'
    ps = tuple(candidates(smooth(nz,limit) if smoothed else nz,limit,spec['candidates'] != 'P0'))
    entries = [smooth((v,),limit) if smoothed else {v:1} for v in nz]
    loss = [[sum(w*cost[remap(v,p)] for v,w in entry.items()) for entry in entries] for p in ps]
    scores = tuple(map(sum,loss))
    raw_idx = min(range(len(ps)),key=lambda k:(scores[k],rank(ps[k],current)))
    cur = ps.index(current)
    gain = scores[cur]-scores[raw_idx]
    margin = gain-max([0]+[x-y for x,y in zip(loss[cur],loss[raw_idx])])
    chosen, regrets = ps[raw_idx], ()
    rule = spec['decision']
    if rule == 'guard':
        chosen = chosen if margin > 0 else current
    elif rule == 'unaccepted_to_identity':
        chosen = chosen if margin > 0 else 0
    elif rule == 'rejected_to_identity':
        chosen = 0 if chosen != current and margin <= 0 else chosen
    elif rule in ('trim_cost','trim_saving'):
        robust = [s-min(row) if rule == 'trim_cost' else
                  s+max([0]+[cost[v]-r for v,r in zip(nz,row)]) for s,row in zip(scores,loss)]
        chosen = ps[min(range(len(ps)),key=lambda k:(robust[k],rank(ps[k],current)))]
    elif rule == 'minimax_regret':
        regrets = tuple(regret_brute(loss))
        chosen = ps[min(range(len(ps)),key=lambda k:(regrets[k],scores[k],rank(ps[k],current)))]
    else:
        assert rule == 'raw',rule
    return Decision(current,chosen,n,ps,scores,ps[raw_idx],gain,margin,regrets)
