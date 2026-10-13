"""Deterministic, labelled synthetic journeys. Never publish captured customer traffic."""
import json
from pathlib import Path
import random

ROOT = Path(__file__).resolve().parents[1]

def generate(seed=42):
    rng = random.Random(seed)
    events = []
    routes = ('catalog', 'products', 'search', 'login', 'cart', 'session')
    for split, offset in (('calibration', 0), ('validation', 3600), ('holdout', 7200)):
        for route in routes:
            for buyer in range(30):
                actor = f'{split}-{route}-buyer-{buyer:02}'
                start = offset + rng.uniform(0, 50)
                # NAT buyers share one source, but have independent signed sessions.
                source = f'shared-network-{buyer // 10}'
                count = 2 if route == 'login' else 6
                for i in range(count):
                    cost = 4 if route == 'search' and i == 0 else 1
                    events.append(dict(timestamp=round(start+i*.15, 3), actor=actor, source=source,
                        route=route, cost=cost, resource=f'product-{i}' if route == 'products' else None,
                        ja4='shared-browser-fingerprint', status=401 if route == 'login' and i == 0 else 200,
                        label='legitimate', split=split, journey='buyer'))
            if split != 'calibration':
                for attacker in range(8):
                    actor = f'{route}-automation-{attacker}'
                    for i in range(80):
                        events.append(dict(timestamp=round(offset+65+attacker*.1+i*.04, 3), actor=actor,
                            source=f'automation-source-{attacker}', route=route,
                            cost=4 if route == 'search' else 1, resource=f'product-{i}' if route == 'products' else None,
                            ja4='shared-browser-fingerprint' if attacker == 0 else 'automation-fingerprint',
                            status=401 if route == 'login' else 200, label='abusive', split=split, journey='burst-abuse'))
                # Below-threshold scraper: deliberately shows residual risk.
                for i in range(8):
                    events.append(dict(timestamp=offset+100+i*5, actor=route+'-slow-automation',
                        source='slow-source', route=route, cost=1, resource=f'product-{i}' if route == 'products' else None,
                        ja4='shared-browser-fingerprint', status=200, label='abusive', split=split,
                        journey='slow-abuse'))
    return sorted(events, key=lambda e: (e['timestamp'], e['actor']))

if __name__ == '__main__':
    destination = ROOT/'traffic/scenarios.jsonl'
    events = generate()
    destination.write_text(''.join(json.dumps(e, separators=(',', ':'))+'\n' for e in events))
    print(f'Generated {len(events)} synthetic events; calibration and validation windows are separate.')
