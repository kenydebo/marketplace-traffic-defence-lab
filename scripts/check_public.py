"""Fail CI before credentials, raw logs or local state enter the public source."""
from pathlib import Path
import os
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
result = subprocess.run(['git', 'ls-files', '-z'], cwd=ROOT, capture_output=True)
files = [ROOT/p.decode() for p in result.stdout.split(b'\0') if p] if result.returncode == 0 else [
    p for p in ROOT.rglob('*') if p.is_file() and not any(part in ('.local', '.env', '__pycache__', '.git') for part in p.relative_to(ROOT).parts)]
failures = []
known_secrets = [os.environ[name].encode() for name in ('AWS_ACCESS_KEY_ID', 'AWS_SECRET_ACCESS_KEY', 'AWS_SESSION_TOKEN')
    if os.environ.get(name)]
for p in files:
    relative = p.relative_to(ROOT)
    if any(part in ('.env', '.local', '.aws', 'raw-logs') for part in relative.parts) or p.name.endswith(('.tfstate', '.tfvars')):
        failures.append(str(relative)+': private file')
        continue
    data = p.read_bytes()
    private_key_marker = b'-----BEGIN '+b'PRIVATE KEY-----'
    if re.search(rb'\b(?:AKIA|ASIA)[A-Z0-9]{16}\b', data) or private_key_marker in data or any(secret in data for secret in known_secrets):
        failures.append(str(relative)+': credential pattern')
if failures:
    raise SystemExit('\n'.join(failures))
print(f'Public-source credential and private-file checks passed for {len(files)} files.')
