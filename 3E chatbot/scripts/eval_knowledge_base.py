import json
from pathlib import Path

import numpy as np
from sentence_transformers import SentenceTransformer

MODEL_NAME = "all-MiniLM-L6-v2"
KB_PATH = Path("knowledge_base.json")

TEST_QUESTIONS = [
    "How can I book a class?",
    "What classes are offered?",
    "How much is the 10 class package?",
    "Where are classes held?",
    "What is SUP Yoga?",
    "What is the studio address?",
    "What classes are on the schedule?",
    "Who is Daniela Bocoum?",
    "What is the beginner-friendly evening class like?",
    "Can the packages be used for private sessions?",
]


def load_knowledge_base():
    with KB_PATH.open(encoding="utf-8") as f:
        kb = json.load(f)
    return kb


def main():
    kb = load_knowledge_base()
    model = SentenceTransformer(MODEL_NAME)

    questions = [item["question"] for item in kb]
    embeddings = model.encode(questions, normalize_embeddings=True)

    print(f"KB entries: {len(kb)}")
    print()

    for question in TEST_QUESTIONS:
        q_emb = model.encode(question, normalize_embeddings=True)
        scores = np.dot(embeddings, q_emb)
        best_idx = int(scores.argmax())
        best_score = float(scores[best_idx])
        best_item = kb[best_idx]

        print(f"Q: {question}")
        print(f"Best match score: {best_score:.3f}")
        print(f"Best matched KB question: {best_item['question']}")
        print(f"Answer: {best_item['answer']}")
        print("-" * 60)


if __name__ == "__main__":
    main()
