"""
Tenant Lifecycle Prometheus Metrics
CAB-409: Observability for demo tenant lifecycle

Labels: notification_type + lifecycle_state only (no tenant_id — cardinality explosion).
"""
from prometheus_client import Counter, Gauge, Histogram


class LifecycleMetrics:
    """All Prometheus metrics for tenant lifecycle management."""

    def __init__(self, prefix: str = "stoa_demo"):
        # ─── Gauges: Current state ────────────────────────────────────
        self.state_gauge = Gauge(
            f"{prefix}_tenants_by_state",
            "Number of demo tenants in each lifecycle state",
            ["state"],
        )

        # ─── Counters: Events ─────────────────────────────────────────
        self.trial_extensions_total = Counter(
            f"{prefix}_trial_extensions_total",
            "Total number of trial extensions granted",
        )

        self.conversions_total = Counter(
            f"{prefix}_conversions_total",
            "Total number of demo-to-paid conversions",
            ["tier"],
        )

        self.notifications_sent_total = Counter(
            f"{prefix}_notifications_sent_total",
            "Total lifecycle notifications sent",
            ["type", "channel"],
        )

        self.cleanup_errors_total = Counter(
            f"{prefix}_cleanup_errors_total",
            "Total errors during tenant cleanup",
        )

        self.cron_runs_total = Counter(
            f"{prefix}_lifecycle_cron_runs_total",
            "Total lifecycle cron job executions",
        )

        # ─── Histograms: Timing ───────────────────────────────────────
        self.tenant_lifetime_days = Histogram(
            f"{prefix}_tenant_lifetime_days",
            "How many days tenants survive before deletion or conversion",
            buckets=[1, 3, 7, 10, 14, 21, 30, 60, 90],
        )

        self.time_to_conversion_days = Histogram(
            f"{prefix}_time_to_conversion_days",
            "Days from signup to Enterprise conversion",
            buckets=[1, 3, 7, 10, 14, 21, 30],
        )

        # ─── Gauge: Cron health ───────────────────────────────────────
        self.last_cron_run = Gauge(
            f"{prefix}_lifecycle_last_cron_run_timestamp",
            "Timestamp of last successful lifecycle cron run",
        )


# Singleton instance
lifecycle_metrics = LifecycleMetrics()
