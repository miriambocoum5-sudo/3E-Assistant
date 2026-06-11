# Website RAG Chatbot

This project is a simple Retrieval-Augmented Generation (RAG) chatbot that answers questions using content from your website, with dynamic corpus refresh support and a WhatsApp webhook.

## Project Structure

- `app_new.py` — Streamlit chat app for Q&A
- `whatsapp_webhook.py` — Flask webhook that answers incoming WhatsApp messages
- `ingest_new.py` — Script to fetch, clean, and chunk website text
- `urls.txt` — List of website URLs to ingest
- `data.json` — Output of ingested website chunks
- `embeddings.npy` — Cached embeddings for the website chunks
- `knowledge_base.json` — FAQ-style knowledge base

## Setup

1. Install dependencies:
   ```
   pip install -r requirements.txt
   ```
2. Add your website URLs to `urls.txt` (one per line).
3. Run the ingestion script:
   ```
   python ingest_new.py
   ```
4. Start the chatbot app:
   ```
   streamlit run app_new.py
   ```

## Dynamic Data

- Update `urls.txt` when the website sources change.
- Re-run `python ingest_new.py` to rebuild `data.json` and `embeddings.npy`.
- In the Streamlit app, use the sidebar button to refresh the cached corpus after updating the files.

## WhatsApp

The chatbot can receive and respond to WhatsApp messages via Meta Cloud API. 

**To get started**, see [WHATSAPP_QUICKSTART.md](WHATSAPP_QUICKSTART.md) for a 5-minute setup.

For detailed setup including production deployment, see [WHATSAPP_SETUP.md](WHATSAPP_SETUP.md).

Quick summary:
- Install dependencies and copy `.env.example` to `.env` with your Meta credentials
- Run `.\run_whatsapp_webhook.ps1` (Windows) or `& .\.venv\Scripts\python.exe whatsapp_webhook.py`
- Expose publicly with ngrok (local testing) or deploy to Heroku/Railway/AWS (production)
- Configure webhook URL and verify token in Meta's WhatsApp settings
- The bot stays local using Ollama at `http://localhost:11434`

## Notes
- API keys (for LLMs) should be set as environment variables, not in code.
- The current search is simple; swap in a vector DB and LLM for production.
