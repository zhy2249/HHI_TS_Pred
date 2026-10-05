#!/usr/bin/env python3
"""Observer configuration must invalidate incompatible resumes; no codecs run."""
from dataclasses import replace
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import batch_test as batch


class StatsFingerprintTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='ts-observer-fingerprint-')
        self.root = Path(self.temporary.name)
        self.encoder = self.root / 'EncoderApp.placeholder'
        self.encoder.write_bytes(b'not an executable: subprocess is mocked')
        self.cfg = self.root / 'LB.cfg'
        self.cfg.write_text('FramesToBeEncoded: 2\n')
        self.sequence = self.root / 'Sequence.cfg'
        self.sequence.write_text('FrameRate: 30\n')
        self.input = self.root / 'input.placeholder'
        self.input.write_bytes(b'not video')
        self.calls = []

    def tearDown(self):
        self.temporary.cleanup()

    def job(self, label='case', mode='r3_risk_guard'):
        out = self.root / label
        return batch.TestJob(
            order=0, name=label, repo_root=self.root, cwd=self.root,
            encoder=self.encoder, decoder=self.encoder, cfgs=[self.cfg],
            sequence_cfg=self.sequence, input_path=self.input, qp=32, frames=2,
            extra_args=[], decoder_args=[], decode_md5=False, xlsm_tag='lb',
            out_dir=out, bitstream=out/'stream.bin', recon=out/'recon.yuv',
            encode_log=out/'encode.log', decode_log=out/'decode.log',
            overwrite=False, fixed_predictor=mode, no_recon=True)

    def execute(self, job, environment):
        def fake_run(command, **kwargs):
            self.calls.append(dict(kwargs['env']))
            self.assertEqual(command[-2:], ['-o', ''])
            Path(command[command.index('-b') + 1]).write_bytes(b'fake bitstream')
            runtime = job.fixed_predictor or 'current'
            kwargs['stdout'].write(
                f'EXPERIMENT: TS_FIXED_PREDICTOR={runtime}; syntax=experimental-v1\n'
                'Total Frames Y-PSNR U-PSNR V-PSNR\n2 a 100.0 35.0 36.0 37.0\n')
            return SimpleNamespace(returncode=0)

        with patch.dict(os.environ, environment, clear=True), \
             patch.object(batch.subprocess, 'run', side_effect=fake_run):
            result = batch._run_one(job)
        marker = json.loads(job.bitstream.with_suffix('.done.json').read_text())
        return result['encode_status'], marker['fingerprint']

    def assert_variants_invalidate(self, key, mode, values=(None, '0', '1')):
        job = self.job(key + '_' + str(mode), mode)
        fingerprints = []
        for value in values:
            environment = {} if value is None else {key: value}
            before = len(self.calls)
            status, fingerprint = self.execute(job, environment)
            self.assertEqual(status, 'ok', (key, value))
            self.assertEqual(len(self.calls), before + 1)
            self.assertEqual(self.execute(job, environment), ('skipped_exists', fingerprint))
            self.assertEqual(len(self.calls), before + 1)
            # Fingerprinting must not normalize or inject anything into jobs.
            expected = dict(environment)
            if mode:
                expected['TS_FIXED_PREDICTOR'] = mode
            self.assertEqual(self.calls[-1], expected)
            fingerprints.append(fingerprint)
        self.assertEqual(len(set(fingerprints)), len(values), key)

    def test_all_stats_default_off_on_changes_invalidate(self):
        for round_ in (*range(2, 7), *range(8, 13)):
            with self.subTest(round=round_):
                self.assert_variants_invalidate(f'TS_R{round_}_STATS', 'r3_risk_guard')

    def test_r6_and_compiled_mode_settings_are_fingerprinted(self):
        for mode in ('r6_reject_nopred', None):
            with self.subTest(mode=mode):
                self.assert_variants_invalidate('TS_R6_STATS', mode)

    def test_cond_trace_presence_including_zero_is_not_default(self):
        # Legacy C++ semantics: both an empty value and "0" still enable this
        # trace because getenv() returns a non-null pointer. Never fold into off.
        self.assert_variants_invalidate('TS_COND_TRACE', 'r3_risk_guard',
                                       (None, '0', '', '1'))

    def test_newer_trace_values_are_preserved(self):
        for round_ in range(8, 13):
            with self.subTest(round=round_):
                self.assert_variants_invalidate(f'TS_R{round_}_TRACE', None,
                                               (None, '0', '1'))

    def test_unrelated_environment_does_not_invalidate(self):
        job = self.job()
        status, fingerprint = self.execute(job, {'UNRELATED_TEST_SETTING': 'one'})
        self.assertEqual(status, 'ok')
        self.assertEqual(self.execute(job, {'UNRELATED_TEST_SETTING': 'two'}),
                         ('skipped_exists', fingerprint))
        self.assertEqual(len(self.calls), 1)

    def test_job_mode_override_and_other_environment_unchanged(self):
        job = replace(self.job(), fixed_predictor='r6_reject_nopred')
        environment = {'TS_FIXED_PREDICTOR': 'r3_risk_guard', 'TS_R6_STATS': '1',
                       'TS_COND_TRACE': '0', 'UNCHANGED': 'value'}
        self.assertEqual(self.execute(job, environment)[0], 'ok')
        self.assertEqual(self.calls[-1], {**environment, 'TS_FIXED_PREDICTOR': 'r6_reject_nopred'})


if __name__ == '__main__':
    unittest.main()
