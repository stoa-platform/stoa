#!/usr/bin/env python3
"""Manual Phase 5B gateway runtime telemetry probe."""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import secrets
import ssl
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from typing import Any

TRACE_ID_RE = re.compile(r'"trace_id":"([0-9a-f]{32})"')


def truthy(value: str | None) -> bool:
    return (value or "").lower() in {"1", "true", "yes", "y", "on", "operator-approved"}


def get_json(
    url: str,
    headers: dict[str, str] | None = None,
    *,
    insecure: bool = False,
    timeout: float = 10.0,
) -> tuple[int, dict[str, Any]]:
    ctx = ssl._create_unverified_context() if insecure else None
    req = urllib.request.Request(url, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            body = resp.read()
            status = resp.status
    except urllib.error.HTTPError as exc:
        body = exc.read()
        status = exc.code
    try:
        return status, json.loads(body.decode("utf-8")) if body else {}
    except json.JSONDecodeError:
        return status, {"raw": body.decode("utf-8", errors="replace")[:500]}


def url(base: str, path: str, params: dict[str, Any] | None = None) -> str:
    target = base.rstrip("/") + path
    return target if not params else f"{target}?{urllib.parse.urlencode(params)}"


def auth_headers(args: argparse.Namespace) -> dict[str, str]:
    if args.api_token:
        return {"Authorization": f"Bearer {args.api_token}"}
    if args.operator_key:
        return {"X-Operator-Key": args.operator_key}
    raise ValueError("set STOA_API_TOKEN or STOA_OPERATOR_KEY")


def basic_auth(user: str, password: str) -> dict[str, str]:
    token = base64.b64encode(f"{user}:{password}".encode()).decode("ascii")
    return {"Authorization": f"Basic {token}"}


def positive_prom_result(payload: dict[str, Any]) -> bool:
    for item in payload.get("data", payload).get("result", []):
        samples = item.get("values") or [item.get("value", [])]
        for sample in samples:
            try:
                if float(sample[1]) > 0:
                    return True
            except (IndexError, TypeError, ValueError):
                continue
    return False


def hop(status: str, detail: str, evidence: Any | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {"status": status, "detail": detail}
    if evidence is not None:
        payload["evidence"] = evidence
    return payload


def gateway_request(args: argparse.Namespace, probe_id: str, traceparent: str, user_agent: str) -> dict[str, Any]:
    headers = {"traceparent": traceparent, "X-Probe-Id": probe_id, "User-Agent": user_agent}
    status, data = get_json(url(args.gateway_url, args.gateway_path), headers=headers)
    accepted = {int(code) for code in args.accept_status.split(",")}
    return hop("pass" if status in accepted else "fail", f"gateway HTTP {status}", data)


def query_range(args: argparse.Namespace, started_at: int) -> dict[str, Any]:
    end = int(time.time())
    params = {
        "query": args.prometheus_query,
        "start": str(min(started_at, end - args.metrics_window_seconds)),
        "end": str(end),
        "step": args.metrics_step,
    }
    status, data = get_json(url(args.api_url, "/v1/metrics/query_range", params), auth_headers(args))
    evidence = {
        "http_status": status,
        "result_count": len(data.get("data", {}).get("result", [])),
    }
    if status != 200:
        return hop("fail", f"query_range HTTP {status}", data)
    return hop("pass" if positive_prom_result(data) else "fail", "query_range has positive route samples", evidence)


def gateway_trace_id(args: argparse.Namespace, user_agent: str) -> tuple[str | None, dict[str, Any]]:
    if args.gateway_trace_id:
        return args.gateway_trace_id, hop("pass", "trace id supplied")
    if not args.gateway_log_lookup:
        return None, hop("skipped", "gateway log lookup disabled")

    cmd = [
        args.kubectl,
        "-n",
        args.gateway_namespace,
        "logs",
        "-l",
        args.gateway_selector,
        f"--since={args.gateway_log_since_seconds}s",
        f"--tail={args.gateway_log_tail}",
    ]
    completed = subprocess.run(cmd, check=False, capture_output=True, text=True, timeout=20)
    if completed.returncode != 0:
        return None, hop("fail", "kubectl logs failed", completed.stderr[-500:])
    for line in completed.stdout.splitlines():
        if user_agent in line and (match := TRACE_ID_RE.search(line)):
            return match.group(1), hop("pass", "trace id extracted from gateway access log")
    return None, hop("fail", "probe user-agent not found in gateway access logs")


def opensearch_span(args: argparse.Namespace, trace_id: str) -> dict[str, Any]:
    if not (args.opensearch_url and args.opensearch_user and args.opensearch_password):
        return hop("fail", "set OPENSEARCH_URL, OPENSEARCH_USER, and OPENSEARCH_PASSWORD")
    params = {
        "q": f"traceId:{trace_id}",
        "size": "5",
        "filter_path": "hits.total,hits.hits._index,hits.hits._source.name",
    }
    status, data = get_json(
        url(args.opensearch_url, "/otel-v1-apm-span-*/_search", params),
        basic_auth(args.opensearch_user, args.opensearch_password),
        insecure=args.opensearch_insecure,
    )
    total = data.get("hits", {}).get("total", {})
    count = total.get("value", 0) if isinstance(total, dict) else int(total or 0)
    return hop("pass" if status == 200 and count > 0 else "fail", f"OpenSearch spans={count}", data)


def transaction_detail(args: argparse.Namespace, trace_id: str) -> dict[str, Any]:
    status, data = get_json(url(args.api_url, f"/v1/monitoring/transactions/{trace_id}"), auth_headers(args))
    spans = data.get("spans", [])
    passed = status == 200 and data.get("source") == "opensearch" and len(spans) > 0
    evidence = {"http_status": status, "source": data.get("source"), "span_count": len(spans)}
    return hop("pass" if passed else "fail", "cp-api transaction detail", evidence)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--environment", default=os.getenv("ENVIRONMENT", "dev"))
    parser.add_argument("--phase0-verdict", default=os.getenv("PHASE0_VERDICT", "pipeline_partial"))
    parser.add_argument("--gateway-url", default=os.getenv("STOA_GATEWAY_URL", "https://mcp.gostoa.dev"))
    parser.add_argument("--gateway-path", default=os.getenv("STOA_GATEWAY_PROBE_PATH", "/apis/echo-fallback/"))
    parser.add_argument("--accept-status", default=os.getenv("STOA_GATEWAY_PROBE_ACCEPT_STATUS", "200,204,404"))
    parser.add_argument("--api-url", default=os.getenv("STOA_API_URL", "https://api.gostoa.dev"))
    parser.add_argument("--api-token", default=os.getenv("STOA_API_TOKEN", ""))
    parser.add_argument("--operator-key", default=os.getenv("STOA_OPERATOR_KEY", ""))
    parser.add_argument("--metrics-window-seconds", type=int, default=300)
    parser.add_argument("--metrics-step", default="60s")
    parser.add_argument("--prometheus-query", default=os.getenv("STOA_GATEWAY_PROMQL", 'sum by (http_route) (increase(stoa_http_requests_total{http_route="/apis/echo-fallback/"}[5m]))'))
    parser.add_argument("--gateway-trace-id", default=os.getenv("STOA_GATEWAY_TRACE_ID", ""))
    parser.add_argument("--gateway-log-lookup", action="store_true", default=truthy(os.getenv("STOA_GATEWAY_LOG_LOOKUP")))
    parser.add_argument("--kubectl", default=os.getenv("KUBECTL", "kubectl"))
    parser.add_argument("--gateway-namespace", default=os.getenv("STOA_GATEWAY_NAMESPACE", "stoa-system"))
    parser.add_argument("--gateway-selector", default=os.getenv("STOA_GATEWAY_SELECTOR", "app=stoa-gateway"))
    parser.add_argument("--gateway-log-since-seconds", type=int, default=600)
    parser.add_argument("--gateway-log-tail", type=int, default=4000)
    parser.add_argument("--opensearch-url", default=os.getenv("OPENSEARCH_URL", ""))
    parser.add_argument("--opensearch-user", default=os.getenv("OPENSEARCH_USER", ""))
    parser.add_argument("--opensearch-password", default=os.getenv("OPENSEARCH_PASSWORD", ""))
    parser.add_argument("--opensearch-insecure", action="store_true", default=truthy(os.getenv("OPENSEARCH_INSECURE", "1")))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.environment == "production" and not truthy(os.getenv("OPERATOR_OPT_IN")):
        print(json.dumps({"status": "refused", "detail": "production requires OPERATOR_OPT_IN"}, indent=2))
        return 2

    started_at = int(time.time())
    probe_id = f"probe-{datetime.now(tz=UTC).strftime('%Y%m%dT%H%M%SZ')}-{secrets.token_hex(4)}"
    injected_trace_id = secrets.token_hex(16)
    traceparent = f"00-{injected_trace_id}-{secrets.token_hex(8)}-01"
    user_agent = f"stoa-phase5b-probe/{probe_id}"

    hops = {
        "gateway_request": gateway_request(args, probe_id, traceparent, user_agent),
        "metrics_query_range": query_range(args, started_at),
    }
    trace_id, hops["gateway_trace_id"] = gateway_trace_id(args, user_agent)
    trace_id = trace_id or injected_trace_id

    if args.phase0_verdict == "pipeline_absent":
        hops["opensearch_span"] = hop("blocked_by_infra", "Phase 0 verdict pipeline_absent")
        hops["monitoring_transaction"] = hop("blocked_by_infra", "Phase 0 verdict pipeline_absent")
    else:
        hops["opensearch_span"] = opensearch_span(args, trace_id)
        hops["monitoring_transaction"] = transaction_detail(args, trace_id)

    required = [
        name
        for name, result in hops.items()
        if result["status"] != "pass" and result["status"] != "blocked_by_infra"
    ]
    output = {
        "probe": "gateway-runtime-telemetry",
        "phase": "5B",
        "status": "pass" if not required else "fail",
        "probe_id": probe_id,
        "traceparent": traceparent,
        "injected_trace_id": injected_trace_id,
        "validated_trace_id": trace_id,
        "failed_hops": required,
        "hops": hops,
    }
    print(json.dumps(output, indent=2, sort_keys=True))
    return 0 if not required else 1


if __name__ == "__main__":
    sys.exit(main())
