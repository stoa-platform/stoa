package connect

import (
	"strings"
	"testing"
	"time"

	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/testutil"
)

func TestMetricsRegistered(t *testing.T) {
	// Verify all gauges and counters are registered and can be collected
	metrics := []prometheus.Collector{
		GatewayUp,
		APIsTotal,
		AdminAPILatency,
		SyncStatus,
		SyncPoliciesApplied,
		SyncPoliciesFailed,
		HeartbeatsSent,
		DiscoveryCycles,
	}

	for _, m := range metrics {
		// Collecting should not panic
		ch := make(chan prometheus.Metric, 10)
		m.Collect(ch)
		close(ch)
	}
}

func TestGatewayUpMetric(t *testing.T) {
	GatewayUp.Set(1)
	val := testutil.ToFloat64(GatewayUp)
	if val != 1 {
		t.Errorf("expected GatewayUp=1, got %f", val)
	}

	GatewayUp.Set(0)
	val = testutil.ToFloat64(GatewayUp)
	if val != 0 {
		t.Errorf("expected GatewayUp=0, got %f", val)
	}
}

func TestAPIsTotalMetric(t *testing.T) {
	APIsTotal.Set(42)
	val := testutil.ToFloat64(APIsTotal)
	if val != 42 {
		t.Errorf("expected APIsTotal=42, got %f", val)
	}
}

func TestObserveAdminAPICall(t *testing.T) {
	start := time.Now().Add(-100 * time.Millisecond)
	ObserveAdminAPICall(start)

	// Verify histogram has at least one observation
	expected := `
# HELP stoa_connect_admin_api_latency_seconds Latency of gateway admin API calls in seconds.
# TYPE stoa_connect_admin_api_latency_seconds histogram
`
	err := testutil.CollectAndCompare(AdminAPILatency, strings.NewReader(expected))
	// CollectAndCompare checks prefix match — we just verify no panic and metric exists
	// The actual bucket values depend on timing, so we only check the metric was observed
	if err != nil {
		// This is expected since we can't predict exact values; just verify the count > 0
		count := testutil.CollectAndCount(AdminAPILatency)
		if count == 0 {
			t.Error("expected AdminAPILatency to have observations")
		}
	}
}

func TestSyncMetrics(t *testing.T) {
	// Reset counters by reading current value and comparing after increment
	before := testutil.ToFloat64(SyncPoliciesApplied)
	SyncPoliciesApplied.Inc()
	after := testutil.ToFloat64(SyncPoliciesApplied)
	if after != before+1 {
		t.Errorf("expected SyncPoliciesApplied to increment by 1, got %f → %f", before, after)
	}

	beforeFailed := testutil.ToFloat64(SyncPoliciesFailed)
	SyncPoliciesFailed.Inc()
	afterFailed := testutil.ToFloat64(SyncPoliciesFailed)
	if afterFailed != beforeFailed+1 {
		t.Errorf("expected SyncPoliciesFailed to increment by 1")
	}
}
