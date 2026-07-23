"""Retrieval tests over the real corpus.

This is the test Step 2.2 of the build plan asks for: a known query must return
the expected chunk in the top-k results.

Requires the sqlite-vec extension, which has no Windows ARM64 wheel, and the
embedding model. These run in the Linux container — see backend/test/. They
skip rather than fail where sqlite-vec is unavailable, so the rest of the suite
stays usable on the dev machine.
"""

from __future__ import annotations

import pytest

from app.config import DATA_DIR, TOP_K
from app.ingest import load_chunks

sqlite_vec = pytest.importorskip(
    "sqlite_vec",
    reason="sqlite-vec has no Windows ARM64 wheel; run these in the Linux container",
)


@pytest.fixture(scope="module")
def index(tmp_path_factory):
    """Build a real index over the real corpus, once for all tests here."""
    from app import store
    from app.embeddings import embed_texts

    chunks = load_chunks(DATA_DIR)
    assert chunks, f"no corpus found in {DATA_DIR}"

    db_path = tmp_path_factory.mktemp("vectors") / "test.db"
    conn = store.connect(db_path)
    store.init_schema(conn)
    store.replace_all(
        conn,
        [(c.source, c.heading, c.text) for c in chunks],
        embed_texts([c.text for c in chunks]),
    )
    yield conn
    conn.close()


def _headings(results) -> list[str]:
    return [r.heading for r in results]


def search(index, query: str, k: int = TOP_K):
    from app import store
    from app.embeddings import embed_query

    return store.search(index, embed_query(query), k)


def test_index_contains_every_chunk(index):
    from app import store

    assert store.count(index) == len(load_chunks(DATA_DIR))


# Specific questions with one clearly correct chunk. The expected substring must
# appear in the heading of at least one top-k result.
RETRIEVAL_CASES = [
    ("What warehouse software has he built?", "Ozone Warehouse"),
    ("Tell me about the Montblanc project", "Montblanc"),
    ("Does he have any experience with banking?", "Atlantic Money"),
    ("What did he study for his cyber security master's degree?", "Master of Information Technology"),
    ("Has he worked with virtual reality for schools?", "Hood VR"),
    ("Does he have AI experience?", "AI"),
    ("What certifications does he hold?", "Certifications"),
]

# Questions where what matters is that the FACT reaches the model, regardless of
# which chunk carries it. "What is he doing now?" is answered correctly by the
# FAQ entry "What does Ljuben actually do?" as well as by the AI Talent role
# entry — insisting on one specific heading would test a preference rather than
# correctness. Asserting on retrieved text is also stricter in one respect: the
# fact must actually be present, not merely implied by a heading.
CONTENT_CASES = [
    ("What is he doing now?", "AI Talent"),
    ("Who does he work for?", "AI Talent"),
    ("How many years of experience does he have?", "ten years"),
    ("Where is he based?", "Brisbane"),
]

# Broader questions where several chunks are legitimately correct. Asserting one
# specific heading would be testing a preference, not correctness — "Where did
# he study?" is fairly answered by either master's degree or the bootcamp, so
# the assertion is on the source document instead.
TOPICAL_CASES = [
    ("Where did he study?", "education.md"),
    ("What programming languages does he use?", "skills.md"),
    ("Tell me about his VR work", "projects-xr.md"),
]


@pytest.mark.parametrize("query,expected_heading_fragment", RETRIEVAL_CASES)
def test_known_query_returns_expected_chunk(index, query, expected_heading_fragment):
    results = search(index, query)
    headings = _headings(results)
    assert any(expected_heading_fragment.lower() in h.lower() for h in headings), (
        f"query {query!r} did not retrieve a chunk matching "
        f"{expected_heading_fragment!r}; got {headings}"
    )


@pytest.mark.parametrize("query,expected_source", TOPICAL_CASES)
def test_topical_query_retrieves_from_expected_document(index, query, expected_source):
    results = search(index, query)
    sources = [r.source for r in results]
    assert expected_source in sources, (
        f"query {query!r} retrieved nothing from {expected_source}; got {sources}"
    )


@pytest.mark.parametrize("query,expected_fact", CONTENT_CASES)
def test_retrieved_context_contains_the_answer(index, query, expected_fact):
    """The fact must reach the model, whichever chunk happens to carry it."""
    results = search(index, query)
    context = " ".join(r.text for r in results)
    assert expected_fact.lower() in context.lower(), (
        f"query {query!r} retrieved no chunk containing {expected_fact!r}; "
        f"got headings {_headings(results)}"
    )


def test_results_are_ordered_by_distance(index):
    results = search(index, "What programming languages does he use?")
    distances = [r.distance for r in results]
    assert distances == sorted(distances)


def test_returns_at_most_k(index):
    assert len(search(index, "mobile development", k=3)) <= 3


def test_no_pii_in_the_index(index):
    """The corpus is public and queryable. Personal details must not be in it."""
    from app import store

    rows = index.execute("SELECT text FROM chunks").fetchall()
    corpus = " ".join(r[0] for r in rows).lower()
    for forbidden in ["+61", "@gmail.com", "wanora", "warana"]:
        assert forbidden not in corpus, f"{forbidden!r} leaked into the retrievable corpus"
    assert store.count(index) > 0
