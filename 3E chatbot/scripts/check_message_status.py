import os
import json
import requests
from pathlib import Path

CACHE = Path('.webhook_dedup_cache.json')
TOKEN = os.environ.get('META_ACCESS_TOKEN')
API_VERSION = os.environ.get('META_GRAPH_API_VERSION','v25.0')

if not TOKEN:
    # try loading from .env
    env_path = Path('.env')
    if env_path.exists():
        for ln in env_path.read_text().splitlines():
            if ln.strip().startswith('META_ACCESS_TOKEN='):
                TOKEN = ln.split('=',1)[1].strip().strip('"')
            if ln.strip().startswith('META_GRAPH_API_VERSION='):
                API_VERSION = ln.split('=',1)[1].strip().strip('"')

if not TOKEN:
    print('META_ACCESS_TOKEN not found in environment or .env')
    raise SystemExit(1)

if not CACHE.exists():
    print('No dedup cache found at', CACHE)
    raise SystemExit(1)

data = json.loads(CACHE.read_text())
ids = data.get('ids', {})
# find keys that look like wa message ids (start with 'wamid.')
wamids = [(k,v) for k,v in ids.items() if k.startswith('wamid')]
if not wamids:
    print('No wa message ids found in cache. Keys:', list(ids.keys())[:10])
    raise SystemExit(1)

# pick latest by timestamp
wamid, ts = max(wamids, key=lambda kv: kv[1])
print('Checking status for', wamid, 'timestamp', ts)

url = f'https://graph.facebook.com/{API_VERSION}/{wamid}'
params = {'access_token': TOKEN, 'fields': 'id,status,recipient_id,created_time'}
resp = requests.get(url, params=params)
print('HTTP', resp.status_code)
try:
    print(json.dumps(resp.json(), indent=2))
except Exception:
    print(resp.text)
