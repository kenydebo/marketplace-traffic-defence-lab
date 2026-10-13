"""Create ignored demo-only secrets. Existing settings are preserved."""
import os
from pathlib import Path
import secrets
target = Path(__file__).resolve().parents[1] / '.env'
if target.exists():
    print('Existing .env preserved.')
else:
    descriptor = os.open(target, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(descriptor, 'w') as output:
        output.write('SESSION_SECRET=' + secrets.token_urlsafe(40) + '\n')
        output.write('DEMO_LOGIN_PASSWORD=' + secrets.token_urlsafe(24) + '\n')
    print('Created owner-only, ignored .env with random demo credentials.')
