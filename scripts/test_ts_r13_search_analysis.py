import json
from pathlib import Path
import tempfile
import subprocess
import shutil
import unittest

from ts_r13_search_analysis import parse, review


class SearchAnalysisTests(unittest.TestCase):
    def rows(self, extra=(), change=False):
        rows=[dict(event='ctu_begin',node_path='',node=0,parent=0,ctx_hash=123),
              dict(event='cu_begin',node_path='/8_0_8_8_0_1#1',node=1,parent=0),
              dict(event='transform_entry',node_path='/8_0_8_8_0_1#1',node=1,parent=0,
                   component=0,tu_x=8,tu_y=0,tu_w=8,tu_h=8,tr_group=0,tr=1,
                   ctx_hash=42,input_resi_hash=11,pred_hash=22,quant_lambda=3),
              dict(event='transform_trial',node_path='/8_0_8_8_0_1#1',node=1,parent=0,
                   component=0,tu_x=8,tu_y=0,tu_w=8,tu_h=8,tr_group=0,tr=1,
                   cost=5 if change else 6,frac_bits=10,dist=2,q_hash=31,accepted=1),
              *extra,
              dict(event='ctu_end',node_path='',node=0,parent=0,reco_y_hash=18)]
        return [dict(schema=1,seq=i+1,poc=16,ctu=36,**r) for i,r in enumerate(rows)]

    def parsed(self, rows):
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory)/'trace.log'
            p.write_text('\n'.join('TS_R13_SEARCH '+json.dumps(r) for r in rows)+'\n')
            return parse(p)

    def test_native_json_field_types(self):
        compiler = shutil.which('c++')
        if not compiler:
            self.skipTest('C++ compiler unavailable')
        root = Path(__file__).resolve().parents[1]
        source = r'''#include "EncoderLib/TsR13SearchDiagnostic.h"
#include <iostream>
#include <limits>
int main() {
  R13SearchDiagnostic::Fields f;
  f.add("qp",int8_t(33)).add("negative",int8_t(-3)).add("rdo_tried",uint8_t(5))
   .add("flag",true).add("hash",std::numeric_limits<uint64_t>::max())
   .number("infinite",std::numeric_limits<double>::infinity())
   .number("nan",std::numeric_limits<double>::quiet_NaN());
  std::cout<<"{\"schema\":1"<<f.out.str()<<"}\n";
}
'''
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory)/'fields.cpp'; exe=Path(directory)/'fields'
            p.write_text(source)
            subprocess.run([compiler,'-std=c++17','-I',str(root/'source/Lib'),
                '-I',str(root/'source/Lib/CommonLib'),'-I',str(root/'thirdparty'),
                '-I',str(root/'thirdparty/sadl'),str(p),'-o',str(exe)],check=True,
                stdout=subprocess.PIPE,stderr=subprocess.PIPE)
            row=json.loads(subprocess.check_output([str(exe)],text=True))
        self.assertEqual(row,dict(schema=1,qp=33,negative=-3,rdo_tried=5,flag=1,
                                 hash=2**64-1,infinite=None,nan=None))

    def test_equal_input_cost_change(self):
        summary,changes,_=review(self.parsed(self.rows()),self.parsed(self.rows(change=True)))
        self.assertEqual(summary['exact_common_prefix_events'],3)
        first=summary['first_transform_cost_or_q_difference_with_equal_logged_entry']
        self.assertEqual(first['changes'],{'cost':[6,5]})
        self.assertEqual(first['matched_transform_entry_changes'],{})
        self.assertEqual(len(changes),1)

    def test_added_event_is_unmatched_not_ordinal_pair(self):
        extra=[dict(event='mode_result',node_path='/8_0_8_8_0_1#1',node=1,parent=0,mode=7,opts=0,accepted=0)]
        summary,changes,unmatched=review(self.parsed(self.rows()),self.parsed(self.rows(extra)))
        self.assertEqual(summary['unmatched_events'],1)
        self.assertFalse(changes)
        self.assertEqual(unmatched[0]['side'],'test_only')
        self.assertEqual(unmatched[0]['event'],'mode_result')

    def test_parent_mode_change_does_not_pair_same_child_geometry(self):
        def trace(mode):
            rows = [dict(event='ctu_begin',node_path='',node=0,parent=0),
                    dict(event='cu_begin',node_path='/root#1',node=1,parent=0),
                    dict(event='mode_prepare',node_path='/root#1',node=1,parent=0,
                         mode=mode,opts=0,mode_qp=33),
                    dict(event='cu_begin',node_path='/root#1/child#1',node=2,parent=1),
                    dict(event='cu_end',node_path='/root#1/child#1',node=2,parent=1),
                    dict(event='cu_end',node_path='/root#1',node=1,parent=0),
                    dict(event='ctu_end',node_path='',node=0,parent=0)]
            return [dict(schema=1,seq=i+1,poc=16,ctu=36,**r) for i,r in enumerate(rows)]
        _, _, unmatched = review(self.parsed(trace(10)), self.parsed(trace(11)))
        child = [r for r in unmatched if r['event']=='cu_begin']
        self.assertEqual(len(child),2)
        self.assertEqual({r['side'] for r in child},{'reference_only','test_only'})

    def test_different_residual_candidate_does_not_pair_transform(self):
        def trace(sse_key):
            rows=self.rows()
            rows.insert(2,dict(event='mode_prepare',node_path='/8_0_8_8_0_1#1',
                              node=1,parent=0,mode=1,opts=0,mode_qp=33))
            rows.insert(3,dict(event='sbt_read',node_path='/8_0_8_8_0_1#1',
                              node=1,parent=0,sse_key=sse_key,hist_sbt=255))
            return [dict(r,schema=1,seq=i+1,poc=16,ctu=36) for i,r in enumerate(rows)]
        summary, _, unmatched=review(self.parsed(trace(58)),self.parsed(trace(62)))
        trials=[r for r in unmatched if r['event']=='transform_trial']
        self.assertEqual(len(trials),2)
        self.assertEqual({r['side'] for r in trials},{'reference_only','test_only'})
        self.assertIsNone(summary['first_transform_cost_or_q_difference'])

    def test_reject_truncated(self):
        with self.assertRaisesRegex(ValueError,'truncated'):
            self.parsed(self.rows()+[dict(schema=1,event='truncated',poc=16,ctu=36,limit=5)])

    def test_explicit_legacy_recovery_keeps_raw_file(self):
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory)/'trace.log'
            lines=['TS_R13_SEARCH '+json.dumps(r) for r in self.rows()]
            lines[3]=lines[3][:-1]+',"qp":!,"rdo_tried":'+chr(5)+'}'
            original='\n'.join(lines)+'\n'
            p.write_text(original)
            with self.assertRaises(json.JSONDecodeError): parse(p)
            rows=parse(p,legacy_byte_fields=True)
            self.assertEqual(rows[3]['qp'],33)
            self.assertEqual(rows[3]['rdo_tried'],5)
            self.assertEqual(rows[-1]['_legacy_repairs'],1)
            self.assertEqual(p.read_text(),original)

    def test_explicit_truncated_prefix_marks_incomplete(self):
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory)/'trace.log'
            rows=self.rows()[:-1]+[dict(schema=1,event='truncated',poc=16,ctu=36,limit=4)]
            p.write_text('\n'.join('TS_R13_SEARCH '+json.dumps(r) for r in rows)+'\n')
            rows=parse(p,allow_truncated=True)
            self.assertFalse(rows[-1]['_trace_complete'])
            summary,_,_=review(rows,rows)
            self.assertFalse(summary['reference_trace_complete'])
            self.assertFalse(summary['test_trace_complete'])

    def test_reject_incomplete_ctu(self):
        with self.assertRaisesRegex(ValueError,'incomplete CTU'):
            self.parsed(self.rows()[:-1])


if __name__=='__main__': unittest.main()
