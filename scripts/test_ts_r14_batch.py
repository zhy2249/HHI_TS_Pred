#!/usr/bin/env python3
"""R14 v3 planning/provenance tests; fake jobs or dry-run only, no encoding."""
from contextlib import redirect_stdout, redirect_stderr
from dataclasses import replace
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import batch_test as batch
import test_ts_fixed_batch as existing
from ts_predictor_naming import (R14_MODE_NUMBERS, R14_MODE_SPECS, R14_PHASE_A,
                                R14_PHASE_B, R14_REVISION, R14_NUMBERING,
                                R14_LEGACY_PUBLIC_MODES, directory_name, r14_protocol)

ROOT = Path(__file__).resolve().parents[1]


class R14BatchTests(unittest.TestCase):
    job = existing.FixedBatchTests.job

    def setUp(self):
        batch._binary_sha256.cache_clear()
        batch._local_source_snapshot.cache_clear()

    def test_registry_and_shared_pool(self):
        existing.FixedBatchTests.exercise_modes_and_shared_pool(self, tuple(R14_MODE_NUMBERS))
        self.assertEqual(set(R14_MODE_NUMBERS.values()), set(range(1, 16)))
        for mode, public in R14_MODE_NUMBERS.items():
            self.assertEqual(directory_name(mode), f'r14_{public}_{mode[4:]}')
            self.assertEqual(r14_protocol(mode)['internal_policy'], 99 + public)

    def test_retired_names_and_numeric_modes_rejected(self):
        for name in ['2', '19', 'r14_g2_target2_equal', 'r14_g4_dir2_zero', 'r14_target2']:
            with self.subTest(mode=name), redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
                batch.main(['--fixed-predictors', name, '--dry-run'])
            self.assertEqual(error.exception.code, 2)

    @staticmethod
    def startup(mode):
        public, k, update, r0, s0 = R14_MODE_SPECS[mode]
        return (f'TS R14 revision={R14_REVISION}; numbering={R14_NUMBERING}; mode={public}; runtime={mode}; K={k}; '
                f'update={update}; r0={r0}; s0={s0 if s0 is not None else -1}; '
                'score-scale=168; target=TSRC-enabled-nonBDPCM; stats=0; trace=0')

    def test_all_startup_identities_and_stale_revision_rejected(self):
        for mode in R14_MODE_NUMBERS:
            line = self.startup(mode)
            self.assertTrue(batch._r14_startup_matches(line, mode))
            for old, wrong in [('v3', 'v2'), ('score-scale=168', 'score-scale=128'),
                               (R14_NUMBERING, 'legacy-gapped'),
                               ('target=TSRC-enabled-nonBDPCM', 'target=RDOQ-only'),
                               ('r0=', 'obsolete-r0='), ('s0=', 'obsolete-s0=')]:
                self.assertFalse(batch._r14_startup_matches(line.replace(old, wrong), mode), (mode, old))
            self.assertFalse(batch._r14_startup_matches(line.replace(f'numbering={R14_NUMBERING}; ', ''), mode))
            old_public = R14_LEGACY_PUBLIC_MODES[mode]
            if old_public != R14_MODE_NUMBERS[mode]:
                old_identity = line.replace(f'mode={R14_MODE_NUMBERS[mode]};', f'mode={old_public};')
                self.assertFalse(batch._r14_startup_matches(old_identity, mode))
            self.assertFalse(batch._r14_startup_matches('', mode))
        self.assertTrue(batch._r14_startup_matches('', 'r3_risk_guard'))

    def test_decoder_requires_both_v3_identity_and_full_hash_count(self):
        mode = 'r14_g2_pair2_equal'
        prefix = f'EXPERIMENT: TS_FIXED_PREDICTOR={mode}; syntax=experimental-v1\n'
        with tempfile.TemporaryDirectory() as directory:
            job = replace(self.job(Path(directory)), fixed_predictor=mode, no_recon=True, decode_md5=True)
            for line, hashes, expected in [(self.startup(mode), 2, 'ok'),
                                            (self.startup(mode).replace('v3', 'v2'), 2, 'failed'),
                                            (self.startup(mode), 1, 'failed')]:
                def run(cmd, **kwargs):
                    self.assertEqual(cmd[-2:], ['-o', ''])
                    self.assertEqual(kwargs['env']['TS_FIXED_PREDICTOR'], mode)
                    kwargs['stdout'].write(prefix + line + '\n' + 'MD5: test (OK)\n' * hashes)
                    return SimpleNamespace(returncode=0)
                with patch.object(batch.subprocess, 'run', side_effect=run):
                    self.assertEqual(batch._run_decode(job)['decode_status'], expected)

    def test_real_workbook_is_numbered_and_reference_unchanged(self):
        from ts_fixed_analyze import sheet_values
        from argparse import Namespace
        mode = 'r14_g2_pair2_equal'
        template = ROOT / 'scripts/JVET-hhi.xlsm'
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            row = dict(fixed_predictor=mode, sequence='BasketballDrill', qp=22,
                       xlsm_tag='lb', kbps=123.456, ypsnr=40., upsnr=41., vpsnr=42., error_info='pass')
            with redirect_stdout(io.StringIO()):
                batch._write_xlsm_reports(repo_root=ROOT, out_dir=out, rows=[row],
                                          args=Namespace(xlsm_template=template, xlsm_report=True))
            output = out / directory_name(mode) / 'JVET-hhi.xlsm'
            self.assertEqual(sheet_values(output, 'Reference'), sheet_values(template, 'Reference'))
            self.assertFalse((out / mode).exists())

    def test_cross_group_start_and_per_group_workbook(self):
        first, second = 'r14_fixed_near_only', 'r14_g2_none_equal'
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            next_started, first_written = threading.Event(), threading.Event()
            events, reports = [], []
            base = [self.job(root, 'slow'), replace(self.job(root, 'fast'), order=1)]
            def worker(job):
                if job.fixed_predictor == first and job.name.endswith('__slow'):
                    events.append(next_started.wait(3))
                if job.fixed_predictor == second:
                    next_started.set()
                    events.append(first_written.wait(3))
                return dict(order=job.order, name=job.name, fixed_predictor=job.fixed_predictor,
                            encode_status='ok', error_info='pass')
            def report(**kwargs):
                modes = {row['fixed_predictor'] for row in kwargs['rows']}
                reports.append(modes)
                if modes == {first}:
                    first_written.set()
            with patch.object(batch, '_plan_auto', return_value=base), \
                 patch.object(batch, '_check_tools', return_value=0), \
                 patch.object(batch, '_detect_experiment_line', side_effect=lambda exe, cwd, mode=None:
                              f'EXPERIMENT: TS_FIXED_PREDICTOR={mode or first}; syntax=experimental-v1'), \
                 patch.object(batch, '_run_one', side_effect=worker), \
                 patch.object(batch, '_write_xlsm_reports', side_effect=report), \
                 redirect_stdout(io.StringIO()):
                rc = batch.main(['--local-preset', 'LB', '--out-dir', str(root),
                                 '--fixed-predictors', f'{first},{second}', '--jobs', '2'])
            self.assertEqual(rc, 0)
            self.assertEqual(events, [True] * 3)
            self.assertEqual(reports, [{first}, {second}])

    def test_no_argument_uses_compiled_macro_default(self):
        with tempfile.TemporaryDirectory() as directory:
            root, seen = Path(directory), []
            mode = 'r14_g2_pair2_equal'
            with patch.object(batch, '_plan_auto', return_value=[self.job(root)]), \
                 patch.object(batch, '_check_tools', return_value=0), \
                 patch.object(batch, '_detect_experiment_line', return_value=
                              f'EXPERIMENT: TS_FIXED_PREDICTOR={mode}; syntax=experimental-v1'), \
                 patch.object(batch, '_run_one', side_effect=lambda job: seen.append(job.fixed_predictor) or
                              dict(order=job.order, name=job.name, fixed_predictor=job.fixed_predictor,
                                   encode_status='ok', error_info='pass')), redirect_stdout(io.StringIO()):
                self.assertEqual(batch.main(['--local-preset', 'LB', '--out-dir', str(root),
                                             '--no-xlsm-report']), 0)
            self.assertEqual(seen, [mode])

    def test_old_observer_fingerprints_preserved_and_probe_clears_r14(self):
        with patch.dict(os.environ, {}, clear=True):
            keys = set(batch._TS_OBSERVATION_ENV_KEYS)
            self.assertEqual(set(batch._observation_identity('r3_risk_guard')), keys)
            self.assertEqual(set(batch._observation_identity('r13_keep_hit_uniform')),
                             keys | set(batch._TS_R13_LEGACY_OBSERVATION_KEYS))
            self.assertEqual(set(batch._observation_identity('r14_g2_none_equal')),
                             keys | set(batch._TS_R14_OBSERVATION_KEYS))
        with patch.dict(os.environ, {'TS_R13_DIAG': '1'}, clear=True):
            self.assertEqual(set(batch._observation_identity('r13_keep_hit_uniform')),
                             keys | set(batch._TS_R13_OBSERVATION_KEYS))
        seen = []
        def run(cmd, **kwargs):
            seen.append(kwargs['env'])
            return SimpleNamespace(stdout='EXPERIMENT: TS_FIXED_PREDICTOR=current; syntax=experimental-v1\n')
        with patch.dict(os.environ, {key: '1' for key in batch._TS_R14_OBSERVATION_KEYS}), \
             patch.object(batch.os, 'access', return_value=True), \
             patch.object(batch.subprocess, 'run', side_effect=run):
            self.assertIsNotNone(batch._detect_experiment_line(Path(__file__), ROOT))
        self.assertFalse(set(batch._TS_R14_OBSERVATION_KEYS) & set(seen[0]))

    def test_wrapper_half_frame_planning_and_phase_priority(self):
        counts = {'BasketballDrill': 250, 'BQMall': 300, 'PartyScene': 250, 'RaceHorsesC': 150,
                  'FourPeople': 300, 'Johnny': 300, 'KristenAndSara': 300}
        reverse = {public: mode for mode, public in R14_MODE_NUMBERS.items()}
        for phase, public_modes in [('A', R14_PHASE_A), ('B', R14_PHASE_B),
                                    ('all', R14_PHASE_A + R14_PHASE_B)]:
            with self.subTest(phase=phase), tempfile.TemporaryDirectory() as directory:
                result = subprocess.run(['bash', 'scripts/run_ts_r14_lb_ce.sh', '--phase', phase,
                                         '--dry-run', '--allow-missing-input', '--input-dir', directory,
                                         '--out-dir', directory, '--encoder', directory + '/absent-encoder',
                                         '--decoder', directory + '/absent-decoder'], cwd=ROOT,
                                        capture_output=True, text=True, check=False)
                self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
                lines = [line for line in result.stdout.splitlines() if line.startswith('- ')]
                self.assertEqual(len(lines), 28 * len(public_modes))
                for sequence, count in counts.items():
                    selected = [line for line in lines if f'LBeu_{sequence} ' in line]
                    self.assertEqual(len(selected), 4 * len(public_modes))
                    self.assertTrue(all(f'frames={count},' in line for line in selected))
                self.assertTrue(all('decode-md5=on' in line and 'recon=off' in line for line in lines))
                for i, public in enumerate(public_modes):
                    self.assertTrue(all(reverse[public] in line for line in lines[i*28:(i+1)*28]))

    def test_metadata_templates_match_protocol_without_claiming_results(self):
        for mode in R14_MODE_NUMBERS:
            path = ROOT / 'experiments/ts_predictor_r14' / directory_name(mode)
            actual = json.loads((path / 'run_metadata.template.json').read_text())
            for key, value in r14_protocol(mode).items():
                self.assertEqual(actual[key], value, (mode, key))
            self.assertIsNone(actual['actual_encoder_sha256'])
            self.assertFalse(actual['server_build_verified'])
            self.assertTrue((path / 'LB_CE/README.md').is_file())

    def test_resume_tracks_protocol_observation_binary_and_config(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            executable = root / 'fake-encoder'
            executable.write_bytes(b'not an encoder')
            config = root / 'test.cfg'
            config.write_text('FramesToBeEncoded : 2\nFrameRate : 30\n')
            mode = 'r14_g2_pair2_equal'
            job = replace(self.job(root), encoder=executable, fixed_predictor=mode, no_recon=True,
                          cfgs=[config], sequence_cfg=config)
            calls = []
            def run(cmd, **kwargs):
                calls.append(cmd)
                self.assertEqual(cmd[-2:], ['-o', ''])
                Path(cmd[cmd.index('-b') + 1]).write_bytes(b'mock bitstream')
                kwargs['stdout'].write(f'EXPERIMENT: TS_FIXED_PREDICTOR={mode}; syntax=experimental-v1\n'
                                       f'TS R14 revision={R14_REVISION}; numbering={R14_NUMBERING}; mode=10; runtime={mode}; K=2; '
                                       'update=PAIR2; r0=2; s0=5; score-scale=168; '
                                       'target=TSRC-enabled-nonBDPCM\n'
                                       'Total Frames Y-PSNR U-PSNR V-PSNR\n2 a 100.0 35.0 36.0 37.0\n')
                return SimpleNamespace(returncode=0)
            with patch.dict(os.environ, {}, clear=True), \
                 patch.object(batch, '_local_source_snapshot', return_value={'binary_build_origin_verified': False}), \
                 patch.object(batch.subprocess, 'run', side_effect=run):
                self.assertEqual(batch._run_one(job)['encode_status'], 'ok')
                self.assertEqual(batch._run_one(job)['encode_status'], 'skipped_exists')
                for key, value in [('TS_R14_STATS', '1'), ('TS_R14_TRACE', '1'),
                                   ('TS_R14_DETAIL_LIMIT', '3'), ('TS_R14_POC', '0')]:
                    os.environ[key] = value
                    self.assertEqual(batch._run_one(job)['encode_status'], 'ok', key)
                    self.assertEqual(batch._run_one(job)['encode_status'], 'skipped_exists', key)
                self.assertEqual(len(calls), 5)
                identity = json.loads(job.bitstream.with_suffix('.identity.json').read_text())
                for key, value in r14_protocol(mode).items():
                    self.assertEqual(identity[key], value)
                self.assertEqual(identity['encoder']['sha256'], hashlib.sha256(executable.read_bytes()).hexdigest())
                self.assertEqual(identity['observation_env']['TS_R14_POC'], '0')
                self.assertFalse(identity['local_source_snapshot']['binary_build_origin_verified'])
                self.assertIsNone(identity['input_identity']['content_sha256'])
                marker = json.loads(job.bitstream.with_suffix('.done.json').read_text())
                self.assertEqual(marker['r14_identity']['revision'], R14_REVISION)
                self.assertEqual(marker['r14_identity']['numbering'], R14_NUMBERING)
                # Old markers cannot be resumed as new numbers, even when a
                # runtime name and the algorithm revision remain unchanged.
                stale = json.loads(job.bitstream.with_suffix('.done.json').read_text())
                stale['r14_identity'].pop('numbering')
                job.bitstream.with_suffix('.done.json').write_text(json.dumps(stale))
                self.assertEqual(batch._run_one(job)['encode_status'], 'ok')
                executable.write_bytes(b'changed executable')
                self.assertEqual(batch._run_one(job)['encode_status'], 'ok')
                job.sequence_cfg.write_text(job.sequence_cfg.read_text() + '\n# changed config\n')
                self.assertEqual(batch._run_one(job)['encode_status'], 'ok')
                self.assertFalse(job.recon.exists())


if __name__ == '__main__':
    unittest.main()
