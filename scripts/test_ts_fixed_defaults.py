#!/usr/bin/env python3
"""Compile lightweight probes; never overwrite existing experiment binaries."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import batch_test as batch
from ts_predictor_naming import R8_MODE_NUMBERS


class FixedDefaultsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix='ts-fixed-defaults-')
        cls.root = Path(__file__).resolve().parents[1]
        cls.base_cmd = ['g++', '-std=c++17', '-I', str(cls.root/'source/Lib/CommonLib'),
                        str(cls.root/'scripts/ts_fixed_mode_probe.cpp')]
        cls.binaries = {}
        cls.conditional = ('q32','conf2','prev','ewma','q32_ewma')
        cls.r2 = ('r2_modal','r2_risk','r2_cn_log','r2_cn_frac')
        cls.r3 = ('r3_risk_guard','r3_risk_guard_y','r3_cn_guard','r3_cn_guard_y')
        cls.r4 = ('r4_identity_only','r4_magnitude_only','r4_guard_rescue','r4_directional_risk','r4_causal_models','r4_signed_plane')
        cls.r5 = ('r5_margin_first','r5_current_veto')
        cls.r6 = ('r6_dense_nopred','r6_reject_nopred','r6_trim_cost','r6_trim_saving','r6_sparse_max','r6_sparse_mean','r6_sparse_min')
        cls.rate = ('rate_raw','rate_guard')
        cls.modes = ('current','nopred','gradient','directional', *cls.conditional, *cls.r2, *cls.r3, *cls.r4, *cls.r5, *cls.r6, *cls.rate, *R8_MODE_NUMBERS)
        for mode in (*cls.modes, 'off'):
            exe = Path(cls.tmp.name)/mode
            defines = ['-DJVET_BJUT_TS_FIXED_PREDICTOR='+('0' if mode=='off' else '1')]
            for m in ('nopred','gradient','directional'):
                defines.append(f'-DJVET_BJUT_TS_FIXED_{m.upper()}={int(m==mode)}')
            defines.append('-DJVET_BJUT_TS_CONDITIONAL_MODE='+str(cls.conditional.index(mode)+1 if mode in cls.conditional else 0))
            defines.append('-DJVET_BJUT_TS_R2_MODE='+str(cls.r2.index(mode)+1 if mode in cls.r2 else 0))
            defines.append('-DJVET_BJUT_TS_R3_MODE='+str(cls.r3.index(mode)+1 if mode in cls.r3 else 0))
            defines.append('-DJVET_BJUT_TS_R4_MODE='+str(cls.r4.index(mode)+1 if mode in cls.r4 else 0))
            defines.append('-DJVET_BJUT_TS_R5_MODE='+str(cls.r5.index(mode)+1 if mode in cls.r5 else 0))
            defines.append('-DJVET_BJUT_TS_R6_MODE='+str(cls.r6.index(mode)+1 if mode in cls.r6 else 0))
            defines.append('-DJVET_BJUT_TS_R7_MODE='+str(cls.rate.index(mode)+1 if mode in cls.rate else 0))
            defines.append('-DJVET_BJUT_TS_R7_SHADOW=0')
            defines.append('-DJVET_BJUT_TS_R8_MODE='+str(R8_MODE_NUMBERS.get(mode,0)))
            subprocess.run(cls.base_cmd+defines+['-o',str(exe)],check=True,capture_output=True)
            cls.binaries[mode] = exe

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def run_probe(self, mode, override=None):
        env = os.environ.copy()
        env.pop('TS_FIXED_PREDICTOR',None)
        env.pop('TS_RATE_SHADOW',None)
        env.pop('TS_RATE_RDOQ_SHADOW',None)
        if override is not None:
            env['TS_FIXED_PREDICTOR'] = override
        return subprocess.run([str(self.binaries[mode])],env=env,capture_output=True,text=True)

    def test_all_defaults(self):
        for mode in self.modes:
            r = self.run_probe(mode)
            self.assertEqual(r.returncode,0)
            self.assertIn(f'ACTUAL_MODE={mode}',r.stdout)
            self.assertIn('selection: TypeDef.h default',r.stdout)
            if mode in self.rate:
                self.assertIn(f'TS R7 experiment=R7-{self.rate.index(mode)+1};',r.stdout)
            if mode in R8_MODE_NUMBERS:
                self.assertIn(f'mode={R8_MODE_NUMBERS[mode]}; runtime={mode};',r.stdout)

    def test_all_overrides(self):
        for default in self.modes:
            for override in self.modes:
                r = self.run_probe(default,override)
                self.assertEqual(r.returncode,0)
                self.assertIn(f'ACTUAL_MODE={override}',r.stdout)

    def test_invalid_override(self):
        self.assertNotEqual(self.run_probe('gradient','invalid').returncode,0)

    def test_master_off(self):
        r = self.run_probe('off')
        self.assertEqual(r.returncode,0)
        self.assertIn('ACTUAL_MODE=current',r.stdout)
        self.assertNotIn('EXPERIMENT:',r.stdout)
        for mode in self.modes:
            self.assertEqual(self.run_probe('off',mode).returncode == 0, mode == 'current')

    def test_invalid_compile_settings(self):
        for defines in [
            ['-DJVET_BJUT_TS_FIXED_NOPRED=1','-DJVET_BJUT_TS_FIXED_GRADIENT=1'],
            ['-DJVET_BJUT_TS_FIXED_DIRECTIONAL=2'],
            ['-DJVET_BJUT_TS_CONDITIONAL_MODE=6'],
            ['-DJVET_BJUT_TS_CONDITIONAL_MODE=1', '-DJVET_BJUT_TS_FIXED_DIRECTIONAL=1'],
            ['-DJVET_BJUT_TS_R2_MODE=5'],
            ['-DJVET_BJUT_TS_R2_MODE=1','-DJVET_BJUT_TS_CONDITIONAL_MODE=1'],
            ['-DJVET_BJUT_TS_R2_MODE=1','-DJVET_BJUT_TS_FIXED_NOPRED=1'],
            ['-DJVET_BJUT_TS_R2_MODE=1','-DJVET_BJUT_TS_FIXED_PREDICTOR=0'],
            ['-DJVET_BJUT_TS_R3_MODE=5'],
            ['-DJVET_BJUT_TS_R3_MODE=-1'],
            ['-DJVET_BJUT_TS_R3_MODE=1','-DJVET_BJUT_TS_R2_MODE=1'],
            ['-DJVET_BJUT_TS_R3_MODE=1','-DJVET_BJUT_TS_CONDITIONAL_MODE=1'],
            ['-DJVET_BJUT_TS_R3_MODE=1','-DJVET_BJUT_TS_FIXED_NOPRED=1'],
            ['-DJVET_BJUT_TS_R3_MODE=1','-DJVET_BJUT_TS_FIXED_GRADIENT=1'],
            ['-DJVET_BJUT_TS_R3_MODE=1','-DJVET_BJUT_TS_FIXED_DIRECTIONAL=1'],
            ['-DJVET_BJUT_TS_R3_MODE=1','-DJVET_BJUT_TS_FIXED_PREDICTOR=0'],
            ['-DJVET_BJUT_TS_R4_MODE=-1'],
            ['-DJVET_BJUT_TS_R4_MODE=7'],
            ['-DJVET_BJUT_TS_R4_MODE=1','-DJVET_BJUT_TS_R3_MODE=1'],
            ['-DJVET_BJUT_TS_R4_MODE=2','-DJVET_BJUT_TS_R2_MODE=1'],
            ['-DJVET_BJUT_TS_R4_MODE=3','-DJVET_BJUT_TS_CONDITIONAL_MODE=1'],
            ['-DJVET_BJUT_TS_R4_MODE=4','-DJVET_BJUT_TS_FIXED_NOPRED=1'],
            ['-DJVET_BJUT_TS_R4_MODE=5','-DJVET_BJUT_TS_FIXED_GRADIENT=1'],
            ['-DJVET_BJUT_TS_R4_MODE=6','-DJVET_BJUT_TS_FIXED_DIRECTIONAL=1'],
            ['-DJVET_BJUT_TS_R4_MODE=1','-DJVET_BJUT_TS_FIXED_PREDICTOR=0'],
            ['-DJVET_BJUT_TS_R5_MODE=-1'],
            ['-DJVET_BJUT_TS_R5_MODE=3'],
            ['-DJVET_BJUT_TS_R5_MODE=1','-DJVET_BJUT_TS_R4_MODE=1'],
            ['-DJVET_BJUT_TS_R5_MODE=2','-DJVET_BJUT_TS_R3_MODE=1'],
            ['-DJVET_BJUT_TS_R5_MODE=1','-DJVET_BJUT_TS_R2_MODE=1'],
            ['-DJVET_BJUT_TS_R5_MODE=2','-DJVET_BJUT_TS_CONDITIONAL_MODE=1'],
            ['-DJVET_BJUT_TS_R5_MODE=1','-DJVET_BJUT_TS_FIXED_NOPRED=1'],
            ['-DJVET_BJUT_TS_R5_MODE=2','-DJVET_BJUT_TS_FIXED_GRADIENT=1'],
            ['-DJVET_BJUT_TS_R5_MODE=1','-DJVET_BJUT_TS_FIXED_DIRECTIONAL=1'],
            ['-DJVET_BJUT_TS_R5_MODE=2','-DJVET_BJUT_TS_FIXED_PREDICTOR=0'],
            ['-DJVET_BJUT_TS_CONDITIONAL_MODE=1','-DJVET_BJUT_TS_FIXED_PREDICTOR=0'],
            ['-DJVET_BJUT_TS_FIXED_NOPRED=1','-DJVET_BJUT_TS_FIXED_PREDICTOR=0'],
            ['-DJVET_BJUT_TS_FIXED_PREDICTOR=1','-DJVET_BJUT_TS_PRED_ANALYSIS=1']]:
            r = subprocess.run(self.base_cmd+defines+['-fsyntax-only'],capture_output=True,text=True)
            self.assertNotEqual(r.returncode,0)
            self.assertIn('error:',r.stderr)

    def test_probe_ignores_ambient_override(self):
        with patch.dict(os.environ,{'TS_FIXED_PREDICTOR':'directional'}):
            banner = batch._detect_experiment_line(self.binaries['gradient'],self.root)
            self.assertIn('TS_FIXED_PREDICTOR=gradient;',banner)

    def test_r8_invalid_and_old_conflicts(self):
        values = set(R8_MODE_NUMBERS.values()) | {0}
        cases = [[f'-DJVET_BJUT_TS_R8_MODE={n}'] for n in range(-1,26) if n not in values]
        for old in ('TS_FIXED_NOPRED','TS_FIXED_GRADIENT','TS_FIXED_DIRECTIONAL',
                    'TS_CONDITIONAL_MODE','TS_R2_MODE','TS_R3_MODE','TS_R4_MODE','TS_R5_MODE',
                    'TS_R6_MODE','TS_R7_MODE','TS_RATE_MODE'):
            cases.append(['-DJVET_BJUT_TS_R8_MODE=19',f'-DJVET_BJUT_{old}=1'])
        cases.append(['-DJVET_BJUT_TS_R8_MODE=1','-DJVET_BJUT_TS_FIXED_PREDICTOR=0'])
        for defines in cases:
            r = subprocess.run(self.base_cmd+defines+['-fsyntax-only'],capture_output=True,text=True)
            self.assertNotEqual(r.returncode,0)
            self.assertIn('error:',r.stderr)
        for mode in ('r8_unknown','r8_2_raw_sparse_mean','r8_path'):
            self.assertNotEqual(self.run_probe('current',mode).returncode,0)

    def test_r6_invalid_and_old_conflicts(self):
        cases = [[f'-DJVET_BJUT_TS_R6_MODE={n}'] for n in (-1,8)]
        for old in ('TS_FIXED_NOPRED','TS_FIXED_GRADIENT','TS_FIXED_DIRECTIONAL',
                    'TS_CONDITIONAL_MODE','TS_R2_MODE','TS_R3_MODE','TS_R4_MODE','TS_R5_MODE'):
            cases.append(['-DJVET_BJUT_TS_R6_MODE=1',f'-DJVET_BJUT_{old}=1'])
        cases.append(['-DJVET_BJUT_TS_R6_MODE=7','-DJVET_BJUT_TS_FIXED_PREDICTOR=0'])
        for defines in cases:
            r = subprocess.run(self.base_cmd+defines+['-fsyntax-only'],capture_output=True,text=True)
            self.assertNotEqual(r.returncode,0)
            self.assertIn('error:',r.stderr)

    def test_rate_invalid_and_old_conflicts(self):
        cases = [[f'-DJVET_BJUT_TS_RATE_MODE={n}'] for n in (-1,3)]
        cases += [[f'-DJVET_BJUT_TS_RATE_SHADOW={n}'] for n in (-1,2)]
        for old in ('TS_FIXED_NOPRED','TS_FIXED_GRADIENT','TS_FIXED_DIRECTIONAL',
                    'TS_CONDITIONAL_MODE','TS_R2_MODE','TS_R3_MODE','TS_R4_MODE','TS_R5_MODE','TS_R6_MODE'):
            cases.append(['-DJVET_BJUT_TS_RATE_MODE=1',f'-DJVET_BJUT_{old}=1'])
        cases += [['-DJVET_BJUT_TS_RATE_MODE=2','-DJVET_BJUT_TS_FIXED_PREDICTOR=0'],
                  ['-DJVET_BJUT_TS_RATE_SHADOW=1','-DJVET_BJUT_TS_FIXED_PREDICTOR=0']]
        cases += [[d.replace('TS_RATE_', 'TS_R7_') for d in defines] for defines in cases]
        cases += [['-DJVET_BJUT_TS_R7_MODE=1','-DJVET_BJUT_TS_RATE_MODE=2'],
                  ['-DJVET_BJUT_TS_R7_SHADOW=1','-DJVET_BJUT_TS_RATE_SHADOW=0']]
        for defines in cases:
            r = subprocess.run(self.base_cmd+defines+['-fsyntax-only'],capture_output=True,text=True)
            self.assertNotEqual(r.returncode,0)
            self.assertIn('error:',r.stderr)

    def test_uncompiled_shadow_fails_closed(self):
        for mode in ('off','current','r3_risk_guard','rate_guard'):
            for flag in ('TS_RATE_SHADOW','TS_RATE_RDOQ_SHADOW'):
                env = os.environ.copy()
                for key in ('TS_FIXED_PREDICTOR','TS_RATE_SHADOW','TS_RATE_RDOQ_SHADOW'):
                    env.pop(key,None)
                env[flag]='1'
                r=subprocess.run([str(self.binaries[mode])],env=env,capture_output=True,text=True)
                self.assertNotEqual(r.returncode,0)
                self.assertIn('JVET_BJUT_TS_R7_SHADOW=1',r.stderr+r.stdout)

    def test_r7_legacy_macro_aliases(self):
        env=os.environ.copy()
        for k in ('TS_FIXED_PREDICTOR','TS_RATE_SHADOW','TS_RATE_RDOQ_SHADOW'):
            env.pop(k,None)
        for n in (1,2):
            for same_value in (False,True):
                defines=[f'-DJVET_BJUT_TS_RATE_MODE={n}']
                if same_value:defines.append(f'-DJVET_BJUT_TS_R7_MODE={n}')
                exe=Path(self.tmp.name)/f'r7-alias-{n}-{same_value}'
                subprocess.run(self.base_cmd+defines+['-o',str(exe)],check=True,capture_output=True)
                r=subprocess.run([str(exe)],env=env,capture_output=True,text=True)
                self.assertEqual(r.returncode,0)
                self.assertIn('ACTUAL_MODE='+self.rate[n-1],r.stdout)
        for macro in ('R7','RATE'):
            exe=Path(self.tmp.name)/f'r7-shadow-{macro}'
            defines=['-DJVET_BJUT_TS_R3_MODE=1',f'-DJVET_BJUT_TS_{macro}_SHADOW=1']
            subprocess.run(self.base_cmd+defines+['-o',str(exe)],check=True,capture_output=True)
            r=subprocess.run([str(exe)],env={**env,'TS_RATE_SHADOW':'1'},capture_output=True,text=True)
            self.assertEqual(r.returncode,0)
            self.assertIn('TS R7 observation-only;',r.stdout)


if __name__=='__main__':
    unittest.main()
