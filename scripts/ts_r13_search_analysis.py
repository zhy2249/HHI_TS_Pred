#!/usr/bin/env python3
"""Pair bounded R13 encoder search observations by semantic keys, not line number.

Only the exact common prefix is unambiguously aligned. After control-flow
changes, geometry/path/event/occurrence matching is a diagnostic correspondence,
not a claim that every private encoder input remained equal.
"""
import argparse
from collections import Counter
import csv
import hashlib
import json
import re
from pathlib import Path

PREFIX = 'TS_R13_SEARCH '
IDENTITY = ('poc', 'ctu', 'node_path', 'event', 'component', 'tu_x', 'tu_y',
            'tu_w', 'tu_h', 'tr_group', 'tr', 'mode', 'opts', 'mode_qp',
            'split', 'list', 'index')
IGNORE = {'seq', 'node', 'parent', '_line', '_key', '_occurrence', '_source', '_trace_complete', '_legacy_repairs'}
CONTROL = {'transform_trial': {'accepted'}, 'mode_result': {'accepted'},
           'mode_allowed': {'allowed'}, 'split_allowed': {'allowed'},
           'tt_skip_eval': {'skip'}, 'transform_group_gate': {'break_cbf', 'break_ts'},
           'cu_selected': {'no_finished_mode'}}
COST = {'cost', 'dist', 'frac_bits', 'q_hash', 'abs_sum', 'zero_cost'}


def parse(path, allow_truncated=False, legacy_byte_fields=False):
    rows, visits, count = [], Counter(), Counter()
    ancestry, active_modes, prepared = {}, {}, Counter()
    residual_calls, residual_visits = {}, Counter()
    truncated_groups = set()
    repaired_rows = 0
    for line_number, line in enumerate(path.read_text(errors='strict').splitlines(), 1):
        if not line.startswith(PREFIX):
            continue
        raw = line[len(PREFIX):]
        try:
            row = json.loads(raw)
        except json.JSONDecodeError:
            if not legacy_byte_fields:
                raise
            # Explicit recovery of the first diagnostic formatter revision,
            # whose int8 QP and uint8 RDO count streamed as unquoted characters.
            # Only malformed rows and these known fields are touched in memory.
            recovered = re.sub(r'"(qp|cu_qp|rdo_tried)":([^,}\r\n])(?=[,}])',
                lambda m: '"'+m[1]+'":'+(m[2] if m[2].isdigit() else str(ord(m[2]))), raw)
            row = json.loads(recovered)
            repaired_rows += 1
        if row.get('schema') != 1:
            raise ValueError(f'{path}:{line_number}: unsupported search schema')
        if row.get('event') == 'truncated':
            if not allow_truncated:
                raise ValueError(f'{path}:{line_number}: trace truncated; increase explicit limit')
            truncated_groups.add((row['poc'],row['ctu']))
            continue
        required = {'seq', 'event', 'poc', 'ctu', 'node', 'parent', 'node_path'}
        if not required.issubset(row):
            raise ValueError(f'{path}:{line_number}: incomplete search observation')
        group = row['poc'], row['ctu']
        count[group] += 1
        if row['seq'] != count[group]:
            raise ValueError(f'{path}:{line_number}: skipped/repeated sequence number')
        node_key = group + (row['node'],)
        parent_key = group + (row['parent'],)
        if row['event'] == 'cu_begin':
            parent_chain = ancestry.get(parent_key, ())
            parent_mode = active_modes.get(parent_key)
            ancestry[node_key] = parent_chain + ((parent_mode,) if row['parent'] else ())
        if row['event'] == 'mode_prepare' or (row['event'] == 'split_allowed' and row.get('allowed')):
            # Split search calls xCheckModeSplit directly: it does not call
            # EncCu::prepare. Its successful trySplit event is the parent mode.
            signature = (row['event'], row.get('mode'), row.get('opts'), row.get('mode_qp'))
            prepare_key = node_key + signature
            prepared[prepare_key] += 1
            active_modes[node_key] = signature + (prepared[prepare_key],)
            residual_calls.pop(node_key,None)
        if row['event'] == 'sbt_read':
            signature = (active_modes.get(node_key),row['sse_key'])
            call_key = node_key + signature
            residual_visits[call_key] += 1
            residual_calls[node_key] = signature + (residual_visits[call_key],)
        # Parent geometry/visit alone is insufficient after candidate lists
        # diverge: carry the parent's active prepared mode at child entry.
        row['_ancestry'] = ancestry.get(node_key, ())
        row['_active_mode'] = active_modes.get(node_key) if row['event'] not in (
            'mode_allowed', 'split_allowed', 'mode_prepare') else None
        row['_residual_call'] = residual_calls.get(node_key) if row['event'] in (
            'sbt_read','sbt_write','transform_entry','transform_trial','transform_group_gate',
            'transform_skip_cbf','mode_result','mode_context_restore') else None
        identity = tuple(row.get(k) for k in IDENTITY) + (row['_ancestry'], row['_active_mode'],row['_residual_call'])
        occurrence = visits[identity]
        visits[identity] += 1
        row.update(_key=identity + (occurrence,), _occurrence=occurrence,
                   _line=line_number, _source=str(path))
        rows.append(row)
    if not rows:
        raise ValueError(f'No search observations in {path}')
    for group in count:
        selected = [r for r in rows if (r['poc'], r['ctu']) == group]
        if (selected[0]['event'] != 'ctu_begin' or selected[-1]['event'] != 'ctu_end') and group not in truncated_groups:
            raise ValueError(f'{path}: incomplete CTU {group}; encoding may still be running')
    rows[-1]['_trace_complete'] = not truncated_groups
    rows[-1]['_legacy_repairs'] = repaired_rows
    return rows


def payload(row):
    return {k: v for k, v in row.items() if k not in IGNORE}


def differences(reference, test):
    a, b = payload(reference), payload(test)
    return {k: [a.get(k), b.get(k)] for k in sorted(a.keys() | b.keys())
            if a.get(k) != b.get(k)}


def locator(row):
    return {k: row.get(k) for k in ('_source', '_line', 'seq', 'poc', 'ctu',
            'node_path', '_occurrence', 'event', 'component', 'tu_x', 'tu_y',
            'tu_w', 'tu_h', 'tr_group', 'tr', 'mode', 'opts', '_ancestry', '_active_mode', '_residual_call')}


def transform_key(row):
    return tuple(row.get(k) for k in ('poc', 'ctu', 'node_path', 'component',
                 'tu_x', 'tu_y', 'tu_w', 'tu_h', 'tr_group', 'tr', '_occurrence', '_ancestry', '_active_mode', '_residual_call'))


def first_completed_node_difference(reference, test):
    """Compare completed search nodes; their last tested mode is not node identity.

    This is not the final bitstream tree: an ancestor can later reject a node.
    Report earlier unmatched nodes so correspondence never implies full coverage.
    """
    selected=[[r for r in rows if r['event']=='cu_selected'] for rows in (reference,test)]
    key=lambda r: (r['poc'],r['ctu'],r['node_path'],r['_ancestry'])
    indexes=[{key(r):r for r in rows} for rows in selected]
    fields=('cost','dist','frac_bits','cu_count','tu_count',
            'reco_y_hash','reco_cb_hash','reco_cr_hash')
    for a in selected[0]:
        b=indexes[1].get(key(a))
        if b is None:
            continue
        delta={k:[a.get(k),b.get(k)] for k in fields if a.get(k)!=b.get(k)}
        if delta:
            return dict(reference=locator(a),test=locator(b),changes=delta,
                unmatched_completed_nodes_before=[sum(
                    key(r) not in indexes[1-side]
                    for r in selected[side][:selected[side].index(end)])
                    for side,end in enumerate((a,b))],
                caveat='Completed search node, not necessarily retained in final bitstream tree')
    return None


def review(reference, test):
    exact_prefix = 0
    for a, b in zip(reference, test):
        if differences(a, b):
            break
        exact_prefix += 1
    indexed = [{r['_key']: r for r in rows} for rows in (reference, test)]
    entries = [{transform_key(r): r for r in rows if r['event'] == 'transform_entry'}
               for rows in (reference, test)]
    paired, unmatched = [], []
    first_cost = first_control = first_same_input_cost = first_history = None
    for position, a in enumerate(reference):
        b = indexed[1].get(a['_key'])
        if b is None:
            unmatched.append(dict(side='reference_only', **locator(a)))
            continue
        delta = differences(a, b)
        if not delta:
            continue
        entry_delta = None
        if a['event'] == 'transform_trial':
            ea, eb = (e.get(transform_key(a)) for e in entries)
            if ea is not None and eb is not None:
                entry_delta = differences(ea, eb)
        rec = {'reference': locator(a), 'test': locator(b), 'changes': delta,
               'matched_transform_entry_changes': entry_delta,
               'within_exact_prefix': position < exact_prefix}
        paired.append(rec)
        if first_cost is None and a['event'] == 'transform_trial' and COST.intersection(delta):
            first_cost = rec
        if (first_same_input_cost is None and a['event'] == 'transform_trial'
                and COST.intersection(delta) and entry_delta == {}):
            first_same_input_cost = rec
        if first_control is None and CONTROL.get(a['event'], set()).intersection(delta):
            first_control = rec
        history_fields = {'sbt_read': {'hist_sbt','hist_trs'},
                          'sbt_write': {'sbt','trs','stored','sse_key'},
                          'split_cost_write': {'horz_cost','vert_cost','tri_horz_cost','tri_vert_cost'}}
        if first_history is None and history_fields.get(a['event'],set()).intersection(delta):
            first_history = rec
    for b in test:
        if b['_key'] not in indexed[0]:
            unmatched.append(dict(side='test_only', **locator(b)))
    prefix_event = None
    if exact_prefix < min(len(reference), len(test)):
        a, b = reference[exact_prefix], test[exact_prefix]
        prefix_event = {'reference': locator(a), 'test': locator(b), 'changes': differences(a, b)}
    summary = {
        'schema': 1,
        'scope': 'Encoder search trace; short-prefix diagnosis, no BD-rate',
        'pairing': 'poc/ctu/node_path/event/semantic geometry/mode, active-mode ancestry captured at child entry, local prepared-mode signature, SBT residual-call key/occurrence and per-key occurrence; node IDs and global ordinal ignored',
        'post_divergence_caveat': 'Matched keys after a branch difference do not establish equal private search state; unmatched keys retained explicitly',
        'reference_rows': len(reference), 'test_rows': len(test),
        'reference_trace_complete': reference[-1].get('_trace_complete',True),
        'test_trace_complete': test[-1].get('_trace_complete',True),
        'legacy_byte_field_recovery_rows': [reference[-1].get('_legacy_repairs',0),test[-1].get('_legacy_repairs',0)],
        'truncation_caveat': 'A truncated prefix can locate an observed first divergence but cannot prove absence of later changes or complete the retained-result chain',
        'exact_common_prefix_events': exact_prefix,
        'first_event_difference': prefix_event,
        'first_transform_cost_or_q_difference': first_cost,
        'first_transform_cost_or_q_difference_with_equal_logged_entry': first_same_input_cost,
        'first_matched_control_difference': first_control,
        'first_matched_history_difference': first_history,
        'first_matched_completed_node_difference': first_completed_node_difference(reference,test),
        'paired_changed_events': len(paired), 'unmatched_events': len(unmatched),
        'reference_event_counts': dict(Counter(r['event'] for r in reference)),
        'test_event_counts': dict(Counter(r['event'] for r in test)),
    }
    return summary, paired, unmatched


def write_csv(path, rows):
    if not rows:
        path.write_text('')
        return
    with path.open('w', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--reference', required=True, type=Path)
    ap.add_argument('--test', required=True, type=Path)
    ap.add_argument('--output-dir', required=True, type=Path)
    ap.add_argument('--allow-truncated-prefix', action='store_true', help='Explicitly analyze only observed prefix; records incomplete status and does not certify a complete chain')
    ap.add_argument('--legacy-byte-fields', action='store_true', help='In-memory recovery of malformed QP/RDO-count byte fields in the first diagnostic build only; never alters raw logs')
    ap.add_argument('--details', action='store_true', help='Explicitly write all changed/unmatched event CSVs; may be tens or hundreds of MB. Default writes compact summary and first witnesses only')
    args = ap.parse_args()
    reference, test = parse(args.reference,args.allow_truncated_prefix,args.legacy_byte_fields), parse(args.test,args.allow_truncated_prefix,args.legacy_byte_fields)
    summary, paired, unmatched = review(reference, test)
    summary['sources'] = [{'path': str(p), 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()}
                          for p in (args.reference, args.test)]
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir/'search_comparison.json').write_text(json.dumps(summary, indent=2)+'\n')
    firsts={k:v for k,v in summary.items() if k.startswith('first_')}
    (args.output_dir/'first_search_divergences.json').write_text(json.dumps(dict(
        scope=summary['scope'],sources=summary['sources'],
        exact_common_prefix_events=summary['exact_common_prefix_events'],
        reference_trace_complete=summary['reference_trace_complete'],
        test_trace_complete=summary['test_trace_complete'],
        witnesses=firsts),indent=2)+'\n')
    if args.details:
        write_csv(args.output_dir/'changed_events.csv', [dict(
            **r['reference'], test_line=r['test']['_line'], test_seq=r['test']['seq'],
            changes=json.dumps(r['changes'], sort_keys=True, separators=(',', ':')),
            matched_transform_entry_changes=json.dumps(r['matched_transform_entry_changes'], sort_keys=True))
            for r in paired])
        write_csv(args.output_dir/'unmatched_events.csv', unmatched)
    print(json.dumps({k: summary[k] for k in ('reference_rows', 'test_rows',
          'exact_common_prefix_events', 'paired_changed_events', 'unmatched_events')}, indent=2))


if __name__ == '__main__':
    main()
