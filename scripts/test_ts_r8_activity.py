import unittest
from ts_r8_activity import parse_log, parse_search_log


class R8ActivityTest(unittest.TestCase):
    def test_census_and_decisions(self):
        fields='mode,support,cutoff,tu_count,cg_count,active_count,p_current,p_identity,p_other,remap_vs_parent'
        text='TS_R8_STATS_HEADER '+fields+'\nTS_R8_STATS 1,-1,-1,1,1,0,0,0,0,0\nTS_R8_STATS 1,2,10,0,0,3,1,1,1,2'
        self.assertEqual(len(parse_log(text,1)),2)
        with self.assertRaises(ValueError): parse_log(text,4)
        with self.assertRaises(ValueError): parse_log(text.replace('1,2,10','1,2,0'),1)
        with self.assertRaises(ValueError): parse_log(text+'\nTS_R8_STATS_HEADER '+fields,1)

    def test_no_stats_is_not_fabricated(self):
        self.assertEqual(parse_log('no TS used',1),[])

    def test_search_is_separate_and_local_minimum(self):
        text='TS_R8_SEARCH_HEADER mode,pairs,q_changed,chosen_q1,local_gain_sum\nTS_R8_SEARCH 23,9,2,1,0.25'
        self.assertEqual(parse_log(text,23),[])
        self.assertEqual(parse_search_log(text,23)[0]['local_gain_sum'],0.25)
        with self.assertRaises(ValueError): parse_search_log(text,24)
        with self.assertRaises(ValueError): parse_search_log(text.replace('0.25','-0.25'),23)
        with self.assertRaises(ValueError): parse_search_log(text.replace('23,9,2,1','23,9,10,1'),23)


if __name__=='__main__': unittest.main()
