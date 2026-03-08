FROM python:3.11-slim-bookworm AS base

# Non-root user
RUN groupadd -g 12345 bench && useradd -u 12345 -g bench -s /bin/sh bench

WORKDIR /bench

# Install dependencies (including pytest — needed at runtime for CUJ execution)
COPY pyproject.toml .
RUN pip install --no-cache-dir . && \
    pip install --no-cache-dir "pytest>=8" "pytest-asyncio>=0.24"

# Copy source
COPY scoring/ scoring/
COPY tests/ tests/
COPY config/ config/
COPY runner.py .

# Ensure bench user owns the workdir
RUN chown -R bench:bench /bench

# History dir for L3 JSONL (mounted as emptyDir in K8s)
RUN mkdir -p /tmp/stoa-bench-history /tmp/stoa-bench-results && \
    chown -R bench:bench /tmp/stoa-bench-history /tmp/stoa-bench-results

USER bench

ENTRYPOINT ["python", "/bench/runner.py"]
CMD ["--cron"]
