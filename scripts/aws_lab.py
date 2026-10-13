"""Manual, disposable AWS lab lifecycle. Uses environment credentials; never prints secrets.

Only this run's two CloudFormation stacks can be removed. State is owner-only,
ignored locally and never uploaded. Public evidence is explicit allowlisted JSON.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import datetime
import ipaddress
import json
import os
from pathlib import Path
import re
import subprocess
import time
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT/'.local/aws-run.json'
AWS = os.environ.get('AWS_CLI', 'aws')

def aws(*args, parse=True):
    result = subprocess.run([AWS, *args, '--output', 'json'], capture_output=True, text=True)
    if result.returncode:
        # AWS errors can include resource IDs. Keep them private, report operation and error class only.
        private = ROOT/'.local/aws-error.txt'
        private.parent.mkdir(exist_ok=True, mode=0o700)
        private.write_text(result.stderr)
        private.chmod(0o600)
        code = re.search(r'\(([^)]+)\)', result.stderr)
        raise RuntimeError(f'AWS {args[0]} {args[1]} failed: {code.group(1) if code else "see ignored .local/aws-error.txt"}')
    return json.loads(result.stdout) if parse and result.stdout.strip() else result.stdout

def save(state):
    STATE.parent.mkdir(exist_ok=True, mode=0o700)
    STATE.parent.chmod(0o700)
    STATE.write_text(json.dumps(state, indent=2)+'\n')
    STATE.chmod(0o600)

def load(): return json.loads(STATE.read_text())

def prepare():
    expected = os.environ.get('AWS_EXPECTED_ACCOUNT_ID', '')
    if not re.fullmatch(r'[0-9]{12}', expected):
        raise RuntimeError('Set AWS_EXPECTED_ACCOUNT_ID to the authorized disposable lab account.')
    if os.environ.get('AWS_DEFAULT_REGION', os.environ.get('AWS_REGION', 'us-east-1')) != 'us-east-1':
        raise RuntimeError('This CloudFront lab supports us-east-1 only.')
    if aws('sts', 'get-caller-identity')['Account'] != expected:
        raise RuntimeError('AWS identity differs from the explicitly configured disposable account.')
    run_id = os.environ.get('GITHUB_RUN_ID', str(int(time.time())))
    if not re.fullmatch(r'[0-9]{1,20}', run_id):
        raise RuntimeError('Invalid numeric run ID')
    if STATE.exists() and not load().get('cleanup_verified'):
        raise RuntimeError('Previous run needs cleanup; refusing to lose its resource inventory.')
    with urllib.request.urlopen('https://checkip.amazonaws.com', timeout=10) as response:
        source = str(ipaddress.IPv4Address(response.read(64).decode().strip()))+'/32'
    zones = aws('ec2', 'describe-availability-zones')['AvailabilityZones']
    zones = [z['ZoneName'] for z in zones if z['State'] == 'available' and z['ZoneId'] != 'use1-az3']
    if len(zones) < 2:
        raise RuntimeError('Two supported availability zones are required')
    lists = aws('ec2', 'describe-managed-prefix-lists', '--filters', 'Name=prefix-list-name,Values=com.amazonaws.global.cloudfront.origin-facing')['PrefixLists']
    if not lists:
        raise RuntimeError('CloudFront managed prefix list unavailable')
    save({'account': expected, 'stack': 'marketplace-traffic-lab-'+run_id, 'bootstrap': 'marketplace-traffic-image-'+run_id,
        'source': source, 'zones': zones[:2], 'prefix': lists[0]['PrefixListId'], 'started': time.time(), 'created': []})
    (ROOT/'site/data/aws.json').write_text(json.dumps({'evidence_type': 'aws_deployment_in_progress', 'checks': [],
        'started_at': datetime.datetime.now(datetime.timezone.utc).isoformat(), 'cleanup_verified': False}, indent=2)+'\n')
    print('Authorized lab identity verified. Network settings saved privately.', flush=True)

def output(stack):
    value = aws('cloudformation', 'describe-stacks', '--stack-name', stack)['Stacks'][0]
    return {item['OutputKey']: item['OutputValue'] for item in value.get('Outputs', [])}

def deploy_file(stack, file, parameters=None):
    aws('cloudformation', 'validate-template', '--template-body', 'file://'+str(ROOT/file))
    args = ['cloudformation', 'deploy', '--stack-name', stack, '--template-file', str(ROOT/file),
        '--capabilities', 'CAPABILITY_IAM', '--tags', 'Project=marketplace-traffic-defence-lab', '--no-fail-on-empty-changeset']
    if parameters:
        args += ['--parameter-overrides', *[k+'='+v for k, v in parameters.items()]]
    aws(*args, parse=False)

def bootstrap():
    state = load()
    state['created'].append(state['bootstrap'])
    save(state)  # Inventory before mutation, including failed partial creation.
    print('Creating disposable image repository.', flush=True)
    deploy_file(state['bootstrap'], 'infra/bootstrap.json')
    state['repository'] = output(state['bootstrap'])['RepositoryUri']
    save(state)
    registry = state['repository'].split('/')[0]
    password = aws('ecr', 'get-login-password', parse=False).strip()
    subprocess.run(['docker', 'login', '--username', 'AWS', '--password-stdin', registry], input=password,
        text=True, check=True, stdout=subprocess.DEVNULL)
    tag = 'run-'+state['stack'].rsplit('-', 1)[-1]
    image = state['repository']+':'+tag
    try:
        subprocess.run(['docker', 'build', '--platform', 'linux/amd64', '-t', image, '.'], cwd=ROOT, check=True)
        subprocess.run(['docker', 'push', image], check=True)
    finally:
        subprocess.run(['docker', 'logout', registry], stdout=subprocess.DEVNULL, check=False)
    detail = aws('ecr', 'describe-images', '--repository-name', state['repository'].split('/', 1)[1],
        '--image-ids', 'imageTag='+tag)['imageDetails'][0]
    state['image'] = state['repository']+'@'+detail['imageDigest']
    state['parameters'] = {'ImageUri': state['image'], 'SourceCidr': state['source'], 'AvailabilityZoneA': state['zones'][0],
        'AvailabilityZoneB': state['zones'][1], 'CloudFrontPrefixList': state['prefix'], 'ProbeMode': 'Count'}
    save(state)
    print('Immutable application image uploaded.', flush=True)

def deploy():
    state = load()
    state['created'].append(state['stack'])
    save(state)
    print('Creating CloudFront/WAF, private ALB, two tasks and encrypted Redis. Provisioning may take 15–25 minutes.', flush=True)
    deploy_file(state['stack'], 'infra/lab.json', state['parameters'])
    state['outputs'] = output(state['stack'])
    save(state)
    print('AWS stack deployment completed. Endpoint saved privately.', flush=True)

def call(base, path, token=None, body=None, agent='marketplace-lab-validation'):
    headers = {'Content-Type': 'application/json', 'User-Agent': agent}
    if token:
        headers['Authorization'] = 'Bearer '+token
    request = urllib.request.Request(base+path, headers=headers, data=json.dumps(body).encode() if body is not None else None)
    try:
        response = urllib.request.urlopen(request, timeout=15)
    except urllib.error.HTTPError as error:
        response = error
    with response:
        data = response.read(16384)
        try: value = json.loads(data)
        except ValueError: value = {}
        return response.status, value, response.headers.get('X-Lab-Instance')

def test():
    state = load()
    base = state['outputs']['Endpoint']
    checks = []
    def check(name, condition, detail=None):
        checks.append({'check': name, 'passed': bool(condition), 'detail': detail or {}})
        (ROOT/'site/data/aws.json').write_text(json.dumps({'evidence_type': 'aws_live_verified',
            'tested_at': datetime.datetime.now(datetime.timezone.utc).isoformat(), 'checks': checks,
            'cleanup_verified': False, 'architecture': 'CloudFront/WAF → private ALB → two Fargate tasks → encrypted Redis'}, indent=2)+'\n')
        print(name+': '+('PASS' if condition else 'FAIL'), flush=True)
        if not condition:
            raise AssertionError(name)
    for attempt in range(20):
        try:
            if call(base, '/health')[0] == 200: break
        except OSError: pass
        time.sleep(3)
    check('normal edge request', call(base, '/api/catalog')[0] == 200)
    check('synthetic WAF marker blocked', call(base, '/api/catalog', agent='lab-block-me')[0] == 403)
    status, session, _ = call(base, '/api/session', body={})
    check('anonymous signed session issued', status == 200)
    token = session['token']
    start = time.monotonic()
    with ThreadPoolExecutor(max_workers=32) as pool:
        replies = list(pool.map(lambda _: call(base, '/api/catalog', token), range(40)))
    elapsed = time.monotonic()-start
    allowed = sum(r[0] == 200 for r in replies)
    maximum = 12+int(2*elapsed)+1
    instances = len(set(r[2] for r in replies if r[2]))
    check('shared Redis allowance in AWS', 0 < allowed <= maximum and any(r[0] == 429 for r in replies)
        and all(r[1].get('mode') == 'shared_redis' for r in replies),
        {'requests': 40, 'allowed': allowed, 'rate_limited': sum(r[0] == 429 for r in replies),
         'elapsed_seconds': round(elapsed, 3), 'maximum_given_elapsed_time': maximum, 'application_instances_seen': instances})
    check('both application instances observed', instances == 2)
    check('tampered session rejected', call(base, '/api/catalog', token+'0')[0] == 401)
    secret_value = aws('secretsmanager', 'get-secret-value', '--secret-id', state['outputs']['LoginSecretArn'])
    password = json.loads(secret_value['SecretString'])['token']
    login_status, login, _ = call(base, '/api/login', body={'account': 'buyer-001', 'password': password})
    check('fixture account authenticates', login_status == 200)
    check('signed account can submit synthetic cart', call(base, '/api/cart', login['token'], body={'product_id': 1, 'quantity': 1})[0] == 200)
    check('unsigned cart request rejected', call(base, '/api/cart', body={'product_id': 1, 'quantity': 1})[0] == 401)
    check('health remains available', call(base, '/health')[0] == 200)
    # Only the separate synthetic probe moves to Block; recommended policies stay Count.
    parameters = dict(state['parameters'], ProbeMode='Block')
    print('Testing a separate scoped WAF enforcement probe; recommendation rules remain in Count.', flush=True)
    try:
        deploy_file(state['stack'], 'infra/lab.json', parameters)
        statuses = []
        for _ in range(24):
            statuses.extend(call(base, '/api/catalog', agent='lab-rate-probe')[0] for _ in range(5))
            if 403 in statuses: break
            time.sleep(2)
        check('scoped WAF rate enforcement', 403 in statuses,
            {'requests': len(statuses), 'waf_block_responses': statuses.count(403), 'maximum_probe_requests': 120})
        check('WAF catalog probe preserves health', call(base, '/health')[0] == 200)
    finally:
        deploy_file(state['stack'], 'infra/lab.json', state['parameters'])
    check('WAF probe rollback to Count', call(base, '/api/catalog', token)[0] == 200)
    endpoint_test()
    # Allow asynchronous CloudWatch delivery; collect with a later command as needed.

def endpoint_test():
    state = load()
    base = state['outputs']['Endpoint']
    destination = ROOT/'site/data/aws.json'
    report = json.loads(destination.read_text())
    def check(name, condition, detail=None):
        report['checks'].append({'check': name, 'passed': bool(condition), 'detail': detail or {}})
        destination.write_text(json.dumps(report, indent=2)+'\n')
        print(name+': '+('PASS' if condition else 'FAIL'), flush=True)
        if not condition: raise AssertionError(name)
    _, session, _ = call(base, '/api/session', body={})
    token = session['token']
    with ThreadPoolExecutor(max_workers=16) as pool:
        products = list(pool.map(lambda i: call(base, '/api/products/'+str(i+1), token), range(16)))
    check('AWS product ID rotation shares route allowance', any(r[0] == 429 for r in products)
        and all(r[0] in (200, 429) for r in products),
        {'requests': 16, 'allowed': sum(r[0] == 200 for r in products), 'rate_limited': sum(r[0] == 429 for r in products)})
    _, session, _ = call(base, '/api/session', body={})
    with ThreadPoolExecutor(max_workers=2) as pool:
        searches = list(pool.map(lambda _: call(base, '/api/search?q=chairs&page_size=40', session['token']), range(2)))
    check('AWS expensive queries consume shared cost budget', sorted(r[0] for r in searches) == [200, 429]
        and all(r[1].get('cost') == 4 for r in searches if r[0] == 200), {'statuses': sorted(r[0] for r in searches), 'cost_per_query': 4})
    check('AWS excessive query cost rejected', call(base, '/api/search?page_size=9999')[0] == 400)
    resources = aws('cloudformation', 'describe-stack-resources', '--stack-name', state['stack'])['StackResources']
    alb = next(r['PhysicalResourceId'] for r in resources if r['LogicalResourceId'] == 'Alb')
    record = aws('elbv2', 'describe-load-balancers', '--load-balancer-arns', alb)['LoadBalancers'][0]
    check('AWS origin load balancer is internal', record['Scheme'] == 'internal' and record['State']['Code'] == 'active')

def collect():
    state = load()
    report_path = ROOT/'site/data/aws.json'
    report = json.loads(report_path.read_text()) if report_path.exists() else {'evidence_type': 'aws_deployment_only', 'checks': []}
    start = int(state['started']*1000)
    aggregates = {'app': {}, 'waf': {}, 'fingerprints': {}, 'endpoint_patterns': {},
        'live_recommendation_status': 'insufficient_evidence_unlabelled_live_traffic'}
    actors = {}
    resources = {}
    for kind, name in [('app', 'AppLogGroup'), ('waf', 'WafLogGroup')]:
        response = aws('logs', 'filter-log-events', '--log-group-name', state['outputs'][name], '--start-time', str(start), '--limit', '10000')
        for event in response.get('events', []):
            try: e = json.loads(event['message'])
            except ValueError: continue
            if kind == 'app':
                route = e.get('route', 'unknown')
                key = route+' / '+str(e.get('status'))+' / '+e.get('limiter_mode', '')
                aggregates['app'][key] = aggregates['app'].get(key, 0)+1
                pattern = aggregates['endpoint_patterns'].setdefault(route, {'requests': 0, 'cost_units': 0, 'authentication_failures': 0})
                pattern['requests'] += 1
                pattern['cost_units'] += e.get('cost', 0)
                pattern['authentication_failures'] += int(route == 'login' and e.get('status') == 401)
                actors.setdefault(route, set()).add(e.get('actor_pseudonym'))
                if e.get('resource_pseudonym'):
                    resources.setdefault(route, set()).add(e['resource_pseudonym'])
            else:
                key = e.get('terminatingRuleId', 'unknown')+' / '+e.get('action', 'unknown')
                aggregates['waf'][key] = aggregates['waf'].get(key, 0)+1
                fp = e.get('ja4Fingerprint')
                if fp and re.fullmatch(r'[tq][a-zA-Z0-9]{9}_[a-f0-9]{12}_[a-f0-9]{12}', fp):
                    aggregates['fingerprints'][fp] = aggregates['fingerprints'].get(fp, 0)+1
    for route, pattern in aggregates['endpoint_patterns'].items():
        pattern['distinct_actor_pseudonyms'] = len(actors.get(route, set()) - {None, 'unattributed'})
        pattern['distinct_resource_pseudonyms'] = len(resources.get(route, set()))
    report['live_aggregates'] = aggregates
    report['waf_rate_block_attribution_verified'] = aggregates['waf'].get('EnforcementProbe / BLOCK', 0) > 0
    name, ident = state['outputs']['WafArn'].split('/')[-2:]
    rules = aws('wafv2', 'get-web-acl', '--scope', 'CLOUDFRONT', '--name', name, '--id', ident)['WebACL']['Rules']
    observed = [{'name': r['Name'], 'action': next(iter(r['Action'])),
        'limit': r['Statement'].get('RateBasedStatement', {}).get('Limit')} for r in rules
        if r['Name'].endswith('Observe') or r['Name'] == 'EnforcementProbe']
    proposals = json.loads((ROOT/'site/data/recommendations.json').read_text())['proposals']
    expected = {p['route'].title()+'Observe' for p in proposals if p['decision'] == 'propose_observation'}
    actual = {r['name'] for r in observed if r['name'] not in ('JA4Observe', 'EnforcementProbe')}
    names = {r['name'] for r in observed}
    expected_limits = {p['route'].title()+'Observe': p['edge_proposal']['limit'] for p in proposals if p['decision'] == 'propose_observation'}
    expected_limits.update({'JA4Observe': 30, 'EnforcementProbe': 10})
    verified = actual == expected and {'JA4Observe', 'EnforcementProbe'}.issubset(names) and all(
        r['action'] == 'Count' and r['limit'] == expected_limits.get(r['name']) for r in observed)
    report['deployed_edge_rules'] = observed
    report['recommendation_dataset_sha256'] = json.loads((ROOT/'site/data/recommendations.json').read_text())['dataset_sha256']
    check_name = 'eligible recommendations and JA4 remain Count; withheld login absent'
    report['checks'] = [c for c in report['checks'] if c['check'] != check_name] + [
        {'check': check_name, 'passed': verified, 'detail': {'eligible_endpoint_policies': len(expected), 'observed_count_rules': len(observed)}}]
    report['log_snapshot_note'] = 'Asynchronous log delivery can make this bounded snapshot incomplete; it is not a full traffic denominator.'
    report['logs_collected_at'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    report_path.write_text(json.dumps(report, indent=2)+'\n')
    print('Sanitized live log aggregates collected; no raw IPs, tokens or account IDs published.', flush=True)
    if not verified:
        raise AssertionError('Deployed edge policies differ from eligible Count proposals')

def cleanup():
    if not STATE.exists():
        print('No run inventory; no resources touched.', flush=True)
        return
    state = load()
    if state.get('account') and aws('sts', 'get-caller-identity')['Account'] != state['account']:
        raise RuntimeError('Cleanup credentials belong to a different account; no deletion attempted')
    for stack in reversed(list(dict.fromkeys(state['created']))):
        if not re.fullmatch(r'marketplace-traffic-(lab|image)-[0-9]{1,20}', stack):
            raise RuntimeError('Refusing to delete an unrecognized stack')
        try:
            record = aws('cloudformation', 'describe-stacks', '--stack-name', stack)['Stacks'][0]
        except RuntimeError:
            error = (ROOT/'.local/aws-error.txt').read_text()
            if 'does not exist' in error: continue
            raise
        if not any(t['Key'] == 'Project' and t['Value'] == 'marketplace-traffic-defence-lab' for t in record.get('Tags', [])):
            raise RuntimeError('Refusing deletion: project ownership tag missing')
        print('Deleting this run’s '+('application stack' if '-lab-' in stack else 'image repository')+'.', flush=True)
        aws('cloudformation', 'delete-stack', '--stack-name', stack)
        aws('cloudformation', 'wait', 'stack-delete-complete', '--stack-name', stack, parse=False)
        try:
            aws('cloudformation', 'describe-stacks', '--stack-name', stack)
        except RuntimeError:
            if 'does not exist' not in (ROOT/'.local/aws-error.txt').read_text(): raise
        else:
            raise RuntimeError('Stack is still present after deletion waiter')
    state['cleanup_verified'] = True
    save(state)
    report_path = ROOT/'site/data/aws.json'
    report = json.loads(report_path.read_text()) if report_path.exists() else {'evidence_type': 'aws_attempt', 'checks': []}
    report['cleanup_verified'] = True
    report['cleanup_verified_at'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    report_path.write_text(json.dumps(report, indent=2)+'\n')
    print('Both owned stacks are absent. Cleanup verified.', flush=True)

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['prepare', 'bootstrap', 'deploy', 'test', 'endpoint-test', 'collect', 'cleanup', 'run'])
    action = parser.parse_args().action
    if action == 'run':
        prepare()
        try:
            bootstrap(); deploy(); test(); collect()
        finally:
            cleanup()
    else:
        try:
            globals()[action.replace('-', '_')]()
        except Exception:
            if action in ('bootstrap', 'deploy', 'test'):
                destination = ROOT/'site/data/aws.json'
                report = json.loads(destination.read_text()) if destination.exists() else {'checks': []}
                report['evidence_type'] = 'aws_live_partial' if report.get('checks') else 'aws_attempt'
                report['failure_summary'] = action+' did not complete. Review individual checks and the private/workflow diagnostics.'
                report['cleanup_verified'] = False
                destination.write_text(json.dumps(report, indent=2)+'\n')
            raise
