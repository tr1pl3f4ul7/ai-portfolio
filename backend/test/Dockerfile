# Linux test environment for the backend.
#
# sqlite-vec publishes no Windows ARM64 wheel, so retrieval code cannot run
# natively on the dev machine. Rather than split the stack between dev and
# production, the whole backend test suite runs here — on linux/arm64, matching
# the Oracle Ampere A1 VM.
#
# Dependencies are baked into the image so the test loop is fast and does not
# re-download torch on every run.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    # Keep the embedding model inside the image rather than re-downloading it.
    HF_HOME=/opt/hf-cache

WORKDIR /app

COPY requirements.txt requirements-dev.txt ./
RUN pip install --no-cache-dir -r requirements.txt -r requirements-dev.txt

# Pre-download the embedding model at build time. Without this, every test run
# re-pulls it and the suite looks hung rather than slow.
#
# Keep in sync with EMBEDDING_MODEL in app/config.py. Hardcoded rather than read
# from config so this layer is only invalidated when the model actually changes,
# not on every edit to config.py.
RUN python -c "from sentence_transformers import SentenceTransformer; \
    SentenceTransformer('thenlper/gte-small')"

CMD ["python", "-m", "pytest", "-v"]
