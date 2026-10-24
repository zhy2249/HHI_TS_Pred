import csv
from pathlib import Path
import tempfile
import unittest

from ts_r13_diagnostic import KEYS, RDOQ_COUNTS, export, parse


class R13DiagnosticTests(unittest.TestCase):
    def fixture(self):
        cg = dict(zip(KEYS['CG'], (99, 0, 1, 4, 4, 32, 1, 0, 1, 2)))
        cg.update(tu_count=1, cg_count=1, coded_cg_count=1, coeff_count=2, nonzero_count=1,
                  current_fracbits=65536, uniform_fracbits=65536, spatial_fracbits=98304)
        for ref in ('current', 'uniform'):
            cg.update({f'spatial_vs_{ref}_better': 0, f'spatial_vs_{ref}_tie': 0,
                       f'spatial_vs_{ref}_worse': 1, f'spatial_vs_{ref}_gain_fracbits': 0,
                       f'spatial_vs_{ref}_loss_fracbits': 32768})
        coeff = []
        for m in range(3):
            row = dict(zip(KEYS['COEFF'], (99, 0, 1, 4, 4, 32, 1, 0, m, 10, 3, 1)))
            row.update(coeff_count=2, nonzero_count=1, regular_nonzero_count=1,
                       target_hit_count=int(m < 2), target_under_count=0, target_over_count=int(m == 2),
                       actual_map1_count=int(m < 2), actual_map2_count=int(m == 2), actual_map_gt2_count=0)
            coeff.append(row)
        lines = ['TS R13 diagnosis=R13-DIAG-v1; frac-scale=32768; no-decision-feedback']
        for name, rows in (('CG', [cg]), ('COEFF', coeff)):
            lines.append(f'TS_R13_DIAG_{name}_HEADER ' + ','.join(rows[0]))
            lines.extend(f'TS_R13_DIAG_{name} ' + ','.join(str(v) for v in r.values()) for r in rows)
        return '\n'.join(lines) + '\n'

    def test_parse_and_fractional_summary(self):
        text = self.fixture()
        reports, scale = parse(text)
        self.assertEqual(scale, 32768)
        self.assertEqual(len(reports['COEFF']), 3)
        with tempfile.TemporaryDirectory() as folder:
            log, out = Path(folder)/'input.log', Path(folder)/'out'
            log.write_text(text)
            self.assertEqual(export([log], out, 'Johnny', '32'), 1)
            with (out/'writer_by_poc_component.csv').open() as stream:
                row = next(csv.DictReader(stream))
            self.assertEqual(float(row['spatial_minus_uniform_bits']), 1)
            self.assertEqual(int(row['nonzero_count']), 1)
            self.assertEqual(int(row['spatial_nonzero_count']), 1)
            self.assertEqual(float(row['spatial_over_rate']), 1)
            self.assertEqual(log.read_text(), text)

    def test_missing_duplicate_and_truncated(self):
        text = self.fixture()
        for bad in ('', text + text, text.replace('TS_R13_DIAG_CG_HEADER', 'OTHER'),
                    text + 'TS_R13_DIAG_COEFF 1,2\n'):
            with self.subTest(bad=bad[:50]), self.assertRaises(ValueError):
                parse(bad)

    def test_outcome_conservation(self):
        reports, _ = parse(self.fixture())
        row = reports['CG'][0]
        row['spatial_vs_uniform_worse'] = 2
        prefix = self.fixture().split('TS_R13_DIAG_CG_HEADER')[0]
        bad = prefix + 'TS_R13_DIAG_CG_HEADER ' + ','.join(row) + '\n'
        bad += 'TS_R13_DIAG_CG ' + ','.join(map(str, row.values())) + '\n'
        bad += 'TS_R13_DIAG_COEFF_HEADER' + self.fixture().split('TS_R13_DIAG_COEFF_HEADER', 1)[1]
        with self.assertRaisesRegex(ValueError, 'conserve'):
            parse(bad)

    def test_target_population_conservation(self):
        reports, _ = parse(self.fixture())
        rows = reports['COEFF']
        rows[2]['target_over_count'] = 0
        text = self.fixture().split('TS_R13_DIAG_COEFF_HEADER')[0]
        text += 'TS_R13_DIAG_COEFF_HEADER ' + ','.join(rows[0]) + '\n'
        text += ''.join('TS_R13_DIAG_COEFF ' + ','.join(map(str, r.values())) + '\n' for r in rows)
        with self.assertRaisesRegex(ValueError, 'conserve nonzeros'):
            parse(text)

    def rdoq_fixture(self, scope='all', component=1):
        actual = 0 if (scope == 'luma' and component != 0) or (scope == 'chroma' and component == 0) else 2
        rows = []
        for probe in range(3):
            changed = int(probe != actual)
            row = dict(zip(KEYS['RDOQ'], (99, 0, component, 4, 4, 32, 1, 10, 3, probe, 1, 0)))
            row.update({k: 0 for k in RDOQ_COUNTS})
            row.update(position_count=2, actual_nonzero=1, predictor_changed=changed,
                       quant_level_changed=changed, quant_level_increased=changed,
                       fixed_candidates_quant_changed=changed,
                       actual_distortion=8, probe_distortion=8+2*changed,
                       actual_rate_est_bits=4, probe_rate_est_bits=4+changed,
                       delta_distortion_over_lambda=changed, delta_rate_est_bits=changed,
                       delta_rd_over_lambda=2*changed, fixed_candidates_delta_rd_over_lambda=2*changed,
                       lambda_sum=4)
            rows.append(row)
        lines = ['TS R13 diagnosis=R13-DIAG-v1; frac-scale=32768; no-decision-feedback']
        if scope != 'all':
            lines.append(f'TS R13 ablation=R13-COMPONENT-v1; scope={scope}; changes-coding=1; decoder-must-match=1;')
        lines.append('TS_R13_DIAG_RDOQ_HEADER ' + ','.join(rows[0]))
        lines.extend('TS_R13_DIAG_RDOQ ' + ','.join(map(str, row.values())) for row in rows)
        return '\n'.join(lines) + '\n'

    def test_rdoq_only_and_scoped_actual_probe(self):
        for scope, component in (('all', 1), ('luma', 1), ('chroma', 0), ('chroma', 1)):
            with self.subTest(scope=scope, component=component), tempfile.TemporaryDirectory() as folder:
                log, out = Path(folder)/'rdoq.log', Path(folder)/'out'
                log.write_text(self.rdoq_fixture(scope, component))
                self.assertEqual(export([log], out), 3)
                self.assertFalse((out/'writer_cg.csv').exists())
                with (out/'rdoq_by_poc_component_probe_cg.csv').open() as stream:
                    rows = list(csv.DictReader(stream))
                self.assertEqual({r['diagnostic_scope'] for r in rows}, {scope})
                self.assertTrue(all(float(r['rd_identity_residual']) == 0 for r in rows))
                self.assertTrue(all('not_final_selected' in r['population'] for r in rows))

    def rewrite_probe(self, text, probe, field, value):
        lines = text.splitlines()
        fields = next(l.split(' ', 1)[1].split(',') for l in lines if l.startswith('TS_R13_DIAG_RDOQ_HEADER '))
        for i, line in enumerate(lines):
            if line.startswith('TS_R13_DIAG_RDOQ '):
                values = line.split(' ', 1)[1].split(',')
                if int(values[fields.index('probe_mode')]) == probe:
                    values[fields.index(field)] = str(value)
                    lines[i] = 'TS_R13_DIAG_RDOQ ' + ','.join(values)
        return '\n'.join(lines)

    def test_rdoq_rd_identity_and_matching_probe_rejected(self):
        with self.assertRaisesRegex(ValueError, 'delta D/lambda'):
            parse(self.rewrite_probe(self.rdoq_fixture(), 0, 'delta_rd_over_lambda', 3))
        with self.assertRaisesRegex(ValueError, 'matching actual scoped trajectory'):
            parse(self.rewrite_probe(self.rdoq_fixture(), 2, 'predictor_changed', 1))
        # A chroma component excluded by a luma-only ablation uses Current.
        with self.assertRaisesRegex(ValueError, 'matching actual scoped trajectory'):
            parse(self.rewrite_probe(self.rdoq_fixture('luma', 1), 0, 'predictor_changed', 1))

    def test_rdoq_missing_probe_population_rejected(self):
        text = '\n'.join(self.rdoq_fixture().splitlines()[:-1])
        with self.assertRaisesRegex(ValueError, 'Incomplete RDOQ'):
            parse(text)


if __name__ == '__main__':
    unittest.main()
