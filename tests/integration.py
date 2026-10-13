"""Real two-instance/Redis assertions; synthetic clients, not a production benchmark."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import math
from pathlib import Path
import subprocess
import time
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
BASES = ['http://127.0.0.1:18081', 'http://127.0.0.1:18082']
results = []

def call(index, path, token=None, body=None, extra=None):
    headers = {'Content-Type': 'application/json', **(extra or {})}
    if token:
        headers['Authorization'] = 'Bearer ' + token
    request = urllib.request.Request(BASES[index] + path,
        data=json.dumps(body).encode() if body is not None else None, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.status, json.loads(response.read()), response.headers.get('X-Lab-Instance')
    except urllib.error.HTTPError as error:
        with error:
            return error.code, json.loads(error.read()), error.headers.get('X-Lab-Instance')

def check(name, condition, detail):
    if not condition:
        raise AssertionError(name + ': ' + json.dumps(detail))
    results.append({'check': name, 'passed': True, 'detail': detail})
    print(json.dumps(results[-1]), flush=True)

def session():
    status, body, _ = call(0, '/api/session', body={})
    if status != 200:
        raise AssertionError('Session fixture issuance failed')
    return body['token']

parser = argparse.ArgumentParser()
parser.add_argument('--outage', action='store_true')
args = parser.parse_args()
for _ in range(30):
    try:
        if all(call(i, '/health')[0] == 200 for i in range(2)):
            break
    except (OSError, urllib.error.URLError):
        time.sleep(1)
else:
    raise SystemExit('Application instances are not healthy.')

token = session()
start = time.monotonic()
with ThreadPoolExecutor(max_workers=32) as pool:
    responses = list(pool.map(lambda i: call(i % 2, '/api/catalog', token), range(40)))
duration = time.monotonic() - start
allowed = sum(response[0] == 200 for response in responses)
limit = 12 + math.ceil(2 * duration)
check('shared allowance across two instances', 0 < allowed <= limit and allowed < 24,
    {'requests': 40, 'allowed': allowed, 'rejected': 40-allowed, 'maximum_given_elapsed_time': limit,
     'duration_seconds': round(duration, 3), 'instances': sorted(set(response[2] for response in responses))})
check('no fallback during shared-state test', all(response[1]['mode'] == 'shared_redis' for response in responses), {'responses': 40})
second = session()
check('independent signed session gets own allowance', call(1, '/api/catalog', second)[0] == 200, {})
check('modified token rejected', call(0, '/api/catalog', token + '0')[0] == 401, {})
check('arbitrary account header grants no identity', call(0, '/api/cart', extra={'X-Account-ID': 'buyer-001'}, body={'product_id': 1, 'quantity': 1})[0] == 401, {})

product_token = session()
statuses = [call(i % 2, '/api/products/' + str(i + 1), product_token)[0] for i in range(16)]
check('product IDs share one route-class allowance', 429 in statuses, {'statuses': statuses})
search_token = session()
first = call(0, '/api/search?q=chairs&page_size=40', search_token)
second_search = call(1, '/api/search?q=chairs&page_size=10', search_token)
check('query cost consumes shared tokens', first[0] == 200 and first[1]['cost'] == 4 and second_search[0] == 429, {'first_cost': first[1].get('cost'), 'next_status': second_search[0]})
check('excessive query cost rejected', call(0, '/api/search?page_size=9999')[0] == 400, {})
check('health remains available', call(0, '/health')[0] == call(1, '/health')[0] == 200, {})

if args.outage:
    fallback_token = session()
    subprocess.run(['docker', 'compose', 'stop', 'redis'], cwd=ROOT, check=True, stdout=subprocess.DEVNULL)
    try:
        browsing = [call(0, '/api/catalog', fallback_token) for _ in range(4)]
        check('Redis outage gives bounded browsing fallback', [r[0] for r in browsing] == [200, 200, 429, 429] and browsing[0][1]['mode'] == 'local_bounded_fallback', {'statuses': [r[0] for r in browsing]})
        check('Redis outage rejects login', call(0, '/api/login', body={'account': 'buyer-001', 'password': 'invalid'})[0] == 503, {})
        check('Redis outage rejects cart', call(1, '/api/cart', fallback_token, body={'product_id': 1, 'quantity': 1})[0] == 503, {})
    finally:
        subprocess.run(['docker', 'compose', 'start', 'redis'], cwd=ROOT, check=True, stdout=subprocess.DEVNULL)

destination = ROOT / 'site/data/integration.json'
destination.write_text(json.dumps({'evidence_type': 'local_integration_verified', 'runtime': 'Docker, two Python instances, Redis 7.4',
    'outage_tested': args.outage, 'checks': results}, indent=2) + '\n')
print('Integration evidence written without credentials or tokens.')
