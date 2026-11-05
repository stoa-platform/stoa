FROM python:3.11-slim@sha256:db20d8506e2f15b6db39b40b6015ca46bae855dec6dd326d462cfe79ae972893 AS base

RUN apt-get update && apt-get upgrade -y && rm -rf /var/lib/apt/lists/*

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
