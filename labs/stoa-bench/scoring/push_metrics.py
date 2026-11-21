"""Push STOA Bench metrics to Prometheus Pushgateway.

Supports all 4 layers (L0-L3). Generates Prometheus text format and pushes
via HTTP PUT to the configured Pushgateway.

Usage:
    from scoring.push_metrics import MetricsPusher

    pusher = MetricsPusher()
    pusher.add_gauge("stoa_bench_cuj_status", 1, {"cuj": "CUJ-01", "layer": "L2"})
    pusher.add_gauge("stoa_bench_cuj_duration_seconds", 0.545, {"cuj": "CUJ-01"})
    pusher.push("stoa_bench_l2", instance="k8s")
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

import httpx

PUSHGATEWAY_URL = os.environ.get(
    "PUSHGATEWAY_URL", "http://pushgateway.monitoring.svc:9091"
)
PUSHGATEWAY_AUTH = os.environ.get("PUSHGATEWAY_AUTH", "")
ARENA_INSTANCE = os.environ.get("ARENA_INSTANCE", "k8s")


@dataclass
class _Metric:
    name: str
    value: float
    labels: dict[str, str]
    help_text: str = ""
    metric_type: str = "gauge"


class MetricsPusher:
    """Accumulates Prometheus metrics and pushes to Pushgateway."""

    def __init__(self) -> None:
        self._metrics: list[_Metric] = field(default_factory=list) if False else []
        self._helps: dict[str, str] = {}
        self._types: dict[str, str] = {}

    def add_gauge(
        self,
        name: str,
        value: float,
        labels: dict[str, str] | None = None,
        help_text: str = "",
    ) -> None:
        self._metrics.append(
            _Metric(name=name, value=value, labels=labels or {}, help_text=help_text)
        )
        if help_text and name not in self._helps:
            self._helps[name] = help_text
            self._types[name] = "gauge"

    def render(self) -> str:
        """Render all metrics as Prometheus text exposition format."""
        lines: list[str] = []
        seen_help: set[str] = set()

        for m in self._metrics:
            if m.name not in seen_help:
                if m.name in self._helps:
                    lines.append(f"# HELP {m.name} {self._helps[m.name]}")
                    lines.append(f"# TYPE {m.name} {self._types.get(m.name, 'gauge')}")
                seen_help.add(m.name)

            if m.labels:
                label_str = ",".join(f'{k}="{v}"' for k, v in sorted(m.labels.items()))
                lines.append(f"{m.name}{{{label_str}}} {m.value}")
            else:
                lines.append(f"{m.name} {m.value}")

        return "\n".join(lines) + "\n"

    def push(
        self,
        job: str = "stoa_bench_l2",
        instance: str | None = None,
    ) -> int:
        """Push metrics to Pushgateway. Returns HTTP status code."""
        instance = instance or ARENA_INSTANCE
        url = f"{PUSHGATEWAY_URL}/metrics/job/{job}/instance/{instance}"

        auth = None
        if PUSHGATEWAY_AUTH and ":" in PUSHGATEWAY_AUTH:
            user, password = PUSHGATEWAY_AUTH.split(":", 1)
            auth = (user, password)

        body = self.render()
        import sys
        try:
            resp = httpx.put(
                url,
                content=body,
                headers={"Content-Type": "text/plain"},
                auth=auth,
                timeout=10.0,
            )
            return resp.status_code
        except Exception as exc:
            print(f"Pushgateway push failed: {url} — {exc}", file=sys.stderr)
            return 0

    def clear(self) -> None:
        self._metrics.clear()
        self._helps.clear()
        self._types.clear()
