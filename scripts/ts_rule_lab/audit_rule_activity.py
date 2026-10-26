#!/usr/bin/env python3
"""Causal activity census for preselected diagnostic points, no decoding.

This measures potential remapping changes and TU-local state transitions.
It does not claim those positions use prediction after the TSRC bin budget,
or substitute a per-position rate/accuracy estimate for full-TU replay.
"""
import argparse
from collections import Counter
from pathlib import Path
import benchmark_rules as B
import rule_suite as R
import ts_corpus as P
import ts_learning as L

CASES = {('Johnny', 27), ('Johnny', 32), ('Johnny', 37),
         ('KristenAndSara', 32), ('FourPeople', 32)}


def census(tu):
    rows = list(L.causal_rows(tu))
    active = [row for row in rows if row['cache']]
    current = [row['pred'][0] for row in rows]
    nonzero = [row for row in rows if row['a']]
    pop = Counter(tu=1, positions=len(rows), nonzero=len(nonzero),
                  eligible_nonzero=sum(bool(row['cache']) for row in nonzero),
                  n3_nonzero=sum(sum(bool(v) for v in row['h']) == 3 for row in nonzero),
                  eq_sp_remap_changes=sum(L.remap(row['a'], row['pred'][L.EQ]) !=
                                          L.remap(row['a'], row['pred'][L.SP]) for row in nonzero))
    changed_positions = set()
    methods = {}
    for cfg in R.catalogue():
        pred = B.full_predictions(tu, cfg, rows, active, current)
        changes = [row['scan'] for row in nonzero
                   if L.remap(row['a'], pred[row['scan']]) != L.remap(row['a'], current[row['scan']])]
        changed_positions.update(changes)
        _, _, events = R.predict(tu, cfg, trace=True, prepared=active)
        methods[cfg['id']] = Counter(
            tu=1, tu_with_potential_remap_change=bool(changes),
            nonzero=len(nonzero), potential_remap_changes=len(changes),
            state_steps=sum(e['state_before'] != e['state_after'] for e in events),
            weight_steps=sum(e['weight_before'] != e['weight_after'] for e in events),
            candidate_margin_feedback=sum(e['feedback'] == 'candidate_margin' and e['direction'] != 0 for e in events),
            guarded_positions=sum(e['guarded'] for e in events))
    pop['any_rule_potential_remap_changes'] = len(changed_positions)
    return pop, methods


def run(index, output):
    idx = P.complete_index(index)
    selected = [r for r in idx['records'] if (r['task']['sequence'], r['task']['nominal_qp']) in CASES]
    if len(selected) != 2 * len(CASES):
        raise ValueError('Both origins of all predefined diagnostic points required')
    populations = []
    methods = []
    for rec in selected:
        total = Counter()
        by_method = {cfg['id']: Counter() for cfg in R.catalogue()}
        for tu in P.records(rec['data']):
            if tu['kind'] != 'tu':
                continue
            pop, stats = census(tu)
            total.update(pop)
            for key, values in stats.items():
                by_method[key].update(values)
        task = rec['task']
        identity = dict(sequence=task['sequence'], qp=task['nominal_qp'], origin=task['origin'])
        populations.append(dict(**identity, **total))
        methods.extend(dict(**identity, method=key, **values) for key, values in by_method.items())
    output.mkdir(parents=True, exist_ok=False)
    P.csvout(output / 'diagnostic_population.csv', populations)
    P.csvout(output / 'diagnostic_activity.csv', methods)
    P.save(output / 'scope.json', dict(cases=sorted(CASES), source_index_sha256=P.sha(index),
        rules_sha256=P.sha(R.__file__), scoring_sha256=P.sha(L.__file__),
        full_streams_at_selected_points=True, no_decode=True, no_rate_accuracy_claim=True,
        remap_scope='potential remapping before applying actual regular-bin budget; zero changes imply no policy coding effect'))
    print(populations)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--index', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    run(args.index, args.output)
