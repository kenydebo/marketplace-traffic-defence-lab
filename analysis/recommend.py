"""Explainable lab recommender. Labels are ground truth, not a production classifier.

The candidate grid uses ONLY a trusted calibration window. Validation labels are
used ONLY to evaluate impact. No automatic deployment or fingerprint-only bans.
"""
import argparse
from collections import defaultdict
import hashlib
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def percentile(values, fraction):
    return sorted(values)[max(0, math.ceil(len(values)*fraction)-1)]

def replay(events, capacity, refill):
    buckets = {}
    counts = {'legitimate_allowed': 0, 'legitimate_rejected': 0, 'abusive_allowed': 0, 'abusive_rejected': 0}
    timeline = defaultdict(lambda: {'legitimate': 0, 'abusive': 0, 'rejected': 0})
    origin = min((e['timestamp'] for e in events), default=0)
    for e in sorted(events, key=lambda x: x['timestamp']):
        # Mirrors app key selection; IP-only login/session, session-aware browsing.
        key = e['source'] if e['route'] in ('login', 'session') else e['actor']
        tokens, updated = buckets.get(key, (capacity, e['timestamp']))
        tokens = min(capacity, tokens + max(0, e['timestamp']-updated)*refill)
        allow = tokens >= e['cost']
        buckets[key] = (tokens-e['cost'] if allow else tokens, e['timestamp'])
        counts[e['label']+('_allowed' if allow else '_rejected')] += 1
        minute = int((e['timestamp']-origin)//10)*10
        timeline[minute][e['label']] += 1
        timeline[minute]['rejected'] += int(not allow)
    legitimate = counts['legitimate_allowed'] + counts['legitimate_rejected']
    abusive = counts['abusive_allowed'] + counts['abusive_rejected']
    return {**counts, 'legitimate_rejection_rate': round(counts['legitimate_rejected']/max(1, legitimate), 4),
        'abuse_rejection_rate': round(counts['abusive_rejected']/max(1, abusive), 4),
        'timeline': [{'second': k, **v} for k, v in sorted(timeline.items())]}

def build(events, policies, source_hash):
    proposals = []
    for route, policy in policies.items():
        calibration = [e for e in events if e['route'] == route and e['split'] == 'calibration']
        validation = [e for e in events if e['route'] == route and e['split'] == 'validation']
        holdout = [e for e in events if e['route'] == route and e['split'] == 'holdout']
        if len(calibration) < 20 or not validation:
            proposals.append({'route': route, 'decision': 'insufficient_evidence'})
            continue
        # Calibrated baseline is an explicitly trusted lab fixture, not guessed from status 200.
        windows = defaultdict(int)
        source_windows = defaultdict(int)
        for e in calibration:
            key = e['source'] if route in ('login', 'session') else e['actor']
            windows[(key, int(e['timestamp']))] += e['cost']
            source_windows[(e['source'], int(e['timestamp']//60))] += 1
        p99 = percentile(list(windows.values()), .99)
        per_source_p99 = percentile(list(source_windows.values()), .99)
        candidates = []
        for margin in (1, 1.5, 2, 3, 4):
            capacity = max(1, math.ceil(p99*margin))
            refill = max(.2, round(capacity/12, 2))
            if capacity > 64 or refill > 6:
                continue  # Explicit LAB per-principal budgets; not measured service capacity.
            result = replay(validation, capacity, refill)
            candidates.append({'capacity': capacity, 'refill_per_second': refill, 'margin': margin, **result})
        # Validation is an evaluation set, not used to fit the candidate grid.
        eligible = [c for c in candidates if c['legitimate_rejection_rate'] <= .01 and c['abuse_rejection_rate'] >= .50]
        selected = max(eligible, key=lambda c: (c['abuse_rejection_rate'], -c['capacity'])) if eligible else None
        holdout_result = replay(holdout, selected['capacity'], selected['refill_per_second']) if selected and holdout else None
        holdout_passed = bool(holdout_result and holdout_result['legitimate_rejection_rate'] <= .01 and holdout_result['abuse_rejection_rate'] >= .50)
        actors = defaultdict(lambda: {'requests': 0, 'cost': 0, 'failed': 0, 'resources': set()})
        fingerprints = defaultdict(set)
        for e in validation:
            a = actors[e['actor']]
            a['requests'] += 1
            a['cost'] += e['cost']
            a['failed'] += int(e['status'] == 401)
            if e.get('resource'): a['resources'].add(e['resource'])
            fingerprints[e['ja4']].add(e['source'])
        observed = replay(validation, policy['capacity'], policy['refill_per_second'])
        edge_limit = max(10, math.ceil(per_source_p99*1.5))
        proposals.append({'route': route, 'decision': 'propose_observation' if selected and holdout_passed else 'insufficient_evidence',
            'owner': policy['owner'], 'risk': policy['risk'], 'evidence_type': 'synthetic_replay',
            'calibration': {'requests': len(calibration), 'p99_cost_per_key_second': p99,
                'p99_requests_per_source_minute': per_source_p99, 'trusted_baseline': True},
            'baseline_policy': policy, 'baseline_result': observed, 'candidates': candidates,
            'selected': selected, 'holdout_result': holdout_result, 'holdout_passed': holdout_passed,
            'observations': {'maximum_requests_per_actor': max(a['requests'] for a in actors.values()),
                'maximum_cost_per_actor': max(a['cost'] for a in actors.values()),
                'maximum_distinct_resources_per_actor': max(len(a['resources']) for a in actors.values()),
                'maximum_authentication_failures_per_actor': max(a['failed'] for a in actors.values()),
                'maximum_sources_sharing_fingerprint': max(len(v) for v in fingerprints.values()),
                'meaning': 'Descriptive evidence only; these features do not label an actor as malicious.'},
            'edge_proposal': {'action': 'COUNT', 'limit': edge_limit,
                'window_seconds': 60, 'aggregation': 'IP', 'scope': '/api/products/' if route == 'products' else '/api/'+route,
                'reason': '1.5 times the trusted per-source-minute P99; shared-network fixture included.',
                'status': 'requires_live_count_validation'},
            'rollback': 'Revert if legitimate scenario rejection exceeds 1%; production buyer budget is not established.',
            'limitations': ['Synthetic labels do not establish production precision or conversion impact.',
                'A separate synthetic holdout is evaluated; real traffic review is required before enforcement.',
                'Slow abuse, rotating identities and distributed sources remain residual risks.',
                'WAF trailing-window behaviour is not reproduced by this token-bucket replay.',
                'Shared JA4 values are investigation context and never a blocking condition.']})
    return {'title': 'Marketplace Traffic Defence Lab', 'evidence_type': 'synthetic_replay',
        'dataset_sha256': source_hash, 'algorithm': 'Trusted baseline P99 → bounded candidate grid → labelled replay → observation proposal',
        'engine': 'Python standard library; no ML, CrowdSec or external recommendation service',
        'budgets': {'legitimate_rejection_max': .01, 'abuse_rejection_min': .50,
            'maximum_capacity': 64, 'maximum_refill_per_second': 6, 'meaning': 'Explicit lab design constraints, not measured production capacity.'},
        'proposals': proposals}

def load_events(path):
    data = path.read_bytes()
    if len(data) > 10_000_000:
        raise ValueError('Input exceeds bounded lab size')
    events = [json.loads(line) for line in data.splitlines() if line.strip()]
    if len(events) > 50_000:
        raise ValueError('Too many events')
    for e in events:
        if e.get('label') not in ('legitimate', 'abusive') or e.get('split') not in ('calibration', 'validation', 'holdout'):
            raise ValueError('Only explicitly labelled lab fixtures are accepted')
        if e['split'] == 'calibration' and e['label'] != 'legitimate':
            raise ValueError('Trusted baseline contains an abusive fixture')
        if type(e.get('cost')) is not int or not 1 <= e['cost'] <= 4 or not math.isfinite(e['timestamp']):
            raise ValueError('Invalid event cost or timestamp')
    return events, hashlib.sha256(data).hexdigest()

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', type=Path, default=ROOT/'traffic/scenarios.jsonl')
    parser.add_argument('--output', type=Path, default=ROOT/'site/data/recommendations.json')
    args = parser.parse_args()
    events, digest = load_events(args.input)
    policies = json.loads((ROOT/'policies/endpoints.json').read_text())
    result = build(events, policies, digest)
    args.output.write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps({'proposals': len(result['proposals']), 'engine': result['engine'], 'source_sha256': digest}))
