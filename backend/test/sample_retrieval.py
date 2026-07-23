"""Print what retrieval actually returns for realistic questions.

For human review — Step 2.2's verification is LJ reading a sample of retrieved
chunks and judging relevance. Reads the store built by `python -m app.ingest`.

    docker run --rm -e PYTHONPATH=/app -v <backend>:/app -w /app \
        ai-portfolio-backend-test:latest python test/sample_retrieval.py
"""

from app import store
from app.config import DB_PATH, TOP_K
from app.embeddings import embed_query

QUESTIONS = [
    "What is Ljuben doing now?",
    "Does he have AI experience?",
    "Tell me about the most technically difficult thing he has built",
    "Has he worked in banking or finance?",
    "What is his security background?",
    "Does he have a computer science degree?",
    "What mobile technologies does he know?",
    "Has he built anything for children?",
    "Why should I hire him?",
    "What does he do outside of work?",
]


def main() -> None:
    conn = store.connect(DB_PATH)
    print(f"index: {store.count(conn)} chunks, top_k={TOP_K}\n")

    for q in QUESTIONS:
        print("=" * 92)
        print(f"Q: {q}")
        print("=" * 92)
        for i, r in enumerate(store.search(conn, embed_query(q), TOP_K), start=1):
            snippet = " ".join(r.text.split())[:150]
            print(f"  {i}. [{r.distance:.3f}] {r.source} :: {r.heading}")
            print(f"     {snippet}...")
        print()
    conn.close()


if __name__ == "__main__":
    main()
