#!/usr/bin/env python3
"""Compile lightweight probes; never overwrite existing experiment binaries."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import batch_test as batch


class FixedDefaultsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix='ts-fixed-defaults-')
        cls.root = Path(__file__).resolve().parents[1]
        cls.base_cmd = ['g++', '-std=c++17', '-I', str(cls.root/'source/Lib/CommonLib'),
                        str(cls.root/'scripts/ts_fixed_mode_probe.cpp')]
        cls.binaries = {}
        for mode in ('current','nopred','gradient','directional','off'):
            exe = Path(cls.tmp.name)/mode
            defines = ['-DJVET_BJUT_TS_FIXED_PREDICTOR='+('0' if mode=='off' else '1')]
            for m in ('nopred','gradient','directional'):
                defines.append(f'-DJVET_BJUT_TS_FIXED_{m.upper()}={int(m==mode or (mode=="off" and m=="nopred"))}')
            subprocess.run(cls.base_cmd+defines+['-o',str(exe)],check=True,capture_output=True)
            cls.binaries[mode] = exe

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def run_probe(self, mode, override=None):
        env = os.environ.copy()
        env.pop('TS_FIXED_PREDICTOR',None)
        if override is not None:
            env['TS_FIXED_PREDICTOR'] = override
        return subprocess.run([str(self.binaries[mode])],env=env,capture_output=True,text=True)

    def test_all_defaults(self):
        for mode in ('current','nopred','gradient','directional'):
            r = self.run_probe(mode)
            self.assertEqual(r.returncode,0)
            self.assertIn(f'ACTUAL_MODE={mode}',r.stdout)
            self.assertIn('selection: TypeDef.h default',r.stdout)

    def test_all_overrides(self):
        for default in ('current','nopred','gradient','directional'):
            for override in ('current','nopred','gradient','directional'):
                r = self.run_probe(default,override)
                self.assertEqual(r.returncode,0)
                self.assertIn(f'ACTUAL_MODE={override}',r.stdout)

    def test_invalid_override(self):
        self.assertNotEqual(self.run_probe('gradient','invalid').returncode,0)

    def test_master_off(self):
        r = self.run_probe('off','directional')
        self.assertEqual(r.returncode,0)
        self.assertIn('ACTUAL_MODE=current',r.stdout)
        self.assertNotIn('EXPERIMENT:',r.stdout)

    def test_invalid_compile_settings(self):
        for defines in [
            ['-DJVET_BJUT_TS_FIXED_NOPRED=1','-DJVET_BJUT_TS_FIXED_GRADIENT=1'],
            ['-DJVET_BJUT_TS_FIXED_DIRECTIONAL=2']]:
            r = subprocess.run(self.base_cmd+defines+['-fsyntax-only'],capture_output=True,text=True)
            self.assertNotEqual(r.returncode,0)
            self.assertIn('error:',r.stderr)

    def test_probe_ignores_ambient_override(self):
        with patch.dict(os.environ,{'TS_FIXED_PREDICTOR':'directional'}):
            banner = batch._detect_experiment_line(self.binaries['gradient'],self.root)
            self.assertIn('TS_FIXED_PREDICTOR=gradient;',banner)


if __name__=='__main__':
    unittest.main()
