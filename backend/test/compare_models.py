"""Compare embedding models on the real corpus and the real test queries.

Not a test — an experiment, to choose the embedding model on evidence rather
than reputation. Run inside the Linux container:

    docker run --rm -e PYTHONPATH=/app -v <backend>:/app -w /app \
        ai-portfolio-backend-test:latest python test/compare_models.py

Reports, for each candidate: how many of the evaluation queries retrieve the
expected chunk within top-k, at what rank, and how much of the corpus the model
truncates.
"""

from __future__ import annotations

import time

from sentence_transformers import SentenceTransformer

from app.config import DATA_DIR
from app.ingest import load_chunks

# (model id, query prefix, document prefix)
# BGE and E5 families are trained asymmetrically and expect an instruction
# prefix on the query side; using them without it measurably hurts retrieval.
CANDIDATES = [
    ("sentence-transformers/all-MiniLM-L6-v2", "", ""),
    ("sentence-transformers/all-MiniLM-L12-v2", "", ""),
    ("BAAI/bge-small-en-v1.5", "Represent this sentence for searching relevant passages: ", ""),
    ("thenlper/gte-small", "", ""),
    ("sentence-transformers/all-mpnet-base-v2", "", ""),
]

# The same cases the test suite asserts on.
CASES = [
    ("What warehouse software has he built?", "Ozone Warehouse"),
    ("Tell me about the Montblanc project", "Montblanc"),
    ("Does he have any experience with banking?", "Atlantic Money"),
    ("What is he doing now?", "AI Talent"),
    ("Where did he study?", "Master of Information Technology"),
    ("Has he worked with virtual reality for schools?", "Hood VR"),
    ("Does he have AI experience?", "AI"),
    ("What certifications does he hold?", "Certifications"),
]

K_VALUES = (4, 6)


def cosine(a, b) -> float:
    return sum(x * y for x, y in zip(a, b))


def main() -> None:
    chunks = load_chunks(DATA_DIR)
    print(f"corpus: {len(chunks)} chunks\n")

    rows = []
    for model_id, q_prefix, d_prefix in CANDIDATES:
        print(f"--- {model_id} ---", flush=True)
        t0 = time.perf_counter()
        model = SentenceTransformer(model_id)
        load_s = time.perf_counter() - t0

        limit = model.max_seq_length
        tok = model.tokenizer
        truncated = sum(1 for c in chunks if len(tok.encode(c.text)) > limit)

        t0 = time.perf_counter()
        doc_vecs = model.encode(
            [d_prefix + c.text for c in chunks],
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        embed_s = time.perf_counter() - t0

        hits = {k: 0 for k in K_VALUES}
        ranks = []
        for query, expected in CASES:
            qv = model.encode(
                [q_prefix + query], normalize_embeddings=True, show_progress_bar=False
            )[0]
            scored = sorted(
                ((cosine(qv, v), c) for v, c in zip(doc_vecs, chunks)),
                reverse=True,
                key=lambda x: x[0],
            )
            rank = next(
                (i for i, (_, c) in enumerate(scored, 1) if expected.lower() in c.heading.lower()),
                None,
            )
            ranks.append((query, expected, rank))
            for k in K_VALUES:
                if rank is not None and rank <= k:
                    hits[k] += 1

        dims = model.get_sentence_embedding_dimension()
        rows.append((model_id, dims, limit, truncated, hits, load_s, embed_s))

        for query, expected, rank in ranks:
            flag = "ok " if rank and rank <= 4 else ("k6 " if rank and rank <= 6 else "MISS")
            print(f"   {flag} #{rank!s:<4} {expected:<34} {query}")
        print(
            f"   dims={dims} max_seq={limit} truncated={truncated}/{len(chunks)} "
            f"top4={hits[4]}/{len(CASES)} top6={hits[6]}/{len(CASES)} "
            f"load={load_s:.1f}s embed={embed_s:.1f}s\n",
            flush=True,
        )

    print("=" * 100)
    print(f"{'model':<44}{'dims':>5}{'seq':>5}{'trunc':>7}{'top4':>7}{'top6':>7}{'embed_s':>9}")
    print("=" * 100)
    for model_id, dims, limit, truncated, hits, _load, embed_s in rows:
        print(
            f"{model_id:<44}{dims:>5}{limit:>5}{truncated:>7}"
            f"{hits[4]:>5}/{len(CASES)}{hits[6]:>5}/{len(CASES)}{embed_s:>9.1f}"
        )


if __name__ == "__main__":
    main()
