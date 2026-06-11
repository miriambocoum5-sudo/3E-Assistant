import requests
import json
import time
import os
import sys
from pathlib import Path

recipient = os.environ.get("WHATSAPP_TEST_RECIPIENT", "")
if not recipient:
    env = Path('.env')
    if env.exists():
        for ln in env.read_text().splitlines():
            if ln.strip().startswith('WHATSAPP_TEST_RECIPIENT='):
                recipient = ln.split('=', 1)[1].strip().strip('"')
                break
if not recipient:
    recipient = "15551563262"
if len(sys.argv) > 1 and sys.argv[1].strip():
    recipient = sys.argv[1].strip()
recipient = "".join(ch for ch in recipient if ch.isdigit())

payload = {
    "entry": [
        {
            "changes": [
                {
                    "value": {
                        "messages": [
                            {
                                "id": f"test_msg_{int(time.time())}",
                                "from": recipient,
                                "timestamp": str(int(time.time())),
                                "text": {
                                    "body": "When are classes?"
                                }
                            }
                        ],
                        "contacts": [
                            {
                                "profile": {
                                    "name": "Test User"
                                }
                            }
                        ]
                    }
                }
            ]
        }
    ]
}

print("Sending test webhook payload...")
print(json.dumps(payload, indent=2))

response = requests.post("http://localhost:5000/webhook", json=payload)
print(f"\nResponse status: {response.status_code}")
print(f"Response body: {response.json()}")
