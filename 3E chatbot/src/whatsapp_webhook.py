import os
from xml.sax.saxutils import escape

import logging
import requests
from flask import Flask, Response, jsonify, request

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - optional convenience dependency
    load_dotenv = None

os.environ.setdefault("CHATBOT_DISABLE_UI", "1")

if load_dotenv is not None:
    load_dotenv(override=True)

from app import generate_answer  # noqa: E402


app = Flask(__name__)

# keep a short in-memory record of recent message ids and responses to avoid duplicate processing
from time import time
import json
from pathlib import Path

_recent_message_ids = {}
_RECENT_RESPONSES = {}  # (recipient, incoming_text) -> (answer, timestamp)
_RECENT_TTL = 1800  # 30 minutes - Meta retries webhooks up to 5 times with exponential backoff
_DEDUP_CACHE_FILE = Path(__file__).parent / '.webhook_dedup_cache.json'

def _load_dedup_cache():
    """Load persistent dedup cache from file to survive process restarts."""
    try:
        if _DEDUP_CACHE_FILE.exists():
            data = json.loads(_DEDUP_CACHE_FILE.read_text())
            now = time()
            # only load non-expired entries
            return {k: v for k, v in data.get('ids', {}).items() if now - v < _RECENT_TTL}
    except Exception as e:
        app.logger.warning("Failed to load dedup cache: %s", e)
    return {}

def _save_dedup_cache():
    """Persist dedup cache to survive process restarts."""
    try:
        _DEDUP_CACHE_FILE.write_text(json.dumps({'ids': _recent_message_ids}))
    except Exception as e:
        app.logger.warning("Failed to save dedup cache: %s", e)

# configure basic logging so incoming webhook payloads are visible in the terminal
logging.basicConfig(level=logging.INFO)

META_GRAPH_API_VERSION = os.environ.get("META_GRAPH_API_VERSION", "v25.0")
META_ACCESS_TOKEN = os.environ.get("META_ACCESS_TOKEN", "").strip()
META_PHONE_NUMBER_ID = os.environ.get("META_PHONE_NUMBER_ID", "").strip()
META_VERIFY_TOKEN = os.environ.get("META_VERIFY_TOKEN", "").strip()
WHATSAPP_TEST_RECIPIENT = os.environ.get("WHATSAPP_TEST_RECIPIENT", "").strip()


def twiml_message(text):
    safe_text = escape(text or "Sorry, I could not generate a response right now.")
    return f'<?xml version="1.0" encoding="UTF-8"?><Response><Message>{safe_text}</Message></Response>'


def extract_twilio_text():
    return request.form.get("Body", "").strip()


def extract_meta_message(payload):
    entries = payload.get("entry", [])
    for entry in entries:
        changes = entry.get("changes", [])
        for change in changes:
            value = change.get("value", {})
            messages = value.get("messages", [])
            contacts = value.get("contacts", [])
            if not messages:
                continue

            message = messages[0]
            # Extract message_id - be thorough since it's critical for dedup
            message_id = message.get("id") or message.get("message_id") or ""
            if not message_id:
                # Fallback: use timestamp + from if no explicit id
                message_id = f"{message.get('from', 'unknown')}_{message.get('timestamp', 'unknown')}"
            sender = message.get("from", "").strip()
            text = message.get("text", {}).get("body", "").strip()
            if not text:
                continue

            contact_name = ""
            if contacts:
                profile = contacts[0].get("profile", {})
                contact_name = profile.get("name", "").strip()

            return sender, text, contact_name, message_id

    return "", "", "", ""


def send_meta_message(recipient, text):
    if not (META_ACCESS_TOKEN and META_PHONE_NUMBER_ID):
        app.logger.error("Cannot send: missing token or phone number id")
        return {"ok": False, "error": {"message": "missing_meta_credentials"}}

    url = f"https://graph.facebook.com/{META_GRAPH_API_VERSION}/{META_PHONE_NUMBER_ID}/messages"
    headers = {"Authorization": f"Bearer {META_ACCESS_TOKEN}"}
    payload = {
        "messaging_product": "whatsapp",
        "to": recipient,
        "type": "text",
        "text": {"preview_url": False, "body": text},
    }
    try:
        app.logger.info("Sending message to %s: %s...", recipient, text[:50])
        response = requests.post(url, headers=headers, json=payload, timeout=30)
        response.raise_for_status()
        app.logger.info("Message sent successfully, response: %s", response.json())
        return {"ok": True, "error": None}
    except requests.RequestException as exc:
        app.logger.error("Failed to send Meta message to %s. Error: %s", recipient, str(exc))
        error_detail = None
        try:
            if 'response' in locals():
                error_detail = response.json()
                app.logger.error("Graph API response: %s", error_detail)
                meta_error = error_detail.get("error", {}) if isinstance(error_detail, dict) else {}
                if meta_error.get("code") == 131030:
                    app.logger.error(
                        "Meta blocked the recipient number %s. Add it to the WhatsApp allowed recipient list in Meta "
                        "or switch the app from development to live mode.",
                        recipient,
                    )
        except Exception:
            pass
        return {"ok": False, "error": error_detail}


def send_meta_message_with_fallback(recipient, text):
    result = send_meta_message(recipient, text)
    if result.get("ok"):
        return {"ok": True, "error": None, "recipient": recipient}

    error_detail = result.get("error") or {}
    error_code = None
    if isinstance(error_detail, dict):
        error_code = error_detail.get("error", {}).get("code")

    fallback_recipient = WHATSAPP_TEST_RECIPIENT if WHATSAPP_TEST_RECIPIENT and WHATSAPP_TEST_RECIPIENT != recipient else ""
    if error_code == 131030 and fallback_recipient:
        app.logger.info(
            "Retrying blocked recipient %s with test recipient %s",
            recipient,
            fallback_recipient,
        )
        fallback_result = send_meta_message(fallback_recipient, text)
        if fallback_result.get("ok"):
            return {
                "ok": True,
                "error": None,
                "recipient": fallback_recipient,
                "fallback_from": recipient,
            }
        return {
            "ok": False,
            "error": fallback_result.get("error") or error_detail,
            "recipient": fallback_recipient,
            "fallback_from": recipient,
        }

    return {"ok": False, "error": error_detail, "recipient": recipient}


@app.get("/")
def index():
    return {
        "status": "ok",
        "service": "3E chatbot WhatsApp webhook",
        "meta_enabled": bool(META_ACCESS_TOKEN and META_PHONE_NUMBER_ID),
    }


@app.get("/webhook")
def verify_webhook():
    mode = request.args.get("hub.mode", "")
    token = request.args.get("hub.verify_token", "")
    challenge = request.args.get("hub.challenge", "")

    if mode == "subscribe" and META_VERIFY_TOKEN and token == META_VERIFY_TOKEN:
        return Response(challenge, mimetype="text/plain")

    return Response("verification failed", status=403, mimetype="text/plain")


@app.post("/webhook")
def webhook():
    # load dedup cache at start of request in case of process restart
    global _recent_message_ids
    if not _recent_message_ids:
        _recent_message_ids = _load_dedup_cache()
    
    twilio_text = extract_twilio_text()
    if twilio_text:
        answer, _, _, _ = generate_answer(twilio_text)
        return Response(twiml_message(answer), mimetype="application/xml")

    # Save raw request body and headers for debugging (useful when web framework logs are not visible)
    try:
        raw = request.get_data(as_text=True)
        headers = {k: v for k, v in request.headers.items()}
        base = Path(__file__).parent
        (base / 'last_webhook_payload_raw.txt').write_text(raw)
        (base / 'last_webhook_headers.json').write_text(json.dumps(headers, indent=2))
    except Exception:
        app.logger.exception("Failed to write raw webhook payload or headers")

    payload = request.get_json(silent=True) or {}
    app.logger.info("Received /webhook POST: %s", payload)
    # Persist parsed payload for offline inspection when logs aren't visible
    try:
        _last_file = Path(__file__).parent / 'last_webhook_payload.json'
        _last_file.write_text(json.dumps(payload, indent=2))
    except Exception:
        app.logger.exception("Failed to write last payload file")
    recipient, incoming_text, contact_name, message_id = extract_meta_message(payload)
    app.logger.info("Extracted recipient=%s incoming_text=%s contact_name=%s message_id=%s", recipient, incoming_text, contact_name, message_id)
    if not incoming_text:
        return jsonify({"status": "ignored"})

    # deduplicate retries: check both message_id and content-based keys
    now = time()
    
    # purge expired entries
    for mid in list(_recent_message_ids.keys()):
        if now - _recent_message_ids[mid] > _RECENT_TTL:
            del _recent_message_ids[mid]
    for key in list(_RECENT_RESPONSES.keys()):
        if now - _RECENT_RESPONSES[key][1] > _RECENT_TTL:
            del _RECENT_RESPONSES[key]
    
    # save cache periodically
    _save_dedup_cache()

    # PRIMARY: check message id dedup (most reliable)
    if message_id:
        if message_id in _recent_message_ids:
            age = now - _recent_message_ids[message_id]
            app.logger.warning("DUPLICATE message_id=%s (age %.1fs) from %s — skipping", message_id, age, recipient)
            return jsonify({"status": "ignored_duplicate_messageid"})
        _recent_message_ids[message_id] = now
        app.logger.info("New message_id=%s cached", message_id)

    # SECONDARY: check response dedup by (recipient, text) key (catch Meta retries without id)
    # Allow the incoming message to be accepted (so the client can send duplicates),
    # but avoid sending a duplicate outgoing message if we've already replied recently.
    response_key = (recipient, incoming_text.lower())
    if response_key in _RECENT_RESPONSES:
        cached_answer, cache_time = _RECENT_RESPONSES[response_key]
        age = now - cache_time
        app.logger.warning("DUPLICATE content from %s: '%s' (age %.1fs, cached: '%s...') — accepted but not re-sending", recipient, incoming_text, age, cached_answer[:40])
        # Return 200 to indicate the incoming message was received, but do not send again.
        return jsonify({"status": "accepted_duplicate", "sent": False})
    
    app.logger.info("Processing new message from %s: '%s'", recipient, incoming_text)

    answer, top_score, top_item, context_items = generate_answer(incoming_text)
    app.logger.info("Generated answer for incoming_text=%s -> %s", incoming_text, answer)
    try:
        summary = [
            (
                row.get("source"),
                float(row.get("score", 0.0)),
                row["item"].get("question") if row.get("source") == "faq" else row["item"].get("title", ""),
            )
            for row in context_items
        ]
        app.logger.info("Context items: %s", summary)
    except Exception:
        app.logger.exception("Failed to summarize context items")

    # Allow forcing a local reply for debugging without sending via Meta Graph API
    if os.environ.get("FORCE_LOCAL_REPLY", "0") == "1":
        app.logger.info("FORCE_LOCAL_REPLY enabled — returning local TwiML response instead of sending via Meta")
        return Response(twiml_message(answer), mimetype="application/xml")

    if recipient and META_ACCESS_TOKEN and META_PHONE_NUMBER_ID:
        if contact_name:
            answer = f"Hi {contact_name}, {answer}"
        # cache this response for dedup and to avoid resending on retries
        try:
            response_key = (recipient, incoming_text.lower())
            _RECENT_RESPONSES[response_key] = (answer, time())
            _save_dedup_cache()
        except Exception:
            app.logger.exception("Error while caching response")
        send_result = send_meta_message_with_fallback(recipient, answer)
        if send_result.get("ok"):
            sent_recipient = send_result.get("recipient", recipient)
            app.logger.info("Message sent to %s, cached for dedup", sent_recipient)
        else:
            app.logger.error("Failed to send message to %s", recipient)
        error_code = None
        error_detail = send_result.get("error") or {}
        if isinstance(error_detail, dict):
            error_code = error_detail.get("error", {}).get("code")
            error_message = error_detail.get("error", {}).get("message", "")
        else:
            error_message = ""

        sent_recipient = send_result.get("recipient", recipient)
        fallback_from = send_result.get("fallback_from", "")

        if send_result.get("ok") and fallback_from:
            return jsonify({
                "status": "sent_to_test_recipient",
                "answer": answer,
                "recipient": sent_recipient,
                "fallback_from": fallback_from,
            })

        if error_code == 131030:
            # Include the generated answer in the response for easier local debugging
            return jsonify({
                "status": "error",
                "reason": "recipient_not_allowed",
                "answer": answer,
                "error_code": error_code,
                "error_message": error_message,
            })

        if send_result.get("ok"):
            return jsonify({"status": "sent", "answer": answer})

        return jsonify({
            "status": "error",
            "answer": answer,
            "error_code": error_code,
            "error_message": error_message,
        })

    return Response(twiml_message(answer), mimetype="application/xml")


@app.get("/health")
def health():
    return {"status": "healthy"}


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=False)