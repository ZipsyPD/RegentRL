import json
import tempfile
import unittest
from pathlib import Path
from research.core import FirstLegalAgent, RandomAgent, load_verified

class ResearchTests(unittest.TestCase):
    def test_agents_only_choose_legal_indices(self):
        actions = [{'Type': 'A'}, {'Type': 'B'}]
        self.assertEqual(FirstLegalAgent().act({}, actions), 0)
        a = RandomAgent(seed=4)
        self.assertTrue(all(0 <= a.act({}, actions) < 2 for _ in range(100)))

    def test_loader_rejects_unverified(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'test.jsonl'
            p.write_text(json.dumps({'Executed': False, 'NextObservation': {}}) + '\n')
            with self.assertRaises(ValueError):
                list(load_verified(p))

if __name__ == '__main__':
    unittest.main()
