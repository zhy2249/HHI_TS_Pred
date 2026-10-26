import json
from pathlib import Path
import unittest
import audit_rule_activity as A


class ActivityTests(unittest.TestCase):
    def fixture(self):
        return json.loads(Path(__file__).with_name('ce01_tu.json').read_text())

    def test_recorded_ce01_scoring_and_remap_scope(self):
        pop, methods = A.census(self.fixture())
        self.assertEqual(pop['eligible_nonzero'], 7)
        self.assertEqual(pop['eq_sp_remap_changes'], 1)
        self.assertEqual(len(methods), 61)
        for values in methods.values():
            self.assertLessEqual(values['weight_steps'], values['state_steps'])
            self.assertLessEqual(values['state_steps'], pop['eligible_nonzero'])
            self.assertLessEqual(values['potential_remap_changes'], pop['nonzero'])

    def test_all_zero_has_no_actions_or_state_updates(self):
        tu = self.fixture()
        tu['q'] = [0] * len(tu['q'])
        pop, methods = A.census(tu)
        self.assertEqual(pop['eligible_nonzero'], 0)
        self.assertEqual(pop['any_rule_potential_remap_changes'], 0)
        for values in methods.values():
            self.assertEqual(values['state_steps'], 0)
            self.assertEqual(values['potential_remap_changes'], 0)


if __name__ == '__main__':
    unittest.main()
