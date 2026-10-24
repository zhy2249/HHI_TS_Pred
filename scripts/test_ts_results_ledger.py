import json
import hashlib
from copy import deepcopy
import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch

from ts_fixed_analyze import QPS
from ts_results_ledger import (BD, METRICS, R9_MODES, R10_MODES, R11_MODES, R12_MODES, R13_MODES, R14_MODES,
                               QP_ANALYSIS_ROUNDS, REJECTED_CSV_SOURCES, build, build_qp_analysis, catalog, csv_sources,
                               csv_text, imputation_allowed, point_values, qp_markdown, qp_result,
                               read_primary_csv, read_sheet, sequence_result)


def curve(scale=1):
    rows = []
    for qp, i in zip(QPS, (3, 2, 1, 0)):
        anchor = [100 * 2**i, 30 + 2*i, 32 + i, 33 + 3*i]
        test = [anchor[0] * scale, *anchor[1:]]
        rows.append(dict(qp=qp, status='measured', anchor_record_status='pass', test_record_status='pass',
                         **dict(zip(('anchor_' + k for k in METRICS), anchor)),
                         **dict(zip(('test_' + k for k in METRICS), test))))
    return rows


class QPResultsTests(unittest.TestCase):
    def test_identity_all_four_qps(self):
        for qp in QPS:
            result = qp_result(curve(), qp)
            self.assertEqual(result['status'], 'calculated')
            for key in BD:
                self.assertAlmostEqual(result[key], 0, places=12)
            self.assertLess(result['max_vba_gap_pp'], 1e-8)

    def test_only_target_tuple_enters_curve_and_does_not_mutate_input(self):
        from ts_fixed_analyze import bd_rate
        rows = curve(.91)
        target = rows[1]
        target['test_psnr_u_db'] += .04
        target['test_psnr_v_db'] -= .03
        original = deepcopy(rows)
        expected = []
        for component in 'yuv':
            anchor = [(r[f'anchor_psnr_{component}_db'], r['anchor_rate_kbps']) for r in rows]
            mixed = anchor[:]
            mixed[1] = (target[f'test_psnr_{component}_db'], target['test_rate_kbps'])
            expected.append(bd_rate(anchor, mixed)[0])
        result = qp_result(rows, 27)
        self.assertEqual(rows, original)
        for i, key in enumerate(BD[:3]):
            self.assertAlmostEqual(result[key], expected[i], places=12)
        self.assertAlmostEqual(result['bd_611_pct'], (6*expected[0]+expected[1]+expected[2])/8, places=12)
        for row in rows:
            if row['qp'] != 27:
                row['status'] = 'missing'
                row['test_record_status'] = 'fail'
                for metric in METRICS:
                    row['test_' + metric] = ''
        self.assertEqual(qp_result(rows, 27), result)

    def test_missing_imputed_excluded_and_failed_target_stay_blank(self):
        for status in ('missing', 'anchor_imputed', 'excluded_unreliable'):
            with self.subTest(status=status):
                rows = curve(.9)
                rows[0]['status'] = status
                result = qp_result(rows, 22)
                self.assertEqual(result['status'], status)
                self.assertTrue(all(result[k] == '' for k in BD))
        rows = curve(.9)
        rows[0]['test_record_status'] = 'fail(md5 mismatch)'
        self.assertEqual(qp_result(rows, 22)['status'], 'invalid_target')
        self.assertEqual(qp_result(rows, 27)['status'], 'calculated')
        for qp in QPS:
            result = qp_result(curve(.9), qp, 'Entire uploaded experiment excluded')
            self.assertEqual(result['status'], 'excluded_unreliable')
            self.assertTrue(all(result[k] == '' for k in BD))

    def test_one_bad_reference_disqualifies_all_targets(self):
        rows = curve(.9)
        rows[-1]['anchor_record_status'] = 'fail(md5 mismatch)'
        for qp in QPS:
            result = qp_result(rows, qp)
            self.assertEqual(result['status'], 'invalid_anchor')
            self.assertTrue(all(result[k] == '' for k in BD))
        rows = curve(.9)
        rows[0]['anchor_psnr_u_db'] = rows[1]['anchor_psnr_u_db']
        self.assertEqual(qp_result(rows, 32)['status'], 'invalid_anchor')

    def test_invalid_mixed_curve_and_unique_qps(self):
        rows = curve(.9)
        rows[1]['test_psnr_y_db'] = rows[0]['anchor_psnr_y_db']
        self.assertEqual(qp_result(rows, 27)['status'], 'invalid')
        self.assertEqual(qp_result(rows, 32)['status'], 'calculated')
        for malformed in (rows[:3], rows[:3] + rows[:1]):
            with self.assertRaises(ValueError):
                qp_result(malformed, 27)
        with self.assertRaises(ValueError):
            qp_result(rows, 30)

    def test_selected_rounds_and_group_coverage_per_qp(self):
        def detailed(sequence, class_name):
            return [dict(r, round='r14', experiment='R14-1', mode='example', configuration='LB',
                         sequence=sequence, class_name=class_name, source_file='test.csv',
                         source_cell=f'CSV!B{i}:E{i}', anchor_file='anchor.xlsm',
                         anchor_cell=f'Reference!B{i}:E{i}') for i, r in enumerate(curve(.98), 1)]
        first, second = detailed('BQMall', 'C'), detailed('BasketballDrill', 'C')
        first[0]['status'] = 'anchor_imputed'
        spec = dict(round='r14', experiment='R14-1', qp_analysis=True)
        records, groups = build_qp_analysis([spec], first + second)
        self.assertEqual(len(records), 8)
        self.assertEqual(len(groups), 4)
        self.assertEqual(groups[0]['expected_sequences'], 4)
        self.assertEqual(groups[0]['valid_sequences'], 1)
        self.assertEqual(groups[0]['valid_sequence_names'], 'BasketballDrill')
        self.assertEqual(groups[0]['scope_status'], 'available_subset')
        self.assertEqual(groups[1]['valid_sequences'], 2)
        valid = [r for r in records if r['qp'] == 22 and r['status'] == 'calculated']
        self.assertEqual(groups[0]['bd_611_pct'], valid[0]['bd_611_pct'])
        self.assertEqual(len(json.loads(records[0]['anchor_sources'])), 4)
        self.assertIn('BQMall:anchor_imputed', groups[0]['unavailable_sequences'])
        text = '\n'.join(qp_markdown('R14-1', 'LB', records, groups))
        self.assertIn('| BQMall | Y |  |', text)  # Blank missing target, not zero or em dash.
        self.assertEqual(build_qp_analysis([dict(spec, qp_analysis=False)], first + second), ([], []))

    def test_catalog_qp_scope_is_explicit(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            path = root / 'experiments/ts_predictor_r8'
            path.mkdir(parents=True)
            for i in range(1, 25):
                (path / f'R8_{i}_JVET-hhi.xlsm').touch()
            selected = [s for s in catalog(root) if s.get('qp_analysis')]
        self.assertEqual({s['round'] for s in selected}, set(QP_ANALYSIS_ROUNDS))
        self.assertEqual(len(selected), 28)


class ResultsLedgerTests(unittest.TestCase):
    def test_r14_primary_csv_registration_and_corrected_result(self):
        from ts_predictor_naming import R14_MODE_NUMBERS
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            r8 = root / 'experiments/ts_predictor_r8'
            r8.mkdir(parents=True)
            for i in range(1, 25):
                (r8 / f'R8_{i}_JVET-hhi.xlsm').touch()
            specs = [s for s in catalog(root) if s['round'] == 'r14']
        self.assertEqual([s['experiment'] for s in specs], [f'R14-{i}' for i in range(1, 16)])
        self.assertEqual([s['mode'] for s in specs], list(R14_MODES))
        self.assertEqual([R14_MODE_NUMBERS[s['mode']] for s in specs], list(range(1, 16)))
        self.assertEqual([s['path'] for s in specs],
                         [f'experiments/ts_predictor_r14/{i}.csv' for i in range(1, 16)])
        self.assertFalse(any(s.get('excluded_reason') for s in specs))
        for spec in specs:
            self.assertEqual(spec['source_format'], 'csv')
            self.assertEqual(spec['numbering_revision'], 'compact-15-v1')
            self.assertEqual(csv_sources(spec, Path(spec['path'])), [])
            for qp in QPS:
                self.assertFalse(imputation_allowed(spec['experiment'], 'lb', 'PartyScene', qp))

    def test_r14_exclusion_follows_rejected_source_not_mode_number(self):
        old_content = b'Known rejected R14-2 upload'
        rejected_sha = hashlib.sha256(old_content).hexdigest()
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            r8 = root / 'experiments/ts_predictor_r8'
            r8.mkdir(parents=True)
            for i in range(1, 25):
                (r8 / f'R8_{i}_JVET-hhi.xlsm').touch()
            source = root / 'experiments/ts_predictor_r14/2.csv'
            source.parent.mkdir(parents=True)
            with patch.dict(REJECTED_CSV_SOURCES, {'R14-2': {rejected_sha: 'Rejected historical upload'}}):
                source.write_bytes(old_content)
                old = next(s for s in catalog(root) if s['experiment'] == 'R14-2')
                self.assertEqual(old['excluded_reason'], 'Rejected historical upload')
                source.write_bytes(b'Corrected partial R14-2 upload')
                corrected = next(s for s in catalog(root) if s['experiment'] == 'R14-2')
                self.assertNotIn('excluded_reason', corrected)
                for qp in QPS:
                    self.assertFalse(imputation_allowed('R14-2', 'lb', 'PartyScene', qp))

    def test_primary_csv_preserves_physical_line_status_and_missing(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / '1.csv'
            path.write_text('name,rate,y,u,v\n\nPartyScene.Q22.ecm.lb\n'
                            'PartyScene.Q27.ecm.lb,100,30,31,32,,,,,pass,2026-10-24\n', encoding='utf-8-sig')
            values, locations, statuses = read_primary_csv(path)
        self.assertEqual(values, {'PartyScene.Q27.ecm.lb': [100., 30., 31., 32.]})
        self.assertEqual(locations['PartyScene.Q27.ecm.lb'], 'CSV!B4:E4')
        self.assertEqual(locations['PartyScene.Q22.ecm.lb'], 'CSV!B3:E3')
        self.assertEqual(statuses, {'PartyScene.Q22.ecm.lb': '', 'PartyScene.Q27.ecm.lb': 'pass'})

    def test_primary_csv_rejects_partial_nonfinite_and_duplicate(self):
        bad_inputs = ('PartyScene.Q27.ecm.lb,100,30\n',
                      'PartyScene.Q27.ecm.lb,100,30,,32\n',
                      'PartyScene.Q27.ecm.lb,nan,30,31,32\n',
                      'PartyScene.Q27.ecm.lb,100,30,inf,32\n',
                      'PartyScene.Q27.ecm.lb,0,30,31,32\n',
                      'PartyScene.Q27.ecm.lb\nPartyScene.Q27.ecm.lb,100,30,31,32\n')
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / '1.csv'
            for text in bad_inputs:
                with self.subTest(text=text):
                    path.write_text(text)
                    with self.assertRaises(ValueError):
                        read_primary_csv(path)

    def test_unreliable_points_never_get_bd_even_complete(self):
        rows = curve(.9)
        rows[0]['status'] = 'excluded_unreliable'
        result = sequence_result(rows)
        self.assertEqual(result['status'], 'excluded_unreliable')
        self.assertEqual(result['measured_points'], 4)
        self.assertTrue(all(result[k] == '' for k in BD))
        self.assertEqual(rows[0]['test_rate_kbps'], 720)

    def test_csv_build_keeps_excluded_values_and_never_infers_neighbor_source(self):
        from ts_fixed_workbook_analysis import CLASSES
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'scripts').mkdir()
            (root / 'scripts/JVET-hhi.xlsm').write_bytes(b'anchor fixture')
            path = root / '2.csv'
            path.write_text('PartyScene.Q27.ecm.lb,123,30,31,32,,,,,pass\n')
            (root / '1.csv').write_text('PartyScene.Q22.ecm.lb,999,40,41,42,,,,,pass\n')
            anchor = {}
            for seq, cls in CLASSES.items():
                if cls == 'C':
                    for row in curve():
                        anchor[f'{seq}.Q{row["qp"]}.ecm.lb'] = [row['anchor_' + k] for k in METRICS]
            reference = (anchor, {k: 'Reference!B1:E1' for k in anchor}, {k: 'pass' for k in anchor})
            specs = [dict(round='r14', experiment='R14-2', mode=R14_MODES[1], path='2.csv',
                          source_format='csv', expected_lb='C', numbering_revision='compact-15-v1',
                          excluded_reason='Known unreliable uploaded result')]
            with patch('ts_results_ledger.catalog', return_value=specs), \
                    patch('ts_results_ledger.read_sheet', return_value=reference) as reader:
                _, points, sequences, summaries, audit = build(root)
            reader.assert_called_once_with(root / 'scripts/JVET-hhi.xlsm', 'Reference')
        received = [r for r in points if r['status'] == 'excluded_unreliable']
        self.assertEqual(len(received), 1)
        self.assertEqual(received[0]['test_rate_kbps'], 123)
        self.assertEqual(received[0]['value_source'], 'CSV')
        self.assertEqual(received[0]['source_cell'], 'CSV!B1:E1')
        self.assertFalse(received[0]['csv_rd_checked'])
        self.assertEqual(sum(r['status'] == 'missing' for r in points), 15)
        self.assertTrue(all(r['status'] == 'excluded_unreliable' for r in sequences))
        self.assertTrue(all(r['scope_status'] == 'excluded_unreliable' for r in summaries))
        self.assertTrue(all(r[k] == '' for r in sequences + summaries for k in BD))
        self.assertEqual(audit['csv_checks'], [])
        self.assertEqual({s['path'] for s in audit['sources']}, {'scripts/JVET-hhi.xlsm', '2.csv'})

    def test_r13_registration_preserves_public_numbering(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            r8 = root / 'experiments/ts_predictor_r8'
            r8.mkdir(parents=True)
            for i in range(1, 25):
                (r8 / f'R8_{i}_JVET-hhi.xlsm').touch()
            specs = [s for s in catalog(root) if s['round'] == 'r13']
        self.assertEqual([s['experiment'] for s in specs], ['R13-1', 'R13-2'])
        self.assertEqual([s['mode'] for s in specs], list(R13_MODES))
        # These committed experiment definitions are independent of pending codec
        # registration edits; result-ledger tests must work before codec upload.
        metadata_root = Path(__file__).resolve().parents[1] / 'experiments/ts_predictor_r13'
        for number, spec in enumerate(specs, 1):
            folder = f'r13_{number}_' + spec['mode'].removeprefix('r13_')
            metadata = json.loads((metadata_root / folder / 'run_metadata.template.json').read_text())
            self.assertEqual(metadata['public_mode'], number)
            self.assertEqual(metadata['runtime'], spec['mode'])
            self.assertEqual(metadata['revision'], 'R13-KH-168-v1')
        self.assertEqual([s['path'] for s in specs],
                         [f'experiments/ts_predictor_r13/R13_{i}_JVET-hhi.xlsm' for i in (1, 2)])
        self.assertTrue(all(s['expected_lb'] == 'CE' for s in specs))

    def test_r13_csv_pairing_is_exact_and_missing_never_imputed(self):
        with tempfile.TemporaryDirectory() as folder:
            p = Path(folder)
            for name in ('R13_1.csv', 'R13_2.csv', 'R13_1_B.csv', 'R13_10.csv',
                         'R13_1_backup.csv', '1.csv', '2.csv'):
                (p / name).touch()
            for i in (1, 2):
                self.assertEqual(csv_sources(dict(round='r13', experiment=f'R13-{i}'),
                                             p / f'R13_{i}_JVET-hhi.xlsm'), [p / f'R13_{i}.csv'])
            self.assertEqual(csv_sources(dict(round='r13', experiment='R13-3'),
                                         p / 'R13_3_JVET-hhi.xlsm'), [])
        for exp in ('R13-1', 'R13-2'):
            for config in ('lb', 'ra', 'ai'):
                for seq in ('BasketballDrill', 'BQMall', 'PartyScene', 'RaceHorsesC',
                            'FourPeople', 'Johnny', 'KristenAndSara'):
                    for qp in QPS:
                        self.assertFalse(imputation_allowed(exp, config, seq, qp))

    def test_r9_registration_preserves_mode_numbering(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            r8 = root / 'experiments/ts_predictor_r8'
            r8.mkdir(parents=True)
            for i in range(1, 25):
                (r8 / f'R8_{i}_JVET-hhi.xlsm').touch()
            specs = [s for s in catalog(root) if s['round'] == 'r9']
        self.assertEqual(len(specs), 13)
        self.assertEqual(len(set(R9_MODES)), 13)
        self.assertEqual([s['experiment'] for s in specs], [f'R9-{i}' for i in range(1, 14)])
        self.assertEqual(specs[0]['mode'], 'r9_p10')
        self.assertEqual(specs[10]['mode'], 'r9_quant_down')
        self.assertEqual(specs[11]['mode'], 'r9_quant_down_up')
        self.assertEqual(specs[12]['mode'], 'r9_axis_feature')
        self.assertTrue(all(s['expected_lb'] == ('BCE' if s['experiment'] == 'R9-9' else 'CE') for s in specs))

    def test_r10_registration_includes_only_received_results(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            r8 = root / 'experiments/ts_predictor_r8'
            r8.mkdir(parents=True)
            for i in range(1, 25):
                (r8 / f'R8_{i}_JVET-hhi.xlsm').touch()
            specs = [s for s in catalog(root) if s['round'] == 'r10']
        self.assertEqual(len(set(R10_MODES)), 6)
        self.assertEqual([s['experiment'] for s in specs], [f'R10-{i}' for i in range(1, 7)])
        self.assertEqual([s['mode'] for s in specs], list(R10_MODES))
        self.assertEqual(specs[5]['path'], 'experiments/ts_predictor_r10/R10_6_JVET-hhi.xlsm')
        self.assertTrue(all(s['expected_lb'] == ('BCE' if s['experiment'] == 'R10-3' else 'CE') for s in specs))
        self.assertEqual(specs[2]['extra_csv'], ('3_B.csv',))
        manifest = Path(__file__).with_name('ts_r10_experiment_manifest.json')
        modes = json.loads(manifest.read_text())['experiments']
        self.assertEqual(list(R10_MODES), [m['runtime'] for m in modes if 1 <= m['mode'] <= 6])

    def test_r11_registration_preserves_manifest_and_numbering(self):
        from ts_predictor_naming import R11_MODE_NUMBERS
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            r8 = root / 'experiments/ts_predictor_r8'
            r8.mkdir(parents=True)
            for i in range(1, 25):
                (r8 / f'R8_{i}_JVET-hhi.xlsm').touch()
            specs = [s for s in catalog(root) if s['round'] == 'r11']
        self.assertEqual([s['experiment'] for s in specs], [f'R11-{i}' for i in range(1, 9)])
        self.assertEqual([R11_MODE_NUMBERS[s['mode']] for s in specs], list(range(1, 9)))
        self.assertTrue(all(s['expected_lb'] == ('BCE' if s['experiment'] == 'R11-2' else 'CE') for s in specs))
        self.assertEqual([s['path'] for s in specs],
                         [f'experiments/ts_predictor_r11/R11_{i}_JVET-hhi.xlsm' for i in range(1, 9)])
        manifest = json.loads(Path(__file__).with_name('ts_r11_experiment_manifest.json').read_text())
        self.assertEqual(list(R11_MODES), [m['runtime'] for m in manifest['experiments']])

    def test_r11_and_partial_r10_b_do_not_extend_imputation(self):
        for exp in [f'R11-{i}' for i in range(1, 9)] + [f'R12-{i}' for i in range(1, 13)] + ['R10-3']:
            for seq in ('BasketballDrive', 'BQTerrace', 'MarketPlace', 'Cactus', 'PartyScene', 'RaceHorsesC'):
                for qp in QPS:
                    self.assertFalse(imputation_allowed(exp, 'lb', seq, qp))

    def test_r12_registration_uses_pos01_public_order(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); r8=root/'experiments/ts_predictor_r8'; r8.mkdir(parents=True)
            for i in range(1,25): (r8/f'R8_{i}_JVET-hhi.xlsm').touch()
            specs=[s for s in catalog(root) if s['round']=='r12']
        self.assertEqual([s['experiment'] for s in specs],[f'R12-{i}' for i in range(1,13)])
        self.assertEqual([s['mode'] for s in specs],list(R12_MODES))
        self.assertEqual([s['path'] for s in specs],
                         [f'experiments/ts_predictor_r12/R12_{i}_JVET-hhi.xlsm' for i in range(1,13)])
        self.assertTrue(all(s['expected_lb']=='CE' for s in specs))
        self.assertEqual(R12_MODES[2],'r12_current_near1')
        self.assertEqual(R12_MODES[10:12],('r12_c_distance_softtrim','r12_c_and_validation_distance'))

    def test_r12_csv_pairing_never_mix_1_and_10(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)
            for name in ('1.csv','10.csv','11.csv','12.csv','1_backup.csv','2_B.csv'): (p/name).touch()
            for i in (1,10,11,12):
                self.assertEqual(csv_sources(dict(round='r12',experiment=f'R12-{i}'),p/f'R12_{i}_JVET-hhi.xlsm'),[p/f'{i}.csv'])
            self.assertEqual(csv_sources(dict(round='r12',experiment='R12-2'),p/'R12_2_JVET-hhi.xlsm'),[])

    def test_r11_csv_pairing_and_explicit_r10_b_supplement(self):
        with tempfile.TemporaryDirectory() as folder:
            p = Path(folder)
            for name in ('1.csv', '3.csv', '3_B.csv', '3_backup.csv', '30.csv', '8.csv', '9.csv'):
                (p / name).touch()
            for i in (1, 3, 8):
                spec = dict(round='r11', experiment=f'R11-{i}')
                self.assertEqual([x.name for x in csv_sources(spec, p/f'R11_{i}_JVET-hhi.xlsm')], [f'{i}.csv'])
            spec = dict(round='r10', experiment='R10-3', extra_csv=('3_B.csv',))
            self.assertEqual([x.name for x in csv_sources(spec, p/'R10_3_JVET-hhi.xlsm')], ['3.csv', '3_B.csv'])

    def test_r9_numbered_csv_pairing(self):
        with tempfile.TemporaryDirectory() as folder:
            p = Path(folder)
            for name in ('1.csv', '2.csv', '10.csv', '11.csv', '13.csv'):
                (p / name).touch()
            for i in (1, 11, 13):
                self.assertEqual([x.name for x in csv_sources(dict(round='r9', experiment=f'R9-{i}'), p/f'R9_{i}_JVET-hhi.xlsm')],
                                 [f'{i}.csv'])
            self.assertEqual(csv_sources(dict(round='r9', experiment='R9-3'), p/'R9_3_JVET-hhi.xlsm'), [])

    def test_r9_missing_points_are_not_imputed(self):
        for i in range(1, 14):
            self.assertFalse(imputation_allowed(f'R9-{i}', 'lb', 'PartyScene', 22))

    def test_r10_numbered_csv_pairing(self):
        with tempfile.TemporaryDirectory() as folder:
            p = Path(folder)
            for name in ('1.csv', '2.csv', '6.csv', '7.csv', '10.csv'):
                (p / name).touch()
            for i in (1, 2, 6):
                self.assertEqual(csv_sources(dict(round='r10', experiment=f'R10-{i}'), p/f'R10_{i}_JVET-hhi.xlsm'),
                                 [p / f'{i}.csv'])
            self.assertEqual(csv_sources(dict(round='r10', experiment='R10-3'), p/'R10_3_JVET-hhi.xlsm'), [])

    def test_new_qp22_imputation_is_explicit_and_measured_wins(self):
        allowed = {'R9-9': ('MarketPlace', 'Cactus', 'BasketballDrive', 'BQTerrace'),
                   'R10-6': ('PartyScene', 'RaceHorsesC')}
        anchor, actual = [100, 30, 31, 32], [99, 30.1, 31.1, 32.1]
        for exp, seqs in allowed.items():
            for seq in seqs:
                self.assertEqual(point_values(exp, 'lb', seq, 22, None, anchor), (anchor, 'anchor_imputed'))
                self.assertEqual(point_values(exp, 'lb', seq, 22, actual, anchor), (actual, 'measured'))
                for config, qp in (('lb', 27), ('lb', 32), ('lb', 37), ('ra', 22), ('ai', 22)):
                    self.assertFalse(imputation_allowed(exp, config, seq, qp))
        for args in (('R9-8', 'lb', 'Cactus', 22), ('R9-9', 'lb', 'RitualDance', 22),
                     ('R10-1', 'lb', 'PartyScene', 22), ('R10-6', 'lb', 'BQMall', 22),
                     ('R10-7', 'lb', 'PartyScene', 22)):
            self.assertFalse(imputation_allowed(*args))

    def test_shared_folder_pairing_does_not_mix_experiments(self):
        with tempfile.TemporaryDirectory() as folder:
            p = Path(folder)
            for name in ('R6_1.csv', 'R6_2.csv', 'R6_2_B.csv', 'R6_20.csv', 'R6_3.csv'):
                (p / name).touch()
            self.assertEqual([x.name for x in csv_sources(dict(round='r6', experiment='R6-2'), p/'R6_2_JVET-hhi.xlsm')],
                             ['R6_2.csv', 'R6_2_B.csv'])

    def test_historical_imputation_is_narrow(self):
        self.assertTrue(imputation_allowed('R8-23', 'lb', 'PartyScene', 22))
        for args in [('R8-23', 'ra', 'PartyScene', 22), ('R8-1', 'lb', 'PartyScene', 22),
                     ('R8-23', 'lb', 'PartyScene', 27), ('R8-23', 'lb', 'BQMall', 22)]:
            self.assertFalse(imputation_allowed(*args))

    def test_measured_supersedes_imputation(self):
        a, t = [100, 30, 31, 32], [99, 30.1, 31.1, 32.1]
        self.assertEqual(point_values('R2-4', 'lb', 'PartyScene', 22, t, a), (t, 'measured'))
        self.assertEqual(point_values('R2-4', 'lb', 'PartyScene', 22, a, a), (a, 'measured'))
        values, status = point_values('R2-4', 'lb', 'PartyScene', 22, None, a)
        self.assertEqual((values, status), (a, 'anchor_imputed'))
        self.assertIsNot(values, a)

    def test_unapproved_missing_stays_empty(self):
        self.assertEqual(point_values('R3-1', 'ra', 'MarketPlace', 22, None, [1, 2, 3, 4]),
                         (['']*4, 'missing'))

    def test_component_first_bd_and_anchor_identity(self):
        for factor, expected in ((1, 0), (.9, -10), (1.1, 10)):
            result = sequence_result(curve(factor))
            self.assertEqual(result['status'], 'complete')
            for key in BD:
                self.assertAlmostEqual(result[key], expected, places=10)
            self.assertLess(result['max_vba_gap_pp'], 1e-8)
        rows = curve(.98)
        for row in rows:
            row['test_psnr_u_db'] += .05
            row['test_psnr_v_db'] -= .1
        r = sequence_result(rows)
        self.assertAlmostEqual(r['bd_611_pct'], (6*r['bd_y_pct']+r['bd_u_pct']+r['bd_v_pct'])/8)
        self.assertNotEqual(r['bd_y_pct'], r['bd_u_pct'])

    def test_incomplete_curve_not_three_point_or_zero_bd(self):
        rows = curve()
        rows[1]['status'] = 'missing'
        for k in METRICS:
            rows[1]['test_' + k] = ''
        r = sequence_result(rows)
        self.assertEqual(r['status'], 'incomplete')
        self.assertEqual(r['missing_points'], 1)
        self.assertTrue(all(r[k] == '' for k in BD))

    def test_imputation_remains_visible(self):
        rows = curve()
        rows[0]['status'] = 'anchor_imputed'
        r = sequence_result(rows)
        self.assertEqual((r['status'], r['measured_points'], r['imputed_points']), ('imputed', 3, 1))
        self.assertEqual(r['bd_611_pct'], 0)

    def test_failed_reference_forbids_bd_but_keeps_values(self):
        rows = curve()
        rows[-1]['anchor_record_status'] = 'fail(md5 mismatch).'
        r = sequence_result(rows)
        self.assertEqual(r['status'], 'invalid_anchor')
        self.assertTrue(all(r[k] == '' for k in BD))
        self.assertEqual(rows[-1]['anchor_rate_kbps'], 100)

    def test_requires_four_unique_qps(self):
        with self.assertRaises(ValueError):
            sequence_result(curve()[:3])
        with self.assertRaises(ValueError):
            sequence_result(curve()[:3]+curve()[:1])

    def test_no_overlap_and_nonmonotonic_curves(self):
        rows = curve()
        for row in rows:
            row['test_psnr_y_db'] += 100
        self.assertEqual(sequence_result(rows)['status'], 'invalid')
        rows = curve()
        rows[1]['test_psnr_y_db'] = rows[0]['test_psnr_y_db']
        self.assertEqual(sequence_result(rows)['status'], 'invalid')

    def test_sheet_preserves_failed_status_for_later_screening(self):
        cells = {'A1': 'PartyScene.Q22.ecm.lb', 'B1': 100, 'C1': 30, 'D1': 31,
                 'E1': 32, 'J1': 'fail(md5 mismatch).', 'A2': 'PartyScene.Q27.ecm.lb'}
        with patch('ts_results_ledger.sheet_values', return_value=cells):
            values, locations, statuses = read_sheet(Path('unused.xlsm'), 'Reference')
        self.assertEqual(values['PartyScene.Q22.ecm.lb'], [100, 30, 31, 32])
        self.assertEqual(locations['PartyScene.Q22.ecm.lb'], 'Reference!B1:E1')
        self.assertEqual(statuses['PartyScene.Q22.ecm.lb'], 'fail(md5 mismatch).')
        self.assertNotIn('PartyScene.Q27.ecm.lb', values)

    def test_partial_and_duplicate_sheet_rows_rejected(self):
        for cells in ({'A1': 'PartyScene.Q22.ecm.lb', 'B1': 100},
                      {'A1': 'PartyScene.Q22.ecm.lb', 'A2': 'PartyScene.Q22.ecm.lb'}):
            with patch('ts_results_ledger.sheet_values', return_value=cells):
                with self.assertRaises(ValueError):
                    read_sheet(Path('unused.xlsm'), 'Test')

    def test_csv_units_and_empty_not_zero(self):
        result = csv_text([dict(test_rate_kbps='', bd_y_pct=0.0, status='missing')])
        self.assertEqual(result, 'test_rate_kbps,bd_y_pct,status\n,0.0,missing\n')


if __name__ == '__main__':
    unittest.main()
