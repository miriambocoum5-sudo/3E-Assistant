# WhatsApp Setup - Quick Start

## 1-Minute Setup (Fastest Route)

### Get credentials:
1. Go to https://developers.facebook.com/apps → Create Business App
2. Add WhatsApp product → Copy **Access Token** and **Phone Number ID**
3. Create a verify token (any string): `my_test_token_123`

### Expose locally:
```powershell
# Download ngrok from https://ngrok.com/download
# Extract and run:
ngrok http 5000
# Copy the HTTPS URL (e.g., https://abc123def456.ngrok.io)
```

### Configure:
```powershell
# Copy and edit .env
copy .env.example .env
# Edit .env with your Meta credentials:
# - META_ACCESS_TOKEN=your_token
# - META_PHONE_NUMBER_ID=your_id
# - META_VERIFY_TOKEN=my_test_token_123
```

### Start:
```powershell
.\run_whatsapp_webhook.ps1
# Or: & .\.venv\Scripts\python.exe whatsapp_webhook.py
```

### Connect to Meta:
1. Go to your WhatsApp settings in Meta
2. Webhook → Edit
3. Callback URL: `https://your-ngrok-url/webhook`
4. Verify Token: `my_test_token_123`
5. Click "Verify and Save"
6. Subscribe to `messages` event

### Test:
Send a message to your test phone number → Bot should reply!

---

## What Happens When You Send a Message

```
You (WhatsApp)
    ↓
Meta Cloud API
    ↓
POST https://your-url/webhook
    ↓
whatsapp_webhook.py (receives message)
    ↓
app_new.py (generates_answer)
    ↓
Ollama (local LLM - http://localhost:11434)
    ↓
Response text
    ↓
Meta Cloud API (sends reply)
    ↓
You (receive message)
```

**Everything stays local** — only the message path goes through Meta.

---

## Environment Variables Reference

```env
PORT=5000                           # Flask port
CHATBOT_DISABLE_UI=1                # Don't start Streamlit UI

# Meta WhatsApp Cloud API
META_GRAPH_API_VERSION=v25.0        # Don't change this
META_ACCESS_TOKEN=xxx               # From Meta > WhatsApp > API Setup
META_PHONE_NUMBER_ID=xxx            # From Meta > WhatsApp > API Setup
META_VERIFY_TOKEN=xxx               # You create this (any string)
WHATSAPP_TEST_RECIPIENT=15551563262  # Must be allowed in your test recipient list

# Local model
OLLAMA_URL=http://localhost:11434   # Where Ollama runs
```

---

## Troubleshooting Quick Fixes

| Issue | Fix |
|-------|-----|
| "Webhook verification failed" | Check verify token matches in `.env` and Meta |
| `recipient_not_allowed` or `(#131030)` | Add the phone number to Meta's allowed recipient list or switch the app from development to live mode |
| Bot doesn't respond | Check Ollama is running (`ollama serve`) |
| 404 on webhook URL | Check ngrok is running and URL is correct |
| Messages delayed | Ollama might be processing slowly |
| Permission denied (PowerShell) | Run: `Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser` |

---

## Files You Edited

- `.env` — Your Meta credentials (DO NOT commit to git)
- `run_whatsapp_webhook.ps1` — Windows starter script
- `whatsapp_webhook.py` — Flask webhook (handles Meta requests)

---

## Next: Going to Production

Once everything works locally:

1. Deploy to Heroku / Railway / AWS
2. Use production URL instead of ngrok URL
3. Update Meta webhook URL to production URL
4. Make sure Ollama is also accessible from production (or use a remote LLM)

See `WHATSAPP_SETUP.md` for detailed production deployment steps.
