#!/usr/bin/env python3
"""Scheduler and experiment isolation tests; no real encoding."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import redirect_stdout
from dataclasses import replace
import io
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
import batch_test as batch


class FixedBatchTests(unittest.TestCase):
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
