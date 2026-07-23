"""Diagnose retrieval quality. Not a test — a tool for understanding failures.

Run inside the Linux container:
    docker run --rm -v <backend>:/app -w /app ai-portfolio-backend-test:latest \
        python test/diagnose.py
"""

from app.config import DATA_DIR, TOP_K
from app.embeddings import embed_query, embed_texts, get_model
from app.ingest import load_chunks

QUERIES = [
    ("Does he have any experience with banking?", "Atlantic Money"),
    ("What is he doing now?", "AI Talent"),
    ("Where did he study?", "Master of Information Technology"),
    ("Has he worked with virtual reality for schools?", "Hood VR"),
]


def main() -> None:
    model = get_model()
    limit = model.max_seq_length
    tokenizer = model.tokenizer

    chunks = load_chunks(DATA_DIR)
    print(f"model max_seq_length: {limit} tokens")
    print(f"chunks: {len(chunks)}\n")

    print("=== chunks exceeding the model's token limit (content past it is INVISIBLE) ===")
    over = []
    for c in chunks:
        n = len(tokenizer.encode(c.text))
        if n > limit:
            over.append((n, c))
    for n, c in sorted(over, reverse=True, key=lambda x: x[0]):
        print(f"  {n:4d} tokens ({n - limit:+d} over)  {c.source}: {c.heading[:60]}")
    print(f"  {len(over)} of {len(chunks)} chunks truncated\n")

    print("=== token length distribution ===")
    lengths = sorted(len(tokenizer.encode(c.text)) for c in chunks)
    print(f"  min {lengths[0]}  median {lengths[len(lengths)//2]}  max {lengths[-1]}")

    print("\n=== per-query ranking, showing where the expected chunk actually lands ===")
    texts = [c.text for c in chunks]
    vectors = embed_texts(texts)

    for query, expected in QUERIES:
        qv = embed_query(query)
        scored = sorted(
            ((sum(a * b for a, b in zip(qv, v)), c) for v, c in zip(vectors, chunks)),
            reverse=True,
            key=lambda x: x[0],
        )
        print(f"\n  QUERY: {query!r}   (expecting {expected!r})")
        for rank, (score, c) in enumerate(scored[:TOP_K], start=1):
            print(f"    {rank}. {score:.4f}  [{c.source}] {c.heading[:64]}")
        for rank, (score, c) in enumerate(scored, start=1):
            if expected.lower() in c.heading.lower():
                marker = "IN TOP-K" if rank <= TOP_K else "MISSED"
                print(f"    -> expected chunk ranked #{rank} (score {score:.4f})  [{marker}]")
                break


if __name__ == "__main__":
    main()
