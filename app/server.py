"""Synthetic marketplace API. No customer data, payment flow or production identity provider."""
import base64
import hashlib
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import ipaddress
import json
import math
import os
from pathlib import Path
import re
import socket
import time
from urllib.parse import parse_qs, urlsplit, quote
import uuid
import redis
from app.limiter import SharedLimiter, LocalFallback

SECRET = os.environ.get('SESSION_SECRET', '')
if len(SECRET) < 32:
    raise SystemExit('SESSION_SECRET must contain at least 32 characters.')
ORIGIN_TOKEN = os.environ.get('ORIGIN_TOKEN', '')
LOGIN_PASSWORD = os.environ.get('DEMO_LOGIN_PASSWORD', '')
INSTANCE = os.environ.get('INSTANCE_ID', socket.gethostname())
POLICIES = json.loads(Path(__file__).resolve().parents[1].joinpath('policies/endpoints.json').read_text())
redis_url = os.environ.get('REDIS_URL', 'redis://redis:6379/0')
if os.environ.get('REDIS_HOST'):
    redis_url = 'rediss://:' + quote(os.environ['REDIS_PASSWORD'], safe='') + '@' + os.environ['REDIS_HOST'] + ':6379/0'
LIMITER = SharedLimiter(redis_url)
FALLBACK = LocalFallback()

def pseudonym(value):
    return hmac.new(SECRET.encode(), value.encode(), hashlib.sha256).hexdigest()[:24]

def issue(kind, subject):
    payload = base64.urlsafe_b64encode(json.dumps({'kind': kind, 'sub': subject,
        'exp': int(time.time()) + 900}, separators=(',', ':')).encode()).decode().rstrip('=')
    signature = hmac.new(SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return payload + '.' + signature

def verify(token):
    try:
        payload, signature = token.split('.')
        expected = hmac.new(SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected):
            return None
        value = json.loads(base64.urlsafe_b64decode(payload + '=' * (-len(payload) % 4)))
        if value['exp'] <= time.time() or value['kind'] not in ('account', 'anonymous'):
            return None
        if not isinstance(value['sub'], str) or not 1 <= len(value['sub']) <= 64:
            return None
        return value
    except (ValueError, KeyError, TypeError):
        return None

def classify(path):
    if re.fullmatch(r'/api/products/[0-9]{1,6}', path):
        return 'products'
    return {'/api/catalog': 'catalog', '/api/search': 'search', '/api/login': 'login',
        '/api/cart': 'cart', '/api/session': 'session'}.get(path)

class Handler(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'

    def setup(self):
        super().setup()
        self.connection.settimeout(5)

    def log_message(self, *_):
        pass  # JSON events below exclude tokens, credentials, raw IPs and request bodies.

    def reply(self, status, body, retry=0):
        if hasattr(self, 'event_written') and not self.event_written and self.request_route != 'unknown':
            self.event(self.request_route, status, self.request_cost, self.request_mode, self.request_actor, self.request_start)
        data = json.dumps(body, separators=(',', ':')).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Content-Security-Policy', "default-src 'none'; frame-ancestors 'none'")
        self.send_header('X-Lab-Instance', INSTANCE)
        self.send_header('Connection', 'close')
        if retry:
            self.send_header('Retry-After', str(retry))
        self.end_headers()
        self.wfile.write(data)
        self.close_connection = True

    def do_GET(self):
        self.handle_request('GET')

    def do_POST(self):
        self.handle_request('POST')

    def handle_request(self, method):
        start = time.monotonic()
        parsed = urlsplit(self.path)
        self.request_start = start
        self.request_route = classify(parsed.path) or 'unknown'
        self.request_cost = 0
        self.request_actor = 'unattributed'
        self.request_mode = 'validation'
        self.request_resource = pseudonym(parsed.path) if self.request_route == 'products' else None
        self.event_written = False
        if parsed.path == '/health' and method == 'GET':
            return self.reply(200, {'ok': True, 'instance': INSTANCE})
        if ORIGIN_TOKEN and not hmac.compare_digest(self.headers.get('X-Lab-Origin-Token', ''), ORIGIN_TOKEN):
            return self.reply(403, {'error': 'origin_path_required'})
        route = classify(parsed.path)
        if not route:
            return self.reply(404, {'error': 'unknown_route'})
        expected = 'POST' if route in ('login', 'cart', 'session') else 'GET'
        if method != expected:
            return self.reply(405, {'error': 'method_not_allowed'})
        body = {}
        if method == 'POST':
            try:
                length = int(self.headers.get('Content-Length', '-1'))
                if not 0 <= length <= 4096 or self.headers.get('Transfer-Encoding'):
                    raise ValueError()
                body = json.loads(self.rfile.read(length) or b'{}')
                if not isinstance(body, dict):
                    raise ValueError()
            except (ValueError, TimeoutError):
                return self.reply(400, {'error': 'invalid_json_body'})
        token = self.headers.get('Authorization', '')
        principal = verify(token[7:]) if token.startswith('Bearer ') else None
        if token and not principal:
            return self.reply(401, {'error': 'invalid_session'})
        if route == 'cart' and not principal:
            return self.reply(401, {'error': 'session_required'})
        source = self.client_address[0]
        # Trust edge metadata only when the origin path has been authenticated.
        if ORIGIN_TOKEN:
            viewer = self.headers.get('CloudFront-Viewer-Address', '')
            try:
                source = str(ipaddress.ip_address(viewer.rsplit(':', 1)[0].strip('[]')))
            except ValueError:
                return self.reply(400, {'error': 'trusted_viewer_metadata_required'})
        actor = ('principal:' + principal['kind'] + ':' + principal['sub']) if principal else ('source:' + source)
        if route in ('login', 'session'):
            actor = 'source:' + source
        cost = 1
        if route == 'search':
            query = parse_qs(parsed.query)
            try:
                size = int(query.get('page_size', ['10'])[0])
                terms = query.get('q', [''])[0]
                if not 1 <= size <= 40 or len(terms) > 120:
                    raise ValueError()
                cost = max(1, math.ceil(size / 10))
            except ValueError:
                return self.reply(400, {'error': 'query_cost_out_of_bounds'})
        policy = POLICIES[route]
        key = route + ':' + pseudonym(actor)
        self.request_actor = key
        self.request_cost = cost
        mode = 'shared_redis'
        try:
            allowed, remaining, retry = LIMITER.take(key, policy['capacity'], policy['refill_per_second'], cost)
        except redis.RedisError:
            if policy['fallback'] == 'reject':
                self.event(route, 503, cost, 'dependency_unavailable', key, start)
                return self.reply(503, {'error': 'limiter_unavailable'}, 5)
            allowed, remaining, retry = FALLBACK.take(key)
            mode = 'local_bounded_fallback'
        if not allowed:
            self.event(route, 429, cost, mode, key, start)
            return self.reply(429, {'error': 'rate_limited', 'mode': mode, 'remaining': remaining}, max(1, retry))
        result = {'route': route, 'instance': INSTANCE, 'mode': mode, 'remaining': remaining, 'cost': cost}
        status = 200
        if route == 'session':
            result['token'] = issue('anonymous', uuid.uuid4().hex)
        elif route == 'login':
            if not LOGIN_PASSWORD or not hmac.compare_digest(str(body.get('password', '')), LOGIN_PASSWORD) or body.get('account') != 'buyer-001':
                status = 401
                result = {'error': 'authentication_failed'}
            else:
                result['token'] = issue('account', 'buyer-001')
        elif route == 'cart':
            if not re.fullmatch(r'[0-9]{1,6}', str(body.get('product_id', ''))) or type(body.get('quantity')) is not int or not 1 <= body['quantity'] <= 10:
                status = 400
                result = {'error': 'invalid_cart_item'}
            else:
                result['accepted'] = True  # Synthetic response; no payment or persistent customer cart.
        else:
            result['items'] = [{'id': i, 'name': 'Sample product ' + str(i)} for i in range(1, 4)]
        self.event(route, status, cost, mode, key, start)
        self.reply(status, result)

    def event(self, route, status, cost, mode, key, start):
        self.event_written = True
        trace = self.headers.get('X-Lab-Trace', '')
        if not re.fullmatch(r'[a-f0-9]{32}', trace):
            trace = uuid.uuid4().hex
        fingerprint = self.headers.get('CloudFront-Viewer-JA4-Fingerprint', '') if ORIGIN_TOKEN else ''
        if not re.fullmatch(r'[tq][a-zA-Z0-9]{9}_[a-f0-9]{12}_[a-f0-9]{12}', fingerprint):
            fingerprint = None
        print(json.dumps({'timestamp': time.time(), 'trace': trace, 'instance': INSTANCE,
            'route': route, 'status': status, 'cost': cost, 'limiter_mode': mode,
            'actor_pseudonym': key.split(':')[-1], 'resource_pseudonym': self.request_resource,
            'ja4': fingerprint, 'latency_ms': round((time.monotonic()-start)*1000, 2)}), flush=True)

if __name__ == '__main__':
    class Server(ThreadingHTTPServer):
        request_queue_size = 128
    Server(('0.0.0.0', int(os.environ.get('PORT', '8080'))), Handler).serve_forever()
