FROM python:3.11-slim@sha256:db20d8506e2f15b6db39b40b6015ca46bae855dec6dd326d462cfe79ae972893

LABEL org.opencontainers.image.source="https://github.com/stoa-platform/stoa"
LABEL org.opencontainers.image.description="STOA Traffic Generator"

RUN pip install --no-cache-dir requests==2.31.0

COPY scripts/traffic/continuous-heartbeat.py /app/heartbeat.py

WORKDIR /app

USER nobody

ENTRYPOINT ["python", "heartbeat.py"]
