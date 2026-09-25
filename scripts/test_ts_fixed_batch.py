#!/usr/bin/env python3
"""Scheduler and experiment isolation tests; no real encoding."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import redirect_stdout
from dataclasses import replace
import io
import argparse
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
import batch_test as batch
from ts_predictor_naming import R4_MODE_NUMBERS, R5_MODE_NUMBERS, R6_MODE_NUMBERS, R7_MODE_NUMBERS, R8_MODE_NUMBERS, directory_name, experiment_directory


class FixedBatchTests(unittest.TestCase):
    def exercise_modes_and_shared_pool(self, modes):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            observed = []
            def worker(job):
                observed.append(job.fixed_predictor)
                self.assertEqual(batch._job_env(job)['TS_FIXED_PREDICTOR'], job.fixed_predictor)
                self.assertTrue(job.no_recon)
                self.assertEqual(job.bitstream.relative_to(root).parts[0], directory_name(job.fixed_predictor))
                return {'order': job.order, 'name': job.name, 'fixed_predictor': job.fixed_predictor,
                        'encode_status': 'ok', 'error_info': 'pass'}
            def probe(exe, cwd, mode=None):
                return f'EXPERIMENT: TS_FIXED_PREDICTOR={mode or modes[0]}; syntax=experimental-v1'
            with patch.object(batch, '_plan_auto', return_value=[self.job(root)]), \
                 patch.object(batch, '_check_tools', return_value=0), \
                 patch.object(batch, '_detect_experiment_line', side_effect=probe), \
                 patch.object(batch, '_run_one', side_effect=worker), redirect_stdout(io.StringIO()):
                rc = batch.main(['--local-preset','LB','--out-dir',str(root),'--no-xlsm-report',
                                 '--fixed-predictors',','.join(modes),'--jobs','4'])
            self.assertEqual(rc, 0)
            self.assertEqual(set(observed), set(modes))
            for mode in modes:
                self.assertTrue((root/directory_name(mode)/'summary.csv').is_file())

    def test_r2_modes_and_shared_pool(self):
        self.exercise_modes_and_shared_pool(('r2_modal', 'r2_risk', 'r2_cn_log', 'r2_cn_frac'))

    def test_r3_modes_and_shared_pool(self):
        self.exercise_modes_and_shared_pool(('r3_risk_guard', 'r3_risk_guard_y', 'r3_cn_guard', 'r3_cn_guard_y'))

    def test_r4_modes_and_shared_pool(self):
        self.exercise_modes_and_shared_pool(('r4_identity_only', 'r4_magnitude_only', 'r4_guard_rescue',
                                            'r4_directional_risk', 'r4_causal_models', 'r4_signed_plane'))

    def test_r4_macro_directory_numbers(self):
        for mode, number in R4_MODE_NUMBERS.items():
            self.assertEqual(directory_name(mode), f'r4_{number}_{mode[3:]}')

    def test_r5_modes_and_shared_pool(self):
        self.exercise_modes_and_shared_pool(tuple(R5_MODE_NUMBERS))

    def test_r5_macro_directory_numbers(self):
        for mode, number in R5_MODE_NUMBERS.items():
            self.assertEqual(directory_name(mode), f'r5_{number}_{mode[3:]}')

    def test_r6_modes_and_shared_pool(self):
        self.exercise_modes_and_shared_pool(tuple(R6_MODE_NUMBERS))

    def test_r6_macro_directory_numbers(self):
        for mode, number in R6_MODE_NUMBERS.items():
            self.assertEqual(directory_name(mode), f'r6_{number}_{mode[3:]}')

    def test_r8_modes_and_shared_pool(self):
        self.exercise_modes_and_shared_pool(tuple(R8_MODE_NUMBERS))
        for mode,n in R8_MODE_NUMBERS.items():
            self.assertEqual(directory_name(mode),f'r8_{n}_{mode[3:]}')

    def test_r7_modes_and_shared_pool(self):
        self.exercise_modes_and_shared_pool(tuple(R7_MODE_NUMBERS))

    def test_r7_names_and_legacy_resume(self):
        for mode,n in R7_MODE_NUMBERS.items():
            self.assertEqual(directory_name(mode),f'r7_{n}_{mode[5:]}')
            for old in (mode,f'rate_{n}_{mode[5:]}'):
                with tempfile.TemporaryDirectory() as d:
                    root=Path(d)
                    self.assertEqual(experiment_directory(root,mode),root/directory_name(mode))
                    (root/old).mkdir()
                    self.assertEqual(experiment_directory(root,mode),root/old)
                    (root/directory_name(mode)).mkdir()
                    with self.assertRaisesRegex(ValueError,'Ambiguous experiment directories'):
                        experiment_directory(root,mode)

    def test_r4_legacy_resume_and_ambiguous_directory(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            mode = 'r4_signed_plane'
            (root/mode).mkdir()
            job = batch._expand_fixed_predictors([self.job(root)], [mode], root)[0]
            self.assertEqual(job.bitstream.relative_to(root).parts[0], mode)
            (root/directory_name(mode)).mkdir()
            with self.assertRaisesRegex(ValueError, 'Ambiguous experiment directories'):
                batch._expand_fixed_predictors([self.job(root)], [mode], root)

    def test_r4_numbered_workbook_output(self):
        from ts_fixed_analyze import sheet_values
        repo = Path(__file__).resolve().parents[1]
        template = repo/'scripts/JVET-hhi.xlsm'
        with tempfile.TemporaryDirectory() as d:
            out = Path(d)
            mode = 'r4_directional_risk'
            row = dict(fixed_predictor=mode, sequence='BasketballDrill', qp=22,
                       xlsm_tag='lb', kbps=123.456, ypsnr=40., upsnr=41., vpsnr=42., error_info='pass')
            args = argparse.Namespace(xlsm_template=template, xlsm_report=True)
            with redirect_stdout(io.StringIO()):
                batch._write_xlsm_reports(repo_root=repo, out_dir=out, rows=[row], args=args)
            output = out/directory_name(mode)/'JVET-hhi.xlsm'
            self.assertEqual(sheet_values(output, 'Reference'), sheet_values(template, 'Reference'))
            self.assertFalse((out/mode).exists())

    def test_group_report_written_before_other_group_finishes(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            first_written = threading.Event()
            timing = []
            reports = []
            def worker(job):
                if job.fixed_predictor == 'gradient':
                    timing.append(first_written.wait(3))
                return {'order': job.order, 'name': job.name, 'fixed_predictor': job.fixed_predictor,
                        'encode_status': 'skipped_exists', 'error_info': 'pass'}
            def report(**kwargs):
                rows = kwargs['rows']
                reports.append([r['fixed_predictor'] for r in rows])
                if reports[-1] == ['nopred']:
                    first_written.set()
            with patch.object(batch, '_plan_auto', return_value=[self.job(root)]), \
                 patch.object(batch, '_check_tools', return_value=0), \
                 patch.object(batch, '_detect_experiment_line', return_value='EXPERIMENT: TS_FIXED_PREDICTOR=current; syntax=experimental-v1'), \
                 patch.object(batch, '_run_one', side_effect=worker), \
                 patch.object(batch, '_write_xlsm_reports', side_effect=report), redirect_stdout(io.StringIO()):
                rc = batch.main(['--local-preset', 'LB', '--out-dir', str(root),
                                 '--fixed-predictors', 'nopred,gradient', '--jobs', '2'])
            self.assertEqual(rc, 0)
            self.assertEqual(timing, [True])
            self.assertEqual(reports, [['nopred'], ['gradient']])

    def test_group_report_refreshed_after_retry(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            reports = []
            def worker(job):
                return {'order': job.order, 'name': job.name, 'fixed_predictor': job.fixed_predictor,
                        'encode_status': 'ok' if job.overwrite else 'failed',
                        'error_info': 'pass' if job.overwrite else 'failed'}
            with patch.object(batch, '_plan_auto', return_value=[self.job(root)]), \
                 patch.object(batch, '_check_tools', return_value=0), \
                 patch.object(batch, '_detect_experiment_line', return_value='EXPERIMENT: TS_FIXED_PREDICTOR=current; syntax=experimental-v1'), \
                 patch.object(batch, '_run_one', side_effect=worker), \
                 patch.object(batch, '_write_xlsm_reports', side_effect=lambda **kw: reports.append(kw['rows'][0]['error_info'])), \
                 redirect_stdout(io.StringIO()):
                rc = batch.main(['--local-preset', 'LB', '--out-dir', str(root),
                                 '--fixed-predictors', 'nopred', '--retry-failed', '1'])
            self.assertEqual(rc, 0)
            self.assertEqual(reports, ['failed', 'pass'])

    def test_real_workbook_staging_preserves_reference(self):
        from ts_fixed_analyze import sheet_values
        repo = Path(__file__).resolve().parents[1]
        template = repo/'scripts/JVET-hhi.xlsm'
        with tempfile.TemporaryDirectory() as d:
            out = Path(d)
            args = argparse.Namespace(xlsm_template=template, xlsm_report=True)
            row = dict(fixed_predictor='nopred', sequence='BasketballDrill', qp=22,
                       xlsm_tag='lb', kbps=123.456, ypsnr=40., upsnr=41., vpsnr=42., error_info='pass')
            with redirect_stdout(io.StringIO()):
                batch._write_xlsm_reports(repo_root=repo, out_dir=out, rows=[row], args=args)
            output = out/'nopred/JVET-hhi.xlsm'
            self.assertEqual(sheet_values(output, 'Reference'), sheet_values(template, 'Reference'))
            vals = sheet_values(output, 'Test')
            key = next(c for c,v in vals.items() if v == 'BasketballDrill.Q22.ecm.lb')
            self.assertEqual(vals['B'+key[1:]], 123.456)
            original = output.read_bytes()
            with patch('xlsm_table_fill.fill_jvet_hhi_test_sheet', return_value=(False, 'test failure')), \
                 redirect_stdout(io.StringIO()):
                batch._write_xlsm_reports(repo_root=repo, out_dir=out, rows=[row], args=args)
            self.assertEqual(output.read_bytes(), original)
            self.assertFalse(list(out.rglob('*.stage.xlsm')))

    def test_conditional_modes_in_real_main(self):
        modes = ['q32', 'conf2', 'prev', 'ewma', 'q32_ewma']
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            observed = []
            def worker(job):
                observed.append(job.fixed_predictor)
                self.assertTrue(job.no_recon)
                self.assertEqual(batch._job_env(job)['TS_FIXED_PREDICTOR'], job.fixed_predictor)
                return {'order': job.order, 'name': job.name, 'fixed_predictor': job.fixed_predictor,
                        'encode_status': 'ok', 'error_info': 'pass'}
            def probe(exe, cwd, mode=None):
                return f'EXPERIMENT: TS_FIXED_PREDICTOR={mode or "ewma"}; syntax=experimental-v1'
            with patch.object(batch, '_plan_auto', return_value=[self.job(root)]), \
                 patch.object(batch, '_check_tools', return_value=0), \
                 patch.object(batch, '_detect_experiment_line', side_effect=probe), \
                 patch.object(batch, '_run_one', side_effect=worker), redirect_stdout(io.StringIO()):
                rc = batch.main(['--local-preset', 'LB', '--out-dir', str(root), '--no-xlsm-report',
                                 '--fixed-predictors', ','.join(modes)])
                self.assertEqual(rc, 0)
                self.assertEqual(observed, modes)
                observed.clear()
                rc = batch.main(['--local-preset', 'LB', '--out-dir', str(root), '--no-xlsm-report'])
                self.assertEqual(rc, 0)
                self.assertEqual(observed, ['ewma'])

    def job(self, root, name='first'):
        return batch._make_job(order=0, name=name, repo_root=root, cwd=root,
            encoder=Path('/fake/encoder'), decoder=Path('/fake/decoder'),
            cfgs=[Path(__file__).resolve()], sequence_cfg=Path(__file__).resolve(),
            input_path=Path(__file__).resolve(), qp=22, frames=2, extra_args=[],
            decoder_args=[], decode_md5=False, xlsm_tag='lb', run_dir=root, overwrite=False)

    def test_isolation(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            jobs = batch._expand_fixed_predictors([self.job(root)], ['nopred', 'gradient', 'directional'], root)
            self.assertEqual(len({j.bitstream for j in jobs}), 3)
            self.assertTrue(all(j.no_recon for j in jobs))
            with patch.dict(os.environ, {'TS_FIXED_PREDICTOR': 'bad', 'TS_PRED_STATS': 'bad'}):
                for job in jobs:
                    env = batch._job_env(job)
                    self.assertEqual(env['TS_FIXED_PREDICTOR'], job.fixed_predictor)
                    self.assertNotIn('TS_PRED_STATS', env)
                self.assertNotIn('TS_FIXED_PREDICTOR', batch._job_env(self.job(root)))

    def test_omitted_option_uses_compiled_default(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            observed = []
            def worker(job):
                observed.append((job.fixed_predictor, batch._job_env(job)['TS_FIXED_PREDICTOR']))
                return {'order':job.order, 'name':job.name, 'fixed_predictor':job.fixed_predictor,
                        'encode_status':'ok', 'error_info':'pass'}
            with patch.object(batch, '_plan_auto', return_value=[self.job(root)]), \
                 patch.object(batch, '_check_tools', return_value=0), \
                 patch.object(batch, '_detect_experiment_line', return_value='EXPERIMENT: TS_FIXED_PREDICTOR=gradient; syntax=experimental-v1'), \
                 patch.object(batch, '_run_one', side_effect=worker), redirect_stdout(io.StringIO()):
                rc = batch.main(['--local-preset','LB','--out-dir',str(root),'--no-xlsm-report'])
            self.assertEqual(rc,0)
            self.assertEqual(observed,[('gradient','gradient')])
            self.assertTrue((root/'gradient'/'summary.csv').is_file())

    def test_no_group_barrier_in_real_main(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            base = [self.job(root, 'slow'), replace(self.job(root, 'fast'), order=1)]
            second_group_started = threading.Event()
            evidence = []
            def worker(job):
                if job.fixed_predictor == 'gradient':
                    second_group_started.set()
                if job.fixed_predictor == 'nopred' and job.name.endswith('__slow'):
                    evidence.append(second_group_started.wait(3))
                return {'order': job.order, 'name': job.name, 'fixed_predictor': job.fixed_predictor,
                        'encode_status': 'ok', 'error_info': 'pass'}
            with patch.object(batch, '_plan_auto', return_value=base), \
                 patch.object(batch, '_check_tools', return_value=0), \
                 patch.object(batch, '_detect_experiment_line', return_value='EXPERIMENT: TS_FIXED_PREDICTOR=current; syntax=experimental-v1'), \
                 patch.object(batch, '_run_one', side_effect=worker), redirect_stdout(io.StringIO()):
                rc = batch.main(['--local-preset', 'LB', '--out-dir', str(root),
                                 '--fixed-predictors', 'nopred,gradient', '--jobs', '2', '--no-xlsm-report'])
            self.assertEqual(rc, 0)
            self.assertEqual(evidence, [True], 'Second group waited for first group completion')

    def test_no_recon_and_resume(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            # Existing regular file supplies stable binary identity for the mock.
            job = replace(self.job(root), encoder=Path(__file__).resolve(),
                          fixed_predictor='nopred', no_recon=True)
            commands = []
            def run(cmd, **kwargs):
                commands.append(cmd)
                self.assertEqual(cmd[-2:], ['-o', ''])
                self.assertEqual(kwargs['env']['TS_FIXED_PREDICTOR'], 'nopred')
                Path(cmd[cmd.index('-b') + 1]).write_bytes(b'test bitstream')
                kwargs['stdout'].write('EXPERIMENT: TS_FIXED_PREDICTOR=nopred; syntax=experimental-v1\n'
                                       'Total Frames Y-PSNR U-PSNR V-PSNR\n2 a 100.0 35.0 36.0 37.0\n')
                return type('Result', (), {'returncode': 0})()
            with patch.object(batch.subprocess, 'run', side_effect=run):
                self.assertEqual(batch._run_one(job)['encode_status'], 'ok')
                self.assertEqual(batch._run_one(job)['encode_status'], 'skipped_exists')
                self.assertEqual(len(commands), 1)
                # A truncated bitstream cannot be treated as a completed job.
                job.bitstream.write_bytes(b'x')
                self.assertEqual(batch._run_one(job)['encode_status'], 'ok')
                self.assertEqual(len(commands), 2)
            self.assertFalse(job.recon.exists())


if __name__ == '__main__':
    unittest.main()
