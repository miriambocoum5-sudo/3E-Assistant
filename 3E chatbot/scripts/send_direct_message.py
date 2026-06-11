import os
import requests
from pathlib import Path

TOKEN = os.environ.get('META_ACCESS_TOKEN')
API_VERSION = os.environ.get('META_GRAPH_API_VERSION','v25.0')
PHONE_ID = os.environ.get('META_PHONE_NUMBER_ID')
RECIPIENT = os.environ.get('WHATSAPP_TEST_RECIPIENT') or os.environ.get('TEST_RECIPIENT') or '221784575909'

# fallback to .env
if not TOKEN or not PHONE_ID:
    env = Path('.env')
    if env.exists():
        for ln in env.read_text().splitlines():
            if ln.strip().startswith('META_ACCESS_TOKEN=') and not TOKEN:
                TOKEN = ln.split('=',1)[1].strip().strip('"')
            if ln.strip().startswith('META_PHONE_NUMBER_ID=') and not PHONE_ID:
                PHONE_ID = ln.split('=',1)[1].strip().strip('"')
            if ln.strip().startswith('WHATSAPP_TEST_RECIPIENT=') and RECIPIENT == '221784575909':
                RECIPIENT = ln.split('=',1)[1].strip().strip('"')

if not TOKEN or not PHONE_ID:
    print('META_ACCESS_TOKEN or META_PHONE_NUMBER_ID not set in env or .env')
    raise SystemExit(1)

url = f'https://graph.facebook.com/{API_VERSION}/{PHONE_ID}/messages'
headers = {'Authorization': f'Bearer {TOKEN}'}
nonce = str(int(__import__('time').time()))[-6:]
body = f'BOT TEST — please look for this message. nonce={nonce}'
payload = {
    'messaging_product': 'whatsapp',
    'to': RECIPIENT,
    'type': 'text',
    'text': {'preview_url': False, 'body': body}
}
print('Sending to', RECIPIENT, 'body=', body)
resp = requests.post(url, headers=headers, json=payload, timeout=30)
print('HTTP', resp.status_code)
try:
    print(resp.json())
except Exception:
    print(resp.text)
