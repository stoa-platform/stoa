FROM python:3.11-slim

LABEL org.opencontainers.image.source="https://github.com/stoa-platform/stoa"
LABEL org.opencontainers.image.description="STOA Traffic Generator"

RUN pip install --no-cache-dir requests==2.31.0

COPY scripts/traffic/continuous-heartbeat.py /app/heartbeat.py

WORKDIR /app

USER nobody

ENTRYPOINT ["python", "heartbeat.py"]
