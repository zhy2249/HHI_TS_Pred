"""Fake jobs only: R15 scheduling, version identity and strict resume."""
from contextlib import redirect_stdout
from dataclasses import replace
import io
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import batch_test as batch
import test_ts_fixed_batch as existing
from ts_predictor_naming import R15_MODE_NUMBERS, r15_protocol, directory_name


class R15BatchTests(unittest.TestCase):
    job = existing.FixedBatchTests.job

    def test_registry_and_shared_pool(self):
        existing.FixedBatchTests.exercise_modes_and_shared_pool(self, tuple(R15_MODE_NUMBERS))
        self.assertEqual(set(R15_MODE_NUMBERS.values()), set(range(1, 19)))
        for name, number in R15_MODE_NUMBERS.items():
            self.assertEqual(directory_name(name), f'r15_{number}_{name[4:]}')
            self.assertEqual(r15_protocol(name)['internal_policy'], 114 + number)

    @staticmethod
    def startup(name):
        p = r15_protocol(name)
        return (f"TS R15 revision={p['revision']}; mapping={p['mapping']}; numbering={p['numbering']}; "
                f"mode={p['public_mode']}; runtime={name}; engine=PREFIX; score=integer-syntax; "
                "target=TSRC-enabled-nonBDPCM; quant-search=map-up-to-1; stats=0; state=none; mode-bits=0")

    def test_identity_rejects_incorrect_or_missing_fields(self):
        for name in R15_MODE_NUMBERS:
            text = self.startup(name)
            self.assertTrue(batch._r15_startup_matches(text, name))
            for field in ('revision', 'mapping', 'numbering', 'mode', 'runtime', 'engine', 'score',
                          'target', 'quant-search', 'state', 'mode-bits'):
                self.assertFalse(batch._r15_startup_matches(text.replace(f'{field}=', f'old-{field}='), name))
            self.assertFalse(batch._r15_startup_matches('', name))
        self.assertTrue(batch._r15_startup_matches('', 'current'))

    def test_decode_hash_and_version_required(self):
        name = 'r15_g_eq_k3'
        with tempfile.TemporaryDirectory() as directory:
            job = replace(self.job(Path(directory)), fixed_predictor=name, no_recon=True, decode_md5=True)
            for version, hashes, status in ((True, 2, 'ok'), (False, 2, 'failed'), (True, 1, 'failed')):
                def run(cmd, **kwargs):
                    self.assertEqual(cmd[-2:], ['-o', ''])
                    self.assertEqual(kwargs['env']['TS_FIXED_PREDICTOR'], name)
                    kwargs['stdout'].write(f'EXPERIMENT: TS_FIXED_PREDICTOR={name}; syntax=experimental-v1\n'
                                          + (self.startup(name) if version else '') + '\n' + 'MD5: test (OK)\n' * hashes)
                    return SimpleNamespace(returncode=0)
                with patch.object(batch.subprocess, 'run', side_effect=run):
                    self.assertEqual(batch._run_decode(job)['decode_status'], status)

    def test_resume_requires_current_protocol_and_observation_identity(self):
        name = 'r15_g_eq_k3'
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            executable = root / 'fake-encoder'
            executable.write_bytes(b'not an encoder')
            job = replace(self.job(root), encoder=executable, fixed_predictor=name, no_recon=True)
            def run(cmd, **kwargs):
                self.assertEqual(cmd[-2:], ['-o', ''])
                Path(cmd[cmd.index('-b') + 1]).write_bytes(b'mock bitstream')
                kwargs['stdout'].write(f'EXPERIMENT: TS_FIXED_PREDICTOR={name}; syntax=experimental-v1\n'
                                       + self.startup(name) + '\n'
                                       'Total Frames Y-PSNR U-PSNR V-PSNR\n2 a 100.0 35.0 36.0 37.0\n')
                return SimpleNamespace(returncode=0)
            with patch.dict(os.environ, {}, clear=True), \
                 patch.object(batch, '_local_source_snapshot', return_value={'binary_build_origin_verified': False}), \
                 patch.object(batch.subprocess, 'run', side_effect=run):
                self.assertEqual(batch._run_one(job)['encode_status'], 'ok')
                self.assertEqual(batch._run_one(job)['encode_status'], 'skipped_exists')
                done = job.bitstream.with_suffix('.done.json')
                marker = json.loads(done.read_text())
                marker['r15_identity']['mapping'] = 'wrong-mapping'
                done.write_text(json.dumps(marker))
                self.assertEqual(batch._run_one(job)['encode_status'], 'ok')
                os.environ['TS_R15_STATS'] = '1'
                self.assertEqual(batch._run_one(job)['encode_status'], 'ok')
                self.assertEqual(batch._run_one(job)['encode_status'], 'skipped_exists')
                identity = json.loads(job.bitstream.with_suffix('.identity.json').read_text())
                self.assertEqual(identity['public_mode'], 3)
                self.assertEqual(identity['MG'], 5)
                self.assertEqual(identity['observation_env']['TS_R15_STATS'], '1')
                self.assertEqual(identity['quant_search'], 'map-up-to-1')
                self.assertFalse(job.recon.exists())

    def test_observer_identity_and_inheritance(self):
        with patch.dict(os.environ, {'TS_R15_STATS': '1'}):
            self.assertEqual(batch._observation_identity('r15_g_eq_k3')['TS_R15_STATS'], '1')
            with tempfile.TemporaryDirectory() as directory:
                job = replace(self.job(Path(directory)), fixed_predictor='r15_g_eq_k3')
                self.assertEqual(batch._job_env(job)['TS_R15_STATS'], '1')


if __name__ == '__main__':
    unittest.main()
