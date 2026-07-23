"""Application configuration.

The only place in the backend that reads os.environ. Everything else imports
from here, so there is exactly one list of what this service can be configured
with and exactly one place to change a default.
"""

import os
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parent.parent

# Source content for retrieval. Markdown files are the source of truth; the
# vector store is a build artefact regenerated from them.
DATA_DIR = Path(os.environ.get("AI_PORTFOLIO_DATA_DIR", BACKEND_ROOT / "data"))

# Vector store location. Gitignored — rebuilt by `python -m app.ingest`.
DB_PATH = Path(os.environ.get("AI_PORTFOLIO_DB_PATH", BACKEND_ROOT / "data" / "vectors.db"))

# Chosen by measurement, not reputation — see backend/test/compare_models.py and
# decision 28. Against the real corpus and the real evaluation queries:
#
#   model                    dims  max_seq  truncated  top-4  top-6
#   all-MiniLM-L6-v2          384      256       3/56    4/8    6/8   <- plan's choice
#   all-MiniLM-L12-v2         384      128      23/56    5/8    6/8
#   bge-small-en-v1.5         384      512          0    5/8    6/8
#   gte-small                 384      512          0    6/8    7/8   <- selected
#   all-mpnet-base-v2         768      384          0    4/8    5/8
#
# gte-small keeps 384 dimensions, so the sqlite-vec schema is unchanged, and its
# 512-token window means nothing in the corpus is truncated. Note all-mpnet-base
# is nine times slower and scored worst; bigger was not better here.
EMBEDDING_MODEL = os.environ.get("AI_PORTFOLIO_EMBEDDING_MODEL", "thenlper/gte-small")
EMBEDDING_DIMENSIONS = 384

# Who the corpus is about. Prepended to every chunk before embedding, so a
# section retrieved in isolation still says whose experience it describes.
CORPUS_SUBJECT = os.environ.get("AI_PORTFOLIO_CORPUS_SUBJECT", "Ljuben Vassilev")

# Chunks retrieved per query.
#
# 6 rather than 4. Measured on the real corpus: several correct chunks landed at
# rank 5, losing to FAQ entries by margins as small as 0.0075 — the FAQ is
# written as questions, so it competes strongly with anything question-shaped.
# At a median 112 tokens per chunk this is roughly 670 tokens of context, which
# is cheap next to the answer Claude generates from it.
TOP_K = int(os.environ.get("AI_PORTFOLIO_TOP_K", "6"))
