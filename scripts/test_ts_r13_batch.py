#!/usr/bin/env python3
"""R13 planning/resume/provenance tests. Encoder/decoder execution is mocked."""
from contextlib import redirect_stdout
from dataclasses import replace
import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import batch_test as batch
import test_ts_fixed_batch as existing
from ts_predictor_naming import R13_MODE_NUMBERS, directory_name


class R13BatchTests(unittest.TestCase):
    job = existing.FixedBatchTests.job

    def setUp(self):
        batch._binary_sha256.cache_clear()
        batch._local_source_snapshot.cache_clear()

    def test_registry_and_shared_pool(self):
        existing.FixedBatchTests.exercise_modes_and_shared_pool(self, tuple(R13_MODE_NUMBERS))
        for mode, number in R13_MODE_NUMBERS.items():
            self.assertIn(mode, batch._TS_PREDICTOR_MODES)
            self.assertEqual(directory_name(mode), f'r13_{number}_{mode[4:]}')

    def test_r13_cross_group_start_and_per_group_report(self):
        first, second = R13_MODE_NUMBERS
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            next_started = threading.Event()
            first_written = threading.Event()
            events = []
            reports = []
            base = [self.job(root, 'slow'), replace(self.job(root, 'fast'), order=1)]
            def worker(job):
                if job.fixed_predictor == first and job.name.endswith('__slow'):
                    events.append(('second_started', next_started.wait(3)))
                if job.fixed_predictor == second:
                    next_started.set()
                    events.append(('first_report_written', first_written.wait(3)))
                return dict(order=job.order, name=job.name, fixed_predictor=job.fixed_predictor,
                            encode_status='ok', error_info='pass')
            def report(**kwargs):
                modes = {row['fixed_predictor'] for row in kwargs['rows']}
                reports.append(modes)
                if modes == {first}:
                    first_written.set()
            with patch.object(batch, '_plan_auto', return_value=base), \
                 patch.object(batch, '_check_tools', return_value=0), \
                 patch.object(batch, '_detect_experiment_line',
                              side_effect=lambda exe, cwd, mode=None:
                              f'EXPERIMENT: TS_FIXED_PREDICTOR={mode or first}; syntax=experimental-v1'), \
                 patch.object(batch, '_run_one', side_effect=worker), \
                 patch.object(batch, '_write_xlsm_reports', side_effect=report), \
                 redirect_stdout(io.StringIO()):
                rc = batch.main(['--local-preset', 'LB', '--out-dir', str(root),
                                 '--fixed-predictors', ','.join(R13_MODE_NUMBERS), '--jobs', '2'])
            self.assertEqual(rc, 0)
            self.assertEqual(len(events), 3)
            self.assertTrue(all(ok for _, ok in events), events)
            self.assertEqual(reports, [{first}, {second}])

    def test_legacy_observer_fingerprint_unchanged_without_r13(self):
        with patch.dict(os.environ, {}, clear=True):
            expected = {key: None for key in batch._TS_OBSERVATION_ENV_KEYS}
            self.assertEqual(batch._observation_identity('r3_risk_guard'), expected)
            self.assertEqual(batch._observation_identity('r12_ci_near1'), expected)
            self.assertEqual(set(batch._observation_identity('r13_keep_hit_uniform')),
                             set(expected) | set(batch._TS_R13_OBSERVATION_KEYS))
            os.environ['TS_R13_STATS'] = '0'
            self.assertEqual(batch._observation_identity('current')['TS_R13_STATS'], '0')
            self.assertIn('TS_R13_POC', batch._observation_identity('current'))

    def test_capability_probe_removes_all_r13_observers(self):
        seen = []
        def run(cmd, **kwargs):
            seen.append(kwargs['env'])
            return SimpleNamespace(stdout='EXPERIMENT: TS_FIXED_PREDICTOR=current; syntax=experimental-v1\n')
        with patch.dict(os.environ, {key: '1' for key in batch._TS_R13_OBSERVATION_KEYS}), \
             patch.object(batch.os, 'access', return_value=True), \
             patch.object(batch.subprocess, 'run', side_effect=run):
            self.assertIsNotNone(batch._detect_experiment_line(Path(__file__), Path.cwd()))
        self.assertEqual(len(seen), 1)
        self.assertFalse(set(batch._TS_R13_OBSERVATION_KEYS) & set(seen[0]))

    def test_ce_plan_is_56_half_frame_jobs_without_execution(self):
        buffer = io.StringIO()
        with tempfile.TemporaryDirectory() as directory, \
             patch.object(batch, '_detect_experiment_line', return_value=None), \
             patch.object(batch, '_run_one', side_effect=AssertionError('No encoding in planning test')), \
             redirect_stdout(buffer):
            rc = batch.main(['--preset', 'LBeu', '--class', 'C,E', '--qps', '22,27,32,37',
                             '--fixed-predictors', ','.join(R13_MODE_NUMBERS), '--decode-md5',
                             '--no-recon', '--allow-missing-input', '--dry-run',
                             '--out-dir', directory, '--input-dir', directory])
        self.assertEqual(rc, 0)
        lines = [line for line in buffer.getvalue().splitlines() if line.startswith('- ')]
        self.assertEqual(len(lines), 56)
        counts = {'BasketballDrill': 250, 'BQMall': 300, 'PartyScene': 250, 'RaceHorsesC': 150,
                  'FourPeople': 300, 'Johnny': 300, 'KristenAndSara': 300}
        for sequence, count in counts.items():
            selected = [line for line in lines if f'LBeu_{sequence} ' in line]
            self.assertEqual(len(selected), 8, sequence)
            self.assertTrue(all(f'frames={count},' in line for line in selected), sequence)
        self.assertTrue(all('decode-md5=on' in line and 'recon=off' in line for line in lines))

    def test_binary_sha_changes_even_if_size_and_mtime_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'fake-executable'
            path.write_bytes(b'original')
            before = path.stat()
            first = batch._binary_sha256(str(path), before.st_size, before.st_mtime_ns, before.st_ctime_ns)
            path.write_bytes(b'changed!')
            os.utime(path, ns=(before.st_atime_ns, before.st_mtime_ns))
            after = path.stat()
            second = batch._binary_sha256(str(path), after.st_size, after.st_mtime_ns, after.st_ctime_ns)
            self.assertEqual(first, hashlib.sha256(b'original').hexdigest())
            self.assertEqual(second, hashlib.sha256(b'changed!').hexdigest())
            self.assertNotEqual(first, second)

    def test_source_snapshot_does_not_claim_binary_origin(self):
        outputs = [b'abc123\n', b'patch-data', b'source/Lib/CommonLib/new.h\n']
        with patch.object(batch.subprocess, 'run', side_effect=[SimpleNamespace(returncode=0, stdout=o)
                                                             for o in outputs]):
            result = batch._local_source_snapshot('/test-checkout')
        self.assertEqual(result['head'], 'abc123')
        self.assertEqual(result['tracked_source_patch_sha256'], hashlib.sha256(b'patch-data').hexdigest())
        self.assertEqual(result['untracked_source_paths'], ['source/Lib/CommonLib/new.h'])
        self.assertFalse(result['binary_build_origin_verified'])

    def test_r13_resume_and_identity_include_observers_binary_and_config(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            executable = root / 'fake-encoder'
            executable.write_bytes(b'not an encoder')
            job = replace(self.job(root), encoder=executable, fixed_predictor='r13_keep_hit_uniform',
                          no_recon=True)
            calls = []
            def run(cmd, **kwargs):
                calls.append(cmd)
                self.assertEqual(cmd[-2:], ['-o', ''])
                Path(cmd[cmd.index('-b') + 1]).write_bytes(b'mock bitstream')
                kwargs['stdout'].write('EXPERIMENT: TS_FIXED_PREDICTOR=r13_keep_hit_uniform; syntax=experimental-v1\n'
                                       'Total Frames Y-PSNR U-PSNR V-PSNR\n2 a 100.0 35.0 36.0 37.0\n')
                return SimpleNamespace(returncode=0)
            with patch.dict(os.environ, {}, clear=True), \
                 patch.object(batch, '_local_source_snapshot', return_value={'binary_build_origin_verified': False}), \
                 patch.object(batch.subprocess, 'run', side_effect=run):
                self.assertEqual(batch._run_one(job)['encode_status'], 'ok')
                self.assertEqual(batch._run_one(job)['encode_status'], 'skipped_exists')
                for key, value in [('TS_R13_STATS', '1'), ('TS_R13_TRACE', '1'),
                                   ('TS_R13_DETAIL_LIMIT', '3'), ('TS_R13_POC', '0')]:
                    os.environ[key] = value
                    self.assertEqual(batch._run_one(job)['encode_status'], 'ok', key)
                    self.assertEqual(batch._run_one(job)['encode_status'], 'skipped_exists', key)
                self.assertEqual(len(calls), 5)
                identity = json.loads(job.bitstream.with_suffix('.identity.json').read_text())
                self.assertEqual(identity['revision'], 'R13-KH-168-v1')
                self.assertEqual(identity['public_mode'], 1)
                self.assertEqual(identity['weights'], [1] * 5)
                self.assertEqual(identity['observation_env']['TS_R13_POC'], '0')
                self.assertEqual(identity['encoder']['sha256'], hashlib.sha256(executable.read_bytes()).hexdigest())
                self.assertEqual(len(identity['configuration_sha256']), 1)
                self.assertFalse(identity['local_source_snapshot']['binary_build_origin_verified'])
                executable.write_bytes(b'changed executable')
                self.assertEqual(batch._run_one(job)['encode_status'], 'ok')
                self.assertFalse(job.recon.exists())


if __name__ == '__main__':
    unittest.main()
