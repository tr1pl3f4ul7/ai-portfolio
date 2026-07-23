"""Does prefixing the document title help or hurt retrieval?

Chunks currently embed as "{document title} — {heading}\\n\\n{body}". That means
all 12 faq.md chunks begin "Frequently asked questions — ", which may be why FAQ
entries dominate question-shaped queries regardless of topic.

Compares three strategies on the real corpus.
"""

from __future__ import annotations

from sentence_transformers import SentenceTransformer

from app.config import DATA_DIR, EMBEDDING_MODEL, TOP_K
from app.ingest import load_chunks

STRATEGIES = {
    "A doc-title prefix (current)": lambda c: f"{c.document_title} — {c.heading}\n\n{c.body}",
    "B heading only": lambda c: f"{c.heading}\n\n{c.body}",
    "C subject prefix": lambda c: f"Ljuben Vassilev — {c.heading}\n\n{c.body}",
}

# Broader than the test suite: includes the questions that retrieved badly.
CASES = [
    ("What warehouse software has he built?", "Ozone Warehouse"),
    ("Tell me about the Montblanc project", "Montblanc"),
    ("Does he have any experience with banking?", "Atlantic Money"),
    ("What is he doing now?", "AI Talent"),
    ("What did he study for his cyber security master's degree?", "Master of Information"),
    ("Has he worked with virtual reality for schools?", "Hood VR"),
    ("What certifications does he hold?", "Certifications"),
    ("What is his security background?", "Application Security Engineer"),
    ("Tell me about the most technically difficult thing he has built", "Ozone Warehouse"),
    ("Has he built anything for children?", "MyKi"),
    ("What mobile technologies does he know?", "Mobile development"),
    ("Who does he work for?", "AI Talent"),
]


def main() -> None:
    chunks = load_chunks(DATA_DIR)
    model = SentenceTransformer(EMBEDDING_MODEL)
    print(f"model: {EMBEDDING_MODEL}   corpus: {len(chunks)} chunks   k={TOP_K}\n")

    summary = []
    for name, render in STRATEGIES.items():
        vecs = model.encode(
            [render(c) for c in chunks], normalize_embeddings=True, show_progress_bar=False
        )
        hits4 = hits6 = 0
        faq_top1 = 0
        lines = []
        for query, expected in CASES:
            qv = model.encode([query], normalize_embeddings=True, show_progress_bar=False)[0]
            scored = sorted(
                ((sum(a * b for a, b in zip(qv, v)), c) for v, c in zip(vecs, chunks)),
                reverse=True,
                key=lambda x: x[0],
            )
            rank = next(
                (i for i, (_, c) in enumerate(scored, 1) if expected.lower() in c.heading.lower()),
                None,
            )
            if scored[0][1].source == "faq.md":
                faq_top1 += 1
            if rank and rank <= 4:
                hits4 += 1
            if rank and rank <= TOP_K:
                hits6 += 1
            flag = "ok  " if rank and rank <= 4 else ("k6  " if rank and rank <= TOP_K else "MISS")
            lines.append(f"   {flag} #{rank!s:<4} {expected:<30} {query[:52]}")

        print(f"--- {name} ---")
        print("\n".join(lines))
        print(
            f"   top4={hits4}/{len(CASES)}  top{TOP_K}={hits6}/{len(CASES)}  "
            f"faq_dominated_top1={faq_top1}/{len(CASES)}\n",
            flush=True,
        )
        summary.append((name, hits4, hits6, faq_top1))

    print("=" * 84)
    print(f"{'strategy':<32}{'top4':>8}{'top6':>8}{'faq #1':>10}")
    print("=" * 84)
    for name, h4, h6, faq in summary:
        print(f"{name:<32}{h4:>6}/{len(CASES)}{h6:>6}/{len(CASES)}{faq:>8}/{len(CASES)}")


if __name__ == "__main__":
    main()
