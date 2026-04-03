package connect

import (
	"time"

	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/promauto"
)

// Prometheus metrics for stoa-connect.
// Exposed at /metrics via promhttp.Handler() in cmd/stoa-connect/main.go.
var (
	// GatewayUp indicates whether the local gateway is reachable (1=up, 0=down).
	GatewayUp = promauto.NewGauge(prometheus.GaugeOpts{
		Namespace: "stoa_connect",
		Name:      "gateway_up",
		Help:      "Whether the local gateway admin API is reachable (1=up, 0=down).",
	})

	// APIsTotal is the number of APIs discovered on the local gateway.
	APIsTotal = promauto.NewGauge(prometheus.GaugeOpts{
		Namespace: "stoa_connect",
		Name:      "apis_total",
		Help:      "Number of APIs discovered on the local gateway.",
	})

	// AdminAPILatency tracks the latency of calls to the gateway admin API.
	AdminAPILatency = promauto.NewHistogram(prometheus.HistogramOpts{
		Namespace: "stoa_connect",
		Name:      "admin_api_latency_seconds",
		Help:      "Latency of gateway admin API calls in seconds.",
		Buckets:   []float64{0.01, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5},
	})

	// SyncStatus reports the last policy sync result (1=success, 0=failure).
	SyncStatus = promauto.NewGauge(prometheus.GaugeOpts{
		Namespace: "stoa_connect",
		Name:      "sync_status",
		Help:      "Last policy sync result (1=success, 0=failure).",
	})

	// SyncPoliciesApplied counts total policies successfully applied.
	SyncPoliciesApplied = promauto.NewCounter(prometheus.CounterOpts{
		Namespace: "stoa_connect",
		Name:      "sync_policies_applied_total",
		Help:      "Total number of policies successfully applied to the gateway.",
	})

	// SyncPoliciesFailed counts total policy apply/remove failures.
	SyncPoliciesFailed = promauto.NewCounter(prometheus.CounterOpts{
		Namespace: "stoa_connect",
		Name:      "sync_policies_failed_total",
		Help:      "Total number of policy sync failures.",
	})

	// HeartbeatsSent counts total heartbeats sent to CP.
	HeartbeatsSent = promauto.NewCounter(prometheus.CounterOpts{
		Namespace: "stoa_connect",
		Name:      "heartbeats_sent_total",
		Help:      "Total number of heartbeats sent to the Control Plane.",
	})

	// DiscoveryCycles counts total discovery cycles executed.
	DiscoveryCycles = promauto.NewCounter(prometheus.CounterOpts{
		Namespace: "stoa_connect",
		Name:      "discovery_cycles_total",
		Help:      "Total number of gateway discovery cycles executed.",
	})

	// UptimeSeconds tracks agent uptime.
	UptimeSeconds = promauto.NewGaugeFunc(prometheus.GaugeOpts{
		Namespace: "stoa_connect",
		Name:      "uptime_seconds",
		Help:      "Agent uptime in seconds.",
	}, func() float64 {
		return time.Since(metricsStartTime).Seconds()
	})
)

var metricsStartTime = time.Now()

// ObserveAdminAPICall records the latency of a gateway admin API call.
func ObserveAdminAPICall(start time.Time) {
	AdminAPILatency.Observe(time.Since(start).Seconds())
}
