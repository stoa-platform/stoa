FROM python:3.11-slim AS base

RUN groupadd -g 1000 stoa && useradd -u 1000 -g stoa -s /bin/sh stoa

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ src/

RUN chown -R stoa:stoa /app

USER stoa

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD ["python", "-c", "print('ok')"]

CMD ["python", "-m", "src.main"]
