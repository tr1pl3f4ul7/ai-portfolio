"""Embedding model access.

The model is loaded once and cached. It is roughly 90 MB resident, and the VM
has 12 GB shared with nginx, the API process and the vector store — loading it
per request would be both slow and wasteful.
"""

from __future__ import annotations

from functools import lru_cache

from app.config import EMBEDDING_MODEL


@lru_cache(maxsize=1)
def get_model():
    """Return the shared SentenceTransformer instance.

    Imported lazily so that modules which only need chunking or configuration
    do not pay the cost of importing torch.
    """
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(EMBEDDING_MODEL)


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Embed a batch of documents for storage."""
    model = get_model()
    vectors = model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
    return [v.tolist() for v in vectors]


def embed_query(text: str) -> list[float]:
    """Embed a single query for search.

    Normalised to unit length, matching how documents are stored, so that
    distance comparisons are consistent.
    """
    model = get_model()
    vector = model.encode([text], normalize_embeddings=True, show_progress_bar=False)[0]
    return vector.tolist()
