"""Evidence integrity and meaningful recommender safety checks."""
import importlib.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('recommend', ROOT/'analysis/recommend.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

class RecommendationTests(unittest.TestCase):
    def test_shared_ip_sessions_remain_independent_for_browsing(self):
        events = [dict(timestamp=0, actor=str(i), source='nat', route='catalog', cost=1, label='legitimate') for i in range(20)]
        self.assertEqual(module.replay(events, 1, 1)['legitimate_rejected'], 0)

    def test_login_is_source_limited_despite_identity_rotation(self):
        events = [dict(timestamp=0, actor=str(i), source='nat', route='login', cost=1, label='abusive') for i in range(20)]
        self.assertEqual(module.replay(events, 5, 1)['abusive_rejected'], 15)

    def test_fingerprint_alone_does_not_change_decisions(self):
        events = [dict(timestamp=i, actor='buyer', source='nat', route='catalog', cost=1, label='legitimate', ja4='suspicious') for i in range(5)]
        first = module.replay(events, 2, 1)
        for e in events:
            e['ja4'] = 'browser'
        self.assertEqual(first, module.replay(events, 2, 1))

    def test_insufficient_data_does_not_propose_rule(self):
        result = module.build([], {'catalog': {}}, 'fixture')
        self.assertEqual(result['proposals'][0]['decision'], 'insufficient_evidence')

    def test_replay_charges_cost_and_refills_with_elapsed_time(self):
        events = [dict(timestamp=t, actor='buyer', source='nat', route='search', cost=4, label='legitimate') for t in (0, 0, 4)]
        result = module.replay(events, 4, 1)
        self.assertEqual(result['legitimate_allowed'], 2)
        self.assertEqual(result['legitimate_rejected'], 1)

    def test_shared_network_holdout_withholds_login_proposal(self):
        events, digest = module.load_events(ROOT/'traffic/scenarios.jsonl')
        policies = json.loads((ROOT/'policies/endpoints.json').read_text())
        result = module.build(events, policies, digest)
        login = next(p for p in result['proposals'] if p['route'] == 'login')
        self.assertLessEqual(login['selected']['legitimate_rejection_rate'], .01)
        self.assertGreater(login['holdout_result']['legitimate_rejection_rate'], .01)
        self.assertEqual(login['decision'], 'insufficient_evidence')

if __name__ == '__main__':
    unittest.main()
