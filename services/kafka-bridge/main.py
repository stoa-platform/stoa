"""Kafka Bridge - HTTP to Kafka relay for webMethods Gateway.

CAB-485: Receives error snapshots via HTTP POST and publishes to Kafka.
This replaces the need for a custom Java policy in webMethods.

Usage:
    webMethods Custom Extension → HTTP POST /snapshots → Kafka Bridge → Kafka
"""

import json
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import JSONResponse
from kafka import KafkaProducer
from kafka.errors import KafkaError
from pydantic import BaseModel, Field

# Configuration
KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "redpanda.stoa-system:9093")
KAFKA_TOPIC = os.getenv("KAFKA_TOPIC", "stoa.errors.snapshots")
KAFKA_SASL_USERNAME = os.getenv("KAFKA_SASL_USERNAME", "")
KAFKA_SASL_PASSWORD = os.getenv("KAFKA_SASL_PASSWORD", "")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# Logging
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format="%(asctime)s %(levelname)s %(name)s - %(message)s"
)
logger = logging.getLogger("kafka-bridge")

# Global producer
producer: KafkaProducer | None = None


# --- PII Masking ---

SENSITIVE_HEADERS = {
    "authorization", "x-api-key", "cookie", "x-auth-token",
    "x-access-token", "proxy-authorization", "x-csrf-token"
}

SENSITIVE_BODY_KEYS = {
    "password", "passwd", "secret", "token", "api_key", "apikey",
    "access_token", "refresh_token", "credit_card", "creditcard",
    "card_number", "cvv", "ssn", "social_security"
}

REDACTED = "[REDACTED]"


def mask_headers(headers: dict[str, str]) -> tuple[dict[str, str], list[str]]:
    """Mask sensitive headers."""
    masked = {}
    fields = []
    for key, value in headers.items():
        if key.lower() in SENSITIVE_HEADERS:
            masked[key] = REDACTED
            fields.append(f"headers.{key}")
        else:
            masked[key] = value
    return masked, fields


def mask_body(body: Any, path: str = "body") -> tuple[Any, list[str]]:
    """Recursively mask sensitive fields in body."""
    fields = []

    if isinstance(body, dict):
        masked = {}
        for key, value in body.items():
            key_lower = key.lower()
            if key_lower in SENSITIVE_BODY_KEYS:
                masked[key] = REDACTED
                fields.append(f"{path}.{key}")
            else:
                masked[key], nested_fields = mask_body(value, f"{path}.{key}")
                fields.extend(nested_fields)
        return masked, fields

    elif isinstance(body, list):
        masked = []
        for i, item in enumerate(body):
            masked_item, nested_fields = mask_body(item, f"{path}[{i}]")
            masked.append(masked_item)
            fields.extend(nested_fields)
        return masked, fields

    return body, fields


def generate_snapshot_id() -> str:
    """Generate a unique snapshot ID with timestamp prefix."""
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    suffix = uuid4().hex[:8]
    return f"SNP-{ts}-{suffix}"


# --- Models ---

class RequestSnapshot(BaseModel):
    method: str
    path: str
    headers: dict[str, str] = Field(default_factory=dict)
    body: Any | None = None
    query_params: dict[str, str] = Field(default_factory=dict)
    client_ip: str | None = None
    user_agent: str | None = None


class ResponseSnapshot(BaseModel):
    status: int
    headers: dict[str, str] = Field(default_factory=dict)
    body: Any | None = None
    duration_ms: int


class RoutingInfo(BaseModel):
    api_name: str | None = None
    api_version: str | None = None
    route: str | None = None
    backend_url: str | None = None


class ErrorSnapshotInput(BaseModel):
    """Input from webMethods Gateway."""
    tenant_id: str
    trigger: str = "5xx"  # 4xx, 5xx, timeout
    request: RequestSnapshot
    response: ResponseSnapshot
    routing: RoutingInfo | None = None
    trace_id: str | None = None

    # Optional enrichment from gateway
    api_name: str | None = None
    api_version: str | None = None


class HealthResponse(BaseModel):
    status: str
    kafka_connected: bool


# --- Kafka ---

def create_producer() -> KafkaProducer | None:
    """Create Kafka producer with optional SASL auth."""
    try:
        config = {
            "bootstrap_servers": KAFKA_BOOTSTRAP_SERVERS.split(","),
            "value_serializer": lambda v: json.dumps(v).encode("utf-8"),
            "acks": "all",
            "retries": 3,
        }

        if KAFKA_SASL_USERNAME:
            config.update({
                "security_protocol": "SASL_PLAINTEXT",
                "sasl_mechanism": "SCRAM-SHA-256",
                "sasl_plain_username": KAFKA_SASL_USERNAME,
                "sasl_plain_password": KAFKA_SASL_PASSWORD,
            })

        return KafkaProducer(**config)
    except KafkaError as e:
        logger.error(f"Failed to create Kafka producer: {e}")
        return None


# --- FastAPI App ---

@asynccontextmanager
async def lifespan(app: FastAPI):
    global producer
    producer = create_producer()
    if producer:
        logger.info(f"Kafka producer connected to {KAFKA_BOOTSTRAP_SERVERS}")
    else:
        logger.warning("Kafka producer not connected - messages will be dropped")
    yield
    if producer:
        producer.close()
        logger.info("Kafka producer closed")


app = FastAPI(
    title="Kafka Bridge",
    description="HTTP to Kafka relay for webMethods Gateway error snapshots",
    version="1.0.0",
    lifespan=lifespan,
)


@app.get("/health", response_model=HealthResponse)
async def health():
    """Health check endpoint."""
    return HealthResponse(
        status="healthy" if producer else "degraded",
        kafka_connected=producer is not None
    )


@app.post("/snapshots", status_code=status.HTTP_202_ACCEPTED)
async def publish_snapshot(snapshot: ErrorSnapshotInput):
    """Receive error snapshot from webMethods and publish to Kafka.

    This endpoint:
    1. Masks PII in headers and body
    2. Enriches with metadata (id, timestamp, source)
    3. Publishes to Kafka topic
    """
    if not producer:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Kafka producer not available"
        )

    # Mask PII
    masked_headers, header_fields = mask_headers(snapshot.request.headers)
    masked_req_body, req_body_fields = mask_body(snapshot.request.body)
    masked_res_body, res_body_fields = mask_body(snapshot.response.body)

    masked_fields = header_fields + req_body_fields + res_body_fields

    # Build full snapshot
    full_snapshot = {
        "id": generate_snapshot_id(),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "tenant_id": snapshot.tenant_id,
        "trigger": snapshot.trigger,
        "source": "webmethods-gateway",

        "request": {
            "method": snapshot.request.method,
            "path": snapshot.request.path,
            "headers": masked_headers,
            "body": masked_req_body,
            "query_params": snapshot.request.query_params,
            "client_ip": snapshot.request.client_ip,
            "user_agent": snapshot.request.user_agent,
        },

        "response": {
            "status": snapshot.response.status,
            "headers": snapshot.response.headers,
            "body": masked_res_body,
            "duration_ms": snapshot.response.duration_ms,
        },

        "routing": {
            "api_name": snapshot.routing.api_name if snapshot.routing else snapshot.api_name,
            "api_version": snapshot.routing.api_version if snapshot.routing else snapshot.api_version,
            "route": snapshot.routing.route if snapshot.routing else None,
            "backend_url": snapshot.routing.backend_url if snapshot.routing else None,
        },

        "policies_applied": [],
        "backend_state": {"health": "unknown"},
        "logs": [],
        "trace_id": snapshot.trace_id,
        "span_id": None,
        "environment": {},
        "masked_fields": masked_fields,
    }

    # Publish to Kafka
    try:
        future = producer.send(KAFKA_TOPIC, value=full_snapshot)
        # Don't block - fire and forget for performance
        logger.info(
            f"Published snapshot id={full_snapshot['id']} "
            f"tenant={snapshot.tenant_id} status={snapshot.response.status}"
        )
        return {"id": full_snapshot["id"], "status": "accepted"}

    except KafkaError as e:
        logger.error(f"Failed to publish snapshot: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Kafka publish failed: {str(e)}"
        )


@app.post("/snapshots/batch", status_code=status.HTTP_202_ACCEPTED)
async def publish_batch(snapshots: list[ErrorSnapshotInput]):
    """Publish multiple snapshots in batch."""
    if not producer:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Kafka producer not available"
        )

    results = []
    for snapshot in snapshots:
        try:
            result = await publish_snapshot(snapshot)
            results.append(result)
        except HTTPException:
            results.append({"status": "failed"})

    return {"count": len(results), "results": results}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
