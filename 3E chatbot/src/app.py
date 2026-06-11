import json
import os
import re
from pathlib import Path

import numpy as np
import requests
import streamlit as st
from sentence_transformers import SentenceTransformer


MODEL_NAME = "all-MiniLM-L6-v2"
PROJECT_ROOT = Path(__file__).resolve().parent.parent  # Go up from src/ to root
DATA_DIR = PROJECT_ROOT / "data"
ASSETS_DIR = PROJECT_ROOT / "assets"
KB_PATH = DATA_DIR / "knowledge_base.json"
LEGACY_KB_PATH = PROJECT_ROOT / "knowledge_base.json"
RAG_PATH = DATA_DIR / "data.json"
RAG_EMBEDDINGS_PATH = DATA_DIR / "embeddings.npy"
OLLAMA_MODEL = "llama3"
OLLAMA_URL = "http://localhost:11434/api/generate"
FAQ_MIN_CONTEXT_SCORE = 0.20
RAG_MIN_CONTEXT_SCORE = 0.15
FAQ_DIRECT_THRESHOLD = 0.55
FAQ_TOP_K = 3
RAG_TOP_K = 3
TOP_K = 6
EMBEDDING_WEIGHT = 0.70
KEYWORD_WEIGHT = 0.30
FAQ_RELATIVE_GAP = 0.12
RAG_RELATIVE_GAP = 0.15
USER_AVATAR = str(ASSETS_DIR / "user_yoga_avatar.svg")
ASSISTANT_AVATAR = str(ASSETS_DIR / "assistant_lotus_avatar.svg")
LOGO_CANDIDATES = [
    PROJECT_ROOT / "logo.png",
    PROJECT_ROOT / "logo.png.png",
    PROJECT_ROOT / "logo.jpg",
    PROJECT_ROOT / "logo.jpeg",
    ASSETS_DIR / "logo.png",
    ASSETS_DIR / "logo.jpg",
    ASSETS_DIR / "logo.jpeg",
    PROJECT_ROOT / "3elements_logo.png",
    PROJECT_ROOT / "3elements-logo.png",
]


@st.cache_resource(show_spinner=False)
def load_embedder():
    return SentenceTransformer(MODEL_NAME)


def file_signature(path):
    if not path.exists():
        return (0, 0)
    stat = path.stat()
    return (stat.st_mtime_ns, stat.st_size)


@st.cache_data(show_spinner=False)
def load_knowledge_base(signature=None):
    kb_source = KB_PATH if KB_PATH.exists() else LEGACY_KB_PATH
    if not kb_source.exists():
        raise FileNotFoundError(
            f"Knowledge base not found at {KB_PATH} or legacy path {LEGACY_KB_PATH}"
        )

    with open(kb_source, encoding="utf-8") as f:
        kb = json.load(f)

    questions = [item["question"] for item in kb]
    embeddings = load_embedder().encode(questions, normalize_embeddings=True)
    return kb, embeddings


@st.cache_data(show_spinner=False)
def load_rag_corpus(rag_signature=None, embeddings_signature=None):
    if not RAG_PATH.exists():
        return [], np.empty((0, 0), dtype=np.float32)

    with open(RAG_PATH, encoding="utf-8") as f:
        raw_docs = json.load(f)

    docs = []
    texts = []
    for doc in raw_docs:
        url = doc.get("url", "")
        text = doc.get("text") or doc.get("content") or ""
        docs.append(
            {
                "url": url,
                "title": doc.get("title") or make_rag_title(url),
                "content": text,
            }
        )
        texts.append(text)

    if not docs:
        return [], np.empty((0, 0), dtype=np.float32)

    if RAG_EMBEDDINGS_PATH.exists():
        embeddings = np.load(RAG_EMBEDDINGS_PATH)
        if len(embeddings) != len(docs) or (embeddings_signature and rag_signature and embeddings_signature < rag_signature):
            embeddings = load_embedder().encode(texts, normalize_embeddings=True)
    else:
        embeddings = load_embedder().encode(texts, normalize_embeddings=True)

    return docs, embeddings


def normalize_text(text):
    normalized = " ".join(text.lower().split())

    # Canonicalize frequent synonym groups so lexical matching is less brittle.
    synonym_patterns = {
        r"\b(kid|kids|child|children|teen|teens|teenager|teenagers|youth)\b": " youth ",
        r"\b(book|reserve|reservation|register|sign up|join)\b": " booking ",
        r"\b(cost|price|pricing|fee|fees|how much)\b": " price ",
        r"\b(classes|class)\b": " class ",
    }

    for pattern, replacement in synonym_patterns.items():
        normalized = re.sub(pattern, replacement, normalized)

    return " ".join(normalized.split())


def tokenize(text):
    return set(re.findall(r"[a-z0-9']+", normalize_text(text)))


def keyword_overlap_score(query, candidate):
    q_tokens = tokenize(query)
    c_tokens = tokenize(candidate)
    if not q_tokens or not c_tokens:
        return 0.0
    return len(q_tokens & c_tokens) / len(q_tokens | c_tokens)


def intent_alignment_score(query, candidate):
    q_tokens = tokenize(query)
    c_tokens = tokenize(candidate)
    if not q_tokens or not c_tokens:
        return 0.0

    # Reward candidates that match the same high-signal intent tokens.
    anchors = {
        "youth": 0.30,
        "price": 0.22,
        "booking": 0.20,
        "schedule": 0.20,
        "address": 0.20,
        "daniela": 0.25,
        "founder": 0.15,
    }

    score = 0.0
    for token, weight in anchors.items():
        if token not in q_tokens:
            continue
        if token in c_tokens:
            score += weight
        else:
            score -= weight * 0.65

    return score


def make_rag_title(url):
    if not url:
        return "Website RAG chunk"

    slug = url.rstrip("/").split("/")[-1]
    if not slug:
        return "Website RAG chunk"

    return slug.replace("-", " ").replace("_", " ").title()


def score_query(query, embeddings):
    q_emb = load_embedder().encode(query, normalize_embeddings=True)
    return np.dot(embeddings, q_emb)


def find_best_match(user_question):
    faq_items = retrieve_faq(user_question, k=1)
    if faq_items:
        return faq_items[0]["item"], faq_items[0]["score"]

    rag_items = retrieve_rag(user_question, k=1)
    if rag_items:
        rag_doc = rag_items[0]["item"]
        return {"question": rag_doc.get("title", "RAG chunk"), "answer": rag_doc.get("content", "")}, rag_items[0]["score"]

    return {"question": None, "answer": None}, 0.0


def retrieve_faq(user_question, k=FAQ_TOP_K, min_score=FAQ_MIN_CONTEXT_SCORE):
    kb, embeddings = load_knowledge_base(file_signature(KB_PATH))
    normalized_question = normalize_text(user_question)
    
    # For time-related queries, lower the threshold so schedule/time FAQs are included
    time_markers = {"when", "time", "schedule", "hours", "date", "times", "what time", "when are", "when is"}
    if any(marker in user_question.lower() for marker in time_markers):
        min_score = max(0.10, min_score - 0.05)  # reduce threshold for time queries

    exact_matches = []
    for item in kb:
        if normalize_text(item["question"]) == normalized_question:
            exact_matches.append({"source": "faq", "score": 1.0, "item": item})

    if exact_matches:
        return exact_matches[:k]

    semantic_scores = score_query(user_question, embeddings)

    scored_items = []
    for idx, semantic_score in enumerate(semantic_scores):
        item = kb[idx]
        item_text = f"{item['question']} {item['answer']}"
        lexical_score = keyword_overlap_score(user_question, item_text)
        intent_score = intent_alignment_score(user_question, item_text)
        score_value = (EMBEDDING_WEIGHT * float(semantic_score)) + (KEYWORD_WEIGHT * lexical_score) + intent_score
        if score_value >= min_score:
            scored_items.append({"source": "faq", "score": score_value, "item": item})

    if not scored_items:
        return []

    scored_items.sort(key=lambda row: row["score"], reverse=True)
    return scored_items[:k]


def retrieve_rag(user_question, k=RAG_TOP_K, min_score=RAG_MIN_CONTEXT_SCORE):
    docs, embeddings = load_rag_corpus(file_signature(RAG_PATH), file_signature(RAG_EMBEDDINGS_PATH))
    if not docs or embeddings.size == 0:
        return []

    semantic_scores = score_query(user_question, embeddings)

    scored_items = []
    for idx, semantic_score in enumerate(semantic_scores):
        doc = docs[idx]
        lexical_score = keyword_overlap_score(user_question, doc.get("content", ""))
        score_value = (EMBEDDING_WEIGHT * float(semantic_score)) + (KEYWORD_WEIGHT * lexical_score)
        if score_value >= min_score:
            scored_items.append({"source": "rag", "score": score_value, "item": doc})

    scored_items.sort(key=lambda row: row["score"], reverse=True)
    return scored_items[:k]


def build_context_items(user_question):
    faq_items = retrieve_faq(user_question)
    context_items = []

    if faq_items:
        faq_top_score = faq_items[0]["score"]
        faq_floor = max(FAQ_MIN_CONTEXT_SCORE, faq_top_score - FAQ_RELATIVE_GAP)
        faq_items = [row for row in faq_items if row["score"] >= faq_floor]
        context_items.extend(faq_items)

    faq_top_score = faq_items[0]["score"] if faq_items else 0.0
    if not faq_items or faq_top_score < FAQ_DIRECT_THRESHOLD:
        rag_items = retrieve_rag(user_question)
        if rag_items:
            rag_top_score = rag_items[0]["score"]
            rag_floor = max(RAG_MIN_CONTEXT_SCORE, rag_top_score - RAG_RELATIVE_GAP)
            rag_items = [row for row in rag_items if row["score"] >= rag_floor]
            context_items.extend(rag_items)

    seen = set()
    deduped = []
    for row in context_items:
        item = row["item"]
        if row["source"] == "faq":
            key = ("faq", normalize_text(item["question"]))
        else:
            key = ("rag", normalize_text(item.get("content", "")))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(row)

    deduped.sort(key=lambda row: (0 if row["source"] == "faq" else 1, -row["score"]))
    return deduped[:TOP_K]


def fallback_with_contact():
    return "I don't have that information. Please contact Daniela Bocoum at +221 78 457 59 04."


def fallback_with_contact_for_language(language):
    if language == "fr":
        return "Je n'ai pas cette information. Veuillez contacter Daniela Bocoum au +221 78 457 59 04."
    return fallback_with_contact()


def normalize_fallback_language(text, language):
    if not text:
        return text

    english_fallback = fallback_with_contact()
    french_fallback = fallback_with_contact_for_language("fr")
    lowered = text.lower()

    if language == "fr":
        # Only normalize when the text is exactly the generic fallback; otherwise keep custom text.
        if text.strip() == english_fallback or text.strip() == french_fallback:
            return french_fallback
        return text

    # Only normalize when the text exactly equals the generic fallback; otherwise keep custom text.
    if text.strip() == english_fallback or text.strip() == french_fallback:
        return english_fallback
    return text


def get_thinking_text(language):
    if language == "fr":
        return "Le bot reflechit"
    return "The bot is thinking"


def find_logo_path():
    for path in LOGO_CANDIDATES:
        if path.exists():
            return path
    return None


def clear_corpus_cache():
    load_knowledge_base.clear()
    load_rag_corpus.clear()


def apply_custom_theme():
    st.markdown(
        """
        <style>
            @import url('https://fonts.googleapis.com/css2?family=Montserrat:wght@500;700;800&family=Nunito:wght@500;700&family=Cormorant+Garamond:ital,wght@1,600&display=swap');

            :root {
                --sea-50: #eef7f7;
                --sea-100: #dceeee;
                --sea-300: #c0e0e0;
                --sea-500: #20b0b0;
                --sea-600: #209090;
                --sea-700: #108080;
                --ink: #106065;
                --ink-soft: #2e7e85;
                --paper: rgba(255, 255, 255, 0.90);
                --shadow-soft: 0 10px 28px rgba(16, 112, 117, 0.14);
            }

            .stApp {
                background:
                    radial-gradient(circle at 12% 14%, rgba(32, 176, 176, 0.20), transparent 32%),
                    radial-gradient(circle at 86% 8%, rgba(128, 192, 208, 0.30), transparent 24%),
                    linear-gradient(160deg, #f9fcfc 0%, #f1f9f9 38%, #e8f3f3 100%);
                color: var(--ink);
                font-family: 'Nunito', sans-serif;
            }

            html, body, [data-testid="stAppViewContainer"], [data-testid="stMain"] {
                background:
                    radial-gradient(circle at 12% 14%, rgba(32, 176, 176, 0.20), transparent 32%),
                    radial-gradient(circle at 86% 8%, rgba(128, 192, 208, 0.30), transparent 24%),
                    linear-gradient(160deg, #f9fcfc 0%, #f1f9f9 38%, #e8f3f3 100%) !important;
            }

            [data-testid="stHeader"] {
                background: rgba(232, 243, 243, 0.92) !important;
                border-bottom: 1px solid rgba(32, 176, 176, 0.28) !important;
            }

            [data-testid="stBottomBlockContainer"] {
                background: transparent !important;
            }

            [data-testid="stBottom"],
            [data-testid="stBottom"] > div,
            [data-testid="stBottom"] > div::before,
            footer {
                background:
                    radial-gradient(circle at 12% 14%, rgba(32, 176, 176, 0.20), transparent 32%),
                    radial-gradient(circle at 86% 8%, rgba(128, 192, 208, 0.30), transparent 24%),
                    linear-gradient(160deg, #f9fcfc 0%, #f1f9f9 38%, #e8f3f3 100%) !important;
            }

            .main .block-container,
            [data-testid="stVerticalBlock"],
            [data-testid="stHorizontalBlock"] {
                background: transparent !important;
            }

            [data-testid="stDecoration"] {
                display: none;
            }

            .main .block-container {
                max-width: 900px;
                padding-top: 2rem;
                padding-bottom: 2.2rem;
            }

            .hero-wrap {
                background: linear-gradient(145deg, rgba(214, 238, 238, 0.95), rgba(192, 224, 224, 0.92));
                border: 1px solid rgba(32, 176, 176, 0.28);
                border-radius: 22px;
                box-shadow: var(--shadow-soft);
                padding: 1rem 1rem 0.7rem 1rem;
                margin-bottom: 1rem;
            }

            .hero-title {
                font-family: 'Montserrat', sans-serif;
                font-size: clamp(1.45rem, 3vw, 2.05rem);
                font-weight: 800;
                line-height: 1.08;
                letter-spacing: 0.2px;
                color: var(--ink);
                margin: 0;
            }

            .hero-sub {
                font-family: 'Nunito', sans-serif;
                color: var(--ink-soft);
                margin-top: 0.32rem;
                margin-bottom: 0.15rem;
                font-size: 0.98rem;
            }

            .hero-sub-fr {
                font-family: 'Cormorant Garamond', serif;
                color: var(--sea-700);
                margin-top: 0;
                margin-bottom: 0.45rem;
                font-size: 1rem;
                font-style: italic;
                letter-spacing: 0.15px;
            }

            .hero-pill {
                display: inline-block;
                padding: 0.3rem 0.72rem;
                border-radius: 999px;
                border: 1px solid rgba(32, 176, 176, 0.42);
                background: rgba(32, 176, 176, 0.14);
                color: var(--sea-600);
                font-weight: 700;
                font-size: 0.8rem;
                letter-spacing: 0.25px;
            }

            [data-testid="stChatMessage"] {
                border-radius: 16px;
                border: 1px solid rgba(32, 176, 176, 0.24);
                box-shadow: 0 5px 18px rgba(14, 95, 105, 0.08);
                margin-top: 0.45rem;
                margin-bottom: 0.45rem;
                backdrop-filter: blur(2px);
                animation: floatIn 220ms ease-out;
            }

            [data-testid="stChatMessage"] [data-testid="stMarkdownContainer"] p {
                font-size: 0.99rem;
                line-height: 1.5;
            }

            [data-testid="chatAvatarIcon-user"] {
                background: linear-gradient(145deg, #e7f3f3, #d6ecec) !important;
                color: #106065 !important;
                border: 1px solid rgba(16, 96, 101, 0.18) !important;
                box-shadow: 0 2px 8px rgba(16, 112, 117, 0.14) !important;
            }

            [data-testid="chatAvatarIcon-assistant"] {
                background: linear-gradient(145deg, #d6ecec, #c0e0e0) !important;
                color: #106065 !important;
                border: 1px solid rgba(16, 96, 101, 0.18) !important;
                box-shadow: 0 2px 8px rgba(16, 112, 117, 0.16) !important;
            }

            [data-testid="chatAvatarIcon-user"] *,
            [data-testid="chatAvatarIcon-assistant"] * {
                background: transparent !important;
                color: #106065 !important;
                fill: #106065 !important;
                stroke: #106065 !important;
            }

            [data-testid="stChatMessage"] [data-testid="stMarkdownContainer"],
            [data-testid="stChatMessage"] [data-testid="stMarkdownContainer"] p,
            [data-testid="stChatMessage"] [data-testid="stMarkdownContainer"] span,
            [data-testid="stChatMessage"] [data-testid="stMarkdownContainer"] li,
            [data-testid="stChatMessage"] [data-testid="stMarkdownContainer"] div {
                color: #106065 !important;
            }

            [data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-user"]) {
                background: linear-gradient(125deg, rgba(96, 192, 192, 0.22), rgba(192, 224, 224, 0.36));
            }

            [data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-assistant"]) {
                background: linear-gradient(135deg, rgba(230, 245, 245, 0.96), rgba(204, 230, 230, 0.86));
            }

            [data-testid="stChatInput"] {
                background: transparent;
                border: none;
                box-shadow: none;
            }

            [data-testid="stChatInput"] > div {
                background: linear-gradient(145deg, rgba(218, 238, 238, 0.96), rgba(206, 231, 231, 0.95));
                border: 1px solid rgba(88, 190, 198, 0.55);
                border-radius: 16px;
                box-shadow: var(--shadow-soft);
            }

            [data-testid="stChatInput"] [data-baseweb="textarea"],
            [data-testid="stChatInput"] [data-baseweb="textarea"] > div,
            [data-testid="stChatInput"] [data-baseweb="input"],
            [data-testid="stChatInput"] [data-baseweb="input"] > div {
                background: rgba(232, 245, 245, 0.98) !important;
                border-radius: 10px;
            }

            [data-testid="stChatInput"] textarea {
                background: rgba(232, 245, 245, 0.98) !important;
                font-family: 'Nunito', sans-serif;
                color: var(--ink) !important;
                border-radius: 10px;
            }

            [data-testid="stChatInput"] textarea::placeholder {
                color: rgba(46, 126, 133, 0.78);
            }

            [data-testid="stChatInput"] textarea:focus {
                background: rgba(240, 251, 251, 1) !important;
                box-shadow: 0 0 0 2px rgba(32, 176, 176, 0.18) inset;
                outline: none !important;
                border: 1px solid rgba(32, 176, 176, 0.45) !important;
            }

            [data-testid="stChatInput"] > div:focus-within {
                border: 1px solid rgba(32, 176, 176, 0.55) !important;
                box-shadow: 0 0 0 3px rgba(32, 176, 176, 0.20) !important;
            }

            [data-testid="stChatInput"] div[role="textbox"],
            [data-testid="stChatInput"] [contenteditable="true"],
            [data-testid="stChatInput"] input {
                background: rgba(232, 245, 245, 0.98) !important;
                color: var(--ink) !important;
            }

            [data-testid="stChatInput"] button {
                background: linear-gradient(145deg, #20b0b0, #209090);
                border: 1px solid rgba(16, 96, 101, 0.25);
                color: #ffffff;
                border-radius: 11px;
            }

            [data-testid="stChatInput"] button:hover {
                background: linear-gradient(145deg, #2ac0c0, #20a0a0);
            }

            .thinking-line {
                color: var(--sea-700);
                font-family: 'Nunito', sans-serif;
                font-weight: 700;
                font-size: 0.98rem;
                letter-spacing: 0.2px;
                display: inline-flex;
                align-items: center;
                gap: 0.15rem;
            }

            .thinking-dots {
                display: inline-flex;
                align-items: center;
                gap: 0.16rem;
                margin-left: 0.12rem;
            }

            .thinking-dots span {
                width: 0.34rem;
                height: 0.34rem;
                border-radius: 50%;
                background: var(--sea-600);
                opacity: 0.28;
                animation: dotPulse 1.05s infinite ease-in-out;
            }

            .thinking-dots span:nth-child(2) {
                animation-delay: 0.16s;
            }

            .thinking-dots span:nth-child(3) {
                animation-delay: 0.32s;
            }

            @keyframes dotPulse {
                0%, 80%, 100% {
                    transform: translateY(0);
                    opacity: 0.28;
                }
                40% {
                    transform: translateY(-2px);
                    opacity: 0.95;
                }
            }

            @keyframes floatIn {
                from {
                    opacity: 0;
                    transform: translateY(7px);
                }
                to {
                    opacity: 1;
                    transform: translateY(0);
                }
            }

            @media (max-width: 640px) {
                .main .block-container {
                    padding-top: 1.15rem;
                }

                .hero-wrap {
                    padding: 0.85rem 0.82rem 0.65rem 0.82rem;
                }
            }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_header():
    logo_path = find_logo_path()
    cols = st.columns([1, 3], vertical_alignment="center")
    with cols[0]:
        if logo_path:
            st.image(str(logo_path), use_container_width=True)

    with cols[1]:
        st.markdown(
            """
            <div class="hero-wrap">
                <h1 class="hero-title">3E Client Assistant</h1>
                <p class="hero-sub">Ask about classes, schedules, packages, and studio details.</p>
                <p class="hero-sub-fr">Posez vos questions sur les cours, les horaires, les forfaits et les details du studio.</p>
            </div>
            """,
            unsafe_allow_html=True,
        )

    if not logo_path:
        st.caption("Tip: add your logo as logo.png in the project root to show it in the header.")


def ask_ollama(prompt):
    try:
        response = requests.post(
            OLLAMA_URL,
            json={"model": OLLAMA_MODEL, "prompt": prompt, "stream": False},
            timeout=60,
        )
        response.raise_for_status()
        data = response.json()
        return data.get("response", "I could not generate a response right now.").strip()
    except requests.RequestException:
        return ""


def detect_language(text):
    sample = (text or "").lower()
    if not sample:
        return "en"

    # Lightweight heuristic: prefer French only when we see clear French words.
    french_markers = {
        "bonjour",
        "salut",
        "merci",
        "prix",
        "forfait",
        "cours",
        "horaire",
        "adresse",
        "quand",
        "comment",
        "je",
        "j",
        "est-ce",
        "peux-tu",
        "s'il",
        "avec",
    }
    sample_tokens = set(re.findall(r"[a-zàâçéèêëîïôûùüÿœæ']+", sample))
    if sample_tokens & french_markers:
        return "fr"

    if re.search(r"[àâçéèêëîïôûùüÿœæ]", sample):
        return "fr"

    tokens = re.findall(r"[a-zA-Z']+", sample)
    if tokens:
        fr_stopwords = {
            "je", "tu", "il", "elle", "nous", "vous", "ils", "elles",
            "le", "la", "les", "un", "une", "des", "du", "de", "d", "au", "aux",
            "et", "ou", "ou", "mais", "donc", "car", "que", "qui", "quoi", "quand",
            "comment", "est", "sont", "pas", "plus", "avec", "pour", "sur", "dans",
            "adresse", "cours", "horaire", "forfait", "prix", "cherche",
        }
        en_stopwords = {
            "i", "you", "he", "she", "we", "they", "the", "a", "an", "and", "or",
            "but", "what", "when", "how", "where", "is", "are", "not", "with", "for",
            "on", "in", "address", "class", "classes", "schedule", "package", "price",
        }

        fr_score = sum(1 for t in tokens if t in fr_stopwords)
        en_score = sum(1 for t in tokens if t in en_stopwords)
        if fr_score > en_score:
            return "fr"

    return "en"


def translate_text(text, target_language):
    if not text:
        return text

    prompt = f"""
Translate the text below to {target_language}.
Rules:
- Preserve meaning exactly.
- Keep names, numbers, phone numbers, and URLs unchanged.
- Return only the translated text.

Text:
{text}

Translated text:
"""
    translated = ask_ollama(prompt)
    if not translated:
        return text

    cleaned = translated.strip()
    cleaned = re.sub(r"\n\s*Note:.*$", "", cleaned, flags=re.IGNORECASE | re.DOTALL)
    cleaned = re.sub(r"^\s*[\"']|[\"']\s*$", "", cleaned)
    return cleaned.strip() or text


def to_retrieval_query(question, language):
    if language == "fr":
        return translate_text(question, "English")
    return question


def adapt_output_language(text, language):
    text = normalize_fallback_language(text, language)
    if language == "fr":
        translated = translate_text(text, "French")
        return normalize_fallback_language(translated, language)
    return text


def format_context_items(context_items):
    lines = []
    for row in context_items:
        item = row["item"]
        if row["source"] == "faq":
            lines.append(f"[FAQ | {row['score']:.2f}] Q: {item['question']}\nA: {item['answer']}")
        else:
            content = item.get("content", "").strip()
            if len(content) > 1200:
                content = content[:1200].rstrip() + "..."
            lines.append(
                f"[RAG | {row['score']:.2f}] {item.get('title', 'Website RAG chunk')}\nURL: {item.get('url', '')}\n{content}"
            )
    return "\n\n".join(lines)


def split_context_items(context_items):
    faq_lines = []
    rag_lines = []

    for row in context_items:
        item = row["item"]
        if row["source"] == "faq":
            faq_lines.append(f"- {item['answer']}")
        else:
            content = item.get("content", "").strip()
            if len(content) > 1200:
                content = content[:1200].rstrip() + "..."
            rag_lines.append(f"- {content}")

    return "\n\n".join(faq_lines), "\n\n".join(rag_lines)


def answer(question, context_items, language="en"):
    faq_text, rag_text = split_context_items(context_items)
    language_rule = "Respond in French." if language == "fr" else "Respond in English."
    fallback_rule_text = fallback_with_contact_for_language(language)
    prompt = f"""
Answer the user question using ONLY the information below.

User question:
{question}

FAQ:
{faq_text}

Other info:
{rag_text}

Rules:
- Use the information exactly as it is; do NOT add qualifiers like 'according to' or 'based on' unnecessarily
- Do NOT add disclaimers such as 'Please note' or 'This answer is based on'
- Find the most relevant information
- Do not ignore useful details
- Do not add new information
- Give a clear, direct answer
- {language_rule}
- If the answer is partially known, provide the best available answer
- If no information is found, say: "{fallback_rule_text}"

Answer:
"""
    return ask_ollama(prompt)


def polish_answer_text(text):
    cleaned = text.strip()
    # Preserve a short greeting (e.g., 'Hi Miriam,') if present
    prefix = ""
    rest = cleaned
    comma_pos = cleaned.find(",")
    if comma_pos != -1 and comma_pos < 40:
        prefix = cleaned[: comma_pos + 1].strip() + " "
        rest = cleaned[comma_pos + 1 :].strip()

    # If the model signals it couldn't find a direct answer, return concise fallback.
    lowered_rest = rest.lower()
    # Broader regex to catch common LLM fallback phrasings.
    if re.search(r"\b(do not have( enough)? information|cannot find( information)?|no direct answer|no information found|not described|not mentioned|no description|not listed|no details|must provide an alternative|i do not know|i'm not sure)\b", lowered_rest):
        return (prefix + fallback_with_contact()).strip()
    # Remove "according to X" phrases from anywhere in the text (not just start)
    cleaned = re.sub(
        r"\s*(according to (the )?(faq|information|knowledge base|sources?|context)[,:]?\s*)",
        " ",
        cleaned,
        flags=re.IGNORECASE,
    )
    # Remove "based on X" phrases
    cleaned = re.sub(
        r"\s*(based on (the )?(information|available information|sources?)[,:]?\s*)",
        " ",
        cleaned,
        flags=re.IGNORECASE,
    )
    # Clean up any double spaces
    cleaned = re.sub(r"\s+", " ", cleaned)
    # Remove common LLM-added disclaimers like 'Please note' or 'This answer is based'
    cleaned = re.sub(r"Please note[\s\S]*$", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"This answer is based[\s\S]*$", "", cleaned, flags=re.IGNORECASE)
    return cleaned.strip()


def generate_answer(question):
    language = detect_language(question)
    retrieval_question = to_retrieval_query(question, language)
    context_items = build_context_items(retrieval_question)
    if not context_items:
        return fallback_with_contact_for_language(language), 0.0, {"question": None, "answer": None}, []

    # For high-confidence FAQ matches, return the exact FAQ answer to prevent LLM drift.
    top_item = context_items[0]
    # If the user question is clearly time-related (when/schedule) but the top FAQ
    # does not look like a time/schedule question, avoid returning that FAQ directly
    # even if it passes the direct threshold. This prevents answers like returning
    # a location when the user asked "When are classes?".
    time_markers = {"when", "time", "schedule", "hours", "date", "times", "what time", "when are", "when is"}
    def contains_time_marker(text):
        if not text:
            return False
        lowered = text.lower()
        return any(marker in lowered for marker in time_markers)

    if top_item["source"] == "faq" and top_item["score"] >= FAQ_DIRECT_THRESHOLD:
        top_faq_question = top_item["item"].get("question", "")
        if contains_time_marker(retrieval_question) and not contains_time_marker(top_faq_question):
            # fall through to allow RAG/LLM to answer instead
            pass
        else:
            direct_answer = top_item["item"]["answer"]
            return adapt_output_language(direct_answer, language), top_item["score"], top_item["item"], context_items

    faq_candidates = [row for row in context_items if row["source"] == "faq"]
    rag_candidates = [row for row in context_items if row["source"] == "rag"]
    print("USER:", question)
    print("\nTOP FAQ:")
    for row in faq_candidates:
        print("-", row["item"]["question"])
    print("\nTOP RAG:")
    for row in rag_candidates:
        snippet = row["item"].get("content", "")[:100].replace("\n", " ")
        print("-", snippet)

    top_score = context_items[0]["score"]
    final_answer = answer(question, context_items, language=language)

    if not final_answer:
        top_faq = next((row for row in context_items if row["source"] == "faq"), None)
        if top_faq:
            return adapt_output_language(top_faq["item"]["answer"], language), top_score, context_items[0]["item"], context_items
        top_rag = next((row for row in context_items if row["source"] == "rag"), None)
        if top_rag:
            return adapt_output_language(top_rag["item"].get("content", ""), language), top_score, context_items[0]["item"], context_items
        return "I could not generate a response right now.", top_score, context_items[0]["item"], context_items

    # If the model simply echoed or restated the question (short/question-like reply),
    # treat it as a failure to answer and fallback to contact.
    try:
        norm_q = normalize_text(question)
        norm_a = normalize_text(final_answer)
        if norm_a == norm_q or (len(final_answer.strip()) < 60 and "?" in final_answer and len(tokenize(final_answer)) <= 6):
            final_answer = fallback_with_contact()
    except Exception:
        pass

    final_answer = polish_answer_text(final_answer)
    final_answer = adapt_output_language(final_answer, language)
    return final_answer, top_score, context_items[0]["item"], context_items


if os.environ.get("CHATBOT_DISABLE_UI") != "1":
    st.set_page_config(page_title="3 Elements Yoga Chatbot", page_icon="🌊", layout="centered")
    apply_custom_theme()
    render_header()

    with st.sidebar:
        st.caption("Dynamic data refresh")
        if st.button("Refresh cached data"):
            clear_corpus_cache()
            st.rerun()

    if "messages" not in st.session_state:
        st.session_state.messages = []

    for message in st.session_state.messages:
        avatar = USER_AVATAR if message["role"] == "user" else ASSISTANT_AVATAR
        with st.chat_message(message["role"], avatar=avatar):
            st.write(message["content"])

    user_input = st.chat_input("Ask something...")

    if user_input:
        st.session_state.messages.append({"role": "user", "content": user_input})
        with st.chat_message("user", avatar=USER_AVATAR):
            st.write(user_input)

        ui_language = detect_language(user_input)
        with st.chat_message("assistant", avatar=ASSISTANT_AVATAR):
            thinking_placeholder = st.empty()
            thinking_placeholder.markdown(
                f"<div class='thinking-line'>{get_thinking_text(ui_language)}<span class='thinking-dots'><span></span><span></span><span></span></span></div>",
                unsafe_allow_html=True,
            )
            answer, score, match, context_items = generate_answer(user_input)
            thinking_placeholder.empty()
            st.write(answer)

        st.session_state.messages.append({"role": "assistant", "content": answer})

