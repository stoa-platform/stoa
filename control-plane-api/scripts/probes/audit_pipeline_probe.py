#!/usr/bin/env python3
"""Phase 5A probe: control-plane audit action -> Kafka -> PG -> audit API."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import uuid
from typing import Any

import httpx
import psycopg2
from kafka import KafkaConsumer, TopicPartition
from psycopg2.extras import Json, RealDictCursor

TENANT_ID = "audit-probe"
TOPIC = "stoa.audit.trail"
API_PREFIX = "audit-pipeline-probe"
TRUTHY = {"1", "true", "yes", "y", "on", "operator-approved"}


def args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the Phase 5A audit pipeline probe.")
    parser.add_argument("--api-url", default=os.getenv("STOA_CONTROL_PLANE_API_URL", "http://localhost:8000"))
    parser.add_argument("--api-token", default=os.getenv("STOA_API_TOKEN") or os.getenv("CONTROL_PLANE_API_TOKEN"))
    parser.add_argument(
        "--database-url", default=os.getenv("DATABASE_URL", "postgresql://stoa:stoa@localhost:5432/stoa")
    )
    parser.add_argument(
        "--kafka-bootstrap-servers",
        default=os.getenv("KAFKA_BOOTSTRAP_SERVERS", "redpanda.stoa-system.svc.cluster.local:9092"),
    )
    parser.add_argument("--environment", default=os.getenv("ENVIRONMENT", "dev"))
    parser.add_argument("--timeout-seconds", type=int, default=60)
    return parser.parse_args(argv)


def gate(env: str) -> None:
    if env.strip().lower() in {"prod", "production"} and os.getenv("OPERATOR_OPT_IN", "").lower() not in TRUTHY:
        raise RuntimeError("Refusing production run without OPERATOR_OPT_IN=true.")


def pg_url(url: str) -> str:
    return (
        "postgresql://" + url.removeprefix("postgresql+asyncpg://") if url.startswith("postgresql+asyncpg://") else url
    )


def new_probe() -> dict[str, str]:
    suffix = uuid.uuid4().hex[:12]
    api_id = f"{API_PREFIX}-{suffix}"
    return {"probe_id": f"probe-{suffix}", "api_id": api_id, "api_version": f"probe-{suffix}"}


def db_cleanup(conn: Any, probe: dict[str, str], *, tenant_created: bool = False) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            DELETE FROM audit_events
            WHERE tenant_id=%s
              AND (id=%s OR (resource_type='api' AND resource_id=%s)
                   OR details->>'name'=%s OR details->>'version'=%s)
            """,
            (TENANT_ID, probe.get("event_id"), probe["api_id"], probe["api_id"], probe["api_version"]),
        )
        cur.execute("DELETE FROM api_catalog WHERE tenant_id=%s AND api_id=%s", (TENANT_ID, probe["api_id"]))
        if tenant_created:
            cur.execute("DELETE FROM tenants WHERE id=%s", (TENANT_ID,))
    conn.commit()


def db_prepare(conn: Any) -> bool:
    with conn.cursor() as cur:
        cur.execute("SELECT id FROM tenants WHERE id=%s", (TENANT_ID,))
        if cur.fetchone():
            return False
        cur.execute(
            """
            INSERT INTO tenants (id, name, description, status, settings, provisioning_status)
            VALUES (%s, %s, %s, 'active', %s, 'ready')
            """,
            (
                TENANT_ID,
                "Audit Probe",
                "Dedicated tenant for Phase 5A audit pipeline probes.",
                Json({"max_apis": 100, "max_applications": 100, "source": "audit_pipeline_probe"}),
            ),
        )
    conn.commit()
    return True


def kafka_consumer(bootstrap: str, timeout: int) -> KafkaConsumer:
    consumer = KafkaConsumer(
        bootstrap_servers=[s.strip() for s in bootstrap.split(",") if s.strip()],
        enable_auto_commit=False,
        value_deserializer=lambda raw: json.loads(raw.decode("utf-8")),
    )
    deadline = time.monotonic() + timeout
    partitions: set[int] | None = None
    while time.monotonic() < deadline and not partitions:
        partitions = consumer.partitions_for_topic(TOPIC)
        time.sleep(0.5)
    if not partitions:
        raise RuntimeError(f"Kafka topic {TOPIC} is not available.")
    tps = [TopicPartition(TOPIC, p) for p in sorted(partitions)]
    consumer.assign(tps)
    consumer.seek_to_end(*tps)
    return consumer


def emit_action(cfg: argparse.Namespace, probe: dict[str, str]) -> None:
    if not cfg.api_token:
        raise RuntimeError("Missing STOA_API_TOKEN or CONTROL_PLANE_API_TOKEN.")
    headers = {
        "Authorization": f"Bearer {cfg.api_token}",
        "X-Probe-Id": probe["probe_id"],
        "User-Agent": "stoa-audit-pipeline-probe/phase-5a",
    }
    payload = {
        "name": probe["api_id"],
        "display_name": f"Audit Pipeline Probe {probe['probe_id']}",
        "version": probe["api_version"],
        "backend_url": "https://audit-probe.invalid",
    }
    with httpx.Client(timeout=cfg.timeout_seconds) as client:
        resp = client.post(f"{cfg.api_url.rstrip('/')}/v1/tenants/{TENANT_ID}/apis", headers=headers, json=payload)
    if resp.status_code < 200 or resp.status_code >= 300:
        raise RuntimeError(f"API create returned HTTP {resp.status_code}: {resp.text[:300]}")
    data = resp.json()
    if data.get("id") != probe["api_id"] or data.get("tenant_id") != TENANT_ID:
        raise RuntimeError(f"Unexpected API create response: {data}")


def match_event(event: Any, probe: dict[str, str]) -> bool:
    payload = event.get("payload") if isinstance(event, dict) else None
    details = payload.get("details") if isinstance(payload, dict) else None
    return (
        isinstance(details, dict)
        and event.get("type") == "audit"
        and event.get("tenant_id") == TENANT_ID
        and payload.get("action") == "create"
        and payload.get("resource_type") == "api"
        and payload.get("resource_id") == probe["api_id"]
        and details.get("name") == probe["api_id"]
        and details.get("version") == probe["api_version"]
    )


def wait_kafka(consumer: KafkaConsumer, probe: dict[str, str], timeout: int) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        for records in consumer.poll(timeout_ms=1000).values():
            for msg in records:
                if match_event(msg.value, probe):
                    probe.update(
                        {"event_id": msg.value["id"], "kafka_partition": msg.partition, "kafka_offset": msg.offset}
                    )
                    return
    raise RuntimeError(f"No matching audit envelope observed on {TOPIC}.")


def wait_pg(conn: Any, probe: dict[str, str], timeout: int) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id FROM audit_events
                WHERE tenant_id=%s AND (id=%s OR (resource_type='api' AND resource_id=%s AND details->>'version'=%s))
                LIMIT 1
                """,
                (TENANT_ID, probe.get("event_id"), probe["api_id"], probe["api_version"]),
            )
            if row := cur.fetchone():
                probe["event_id"] = row["id"]
                return
        time.sleep(1)
    raise RuntimeError("No matching audit_events row observed before timeout.")


def wait_api(cfg: argparse.Namespace, probe: dict[str, str]) -> None:
    headers = {"Authorization": f"Bearer {cfg.api_token}", "X-Probe-Id": probe["probe_id"]}
    with httpx.Client(timeout=cfg.timeout_seconds) as client:
        resp = client.get(
            f"{cfg.api_url.rstrip('/')}/v1/audit/{TENANT_ID}",
            headers=headers,
            params={"search": probe["api_id"], "page_size": 10},
        )
    if resp.status_code < 200 or resp.status_code >= 300:
        raise RuntimeError(f"Audit API returned HTTP {resp.status_code}: {resp.text[:300]}")
    if not any(
        e.get("id") == probe.get("event_id") and e.get("resource_id") == probe["api_id"]
        for e in resp.json().get("entries", [])
    ):
        raise RuntimeError("Audit API did not return the persisted probe event.")


def run(cfg: argparse.Namespace) -> int:
    gate(cfg.environment)
    probe = new_probe()
    hops = {
        name: {"status": "fail", "detail": "not run"}
        for name in ("audit_emit", "kafka_consumed", "pg_persisted", "api_visible")
    }
    conn = psycopg2.connect(pg_url(cfg.database_url), cursor_factory=RealDictCursor)
    consumer: KafkaConsumer | None = None
    tenant_created = False
    try:
        db_cleanup(conn, probe)
        tenant_created = db_prepare(conn)
        consumer = kafka_consumer(cfg.kafka_bootstrap_servers, cfg.timeout_seconds)
        for name, fn in (
            ("audit_emit", lambda: emit_action(cfg, probe)),
            ("kafka_consumed", lambda: wait_kafka(consumer, probe, cfg.timeout_seconds)),
            ("pg_persisted", lambda: wait_pg(conn, probe, cfg.timeout_seconds)),
            ("api_visible", lambda: wait_api(cfg, probe)),
        ):
            try:
                fn()
                hops[name] = {"status": "pass", "detail": "ok"}
            except Exception as exc:
                hops[name] = {"status": "fail", "detail": str(exc)}
                break
    finally:
        cleanup = "pass"
        try:
            db_cleanup(conn, probe, tenant_created=tenant_created)
        except Exception as exc:
            cleanup = f"fail: {exc}"
        conn.close()
        if consumer:
            consumer.close()
    summary = {
        "probe": "control-plane-audit-pipeline",
        "phase": "5A",
        "tenant_id": TENANT_ID,
        "topic": TOPIC,
        **probe,
        "hops": hops,
        "cleanup": cleanup,
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if all(h["status"] == "pass" for h in hops.values()) and cleanup == "pass" else 1


def main(argv: list[str] | None = None) -> int:
    try:
        return run(args(argv or sys.argv[1:]))
    except Exception as exc:
        print(json.dumps({"probe": "control-plane-audit-pipeline", "phase": "5A", "error": str(exc)}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
