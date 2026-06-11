import requests
import json
import time
import sys

recipient = sys.argv[1] if len(sys.argv) > 1 else "15551563262"
text = sys.argv[2] if len(sys.argv) > 2 else "What classes do you offer?"
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
                                "text": {"body": text}
                            }
                        ],
                        "contacts": [
                            {"profile": {"name": "Test User"}}
                        ]
                    }
                }
            ]
        }
    ]
}

print('Posting payload to http://localhost:5000/webhook')
print(json.dumps(payload, indent=2))
resp = requests.post('http://localhost:5000/webhook', json=payload)
print('Status', resp.status_code)
try:
    print(resp.json())
except Exception:
    print(resp.text)
