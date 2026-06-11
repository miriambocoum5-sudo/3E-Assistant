# 3E Chatbot — RAG WhatsApp Bot

A Retrieval-Augmented Generation (RAG) chatbot that answers questions from website content via Streamlit or WhatsApp.

## 📁 Project Structure

```
├── src/                           # Source code
│   ├── app.py                     # Streamlit chat UI
│   ├── ingest.py                  # Website data ingestion
│   └── whatsapp_webhook.py        # WhatsApp integration (Flask)
├── scripts/                       # Utility scripts
│   ├── eval_knowledge_base.py
│   ├── send_direct_message.py
│   ├── check_message_status.py
│   ├── test_webhook.py
│   ├── simulate_incoming.py
│   └── *.ps1                      # Legacy utility scripts
├── run_whatsapp_webhook.ps1       # Windows webhook launcher
├── start_whatsapp.ps1             # Windows webhook + ngrok launcher
├── data/                          # Data files
│   ├── data.json                  # Ingested chunks
│   ├── embeddings.npy             # Cached embeddings
│   └── knowledge_base.json        # FAQ database
├── docs/                          # Documentation
│   ├── README.md                  # Detailed guide
│   ├── WHATSAPP_QUICKSTART.md     # 5-min WhatsApp setup
│   └── WHATSAPP_SETUP.md          # Full deployment guide
├── .env.example                   # Environment template
├── requirements.txt               # Dependencies
└── assets/                        # UI assets
```

## ⚡ Quick Start

### 1️⃣ Install Dependencies
```bash
pip install -r requirements.txt
```

### 2️⃣ Set Up Environment
```bash
cp .env.example .env
# Edit .env with your Meta credentials (for WhatsApp) and Ollama URL
```

### 3️⃣ Ingest Website Data
```bash
# Add your website URLs to urls.txt (one per line)
python src/ingest.py
```

### 4️⃣ Run the Chatbot

**Streamlit UI:**
```bash
streamlit run src/app.py
```

**WhatsApp Webhook (Windows):**
```powershell
./run_whatsapp_webhook.ps1
```

**WhatsApp Webhook (macOS/Linux):**
```bash
python src/whatsapp_webhook.py
```

## 📖 Documentation

- **[docs/README.md](docs/README.md)** — Detailed technical guide
- **[docs/WHATSAPP_QUICKSTART.md](docs/WHATSAPP_QUICKSTART.md)** — WhatsApp setup (5 min)
- **[docs/WHATSAPP_SETUP.md](docs/WHATSAPP_SETUP.md)** — Production deployment

## 🔄 Dynamic Data Refresh

1. Update `urls.txt` with new website URLs
2. Run `python src/ingest.py` to rebuild embeddings
3. Use Streamlit sidebar button to reload cached corpus
4. Restart webhook service to pick up new data

## 🤖 Tech Stack

- **Streamlit** — Web UI
- **Flask** — WhatsApp webhook
- **Sentence-Transformers** — Embeddings
- **Ollama** — Local LLM (configurable)
- **Meta Cloud API** — WhatsApp integration

## Notes
- API keys (for LLMs) should be set as environment variables, not in code.
- The current search is simple; swap in a vector DB and LLM for production.
